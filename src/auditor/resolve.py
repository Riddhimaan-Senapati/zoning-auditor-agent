from __future__ import annotations

import re
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import assert_never

from auditor.corpus import Corpus
from auditor.models import (
    ArticleRef,
    CellQuote,
    DistrictRef,
    RangeRef,
    Reference,
    Resolution,
    ResolutionStatus,
    Section,
    SectionRef,
    SelfSectionRef,
    SelfTableRef,
    Table,
    TableRef,
    TextQuote,
    XRef,
)
from auditor.quotes import normalize
from auditor.xrefs import DISTRICT, district_references, extract_references, family

with (Path(__file__).resolve().parents[2] / "config" / "resolve.toml").open("rb") as _fh:
    THRESHOLD = float(tomllib.load(_fh)["title_similarity"])

_TABLE_ID = re.compile(r"^\d+[A-Z]*:Table([0-9A-Z]+)(?::fn(\w+))?$")
_HEADER_MARK = re.compile(r"\((\d+)\)")
_DEFINES = re.compile(rf'\(["“]({DISTRICT})["”]\)\s*Subdistricts?\.\s*({DISTRICT})\b')

Headings = Callable[[str], dict[str, str]]


def _article(id: str) -> str:
    return re.split(r"[-:]", id, maxsplit=1)[0]


def _where(id: str) -> str:
    """How a claim names a location: 'Section 53-29.4', 'Table K', 'Table K footnote 1'."""
    if m := _TABLE_ID.match(id):
        return f"Table {m[1]}" + (f" footnote {m[2]}" if m[2] else "")
    return f"Article {id}" if id == _article(id) else f"Section {id}"


def _score(a: str, b: str) -> float:
    wa, wb = (set(re.findall(r"[a-z0-9]+", normalize(s).lower())) for s in (a, b))
    return len(wa & wb) / len(wa | wb) if wa | wb else 1.0


def _best(heads: dict[str, str], title: str, exclude: set[str]) -> str | None:
    scored = [(_score(title, h), id) for id, h in heads.items() if id not in exclude]
    score, id = max(scored, default=(0.0, None), key=lambda p: p[0])
    return id if score >= THRESHOLD else None


def _also(heads: dict[str, str], match: str | None) -> str:
    return f' Section {match} is titled "{heads[match]}".' if match else ""


def _key(id: str) -> list[tuple[int, str]]:
    return [(int(n), s) for n, s in re.findall(r"(\d+)([a-z]*)", id.split("-", 1)[1])]


def _r(status: ResolutionStatus, detail: str, resolved_id: str | None = None,
       title_match_id: str | None = None) -> Resolution:
    return Resolution(status=status, detail=detail, resolved_id=resolved_id,
                      title_match_id=title_match_id)


def _lineage(corpus: Corpus, id: str | None) -> Iterator[str]:
    while id is not None:
        yield id
        sec = corpus.section(id)
        id = sec.parent if sec else None


def _self(q: TextQuote, wanted: str, corpus: Corpus) -> Resolution:
    here = _where(q.section_id)
    if wanted in _lineage(corpus, q.section_id):
        return _r("ok", f'{here} says "{q.text}" inside it.', wanted)
    container = _where(re.sub(r":fn\w+$", "", q.section_id))
    return _r("self_mismatch", f'{here} says "{q.text}", but it sits in {container}.')


def _section(q: TextQuote, ref: SectionRef, headings: Headings) -> Resolution:
    here, target, title = _where(q.section_id), ref.target, ref.cited_title
    article, source = _article(target), _article(q.section_id)
    heads = headings(article)
    if target not in heads and heads:
        return _r("missing", f"{here} cites Section {target}, and Article {article} has no Section {target}.")
    if title and article != source and (shadow := _best(headings(source), title, set())):
        return _r("cross_article_shadow",
                  f'{here} cites Section {target} as "{title}"; Section {target} is in Article {article}, '
                  f"and Section {shadow} of Article {source} has that heading.", shadow, shadow)
    if target not in heads:
        return _r("external_unchecked",
                  f"{here} cites Section {target}; Article {article} is neither loaded nor in the table of contents.")
    if title and _score(title, heads[target]) < THRESHOLD:
        match = _best(heads, title, {target})
        return _r("title_mismatch",
                  f'{here} cites Section {target} as "{title}", but Section {target} is titled '
                  f'"{heads[target]}".' + _also(heads, match), target, match)
    return _r("ok", f'{here} cites Section {target} ("{heads[target]}").', target)


