from __future__ import annotations

from decimal import Decimal

from auditor.agents import AgentFailure
from auditor.corpus import Corpus
from auditor.extract_prose import Extraction, RuleDraft, rules_from_section
from auditor.models import RegulatedItem
from conftest import MINI53, call

CORPUS = Corpus.load(MINI53)
GOOD_QUOTE = "In the EBR-3 subdistrict the maximum building height is 35 feet."


def _draft(**over) -> dict:
    return {"section_id": "53-21", "quote_text": GOOD_QUOTE, "item": "building_height_ft",
            "comparator": "max", "value": "35", "unit": "ft", "district": "EBR-3"} | over


def _run(script, run_dir, answer) -> Extraction | AgentFailure:
    script(call("get_section", {"section_id": "53-21"}), call("final_answer", {"answer": answer}))
    return rules_from_section(CORPUS.section("53-21"), CORPUS, build_dir=MINI53, run_dir=run_dir)


def test_verified_draft_becomes_rule(script, run_dir):
    out = _run(script, run_dir, {"drafts": [_draft()]})
    assert out.dropped == []
    [rule] = out.rules
    assert (rule.item, rule.comparator, rule.value, rule.unit, rule.district, rule.source) == (
        RegulatedItem.building_height_ft, "max", Decimal("35"), "ft", "EBR-3", "prose")
    assert rule.review_reason is None
    assert rule.quote.span == (0, 64)


def test_fabricated_quote_is_dropped(script, run_dir):
    out = _run(script, run_dir, {"drafts": [_draft(quote_text="The maximum building height is 80 feet.", value="80")]})
    assert out.rules == []
    assert [(d.draft.quote_text, d.reason) for d in out.dropped] == [
        ("The maximum building height is 80 feet.", "no record: quote not found in section text")]


def test_value_absent_from_quote_gets_review_reason(script, run_dir):
    out = _run(script, run_dir, {"drafts": [_draft(value="40")]})
    [rule] = out.rules
    assert (rule.value, rule.review_reason) == (Decimal("40"), "value '40' is not stated in the quoted text")


def test_value_matches_whole_numbers_not_digits(script, run_dir):
    out = _run(script, run_dir, {"drafts": [_draft(value="5"), _draft(value="35.0")]})
    assert [r.review_reason for r in out.rules] == ["value '5' is not stated in the quoted text", None]


def test_model_drafted_review_reason_is_kept(script, run_dir):
    out = _run(script, run_dir, {"drafts": [_draft(review_reason="district taken from the heading")]})
    assert [r.review_reason for r in out.rules] == ["district taken from the heading"]


def test_invalid_drafts_are_dropped_and_the_rest_kept(script, run_dir):
    bad = [_draft(value="35 feet"), _draft(unit=None), _draft(footnotes=["fn 3"])]
    out = _run(script, run_dir, {"drafts": [*bad, _draft()]})
    assert [r.value for r in out.rules] == [Decimal("35")]
    assert [d.draft for d in out.dropped] == [RuleDraft.model_validate(b) for b in bad]
    assert all(d.reason.startswith("no record: 1 validation error for Rule") for d in out.dropped)


def test_agent_failure_is_returned(script, run_dir):
    out = _run(script, run_dir, "not a RuleDrafts object")
    assert isinstance(out, AgentFailure)
    assert (out.role, out.raw) == ("extract_prose", "not a RuleDrafts object")
