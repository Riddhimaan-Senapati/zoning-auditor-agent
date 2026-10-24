from __future__ import annotations

from auditor.corpus import Corpus
from auditor.find_xrefs import candidates
from auditor.models import Candidate, TextQuote
from auditor.resolve import resolve_corpus
from auditor.verify import SkepticOut, confidence, verify
from conftest import MINI53, call

CORPUS = Corpus.load(MINI53)


def _xref_candidates() -> dict[str, Candidate]:
    xrefs = resolve_corpus(
        CORPUS, {}, articles=["53"],
        established={"53": {"EBR-2.5", "EBR-3", "EBR-4", "EBR-5"}},
        table_sections={"53:TableH": "53-4", "53:TableA": "53-4", "53:Table2": "53-21"},
        defined_terms={"Single-family dwelling", "Accessory Child Care Home"},
        use_tables=["53:TableA"],
    )
    return {c.payload["status"]: c for c in candidates(xrefs)}


def _skeptic_answer(verdict: str, reconciling=(), retrieved=()):
    out = SkepticOut(verdict=verdict, reasoning="r",
                     reconciling_quotes=[{"section_id": s, "text": t} for s, t in reconciling],
                     sections_retrieved=list(retrieved))
    return call("final_answer", {"answer": out.model_dump()})


def test_fabricated_quote_fails_the_gate_with_no_model_call(script, run_dir):
    fake = script()
    bogus = Candidate(id="c1", type="contradiction", origin="model_finder",
                      quotes=[TextQuote(section_id="53-21", text="this text is not in the section")],
                      claim="fabricated", readings=None, payload={})
    returned, verdict = verify(bogus, CORPUS, build_dir=MINI53, run_dir=run_dir)
    assert fake.calls == 0
    assert verdict.skeptic == "not_run"
    assert verdict.quote_failures == ["quote not found in section text"]
    assert returned.quotes[0].span is None


def test_skipped_xref_candidate_skips_the_model(script, run_dir):
    fake = script()
    cand = _xref_candidates()["self_mismatch"]
    returned, verdict = verify(cand, CORPUS, build_dir=MINI53, run_dir=run_dir)
    assert fake.calls == 0
    assert verdict.skeptic == "skipped"
    assert verdict.quote_failures == []
    assert returned.quotes[0].span is not None
    assert confidence(returned, verdict, {}) == "high"


def test_refuted_without_a_reconciling_quote_becomes_uncertain(script, run_dir):
    script(_skeptic_answer("refuted"))
    cand = _xref_candidates()["title_mismatch"]
    _, verdict = verify(cand, CORPUS, build_dir=MINI53, run_dir=run_dir)
    assert verdict.skeptic == "uncertain"
    assert verdict.reconciling_quotes == []


def test_refuted_with_a_verified_reconciling_quote_stays_refuted(script, run_dir):
    script(_skeptic_answer(
        "refuted",
        reconciling=[("53-8", "Development on filled or flowed tidelands shall comply with Chapter 91")]))
    cand = _xref_candidates()["title_mismatch"]
    _, verdict = verify(cand, CORPUS, build_dir=MINI53, run_dir=run_dir)
    assert verdict.skeptic == "refuted"
    assert verdict.reconciling_quotes[0].section_id == "53-8"
    assert verdict.reconciling_quotes[0].span is not None


def test_upheld_title_mismatch_is_high_confidence(script, run_dir):
    script(_skeptic_answer("upheld", retrieved=["53-8", "53-10.4"]))
    cand = _xref_candidates()["title_mismatch"]
    returned, verdict = verify(cand, CORPUS, build_dir=MINI53, run_dir=run_dir)
    assert verdict.skeptic == "upheld"
    assert verdict.sections_retrieved == ["53-8", "53-10.4"]
    assert confidence(returned, verdict, {}) == "high"


def test_a_skeptic_answer_that_does_not_parse_is_uncertain(script, run_dir):
    script(call("final_answer", {"answer": "not a SkepticOut object"}))
    cand = _xref_candidates()["title_mismatch"]
    _, verdict = verify(cand, CORPUS, build_dir=MINI53, run_dir=run_dir)
    assert verdict.skeptic == "uncertain"
    assert verdict.quote_failures == []
