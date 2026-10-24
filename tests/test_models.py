from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from auditor.corpus import Corpus
from auditor.ids import slug
from auditor.models import (
    Candidate, Cell, CellQuote, Finding, Quote, RegulatedItem, Rule, Section, SourceRef,
    Table, TableRow, TextQuote, Verdict,
)

VERIFIED = TextQuote(section_id="53-1", text="hello", span=(0, 5))


def _verdict(**kw) -> Verdict:
    base = dict(candidate_id="c1", quote_failures=[], skeptic="upheld", skeptic_reasoning=None,
                reconciling_quotes=[], sections_retrieved=[])
    return Verdict(**(base | kw))


def _finding(**kw) -> Finding:
    base = dict(id="f1", type="xref", origin="deterministic", quotes=[VERIFIED], claim="x",
                readings=None, confidence="high", candidate_ids=["c1"], verdict=_verdict(),
                neutrality_flags=[])
    return Finding(**(base | kw))


def _rule(**kw) -> Rule:
    base = dict(id="r1", district="EBR-3", use=None, item=RegulatedItem.building_height_ft,
                comparator="max", value=Decimal("35"), unit="ft", status=None, conditions=[],
                footnotes=[], quote=VERIFIED, source="table", review_reason=None)
    return Rule(**(base | kw))


def test_finding_requires_a_verified_quote():
    assert _finding().quotes == [VERIFIED]
    with pytest.raises(ValidationError):
        _finding(quotes=[])
    with pytest.raises(ValidationError):
        _finding(quotes=[TextQuote(section_id="53-1", text="hello")])


@pytest.mark.parametrize("skeptic", ["refuted", "uncertain"])
def test_finding_rejects_unreportable_verdicts(skeptic):
    with pytest.raises(ValidationError):
        _finding(verdict=_verdict(skeptic=skeptic))


def test_failed_quote_gate_means_skeptic_not_run():
    assert _verdict(quote_failures=["missing"], skeptic="not_run").skeptic == "not_run"
    with pytest.raises(ValidationError):
        _verdict(quote_failures=["missing"], skeptic="upheld")
    with pytest.raises(ValidationError):
        _verdict(skeptic="not_run")


def test_readings_only_and_always_for_ambiguity():
    with pytest.raises(ValidationError):
        _finding(readings=("a", "b"))
    with pytest.raises(ValidationError):
        Candidate(id="c", type="ambiguity", origin="model_finder", quotes=[], claim="x",
                  readings=None, payload={})


def test_span_must_be_ordered():
    with pytest.raises(ValidationError):
        TextQuote(section_id="53-1", text="x", span=(7, 2))


def test_quote_union_round_trips_by_kind():
    adapter = TypeAdapter(Quote)
    cell = CellQuote(table_id="53:TableH", row_label="EBR-3", column="Height", text="35", position=(0, 1))
    for q in (VERIFIED, cell):
        assert adapter.validate_json(adapter.dump_json(q)) == q


def test_rule_invariants():
    assert _rule().needs_review is False
    assert _rule(value=None, review_reason="cell reads 'see fn'").needs_review is True
    for bad in (dict(unit=None), dict(value=None), dict(status="A"),
                dict(item=RegulatedItem.other), dict(quote=TextQuote(section_id="53-1", text="35"))):
        with pytest.raises(ValidationError):
            _rule(**bad)
    status = _rule(comparator="status", value=None, unit=None, status="C", item=RegulatedItem.use_permission)
    assert status.status == "C"


def test_section_ids_are_validated_and_slug_is_url_safe():
    with pytest.raises(ValidationError):
        Section(id="not an id!", article="53", heading="h", text="t", parent=None,
                kind="section", source=SourceRef(file="f", anchor="a"))
    assert slug("53:TableH:fn3") == "53__TableH__fn3"
    assert slug("80B-3.1a") == "80B-3_1a"
    with pytest.raises(ValueError):
        slug("53-29..4")


def test_table_must_be_rectangular_with_unique_labels():
    def table(rows, columns=("A",)):
        return Table(id="53:TableH", article="53", title="H", columns=list(columns), rows=rows,
                     footnotes={}, applicable_footnotes=[], source=SourceRef(file="f", anchor="a"))
    cell = Cell(text="1", footnote_marks=[])
    with pytest.raises(ValidationError):
        table([TableRow(label="R", cells=[cell]), TableRow(label="R", cells=[cell])])
    with pytest.raises(ValidationError):
        table([TableRow(label="R", cells=[cell])], columns=("A", "B"))
    with pytest.raises(ValidationError):
        table([TableRow(label="R", cells=[cell, cell])], columns=("A", "A"))


def test_corpus_rejects_duplicate_ids():
    s = Section(id="53-1", article="53", heading="h", text="t", parent=None,
                kind="section", source=SourceRef(file="f", anchor="a"))
    with pytest.raises(ValueError):
        Corpus([s, s], [])
