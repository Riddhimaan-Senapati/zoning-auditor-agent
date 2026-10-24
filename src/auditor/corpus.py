from __future__ import annotations

from pathlib import Path

from auditor.models import Section, Table


class Corpus:
    def __init__(self, sections: list[Section], tables: list[Table]) -> None:
        self._sections = _by_id(sections)
        self._tables = _by_id(tables)

    @classmethod
    def load(cls, build_dir: Path) -> Corpus:
        return cls(
            [Section.model_validate_json(ln) for ln in _lines(build_dir / "sections.jsonl")],
            [Table.model_validate_json(ln) for ln in _lines(build_dir / "tables.jsonl")],
        )

    def section(self, id: str) -> Section | None:
        return self._sections.get(id)

    def table(self, id: str) -> Table | None:
        return self._tables.get(id)

    def article(self, article: str) -> list[Section]:
        return [s for s in self._sections.values() if s.article == article]


def _by_id[T: (Section, Table)](items: list[T]) -> dict[str, T]:
    out: dict[str, T] = {}
    for item in items:
        if item.id in out:
            raise ValueError(f"duplicate id {item.id}")
        out[item.id] = item
    return out


def _lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
