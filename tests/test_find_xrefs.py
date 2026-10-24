from __future__ import annotations

from pathlib import Path

from auditor.corpus import Corpus
from auditor.find_xrefs import candidates, funnel_counts, skipped_verdict
from auditor.models import Finding, TextQuote, is_verified
from auditor.quotes import verify_cell, verify_text
from auditor.resolve import resolve_corpus

CORPUS = Corpus.load(Path(__file__).parent / "fixtures" / "mini53")


def _xrefs():
    return resolve_corpus(
        CORPUS, {},
        articles=["53"],
        established={"53": {"EBR-2.5", "EBR-3", "EBR-4", "EBR-5"}},
        table_sections={"53:TableH": "53-4", "53:TableA": "53-4", "53:Table2": "53-21"},
        defined_terms={"Single-family dwelling", "Accessory Child Care Home"},
        use_tables=["53:TableA"],
    )


def _location(c) -> str:
    q = c.quotes[0]
    return q.section_id if isinstance(q, TextQuote) else q.table_id


def test_mini53_candidates():
    assert [(c.payload["status"], _location(c), c.claim) for c in candidates(_xrefs())] == [
        ("definition_mismatch", "53-4.1",
         "Section 53-4.1 defines EBR-3 Subdistricts, but the paragraph that follows regulates EBR-4."),
        ("self_mismatch", "53-29.4", 'Section 53-29.4 says "this Section 53-27", but it sits in Section 53-29.4.'),
        ("title_mismatch", "53-29.4",
         'Section 53-29.4 cites Section 53-8 as "Waterfront Yard Area Requirements", but Section 53-8 is '
         'titled "Regulations Applicable on Tidelands". Section 53-10.4 is titled "Waterfront Yard Area '
         'Requirements".'),
        ("undefined_district", "53-29.4", "Section 53-29.4 names district EBR-1, which Article 53 does not establish."),
        ("scope_mismatch", "53-31", "Section 53-31 cites Table 2 in Section 53-19, but Table 2 is under Section 53-21."),
        ("self_mismatch", "53:TableK:fn1", 'Table K footnote 1 says "this Table I", but it sits in Table K.'),
        ("district_without_row", "53-5",
         "District EBR-5 is established in Article 53, but no dimensional table of Article 53 has a row for it."),
        ("footnote_missing", "53:TableH",
         'Row "EBR-4", column "Building Height Maximum | Feet" of Table H carries footnote mark (5), and '
         "Table H has no footnote 5."),
        ("footnote_unused", "53:TableH:fn9",
         "Table H footnote 9 is not referenced by any cell, column header, or Applicable Footnotes line of Table H."),
        ("undefined_term", "53:TableA",
         'Table A lists use "Accessory Family Day Care Home", which is not a defined use term.'),
    ]


def test_every_candidate_quote_verifies_against_the_corpus():
    cands = candidates(_xrefs())
    checked = [verify_text(q, CORPUS) if isinstance(q, TextQuote) else verify_cell(q, CORPUS)
               for c in cands for q in c.quotes]
    assert [is_verified(q) for q in checked] == [True] * 10


def test_funnel_counts_every_check_including_ok():
    assert funnel_counts(_xrefs()) == {
        "ok": 18, "definition_mismatch": 1, "self_mismatch": 2, "title_mismatch": 1,
        "undefined_district": 1, "scope_mismatch": 1, "district_without_row": 1,
        "footnote_missing": 1, "footnote_unused": 1, "undefined_term": 1,
    }


def test_only_proved_statuses_get_a_skipped_verdict_and_become_findings():
    built, refused = [], []
    for c in candidates(_xrefs()):
        try:
            verdict = skipped_verdict(c)
        except ValueError:
            refused.append(c.payload["status"])
            continue
        finding = Finding(id=c.id, type=c.type, origin=c.origin, quotes=c.quotes, claim=c.claim,
                          readings=None, confidence="high", candidate_ids=[c.id], verdict=verdict,
                          neutrality_flags=[])
        built.append((c.payload["status"], finding.verdict.skeptic))
    assert built == [("definition_mismatch", "skipped"), ("self_mismatch", "skipped"),
                     ("undefined_district", "skipped"), ("self_mismatch", "skipped"),
                     ("footnote_missing", "skipped"), ("footnote_unused", "skipped")]
    assert refused == ["title_mismatch", "scope_mismatch", "district_without_row", "undefined_term"]


def test_candidate_ids_are_distinct():
    assert len({c.id for c in candidates(_xrefs())}) == 10
