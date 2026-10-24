from __future__ import annotations

import sys
import unicodedata
from dataclasses import asdict
from pathlib import Path

import pdfplumber
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from unredline import (  # noqa: E402
    ApplyError,
    ColorSpaceError,
    Edit,
    _char_kind,
    apply_reverse,
    extract_edits,
    main,
)

_REDLINE = Path(__file__).resolve().parents[1] / "data" / "sources" / "2025-04-redline.pdf"
_GROUND_TRUTH = (
    Path(__file__).resolve().parents[1] / "evals" / "ground_truth" / "city_2025_04.yaml"
)
_REQUIRED_FIELDS = {
    "id", "article", "location", "section_id", "pre_text", "post_text",
    "class", "in_scope", "summary_item", "redline_page", "matched_edit",
}
_CLASSES = {
    "xref_missing", "xref_title_mismatch", "xref_self_mismatch", "xref_wrong_article",
    "undefined_term_or_district", "footnote_integrity", "contradiction", "ambiguity",
    "out_of_scope",
}

pdf_required = pytest.mark.skipif(
    not _REDLINE.exists(),
    reason=f"redline PDF absent (gitignored): {_REDLINE}",
)


@pytest.fixture(scope="module")
def edits() -> list[Edit]:
    return extract_edits(_REDLINE)


def _edit(deleted: str, inserted: str, before: str = "", after: str = "") -> Edit:
    return Edit(page=1, article="53", deleted_text=deleted, inserted_text=inserted,
                context_before=before, context_after=after)


def _pairs(edits: list[Edit], **where) -> set[tuple[str, str]]:
    return {(e.deleted_text.strip(), e.inserted_text.strip()) for e in edits
            if all(getattr(e, k) == v for k, v in where.items())}


# --- extraction (needs the PDF) ---


@pdf_required
def test_extracts_page_31_table_h_substitutions(edits):
    assert _pairs(edits, page=31) == {
        ("Sections 53-6 through 53-8", "Sections 53-8 through 53-10"),
        ("Section 53-8.4", "Section 53-10.4"),
        ("Section 53-8.3", "Section 53-10.3"),
        ("Section 53-19", "Section 53-21"),
        ("Section 53-17", "Section 53-19"),
    }


@pdf_required
def test_extracts_renumbering_district_and_rename_edits(edits):
    article_53 = _pairs(edits, article="53")
    for pair in [
        ("Section 53-12.3", "Section 53-14.3"),
        ("Section 53-15.3", "Section 53-17.3"),
        ("Section 53-26", "Section 53-28"),
        ("Section 53-27", "Section 53-29"),
        ("EBR-1", "EBR-2.5"),
        ("Accessory Family Day Care Home", "Accessory Family Child Care Home"),
    ]:
        assert pair in article_53, pair


@pdf_required
def test_pure_insertions_are_extracted(edits):
    fn2 = [e for e in edits if e.page == 24 and not e.deleted_text]
    assert len(fn2) == 1
    assert unicodedata.normalize("NFKC", fn2[0].inserted_text).startswith(
        "Where designated “A,” and the Lot Frontage is fifty-five (55) feet or less")
    assert [e.inserted_text[:13] for e in edits if e.page == 40 and not e.deleted_text] == ["2F-3000(5) 1 "]
    assert [e.inserted_text[:13] for e in edits if e.page == 44 and not e.deleted_text] == [
        "Building (Per", "3F-D-4,000(5)"]


@pdf_required
def test_article_53_edit_count_by_shape(edits):
    article_53 = [e for e in edits if e.article == "53"]
    shapes = [(bool(e.deleted_text.strip()), bool(e.inserted_text.strip())) for e in article_53]
    assert (shapes.count((True, True)), shapes.count((False, True)), shapes.count((True, False))) == (25, 3, 0)
    assert {e.page for e in article_53 if e.deleted_text.strip() == "EBR-1"} == {20}
    assert {e.page for e in article_53 if e.deleted_text.strip() == "Section 53-26"} == {34}


@pdf_required
def test_every_page_reverse_applies_to_its_pre_correction_text(edits):
    failures = []
    with pdfplumber.open(_REDLINE) as doc:
        for page_no, page in enumerate(doc.pages, start=1):
            layered = [(c["text"], _char_kind(c)) for c in page.chars]
            pre = "".join(t for t, k in layered if k != "ins")
            post = "".join(t for t, k in layered if k != "del")
            try:
                restored = apply_reverse(post, [e for e in edits if e.page == page_no])
            except ApplyError as exc:
                failures.append(f"page {page_no}: {exc}")
                continue
            if restored != pre:
                failures.append(f"page {page_no}: restored text differs from keep+deleted")
    assert len(edits) == 126
    assert failures == []