def _range(q: TextQuote, ref: RangeRef, headings: Headings) -> Resolution:
    here, lo, hi, title = _where(q.section_id), ref.lo, ref.hi, ref.cited_title
    article = _article(lo)
    heads = headings(article)
    if not heads:
        return _r("external_unchecked",
                  f"{here} cites Sections {lo} through {hi}; Article {article} is neither loaded nor in "
                  "the table of contents.")
    if absent := next((s for s in (lo, hi) if s not in heads), None):
        return _r("missing", f"{here} cites Sections {lo} through {hi}, and Article {article} has no Section {absent}.")
    inside = {s for s in heads if "-" in s and s.count(".") == lo.count(".") and _key(lo) <= _key(s) <= _key(hi)}
    off = next((s for s in sorted(inside, key=_key) if _score(title, heads[s]) < THRESHOLD), None) if title else None
    if off:
        match = _best(heads, title, inside)
        return _r("title_mismatch",
                  f'{here} cites Sections {lo} through {hi} as "{title}", but Section {off} in that range '
                  f'is titled "{heads[off]}".' + _also(heads, match), lo, match)
    return _r("ok", f"{here} cites Sections {lo} through {hi}.", lo)


def _table(q: TextQuote, ref: TableRef, corpus: Corpus, table_sections: dict[str, str]) -> Resolution:
    here, article = _where(q.section_id), _article(q.section_id)
    table_id = f"{article}:Table{ref.table}"
    if corpus.table(table_id) is None:
        return _r("missing", f"{here} cites Table {ref.table}, and Article {article} has no Table {ref.table}.")
    actual = table_sections[table_id]
    if ref.within and ref.within != actual:
        return _r("scope_mismatch",
                  f"{here} cites Table {ref.table} in Section {ref.within}, but Table {ref.table} is under "
                  f"Section {actual}.", table_id)
    return _r("ok", f"{here} cites Table {ref.table}.", table_id)


def _resolve(ref: Reference, corpus: Corpus, headings: Headings, table_sections: dict[str, str]) -> Resolution:
    q = ref.quote
    match ref:
        case SelfSectionRef():
            return _self(q, ref.target, corpus)
        case SelfTableRef():
            return _self(q, f"{_article(q.section_id)}:Table{ref.table}", corpus)
        case SectionRef():
            return _section(q, ref, headings)
        case RangeRef():
            return _range(q, ref, headings)
        case TableRef():
            return _table(q, ref, corpus, table_sections)
        case ArticleRef():
            if headings(ref.article):
                return _r("ok", f"{_where(q.section_id)} cites Article {ref.article}.")
            return _r("external_unchecked", f"{_where(q.section_id)} cites Article {ref.article}, which is "
                      "neither loaded nor in the table of contents.")
        case _:
            assert_never(ref)


def _district(ref: DistrictRef, established: set[str]) -> XRef:
    here, article = _where(ref.quote.section_id), _article(ref.quote.section_id)
    if ref.code in established:
        return XRef(quote=ref.quote, resolution=_r("ok", f"{here} names district {ref.code}."))
    return XRef(quote=ref.quote, resolution=_r(
        "undefined_district", f"{here} names district {ref.code}, which Article {article} does not establish."))


def _footnotes(table: Table, corpus: Corpus) -> list[XRef]:
    """(f) for one table: every cell and column-header mark, then every footnote that no
    cell, header or Applicable Footnotes line of this same table uses."""
    name, out = _where(table.id), []
    marks = [(r, c, m, f'Row "{row.label}", column "{table.columns[c]}" of {name}')
             for r, row in enumerate(table.rows) for c, cell in enumerate(row.cells) for m in cell.footnote_marks]
    marks += [(0, c, m, f'Column header "{col}" of {name}')
              for c, col in enumerate(table.columns) for m in _HEADER_MARK.findall(col)]
    for r, c, mark, where in marks:
        quote = CellQuote(table_id=table.id, row_label=table.rows[r].label, column=table.columns[c],
                          text=table.rows[r].cells[c].text, position=(r, c))
        res = (_r("ok", f"{where} carries footnote mark ({mark}).", table.footnotes[mark])
               if mark in table.footnotes else
               _r("footnote_missing", f"{where} carries footnote mark ({mark}), and {name} has no footnote {mark}."))
        out.append(XRef(quote=quote, resolution=res))
    used = {m for _, _, m, _ in marks} | set(table.applicable_footnotes)
    for mark, fn_id in table.footnotes.items():
        if mark not in used:
            if (sec := corpus.section(fn_id)) is None:
                raise ValueError(f"{name} footnote {mark} names {fn_id}, which is not loaded")
            text = sec.text
            out.append(XRef(quote=TextQuote(section_id=fn_id, text=text, span=(0, len(text))), resolution=_r(
                "footnote_unused", f"{name} footnote {mark} is not referenced by any cell, column header, "
                f"or Applicable Footnotes line of {name}.", fn_id)))
    return out


