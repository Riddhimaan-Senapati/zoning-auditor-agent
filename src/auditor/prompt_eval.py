from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from auditor.agents import AgentFailure, spend
from auditor.corpus import Corpus
from auditor.extract_prose import Extraction, rules_from_section


@dataclass(frozen=True)
class Case:
    id: str
    inputs: dict
    expected: dict


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    passed: bool
    diff: str


_EXTRACT_FIELDS = ("item", "comparator", "value", "unit", "district")


def _decimal(v: object) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def score_extract_prose(case: Case, output: Extraction | AgentFailure) -> CaseScore:
    """Pass iff some produced rule matches the expected item, comparator, value, unit, district."""
    if isinstance(output, AgentFailure):
        return CaseScore(case.id, False, f"agent failed: {output.reason}")
    want = {f: case.expected.get(f) for f in _EXTRACT_FIELDS} | {"value": _decimal(case.expected.get("value"))}
    got = [{f: getattr(r, f) for f in _EXTRACT_FIELDS} for r in output.rules]
    if want in got:
        return CaseScore(case.id, True, "")
    return CaseScore(case.id, False, f"expected {want}, got {got or 'no rules'}")


def _extract_prose(case: Case, corpus: Corpus, build_dir: Path, run_dir: Path) -> CaseScore:
    section = corpus.section(case.inputs["section_ids"][0])
    return score_extract_prose(case, rules_from_section(section, corpus, build_dir=build_dir, run_dir=run_dir))


ROLES: dict[str, Callable[[Case, Corpus, Path, Path], CaseScore]] = {"extract_prose": _extract_prose}


def run_prompt_eval(role: str, *, evals_dir: Path, build_dir: Path, run_dir: Path) -> str:
    """Score the role over evals/prompts/<role>.jsonl: "k of n", a line per failure, this run's spend."""
    if role not in ROLES:
        raise KeyError(f"no comparator for role {role!r}; known: {sorted(ROLES)}")
    path = evals_dir / "prompts" / f"{role}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"no case file for role {role!r} at {path}; draft it per evals/prompts/README.md")
    records = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
    cases = [Case(d["id"], d.get("inputs", {}), d.get("expected", {})) for d in records]
    corpus = Corpus.load(build_dir)
    for case in cases:
        if corpus.section(case.inputs["section_ids"][0]) is None:
            raise ValueError(f"case {case.id} names a section absent from {build_dir}")
    ledger = [run_dir / "spend.jsonl"]
    before = spend(ledger)
    scores = [ROLES[role](case, corpus, build_dir, run_dir) for case in cases]
    lines = [f"{sum(s.passed for s in scores)} of {len(scores)}"]
    lines += [f"  FAIL {s.case_id}: {s.diff}" for s in scores if not s.passed]
    lines.append(f"spend: ${spend(ledger) - before}")
    return "\n".join(lines)