def test_non_rgb_color_space_raises():
    with pytest.raises(ColorSpaceError):
        _char_kind({"non_stroking_color": (0.0, 0.0, 0.0, 1.0)})
    assert _char_kind({"non_stroking_color": (1.0, 0.0, 0.0)}) == "del"
    assert _char_kind({"non_stroking_color": (0.2196, 0.4627, 0.1137)}) == "ins"
    assert _char_kind({"non_stroking_color": (0.0, 0.0, 0.0)}) == "keep"


# --- apply_reverse (no PDF) ---


def test_apply_reverse_substitution():
    post = "the provisions of Sections 53-8 through 53-10 (Tidelands) apply."
    edits = [_edit("Sections 53-6 through 53-8", "Sections 53-8 through 53-10", "of ", " (Tide")]
    assert apply_reverse(post, edits) == "the provisions of Sections 53-6 through 53-8 (Tidelands) apply."


def test_apply_reverse_chained_renumbering_does_not_collide():
    post = "see Section 53-19 (CFROD) and also Section 53-21 (Table 2) today."
    edits = [
        _edit("Section 53-17", "Section 53-19", "see ", " (CFROD)"),
        _edit("Section 53-19", "Section 53-21", "also ", " (Table 2)"),
    ]
    assert apply_reverse(post, edits) == "see Section 53-17 (CFROD) and also Section 53-19 (Table 2) today."


def test_apply_reverse_uses_context_to_pick_the_occurrence():
    post = "Section 53-19 here, and Section 53-19 there."
    edits = [_edit("Section 53-17", "Section 53-19", "and ", " there")]
    assert apply_reverse(post, edits) == "Section 53-19 here, and Section 53-17 there."


def test_apply_reverse_removes_a_pure_insertion_and_restores_a_pure_deletion():
    post = "first. Added sentence. third keep this and that."
    edits = [_edit("", "Added sentence. ", "first. ", "third"), _edit("struck ", "", "and ", "that")]
    assert apply_reverse(post, edits) == "first. third keep this and struck that."


def test_apply_reverse_reports_every_failure():
    post = "Section 53-21 here and Section 53-21 there."
    with pytest.raises(ApplyError) as exc:
        apply_reverse(post, [_edit("old", "Section 53-10.4"), _edit("Section 53-19", "Section 53-21")])
    assert str(exc.value).splitlines()[1:] == [
        "page 1: 'Section 53-10.4' -> 'old' matched 0 times with its context, expected once",
        "page 1: 'Section 53-21' -> 'Section 53-19' matched 2 times with its context, expected once",
    ]


def test_apply_reverse_refuses_two_edits_on_one_span():
    with pytest.raises(ApplyError) as exc:
        apply_reverse("a Section 53-21 b", [_edit("x", "Section 53-21", "a "), _edit("y", "Section 53-21", "a ")])
    assert str(exc.value).splitlines()[1:] == ["edits overlap at 2:15 and 2:15"]


def test_apply_command_exits_non_zero_on_a_broken_input(tmp_path, capsys):
    edits_file = tmp_path / "edits.yaml"
    edits_file.write_text(yaml.safe_dump([asdict(_edit("Section 53-17", "Section 53-19", "see ", "."))]))
    good, broken = tmp_path / "good.txt", tmp_path / "broken.txt"
    good.write_text("see Section 53-19.")
    broken.write_text("see Section 53-21.")
    assert main(["apply", str(edits_file), str(good)]) == 0
    assert capsys.readouterr().out == "see Section 53-17."
    assert main(["apply", str(edits_file), str(broken)]) == 1
    assert "'Section 53-19' -> 'Section 53-17' matched 0 times" in capsys.readouterr().err


# --- ground truth ---


def _load_gt() -> list[dict]:
    return yaml.safe_load(_GROUND_TRUTH.read_text(encoding="utf-8"))


def test_ground_truth_entries_have_required_fields_and_unique_ids():
    entries = _load_gt()
    assert [e["id"] for e in entries if _REQUIRED_FIELDS - e.keys() or e["class"] not in _CLASSES] == []
    assert len({e["id"] for e in entries}) == len(entries) == 32


@pdf_required
def test_ground_truth_pre_text_appears_in_its_pre_correction_page():
    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKC", s)
        for a, b in [("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'")]:
            s = s.replace(a, b)
        for d in "\u2010\u2011\u2012\u2013\u2014\u2212":
            s = s.replace(d, "-")
        return " ".join(s.split())

    absences = {"65-missing-2f-3000", "65-missing-3f-d-4000"}
    with pdfplumber.open(_REDLINE) as doc:
        layers = [[(c["text"], _char_kind(c)) for c in page.chars] for page in doc.pages]
    misses = []
    for e in _load_gt():
        kinds = {"ins"} if e["id"] in absences else {"keep", "del"}
        page = norm("".join(t for t, k in layers[e["redline_page"] - 1] if k in kinds))
        if norm(e["pre_text"]) not in page:
            misses.append(e["id"])
    assert misses == []
