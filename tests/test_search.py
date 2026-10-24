from __future__ import annotations

from pathlib import Path

import pytest

from auditor.corpus import Corpus
from auditor.search import build_search, search

FIXTURE = Path(__file__).parent / "fixtures" / "mini53"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    corpus = Corpus.load(FIXTURE)
    sections = corpus.article("53")
    out = tmp_path / "search.db"
    build_search(sections, out)
    return out


def test_waterfront_yard_area(db: Path):
    assert search(db, "waterfront yard area", 3) == [
        ("53-19", "Design Review",
         "Projects shall satisfy the waterfront yard standard in Section 53-10.4 (Waterfront Yard Area Requirements)."),
        ("53-10.4", "Waterfront Yard Area Requirements",
         "A waterfront yard of at least 50 feet shall be provided along the water's edge."),
        ("53-29.4", "Exceptions",
         "Except as otherwise provided in this Section 53-27, lots in EBR-1 shall meet the yard standards "
         "in Section 53-8 (Waterfront Yard Area Requirements)."),
    ]


def test_building_height_ebr3(db: Path):
    assert search(db, "building height EBR-3", 2) == [
        ("53-21", "Dimensional Standards for EBR-3",
         "In the EBR-3 subdistrict the maximum building height is 35 feet."),
        ("53:TableH:fn3", "Table H, Footnote 3",
         "Corner lots shall measure height from the higher adjacent grade."),
    ]


def test_hyphenated_id_query_matches_its_parts(db: Path):
    # '53-8' is FTS5 syntax (a NOT clause) unless escaped; it must not raise and
    # should rank the section that cites Section 53-8 first.
    top = search(db, "53-8", 3)
    assert top[0] == (
        "53-29.4", "Exceptions",
        "Except as otherwise provided in this Section 53-27, lots in EBR-1 shall meet the yard standards "
        "in Section 53-8 (Waterfront Yard Area Requirements).",
    )


def test_punctuation_only_query_returns_empty(db: Path):
    for q in ("!!! ???", "()", '"', "- : ( )", "   "):
        assert search(db, q, 5) == []


def test_rebuild_is_idempotent(tmp_path: Path):
    sections = Corpus.load(FIXTURE).article("53")
    out = tmp_path / "search.db"
    build_search(sections, out)
    build_search(sections, out)
    assert [id for id, _, _ in search(out, "waterfront yard area", 5)] == [
        "53-19", "53-10.4", "53-29.4", "53-5", "53-10"]
