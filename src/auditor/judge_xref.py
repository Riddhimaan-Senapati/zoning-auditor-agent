from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from pydantic import BaseModel

from auditor.agents import AgentFailure, run_agent
from auditor.models import Candidate, Resolution, Section, TextQuote, XRef
from auditor.quotes import normalize

RENAMES = Path(__file__).resolve().parents[2] / "data" / "agency_renames.csv"


class Rename(BaseModel):
    old_name: str
    current_name: str
    citation_url: str
    note: str


def load_renames(path: Path = RENAMES) -> list[Rename]:
    with path.open(encoding="utf-8") as f:
        return [Rename.model_validate(row) for row in csv.DictReader(f)]


def agency_xrefs(section: Section, renames: list[Rename]) -> list[XRef]:
    """Every occurrence of a listed old agency name in the section becomes one XRef with
    status needs_judgment, located by a verified quote over the matched span."""
    text = section.text
    out: list[XRef] = []
    for rename in renames:
        for m in re.finditer(re.escape(rename.old_name), text):
            quote = TextQuote(section_id=section.id, text=m.group(0), span=m.span())
            out.append(XRef(quote=quote, resolution=Resolution(
                status="needs_judgment",
                detail=(f'Section {section.id} names "{rename.old_name}"; the rename table lists '
                        f'"{rename.current_name}" as its current name.'),
                resolved_id=section.id)))
    return out


class Judgment(BaseModel):
    verdict: str  # "ok" or "broken"
    reason: str


def judge(xref: XRef, *, build_dir: Path, run_dir: Path) -> Candidate | None:
    """Run judge_xref over one needs_judgment agency reference. Returns a Candidate
    (origin model_finder) when the agent judges the reference broken, else None."""
    rows = load_renames()
    quote = xref.quote
    cited = "\n".join(f"- {r.old_name} -> {r.current_name} ({r.citation_url}); {r.note}" for r in rows)
    task = (f'Section {quote.section_id} contains the agency name "{quote.text}". Read the '
            "section with the tools. Decide whether, in this context, the name refers to a body "
            "that has since been renamed and so the reference is broken, or whether it is used "
            "correctly (for example in a historical or statutory citation) and so is ok. "
            f"Agency rename table:\n{cited}")
    result = run_agent("judge_xref", task, Judgment, build_dir=build_dir, run_dir=run_dir)
    if isinstance(result, AgentFailure) or normalize(result.verdict).casefold() != "broken":
        return None
    return Candidate(
        id=hashlib.sha256(f"xref|agency|{quote.model_dump_json()}".encode()).hexdigest()[:16],
        type="xref", origin="model_finder", quotes=[quote],
        claim=f"{xref.resolution.detail} {result.reason}", readings=None,
        payload={"status": "needs_judgment", "verdict": "broken"})
