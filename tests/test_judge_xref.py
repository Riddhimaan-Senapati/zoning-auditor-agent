from __future__ import annotations

from pathlib import Path

from auditor.judge_xref import Rename, agency_xrefs, judge, load_renames
from auditor.models import Section, SourceRef, is_verified
from conftest import MINI53, call

RENAMES = load_renames()


def _section(text: str) -> Section:
    return Section(id="53-99", article="53", heading="Review Procedure", text=text, parent="53",
                   kind="section", source=SourceRef(file="mini.html", anchor="s-53-99"))


def test_renames_csv_has_cited_boston_rows():
    assert len(RENAMES) >= 2
    assert any(r.old_name == "Boston Redevelopment Authority"
               and r.current_name == "Boston Planning & Development Agency" for r in RENAMES)
    assert all(r.citation_url.startswith("https://") for r in RENAMES)
    assert all(r.note for r in RENAMES)


def test_agency_extractor_finds_a_planted_old_name():
    section = _section("Applications shall be reviewed by the Boston Redevelopment Authority before approval.")
    [xref] = agency_xrefs(section, RENAMES)
    assert xref.resolution.status == "needs_judgment"
    assert xref.quote.section_id == "53-99"
    assert xref.quote.text == "Boston Redevelopment Authority"
    assert is_verified(xref.quote)
    assert xref.resolution.detail == (
        'Section 53-99 names "Boston Redevelopment Authority"; the rename table lists '
        '"Boston Planning & Development Agency" as its current name.')


def test_no_agency_name_yields_no_xref():
    assert agency_xrefs(_section("Applications shall be reviewed by the board before approval."), RENAMES) == []


def test_every_occurrence_becomes_its_own_xref():
    section = _section("The Boston Redevelopment Authority and the Boston Redevelopment Authority both apply.")
    assert len(agency_xrefs(section, RENAMES)) == 2


def test_judge_broken_returns_a_model_finder_candidate(script, run_dir):
    section = _section("Review by the Boston Redevelopment Authority is required.")
    [xref] = agency_xrefs(section, RENAMES)
    script(call("get_section", {"section_id": "53-99"}),
           call("final_answer", {"answer": {"verdict": "broken", "reason": "names the present-day planning body."}}))
    candidate = judge(xref, build_dir=MINI53, run_dir=run_dir)
    assert candidate is not None
    assert candidate.type == "xref"
    assert candidate.origin == "model_finder"
    assert candidate.payload == {"status": "needs_judgment", "verdict": "broken"}
    assert candidate.claim.endswith("names the present-day planning body.")
    assert [q.text for q in candidate.quotes] == ["Boston Redevelopment Authority"]


def test_judge_ok_returns_none(script, run_dir):
    section = _section("Enacted by the Boston Redevelopment Authority in 1965.")
    [xref] = agency_xrefs(section, RENAMES)
    script(call("final_answer", {"answer": {"verdict": "ok", "reason": "historical citation as enacted."}}))
    assert judge(xref, build_dir=MINI53, run_dir=run_dir) is None
