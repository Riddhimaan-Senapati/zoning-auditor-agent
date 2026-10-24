from __future__ import annotations

import re
from decimal import Decimal

from auditor.corpus import Corpus
from auditor.extract_tables import rules_from_table
from auditor.find_contradictions import model_candidates, structured_candidates
from auditor.ids import rule_id
from auditor.models import RegulatedItem, Rule, TextQuote
from auditor.quotes import verify_text
from conftest import MINI53, call

CORPUS = Corpus.load(MINI53)


def _prose_rule(district: str | None, value: str, conditions: list[str] | None = None) -> Rule:
    quote = verify_text(TextQuote(section_id="53-21",
                                  text="In the EBR-3 subdistrict the maximum building height is 35 feet."), CORPUS)
    assert isinstance(quote, TextQuote)
    return Rule(id=rule_id(quote, district, None, RegulatedItem.building_height_ft),
                district=district, use=None, item=RegulatedItem.building_height_ft, comparator="max",
                value=Decimal(value), unit="ft", status=None, conditions=conditions or [], footnotes=[],
                quote=quote, source="prose", review_reason=None)


def _table_h_ebr3_height() -> Rule:
    [rule] = [r for r in rules_from_table(CORPUS.table("53:TableH"), CORPUS)
              if r.district == "EBR-3" and r.item is RegulatedItem.building_height_ft]
    return rule


def test_seeded_ebr3_height_conflict_is_one_candidate_with_a_literal_claim():
    table_rule = _table_h_ebr3_height()  # EBR-3 building_height_ft = 40 (Table H)
    prose_rule = _prose_rule("EBR-3", "35")  # EBR-3 building_height_ft = 35 (prose 53-21)
    assert table_rule.value == Decimal("40") and prose_rule.value == Decimal("35")
    candidates, disjoint = structured_candidates([table_rule, prose_rule])
    assert disjoint == []
    [candidate] = candidates
    assert candidate.type == "contradiction"
    assert candidate.origin == "structured"
    assert candidate.readings is None
    assert candidate.quotes == [table_rule.quote, prose_rule.quote]
    assert candidate.claim == (
        "building_height_ft in EBR-3 is stated as 40 at 53:TableH and 35 at 53-21.")


def test_equal_values_make_no_candidate():
    candidates, disjoint = structured_candidates([_prose_rule("EBR-3", "35"), _table_h_ebr3_height(),
                                                  _prose_rule("EBR-3", "40")])
    # Two of the three agree at 40 and one is 35: only the 40-vs-35 pairs conflict.
    assert len(candidates) == 2
    assert disjoint == []


def test_different_districts_are_not_grouped_together():
    candidates, disjoint = structured_candidates([_prose_rule("EBR-3", "40"), _prose_rule("EBR-4", "35")])
    assert candidates == [] and disjoint == []


def test_disjoint_conditions_are_excluded_and_returned():
    corner = _prose_rule("EBR-3", "40", conditions=["for corner lots"])
    midblock = _prose_rule("EBR-3", "35", conditions=["for mid-block lots"])
    candidates, disjoint = structured_candidates([corner, midblock])
    assert candidates == []
    assert disjoint == [(corner, midblock)]


def test_same_condition_marker_still_conflicts():
    a = _prose_rule("EBR-3", "40", conditions=["for corner lots"])
    b = _prose_rule("EBR-3", "35", conditions=["for corner lots"])
    candidates, disjoint = structured_candidates([a, b])
    assert len(candidates) == 1 and disjoint == []


def test_needs_review_rules_still_produce_candidates():
    quote = verify_text(TextQuote(section_id="53-21",
                                  text="In the EBR-3 subdistrict the maximum building height is 35 feet."), CORPUS)
    assert isinstance(quote, TextQuote)
    unreviewed = Rule(id=rule_id(quote, "EBR-3", None, RegulatedItem.building_height_ft), district="EBR-3",
                      use=None, item=RegulatedItem.building_height_ft, comparator="max", value=Decimal("35"),
                      unit="ft", status=None, conditions=[], footnotes=[], quote=quote, source="prose",
                      review_reason="district taken from heading")
    assert unreviewed.needs_review
    candidates, _ = structured_candidates([unreviewed, _table_h_ebr3_height()])
    assert len(candidates) == 1


def _spy_run_agent(monkeypatch):
    """Record every task run_agent is called with, and return an empty Proposals so no
    candidate is produced. Lets a test count how many section-sets the finder examined."""
    from auditor import find_contradictions
    tasks: list[str] = []

    def fake(role, task, out, *, build_dir, run_dir, max_steps=6):
        tasks.append(task)
        return find_contradictions.Proposals()

    monkeypatch.setattr(find_contradictions, "run_agent", fake)
    return tasks


def _examined_sets(tasks: list[str]) -> list[frozenset[str]]:
    return [frozenset(re.search(r"Sections: (.+?)\. Read each", t).group(1).split(", ")) for t in tasks]


def test_model_finder_examines_each_unordered_section_set_once(monkeypatch, run_dir):
    # Two rules share (EBR-3, building_height_ft): one on section 53-21, one in Table H
    # (cited id 53:TableH). related_sections(53-21) -> [53:TableH] and the reverse, so the
    # set {53-21, 53:TableH} is reachable from either section. Passing both, the dedupe must
    # examine that set exactly once.
    rules = [_prose_rule("EBR-3", "35"), _table_h_ebr3_height()]
    tasks = _spy_run_agent(monkeypatch)
    sections = [CORPUS.section("53-21"), CORPUS.section("53-21")]  # the same set, reached twice
    candidates, failures = model_candidates(sections, rules, build_dir=MINI53, run_dir=run_dir)
    assert candidates == [] and failures == []
    sets = _examined_sets(tasks)
    assert sets == [frozenset({"53-21", "53:TableH"})]  # examined once, not twice


def test_model_finder_skips_sections_with_no_rules_and_no_obligation(monkeypatch, run_dir):
    # 53-10 ("regulate development along the shoreline") has no rule and no obligation word,
    # so it is never examined; 53-21 (has a rule) is.
    rules = [_prose_rule("EBR-3", "35"), _table_h_ebr3_height()]
    tasks = _spy_run_agent(monkeypatch)
    sections = [CORPUS.section("53-10"), CORPUS.section("53-21")]
    model_candidates(sections, rules, build_dir=MINI53, run_dir=run_dir)
    assert _examined_sets(tasks) == [frozenset({"53-21", "53:TableH"})]


def test_model_finder_converts_an_agent_proposal_to_a_candidate(script, run_dir):
    from auditor.models import is_verified
    proposal = {"candidates": [{
        "quotes": [{"section_id": "53-21", "text": "the maximum building height is 35 feet"},
                   {"section_id": "53:TableH", "text": "40"}],
        "claim": "The EBR-3 height is stated as 35 feet in 53-21 and 40 feet in Table H."}]}
    script(call("final_answer", {"answer": proposal}))
    candidates, failures = model_candidates([CORPUS.section("53-21")],
                                            [_prose_rule("EBR-3", "35"), _table_h_ebr3_height()],
                                            build_dir=MINI53, run_dir=run_dir)
    assert failures == []
    [candidate] = candidates
    assert candidate.type == "contradiction"
    assert candidate.origin == "model_finder"
    assert candidate.claim == "The EBR-3 height is stated as 35 feet in 53-21 and 40 feet in Table H."
    assert [(q.section_id, q.text) for q in candidate.quotes] == [
        ("53-21", "the maximum building height is 35 feet"), ("53:TableH", "40")]
    assert not any(is_verified(q) for q in candidate.quotes)  # verification is the next stage's job
