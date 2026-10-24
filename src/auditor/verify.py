from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from auditor import find_xrefs
from auditor.agents import AgentFailure, run_agent
from auditor.corpus import Corpus
from auditor.models import Candidate, Quote, Rule, TextQuote, Verdict
from auditor.quotes import QuoteError, verify_cell, verify_text

_SKEPTIC_ROLE = {"contradiction": "skeptic_contradiction", "xref": "skeptic_xref",
                 "ambiguity": "skeptic_ambiguity", "trip": "skeptic_contradiction"}


class _ReconcilingQuote(BaseModel):
    section_id: str
    text: str


class SkepticOut(BaseModel):
    verdict: Literal["upheld", "refuted", "uncertain"]
    reasoning: str
    reconciling_quotes: list[_ReconcilingQuote] = []
    sections_retrieved: list[str] = []


def _gate(quotes: list[Quote], corpus: Corpus) -> tuple[list[Quote], list[str]]:
    checked = [verify_text(q, corpus) if isinstance(q, TextQuote) else verify_cell(q, corpus)
               for q in quotes]
    verified = [q for q in checked if not isinstance(q, QuoteError)]
    failures = [q.reason for q in checked if isinstance(q, QuoteError)]
    return verified, failures


def verify(candidate: Candidate, corpus: Corpus, *, build_dir: Path,
           run_dir: Path) -> tuple[Candidate, Verdict]:
    """Verify a candidate. Returns the candidate with its quotes verified in place, and a
    Verdict. The quote gate runs in code first; only a candidate that clears it, and does
    not skip the skeptic by rule, costs a model call."""
    verified, failures = _gate(candidate.quotes, corpus)
    if failures:
        return candidate, Verdict(candidate_id=candidate.id, quote_failures=failures,
                                  skeptic="not_run", skeptic_reasoning=None,
                                  reconciling_quotes=[], sections_retrieved=[])
    candidate = candidate.model_copy(update={"quotes": verified})

    if candidate.type == "xref" and candidate.payload.get("status") in find_xrefs._SKIP_SKEPTIC:
        return candidate, find_xrefs.skipped_verdict(candidate)

    out = run_agent(_SKEPTIC_ROLE[candidate.type], _skeptic_task(candidate), SkepticOut,
                    build_dir=build_dir, run_dir=run_dir)
    if isinstance(out, AgentFailure):
        return candidate, Verdict(candidate_id=candidate.id, quote_failures=[], skeptic="uncertain",
                                  skeptic_reasoning=out.reason, reconciling_quotes=[],
                                  sections_retrieved=[])

    reconciling, _ = _gate(
        [TextQuote(section_id=r.section_id, text=r.text) for r in out.reconciling_quotes], corpus)
    skeptic = out.verdict
    if skeptic == "refuted" and not reconciling:
        # Requirement 8.3: the skeptic must show its quotes to refute.
        skeptic = "uncertain"
    return candidate, Verdict(candidate_id=candidate.id, quote_failures=[], skeptic=skeptic,
                              skeptic_reasoning=out.reasoning, reconciling_quotes=reconciling,
                              sections_retrieved=out.sections_retrieved)


def _skeptic_task(candidate: Candidate) -> str:
    quotes = "\n".join(f"- [{q.section_id if isinstance(q, TextQuote) else q.table_id}] {q.text!r}"
                       for q in candidate.quotes)
    lines = [f"Candidate type: {candidate.type}", f"Claim: {candidate.claim}", "Quotes:", quotes]
    if candidate.readings is not None:
        lines += [f"Reading A: {candidate.readings[0]}", f"Reading B: {candidate.readings[1]}"]
    return "\n".join(lines)


# Design §6.4: needs_review forces low; deterministic or (c)(d)-upheld xrefs are high; trips low; else medium.
def confidence(candidate: Candidate, verdict: Verdict,
               rules_by_id: dict[str, Rule]) -> Literal["high", "medium", "low"]:
    status = candidate.payload.get("status")
    if any(rules_by_id[r].needs_review for r in candidate.payload.get("rule_ids", []) if r in rules_by_id):
        return "low"
    if candidate.type == "trip":
        return "low"
    if candidate.type == "xref" and verdict.skeptic == "skipped":
        return "high"
    if candidate.type == "xref" and verdict.skeptic == "upheld" and status in ("cross_article_shadow", "title_mismatch"):
        return "high"
    return "medium"
