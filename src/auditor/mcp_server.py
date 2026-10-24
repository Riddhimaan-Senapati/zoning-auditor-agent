from __future__ import annotations

import string
import sys
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from auditor.corpus import Corpus
from auditor.exports import cited_id
from auditor.models import Rule, Section, SourceRef, Table
from auditor.quotes import normalize
from auditor.resolve import _resolve
from auditor.search import build_search, search
from auditor.xrefs import extract_references

TEXT_CAP = 2000


def _cap(text: str) -> str:
    return text if len(text) <= TEXT_CAP else text[:TEXT_CAP] + "\u2026[truncated]"


def _lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _keys(rule: Rule) -> set[tuple[str, str, str]]:
    return {(kind, v, rule.item) for kind, v in (("district", rule.district), ("use", rule.use)) if v}


def _defines(text: str, term: str) -> bool:
    t = normalize(text).casefold().lstrip("\"'")
    return t == term or (t.startswith(term) and t[len(term)] in string.punctuation)


class Tools:
    def __init__(self, sections: list[Section], tables: list[Table], rules: list[Rule], search_db: Path):
        self._corpus = Corpus(sections, tables)
        self._rules = rules
        self._db = search_db
        self._children: dict[str, list[str]] = {}
        for sec in sections:
            if sec.parent is not None:
                self._children.setdefault(sec.parent, []).append(sec.id)
        self._table_sections = {t.id: t.article for t in tables}

    @classmethod
    def from_build_dir(cls, build_dir: Path, scratch: Path) -> Tools:
        sections = [Section.model_validate_json(ln) for ln in _lines(build_dir / "sections.jsonl")]
        tables = [Table.model_validate_json(ln) for ln in _lines(build_dir / "tables.jsonl")]
        rules_path = build_dir / "rules.jsonl"
        rules = [Rule.model_validate_json(ln) for ln in _lines(rules_path)] if rules_path.exists() else []
        db = build_dir / "search.sqlite"
        if not db.exists():
            db = scratch / "search.sqlite"
            build_search(sections, db)
        return cls(sections, tables, rules, db)

    def get_section(self, section_id: str) -> dict | None:
        sec = self._corpus.section(section_id)
        if sec is None:
            return None
        return {"id": sec.id, "heading": sec.heading, "text": _cap(sec.text), "parent": sec.parent,
                "children": self._children.get(section_id, [])}

    def get_table(self, table_id: str) -> dict | None:
        table = self._corpus.table(table_id)
        if table is None:
            return None
        return {"id": table.id, "title": table.title, "columns": table.columns,
                "rows": [{"label": r.label, "cells": [c.text for c in r.cells]} for r in table.rows],
                "footnotes": table.footnotes}

    def search_sections(self, query: str, k: int = 5) -> list[dict]:
        return [{"id": id, "heading": heading, "snippet": snippet}
                for id, heading, snippet in search(self._db, query, k)]

    def related_sections(self, section_id: str, k: int = 5) -> list[str]:
        """Sections with a rule sharing (district, item) or (use, item) with a rule of `section_id`."""
        keys = {key for r in self._rules if cited_id(r.quote) == section_id for key in _keys(r)}
        out: list[str] = []
        for rule in self._rules:
            sid = cited_id(rule.quote)
            if sid != section_id and sid not in out and keys & _keys(rule):
                out.append(sid)
        return out[:k]

    def get_rules(self, district: str | None = None, use: str | None = None,
                  item: str | None = None) -> list[dict]:
        return [r.model_dump(mode="json") for r in self._rules
                if (district is None or r.district == district)
                and (use is None or r.use == use)
                and (item is None or r.item == item)]

    def get_definition(self, term: str) -> dict | None:
        """The Article 2 section whose heading or text starts by defining `term`."""
        wanted = normalize(term).casefold()
        if not wanted:
            return None
        for sec in self._corpus.article("2"):
            if _defines(sec.heading, wanted) or _defines(sec.text, wanted):
                return {"id": sec.id, "term": sec.heading, "definition": _cap(sec.text)}
        return None

    def resolve_reference(self, text: str, from_section: str) -> dict:
        """Resolve each reference in `text` as if it sat in `from_section`."""
        host = self._corpus.section(from_section)
        probe = Section(
            id=from_section,
            article=host.article if host else from_section.split("-")[0].split(":")[0],
            heading=host.heading if host else "",
            text=text,
            parent=host.parent if host else None,
            kind=host.kind if host else "section",
            source=host.source if host else SourceRef(file="<resolve_reference>", anchor=""),
        )
        results = []
        for ref in extract_references(probe):
            res = _resolve(ref, self._corpus,
                           lambda a: {s.id: s.heading for s in self._corpus.article(a)},
                           self._table_sections)
            results.append({"raw": ref.quote.text, "status": res.status, "detail": res.detail})
        if not results:
            return {"status": "no_reference", "detail": f"No reference found in {text!r}.", "references": []}
        return {"status": results[0]["status"], "detail": results[0]["detail"], "references": results}


def build_server(build_dir: Path, scratch: Path) -> FastMCP:
    tools = Tools.from_build_dir(build_dir, scratch)
    server = FastMCP(name="auditor-corpus")
    for fn in (tools.get_section, tools.get_table, tools.search_sections, tools.related_sections,
               tools.get_rules, tools.get_definition, tools.resolve_reference):
        server.tool()(fn)
    return server


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not Path(argv[0]).is_dir():
        print("usage: python -m auditor.mcp_server <build_dir>", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="auditor-search-") as scratch:
        build_server(Path(argv[0]), Path(scratch)).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
