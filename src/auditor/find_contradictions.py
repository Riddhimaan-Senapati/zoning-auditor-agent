from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from pydantic import BaseModel, Field

from auditor.agents import AgentFailure, run_agent
from auditor.exports import cited_id
from auditor.models import Candidate, Quote, Rule, Section, Table, TextQuote
from auditor.mcp_server import Tools
from auditor.search import build_search


def _jsonl(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


# A subdistrict variant ("Corner Lot") or a unit-count band ("3 or more units"): the two
# markers design §6.1 names for a disjoint-conditions pair, which code excludes.
_VARIANT = re.compile(r"\b(corner|mid-?block|interior|through|end)\b", re.IGNORECASE)
_BAND = re.compile(r"\b(\d+)\s*(?:or\s+(?:more|fewer)|\+|units?|dwelling)", re.IGNORECASE)

OBLIGATION = re.compile(r"\bshall\b|\bno\b[^.]*\bshall\b|\bmay not\b", re.IGNORECASE)


def _value(rule: Rule) -> str:
    return rule.status if rule.status is not None else ("none" if rule.value is None else str(rule.value))


def _markers(conditions: list[str]) -> set[str]:
    text = " ".join(conditions)
    return {m.group(0).lower() for m in _VARIANT.finditer(text)} | {m.group(1) for m in _BAND.finditer(text)}


def _disjoint(a: Rule, b: Rule) -> bool:
    """Both carry conditions whose variant or unit-band markers name different cases."""
    ma, mb = _markers(a.conditions), _markers(b.conditions)
    return bool(a.conditions and b.conditions and ma and mb and ma != mb and not (ma & mb))


def _candidate(a: Rule, b: Rule) -> Candidate:
    la, lb = cited_id(a.quote), cited_id(b.quote)
    key = a.item if a.district is None else f"{a.item} in {a.district}"
    claim = (f"{key} is stated as {_value(a)} at {la} and {_value(b)} at {lb}.")
    return Candidate(
        id=hashlib.sha256(f"contradiction|{min(a.id, b.id)}|{max(a.id, b.id)}".encode()).hexdigest()[:16],
        type="contradiction", origin="structured", quotes=[a.quote, b.quote], claim=claim,
        readings=None, payload={"rule_ids": sorted((a.id, b.id))},
    )


def structured_candidates(rules: list[Rule]) -> tuple[list[Candidate], list[tuple[Rule, Rule]]]:
    """Group by (district, use, item); each conflicting pair in a group becomes one
    contradiction Candidate, unless both rules' conditions are disjoint. Returns the
    candidates and the disjoint pairs that were excluded (logged, not silently dropped)."""
    groups: dict[tuple, list[Rule]] = defaultdict(list)
    for rule in rules:
        groups[(rule.district, rule.use, rule.item)].append(rule)
    candidates: list[Candidate] = []
    disjoint: list[tuple[Rule, Rule]] = []
    for group in groups.values():
        for a, b in combinations(group, 2):
            if _value(a) == _value(b):
                continue
            if _disjoint(a, b):
                disjoint.append((a, b))
            else:
                candidates.append(_candidate(a, b))
    return candidates, disjoint


class ProposedQuote(BaseModel):
    section_id: str
    text: str


class Proposed(BaseModel):
    quotes: list[ProposedQuote]
    claim: str


class Proposals(BaseModel):
    candidates: list[Proposed] = Field(default_factory=list, max_length=3)


def _neighbors(tools: Tools, section: Section) -> list[str]:
    related = tools.related_sections(section.id, k=4)
    if related:
        return related
    return [hit["id"] for hit in tools.search_sections(section.heading, k=4) if hit["id"] != section.id]


def model_candidates(sections: list[Section], rules: list[Rule], *, build_dir: Path,
                     run_dir: Path) -> tuple[list[Candidate], list[AgentFailure]]:
    """Each section that yields rules or carries an obligation word gets up to 4 neighbors
    via related_sections (search fallback); each unordered section set is examined once.
    The find_contradiction agent proposes 0-3 candidates whose quotes are left unverified."""
    run_dir.mkdir(parents=True, exist_ok=True)
    all_sections = [Section.model_validate_json(ln) for ln in _jsonl(build_dir / "sections.jsonl")]
    all_tables = [Table.model_validate_json(ln) for ln in _jsonl(build_dir / "tables.jsonl")]
    db = run_dir / "search.sqlite"
    if not db.exists():
        build_search(all_sections, db)
    tools = Tools(all_sections, all_tables, rules, db)
    has_rule = {cited_id(r.quote) for r in rules}
    seen: set[frozenset[str]] = set()
    candidates: list[Candidate] = []
    failures: list[AgentFailure] = []
    for section in sections:
        if section.id not in has_rule and not OBLIGATION.search(section.text):
            continue
        group = frozenset({section.id, *_neighbors(tools, section)})
        if len(group) < 2 or group in seen:
            continue
        seen.add(group)
        ids = sorted(group)
        task = ("Examine these sections for a contradiction: two provisions that cannot both "
                f"be followed. Sections: {', '.join(ids)}. Read each with the tools. Return 0-3 "
                "candidates, each with the exact quotes (section id and verbatim text) of both "
                "provisions and one neutral sentence naming the conflict.")
        result = run_agent("find_contradiction", task, Proposals, build_dir=build_dir, run_dir=run_dir)
        if isinstance(result, AgentFailure):
            failures.append(result)
            continue
        for i, proposed in enumerate(result.candidates):
            quotes: list[Quote] = [TextQuote(section_id=q.section_id, text=q.text) for q in proposed.quotes]
            candidates.append(Candidate(
                id=hashlib.sha256(f"model|{'|'.join(ids)}|{i}".encode()).hexdigest()[:16],
                type="contradiction", origin="model_finder", quotes=quotes, claim=proposed.claim,
                readings=None, payload={"sections": ids}))
    return candidates, failures
