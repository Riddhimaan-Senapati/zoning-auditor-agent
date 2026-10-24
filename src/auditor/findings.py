from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from auditor.models import Candidate, Finding, IssueType, Quote, Rule, TextQuote, TraceEvent, Verdict
from auditor.neutrality import flags
from auditor.quotes import normalize
from auditor.verify import confidence

_REPORTABLE = ("upheld", "skipped")


def _dedupe_key(type: IssueType, quotes: list[Quote]) -> str:
    parts = sorted({(q.section_id if isinstance(q, TextQuote) else q.table_id, normalize(q.text))
                    for q in quotes})
    return hashlib.sha256(json.dumps([type, parts], sort_keys=True).encode()).hexdigest()[:16]


def build(pairs: list[tuple[Candidate, Verdict]], run_id: str, run_dir: Path,
          rules_by_id: dict[str, Rule] | None = None) -> list[Finding]:
    """Build the deduplicated Findings for a run and (re)write this run's trace lines.

    Idempotency rule: a run owns its trace lines. build() drops every line whose run_id
    equals `run_id`, then appends this run's events, so rerunning on the same input
    converges to the same file and never doubles a run's lines. Findings are a pure
    function of the input, so a rerun yields the identical list."""
    rules_by_id = rules_by_id or {}
    events: list[TraceEvent] = []
    by_key: dict[str, Finding] = {}

    for candidate, verdict in sorted(pairs, key=lambda p: p[0].id):
        _trace(events, run_id, candidate.id, "proposed", {"type": candidate.type})
        passed = not verdict.quote_failures
        _trace(events, run_id, candidate.id, "quote_gate",
               {"passed": passed, "failures": verdict.quote_failures})
        _trace(events, run_id, candidate.id, "skeptic", {"verdict": verdict.skeptic})

        if verdict.skeptic not in _REPORTABLE:
            _trace(events, run_id, candidate.id, "not_reported", {"reason": verdict.skeptic})
            continue

        key = _dedupe_key(candidate.type, candidate.quotes)
        if key in by_key:
            prior = by_key[key]
            ids = prior.candidate_ids + ([candidate.id] if candidate.id not in prior.candidate_ids else [])
            by_key[key] = prior.model_copy(update={"candidate_ids": ids})
        else:
            by_key[key] = Finding(
                id=key, type=candidate.type, origin=candidate.origin, quotes=candidate.quotes,
                claim=candidate.claim, readings=candidate.readings,
                confidence=confidence(candidate, verdict, rules_by_id),
                candidate_ids=[candidate.id], verdict=verdict,
                neutrality_flags=flags(candidate.claim))
        _trace(events, run_id, candidate.id, "reported", {"finding_id": key})

    _write_trace(run_dir, run_id, events)
    return list(by_key.values())


def _trace(events: list[TraceEvent], run_id: str, candidate_id: str, stage: str, data: dict) -> None:
    events.append(TraceEvent(run_id=run_id, candidate_id=candidate_id, stage=stage,
                             at=datetime.now(timezone.utc), data=data))


def _write_trace(run_dir: Path, run_id: str, events: list[TraceEvent]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "trace.jsonl"
    kept = [ln for ln in path.read_text().splitlines() if ln.strip()
            and json.loads(ln).get("run_id") != run_id] if path.exists() else []
    kept += [e.model_dump_json() for e in events]
    path.write_text("\n".join(kept) + ("\n" if kept else ""))


def funnel(run_dir: Path) -> dict[str, dict[str, int]]:
    """Rebuild {type: {candidates, quote_passed, upheld, reported}} from trace.jsonl alone,
    so the report and the eval read the same numbers (design §6.5)."""
    path = run_dir / "trace.jsonl"
    rows = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()] if path.exists() else []
    by_cand: dict[str, dict] = {}
    for r in rows:
        slot = by_cand.setdefault(r["candidate_id"], {})
        stage, data = r["stage"], r["data"]
        if stage == "proposed":
            slot["type"] = data["type"]
        elif stage == "quote_gate":
            slot["quote_passed"] = data["passed"]
        elif stage == "skeptic":
            slot["upheld"] = data["verdict"] in _REPORTABLE
        elif stage == "reported":
            slot["reported"] = True
    out: dict[str, dict[str, int]] = {}
    for slot in by_cand.values():
        f = out.setdefault(slot.get("type", "unknown"),
                           {"candidates": 0, "quote_passed": 0, "upheld": 0, "reported": 0})
        f["candidates"] += 1
        for k in ("quote_passed", "upheld", "reported"):
            f[k] += int(slot.get(k, False))
    return out
