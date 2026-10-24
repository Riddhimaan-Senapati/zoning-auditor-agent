from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from auditor import findings
from auditor.corpus import Corpus
from auditor.find_xrefs import candidates, skipped_verdict
from auditor.models import Candidate, Quote, TextQuote, Verdict
from auditor.quotes import verify_text
from auditor.resolve import resolve_corpus
from auditor.verify import verify
from conftest import MINI53, call

CORPUS = Corpus.load(MINI53)

# A pool of quotes that verify against mini53, so generated Findings are constructible.
_POOL = [
    ("53-21", "the maximum building height is 35 feet"),
    ("53-8", "Development on filled or flowed tidelands shall comply with Chapter 91"),
    ("53-10.4", "A waterfront yard of at least 50 feet shall be provided"),
]
_VERIFIED: list[Quote] = [verify_text(TextQuote(section_id=s, text=t), CORPUS) for s, t in _POOL]


def _xref(status: str) -> Candidate:
    xrefs = resolve_corpus(
        CORPUS, {}, articles=["53"],
        established={"53": {"EBR-2.5", "EBR-3", "EBR-4", "EBR-5"}},
        table_sections={"53:TableH": "53-4", "53:TableA": "53-4", "53:Table2": "53-21"},
        defined_terms={"Single-family dwelling", "Accessory Child Care Home"},
        use_tables=["53:TableA"],
    )
    return next(c for c in candidates(xrefs) if c.payload["status"] == status)


def test_skipped_xref_becomes_a_high_confidence_finding(run_dir):
    cand = _xref("self_mismatch")
    verdict = skipped_verdict(cand)
    built = findings.build([(cand, verdict)], "r1", run_dir)
    assert len(built) == 1
    assert (built[0].confidence, built[0].verdict.skeptic) == ("high", "skipped")
    assert built[0].candidate_ids == [cand.id]


def test_refuted_candidate_is_not_reported_and_leaves_a_trace_reason(script, run_dir):
    script(call("final_answer", {"answer": {"verdict": "refuted", "reasoning": "r",
                                            "reconciling_quotes": [], "sections_retrieved": []}}))
    cand = _xref("title_mismatch")
    returned, verdict = verify(cand, CORPUS, build_dir=MINI53, run_dir=run_dir)
    built = findings.build([(returned, verdict)], "r1", run_dir)
    assert built == []
    assert findings.funnel(run_dir)["xref"] == {"candidates": 1, "quote_passed": 1,
                                                "upheld": 0, "reported": 0}


# --- generated pairs for the properties -------------------------------------------------

@st.composite
def _pairs(draw):
    out = []
    for i in range(draw(st.integers(min_value=0, max_value=5))):
        quotes = draw(st.lists(st.sampled_from(_VERIFIED), min_size=1, max_size=2))
        skeptic = draw(st.sampled_from(["upheld", "skipped", "refuted", "uncertain", "not_run"]))
        failed = skeptic == "not_run"
        cand = Candidate(id=f"c{i}", type="xref", origin="deterministic", quotes=quotes,
                         claim=draw(st.sampled_from(["a", "should be b", "c"])), readings=None,
                         payload={"status": "missing"})
        verdict = Verdict(candidate_id=cand.id, quote_failures=["f"] if failed else [],
                          skeptic=skeptic, skeptic_reasoning=None, reconciling_quotes=[],
                          sections_retrieved=[])
        out.append((cand, verdict))
    return out


def _signature(fs):
    return sorted((f.id, f.confidence, tuple(sorted(f.candidate_ids))) for f in fs)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pairs=_pairs(), perm=st.randoms())
def test_property3_dedupe_order_independent_and_idempotent(tmp_path, pairs, perm):
    rd: Path = tmp_path / "runs" / "r"
    base = _signature(findings.build(pairs, "r1", rd))

    shuffled = pairs[:]
    perm.shuffle(shuffled)
    assert _signature(findings.build(shuffled, "r1", rd)) == base          # order-independent

    assert _signature(findings.build(pairs + pairs, "r1", rd)) == base     # idempotent under dup
    # Candidate collapsing: a duplicated candidate adds its id, never a second finding.
    for f in findings.build(pairs + pairs, "r1", rd):
        assert len(f.candidate_ids) == len(set(f.candidate_ids))


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pairs=_pairs())
def test_property4_funnel_is_monotone_and_rebuilt_from_trace(tmp_path, pairs):
    rd: Path = tmp_path / "runs" / "r"
    findings.build(pairs, "r1", rd)
    f = findings.funnel(rd)
    for counts in f.values():
        assert counts["reported"] <= counts["upheld"] <= counts["quote_passed"] <= counts["candidates"]
    if pairs:
        assert f["xref"]["candidates"] == len({c.id for c, _ in pairs})
    # Rebuilding from the same trace file is stable (trace is the single source of truth).
    assert findings.funnel(rd) == f


def test_build_is_idempotent_on_trace_lines(run_dir):
    import json

    def stable(path: Path):
        return [{k: r[k] for k in ("run_id", "candidate_id", "stage", "data")}
                for r in (json.loads(ln) for ln in path.read_text().splitlines() if ln.strip())]

    cand = _xref("self_mismatch")
    pair = (cand, skipped_verdict(cand))
    findings.build([pair], "r1", run_dir)
    first = stable(run_dir / "trace.jsonl")
    findings.build([pair], "r1", run_dir)
    # Rerunning the same run_id replaces its lines, never doubles them (only `at` differs).
    assert stable(run_dir / "trace.jsonl") == first
