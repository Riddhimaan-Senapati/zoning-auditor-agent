from __future__ import annotations

import re
from collections.abc import Callable

from auditor.models import (
    ArticleRef,
    DistrictRef,
    RangeRef,
    Reference,
    Section,
    SectionRef,
    SelfSectionRef,
    SelfTableRef,
    TableRef,
    TextQuote,
)

_NUM = r"\d+[A-Z]*-\d+(?:\.[0-9A-Za-z]+)*"  # "53-29.14", "80B-3.1a", "23-9.a"
_ITEM = re.compile(rf"({_NUM})(?:\s+through\s+({_NUM}))?")
_SEP = r"\s*,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+"
_PAREN = re.compile(r"\s*\(([^()]+)\)")
DISTRICT = r"[A-Z0-9]+(?:[-/][A-Z0-9]+(?:\.[0-9]+)?)+|S[0-9]"  # "EBR-2.5", "3F-D-4000", "MFR/LS", "S0"
_DISTRICT = re.compile(rf"\b(?:{DISTRICT})\b")

Quoter = Callable[[int, int], TextQuote]


def _section_list(m: re.Match[str], quote: Quoter, title: str | None) -> list[Reference]:
    items = list(_ITEM.finditer(m.string, m.start(), m.end()))
    refs: list[Reference] = []
    for i, it in enumerate(items):
        q = quote(m.start() if i == 0 else it.start(), it.end())
        t = title if i == len(items) - 1 else None
        refs.append(RangeRef(quote=q, lo=it[1], hi=it[2], cited_title=t) if it[2]
                    else SectionRef(quote=q, target=it[1], cited_title=t))
    return refs


# In priority order: a span claimed by an earlier pattern is not matched again.
_GRAMMAR: list[tuple[re.Pattern[str], Callable[[re.Match[str], Quoter, str | None], list[Reference]]]] = [
    (re.compile(rf"\b[Tt]his Section ({_NUM})"),
     lambda m, q, _: [SelfSectionRef(quote=q(*m.span()), target=m[1])]),
    (re.compile(r"\b[Tt]his Table ([0-9A-Z]+)\b"),
     lambda m, q, _: [SelfTableRef(quote=q(*m.span()), table=m[1])]),
    (re.compile(rf"\bTable ([0-9A-Z]+) in Section ({_NUM})"),
     lambda m, q, _: [TableRef(quote=q(*m.span()), table=m[1], within=m[2])]),
    (re.compile(rf"\bSections? {_ITEM.pattern}(?:(?:{_SEP}){_ITEM.pattern})*"), _section_list),
    (re.compile(r"\bArticle (\d+[A-Z]*)\b"),
     lambda m, q, _: [ArticleRef(quote=q(*m.span()), article=m[1])]),
    (re.compile(r"\bTable ([0-9A-Z]+)\b"),
     lambda m, q, _: [TableRef(quote=q(*m.span()), table=m[1])]),
]


def _quoter(section: Section) -> Quoter:
    return lambda start, end: TextQuote(section_id=section.id, text=section.text[start:end],
                                        span=(start, end))


def _is_title(s: str) -> bool:
    return len(s.split()) >= 2 and not s.lower().startswith("as amended")


def extract_references(section: Section) -> list[Reference]:
    text, quote = section.text, _quoter(section)
    claimed: list[tuple[int, int]] = []
    found: list[Reference] = []
    for pattern, build in _GRAMMAR:
        for m in pattern.finditer(text):
            if any(s < m.end() and m.start() < e for s, e in claimed):
                continue
            paren = _PAREN.match(text, m.end())
            title = paren[1].strip() if paren and _is_title(paren[1].strip()) else None
            claimed.append((m.start(), paren.end() if title else m.end()))
            found += build(m, quote, title)
    return sorted(found, key=lambda r: r.quote.span)


def family(code: str) -> str:
    head = re.split(r"[-/]", code, maxsplit=1)[0]
    return head if head != code else head.rstrip("0123456789")  # "S0" is family "S"


def district_references(section: Section, established: set[str]) -> list[DistrictRef]:
    families = {family(code) for code in established}
    quote = _quoter(section)
    return [DistrictRef(quote=quote(*m.span()), code=m[0])
            for m in _DISTRICT.finditer(section.text) if family(m[0]) in families]
