from __future__ import annotations

from pathlib import Path

from auditor.corpus import Corpus
from auditor.models import Section, SourceRef, TextQuote
from auditor.quotes import verify_text
from auditor.xrefs import district_references, extract_references

CORPUS = Corpus.load(Path(__file__).parent / "fixtures" / "mini53")


def _section(text: str) -> Section:
    return Section(id="53-1", article="53", heading="h", text=text, parent=None,
                   kind="section", source=SourceRef(file="f", anchor="a"))


def _refs(text: str) -> list[tuple]:
    return [(type(r).__name__, r.quote.text, r.model_dump(exclude={"quote"}))
            for r in extract_references(_section(text))]


def test_every_kind_is_extracted_with_a_span_that_re_verifies():
    section = _section(
        "see Section 53-8.4, Section 53-10.4 (Waterfront Yard Area Requirements), "
        "this Table I, Article 2A, Table 2 in Section 53-19, Table H, "
        "Sections 53-6 through 53-8 apply under this Section 53-1."
    )
    refs = extract_references(section)
    assert [(type(r).__name__, r.quote.text) for r in refs] == [
        ("SectionRef", "Section 53-8.4"),
        ("SectionRef", "Section 53-10.4"),
        ("SelfTableRef", "this Table I"),
        ("ArticleRef", "Article 2A"),
        ("TableRef", "Table 2 in Section 53-19"),
        ("TableRef", "Table H"),
        ("RangeRef", "Sections 53-6 through 53-8"),
        ("SelfSectionRef", "this Section 53-1"),
    ]
    one = Corpus([section], [])
    assert [verify_text(TextQuote(section_id="53-1", text=r.quote.text), one).span for r in refs] == [
        r.quote.span for r in refs]


def test_titles_have_two_words_any_case_and_may_hold_commas():
    assert [r[2]["cited_title"] for r in _refs(
        "Section 53-21 (a) and Section 53-12 (as amended on May 9, 1996.) and Section 53-21(3) and "
        "Section 67-32 (Off-Street Parking and Loading Requirements) and "
        "Section 53-9 (Yards, Courts, and Setbacks)")] == [
        None, None, None, "Off-Street Parking and Loading Requirements", "Yards, Courts, and Setbacks"]
    assert _refs("Sections 53-6 through 53-8  (concerning regulations applicable on Tidelands) apply") == [
        ("RangeRef", "Sections 53-6 through 53-8",
         {"lo": "53-6", "hi": "53-8", "cited_title": "concerning regulations applicable on Tidelands"})]


def test_lists_become_one_reference_per_item_and_the_title_goes_to_the_last():
    assert _refs("Sections 53-6 through 53-8 and 53-12 (Design Review), and Section 80B-2 or 80E-2, "
                 "and Sections 53-6, 53-8, and 53-10") == [
        ("RangeRef", "Sections 53-6 through 53-8", {"lo": "53-6", "hi": "53-8", "cited_title": None}),
        ("SectionRef", "53-12", {"target": "53-12", "cited_title": "Design Review"}),
        ("SectionRef", "Section 80B-2", {"target": "80B-2", "cited_title": None}),
        ("SectionRef", "80E-2", {"target": "80E-2", "cited_title": None}),
        ("SectionRef", "Sections 53-6", {"target": "53-6", "cited_title": None}),
        ("SectionRef", "53-8", {"target": "53-8", "cited_title": None}),
        ("SectionRef", "53-10", {"target": "53-10", "cited_title": None}),
    ]


def test_self_references_take_either_case_and_lettered_ids_stay_verbatim():
    assert _refs("This Section 53-27 and this Table I and Section 80B-3.1a and Section 23-9.a") == [
        ("SelfSectionRef", "This Section 53-27", {"target": "53-27"}),
        ("SelfTableRef", "this Table I", {"table": "I"}),
        ("SectionRef", "Section 80B-3.1a", {"target": "80B-3.1a", "cited_title": None}),
        ("SectionRef", "Section 23-9.a", {"target": "23-9.a", "cited_title": None}),
    ]


def test_district_tokens_come_from_established_families_only():
    section = _section("EBR-1 EBR-2.5 EBR-10 2F-3000 3F-D-4000 MFR/LS S0 S5, Section 53-8, COVID-19")
    assert [r.code for r in district_references(section, {"EBR-2.5", "2F-5000", "3F-D-2000", "MFR", "S1"})] == [
        "EBR-1", "EBR-2.5", "EBR-10", "2F-3000", "3F-D-4000", "MFR/LS", "S0", "S5"]


def test_mini53_exceptions_section():
    assert [(type(r).__name__, r.quote.text) for r in extract_references(CORPUS.section("53-29.4"))] == [
        ("SelfSectionRef", "this Section 53-27"), ("SectionRef", "Section 53-8")]
    (s8,) = [r for r in extract_references(CORPUS.section("53-29.4")) if type(r).__name__ == "SectionRef"]
    assert s8.cited_title == "Waterfront Yard Area Requirements"