def _definitions(section: Section) -> list[XRef]:
    """(h): a paragraph that defines one district code but whose body regulates a sibling."""
    out = []
    for m in _DEFINES.finditer(section.text):
        defined, used = m[1], m[2]
        quote = TextQuote(section_id=section.id, text=m[0], span=m.span())
        if used != defined and family(used) == family(defined):
            res = _r("definition_mismatch", f"{_where(section.id)} defines {defined} Subdistricts, but the "
                     f"paragraph that follows regulates {used}.", section.id)
        else:
            res = _r("ok", f"{_where(section.id)} defines {defined} Subdistricts.", section.id)
        out.append(XRef(quote=quote, resolution=res))
    return out


def _terms(table: Table, defined: set[str]) -> list[XRef]:
    """(i): every row label of a use table must be a defined use term."""
    out = []
    for r, row in enumerate(table.rows):
        quote = CellQuote(table_id=table.id, row_label=row.label, column=table.columns[0],
                          text=row.cells[0].text, position=(r, 0))
        known = normalize(row.label) in defined
        out.append(XRef(quote=quote, resolution=_r("ok", f'{_where(table.id)} lists use "{row.label}".') if known
                        else _r("undefined_term", f'{_where(table.id)} lists use "{row.label}", which is not a '
                                "defined use term.")))
    return out


def _rows(article: str, established: set[str], dimensional: list[Table], districts: list[DistrictRef]) -> list[XRef]:
    """(j): every established district needs a row in one of the article's dimensional tables."""
    out = []
    for code in sorted(established):
        quote = next((d.quote for d in districts if d.code == code and _article(d.quote.section_id) == article), None)
        if quote is None:
            raise ValueError(f"established district {code} is not written anywhere in Article {article}")
        if any(code in re.split(r"[\s/]+", row.label) for t in dimensional for row in t.rows):
            res = _r("ok", f"District {code} has a dimensional row.")
        else:
            res = _r("district_without_row", f"District {code} is established in Article {article}, but no "
                     f"dimensional table of Article {article} has a row for it.")
        out.append(XRef(quote=quote, resolution=res))
    return out


def resolve_corpus(corpus: Corpus, toc: dict[str, str], *, articles: list[str],
                   established: dict[str, set[str]], table_sections: dict[str, str],
                   defined_terms: set[str], use_tables: list[str]) -> list[XRef]:
    """Every deterministic check of design §5.3 over the audited articles, one XRef each.
    `toc` maps code-wide section and article ids to headings; `table_sections` maps every
    table of the audited articles to the section it sits under."""
    cache: dict[str, dict[str, str]] = {}

    def headings(article: str) -> dict[str, str]:
        if article not in cache:
            cache[article] = ({id: h for id, h in toc.items() if _article(id) == article}
                              | {s.id: s.heading for s in corpus.article(article)})
        return cache[article]

    tables = [corpus.table(id) for id in table_sections]
    defined = {normalize(t) for t in defined_terms}
    out: list[XRef] = []
    districts: list[DistrictRef] = []
    for article in articles:
        for sec in corpus.article(article):
            out += [XRef(quote=r.quote, resolution=_resolve(r, corpus, headings, table_sections))
                    for r in extract_references(sec)]
            found = district_references(sec, established[article])
            out += [_district(d, established[article]) for d in found]
            districts += found
            out += _definitions(sec)
        dimensional = [t for t in tables if t.article == article and "dimensional" in t.title.lower()]
        out += _rows(article, established[article], dimensional, districts)
    for table in tables:
        out += _footnotes(table, corpus)
    for id in use_tables:
        out += _terms(corpus.table(id), defined)
    return out
