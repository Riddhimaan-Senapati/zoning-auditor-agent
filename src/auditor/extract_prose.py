from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from auditor.agents import AgentFailure, run_agent
from auditor.corpus import Corpus
from auditor.ids import rule_id
from auditor.models import RegulatedItem, Rule, Section, TextQuote, Unit
from auditor.quotes import QuoteError, normalize, verify_text

Comparator = Rule.model_fields["comparator"].annotation
Status = Rule.model_fields["status"].annotation

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class RuleDraft(BaseModel):
    """A Rule as the model proposes it: no id, and the quote as copied text only."""

    section_id: str
    quote_text: str
    district: str | None = None
    use: str | None = None
    item: RegulatedItem
    comparator: Comparator
    value: str | None = None
    unit: Unit | None = None
    status: Status = None
    conditions: list[str] = Field(default_factory=list)
    footnotes: list[str] = Field(default_factory=list)
    review_reason: str | None = None


class RuleDrafts(BaseModel):
    drafts: list[RuleDraft] = Field(default_factory=list)


class DroppedDraft(BaseModel):
    draft: RuleDraft
    reason: str


class Extraction(BaseModel):
    rules: list[Rule]
    dropped: list[DroppedDraft]


def _stated(value: str, quote: str) -> bool:
    try:
        wanted = Decimal(value)
    except InvalidOperation:
        return False
    return any(Decimal(n.replace(",", "")) == wanted for n in _NUMBER.findall(normalize(quote)))


def _rule(draft: RuleDraft, quote: TextQuote) -> Rule:
    value = draft.value or None
    reason = draft.review_reason or None
    if reason is None and value is not None and not _stated(value, quote.text):
        reason = f"value {value!r} is not stated in the quoted text"
    return Rule(
        id=rule_id(quote, draft.district or None, draft.use or None, draft.item),
        district=draft.district or None, use=draft.use or None, item=draft.item,
        comparator=draft.comparator, value=value, unit=draft.unit, status=draft.status,
        conditions=draft.conditions, footnotes=draft.footnotes, quote=quote, source="prose",
        review_reason=reason,
    )


def rules_from_section(section: Section, corpus: Corpus, *, build_dir: Path,
                       run_dir: Path) -> Extraction | AgentFailure:
    """Run extract_prose on one section; drafts whose quote or fields fail are dropped with why."""
    task = (
        f"Extract every dimensional or use rule stated in Section {section.id} "
        f'("{section.heading}"). Read the section with the tools. For each rule, copy the '
        "exact sentence that states it as the quote, and set review_reason naming any of "
        "value, unit, district, or condition that the quoted sentence does not itself state."
    )
    result = run_agent("extract_prose", task, RuleDrafts, build_dir=build_dir, run_dir=run_dir)
    if isinstance(result, AgentFailure):
        return result
    out = Extraction(rules=[], dropped=[])
    for draft in result.drafts:
        try:
            quote = verify_text(TextQuote(section_id=draft.section_id, text=draft.quote_text), corpus)
            if isinstance(quote, QuoteError):
                out.dropped.append(DroppedDraft(draft=draft, reason=f"no record: {quote.reason}"))
            else:
                out.rules.append(_rule(draft, quote))
        except ValidationError as e:
            out.dropped.append(DroppedDraft(draft=draft, reason=f"no record: {e}"))
    return out
