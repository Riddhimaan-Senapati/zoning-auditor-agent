from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum, auto
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, computed_field, model_validator

# Article is digits plus optional capitals ("53", "80B"); then either a dotted section
# number ("29.4", "3.1a") or a colon path ("TableH", "TableH:fn3"). No "_" and no empty
# segments, which is what keeps ids.slug reversible.
SECTION_ID = re.compile(
    r"^\d+[A-Z]*(?:-[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*|:[A-Za-z0-9]+(?::[A-Za-z0-9]+)*)?$"
)


def _section_id(s: str) -> str:
    if not SECTION_ID.match(s):
        raise ValueError(f"not a canonical section id: {s!r}")
    return s


SectionId = Annotated[str, AfterValidator(_section_id)]  # "53-29.4", "53:TableH:fn3"
DistrictCode = str  # "EBR-3", "2F-3000"


class SourceRef(BaseModel):
    file: str
    anchor: str  # HTML id or PDF page


class Section(BaseModel):
    id: SectionId
    article: str
    heading: str
    text: str
    parent: SectionId | None
    kind: Literal["article", "section", "subsection", "table_footnote", "table_note"]
    source: SourceRef


class Cell(BaseModel):
    text: str
    footnote_marks: list[str]  # "(4)" -> ["4"]


class TableRow(BaseModel):
    label: str  # row-header path, e.g. "EBR-3 / Corner Lot"
    cells: list[Cell]


class Table(BaseModel):
    id: SectionId
    article: str
    title: str
    columns: list[str]  # full header path joined, e.g. "Building Height Maximum | Feet"
    rows: list[TableRow]
    footnotes: dict[str, SectionId]  # "3" -> "53:TableH:fn3"
    applicable_footnotes: list[str]  # from "Applicable Footnotes: (1), (5)"
    source: SourceRef

    @model_validator(mode="after")
    def _rectangular_and_unique(self) -> Table:
        if len(set(self.columns)) != len(self.columns):
            raise ValueError(f"{self.id}: duplicate column headers")
        labels = [r.label for r in self.rows]
        if len(set(labels)) != len(labels):
            raise ValueError(f"{self.id}: duplicate row labels")
        if any(len(r.cells) != len(self.columns) for r in self.rows):
            raise ValueError(f"{self.id}: every row needs one cell per column")
        return self


class TextQuote(BaseModel):
    kind: Literal["text"] = "text"
    section_id: SectionId
    text: str
    span: tuple[int, int] | None = None  # offsets into Section.text; set only by verify_text

    @model_validator(mode="after")
    def _ordered_span(self) -> TextQuote:
        if self.span is not None and not 0 <= self.span[0] < self.span[1]:
            raise ValueError(f"bad span {self.span}")
        return self


class CellQuote(BaseModel):
    kind: Literal["cell"] = "cell"
    table_id: SectionId
    row_label: str
    column: str
    text: str
    position: tuple[int, int] | None = None  # (row, column) index; set only by verify_cell


Quote = Annotated[TextQuote | CellQuote, Field(discriminator="kind")]


def is_verified(q: TextQuote | CellQuote) -> bool:
    return (q.span if isinstance(q, TextQuote) else q.position) is not None


class RegulatedItem(StrEnum):
    use_permission = auto()
    building_height_ft = auto()
    building_height_stories = auto()
    far = auto()
    lot_area_min = auto()
    lot_area_per_unit = auto()
    lot_width_min = auto()
    lot_frontage_min = auto()
    front_yard_min = auto()
    side_yard_min = auto()
    rear_yard_min = auto()
    rear_yard_occupancy_max = auto()
    usable_open_space_min = auto()
    lot_coverage_max = auto()
    parking_ratio = auto()
    loading = auto()
    dwelling_units_max = auto()
    other = auto()


Unit = Literal[
    "ft", "stories", "sqft", "ratio", "percent", "spaces_per_unit",
    "spaces_per_1000sqft", "units", "units_per_acre",
]


class Rule(BaseModel):
    id: str  # stable hash of (quote, district, use, item)
    district: DistrictCode | None  # None = article-wide
    use: str | None  # use or dwelling type as written in the code
    item: RegulatedItem
    comparator: Literal["max", "min", "exact", "status"]
    value: Decimal | None
    unit: Unit | None
    status: Literal["A", "C", "F"] | None  # use tables: allowed / conditional / forbidden
    conditions: list[str]  # verbatim condition fragments
    footnotes: list[SectionId]
    quote: Quote
    source: Literal["table", "prose"]
    review_reason: str | None

    @computed_field
    @property
    def needs_review(self) -> bool:
        return self.review_reason is not None

    @model_validator(mode="after")
    def _consistent(self) -> Rule:
        if self.comparator == "status":
            if self.status is None or self.value is not None or self.unit is not None:
                raise ValueError("status comparator requires status, and no value or unit")
        elif self.status is not None:
            raise ValueError("numeric comparator takes no status")
        elif self.review_reason is None and (self.value is None or self.unit is None):
            raise ValueError("numeric rule without value and unit must carry a review_reason")
        if self.item is RegulatedItem.other and self.review_reason is None:
            raise ValueError("item 'other' must carry a review_reason")
        if not is_verified(self.quote):
            raise ValueError("no quote, no record: the rule's quote must be verified")
        return self


class Resolution(BaseModel):
    status: Literal[
        "ok", "missing", "title_mismatch", "self_mismatch", "cross_article_shadow",
        "undefined_district", "footnote_missing", "footnote_unused", "external_unchecked",
        "needs_judgment",
    ]
    resolved_id: SectionId | None
    title_match_id: SectionId | None  # a section whose heading matches cited_title
    detail: str  # code-generated, factual


class XRef(BaseModel):
    id: str
    source_id: SectionId
    raw: str  # "Section 53-8.4"
    span: tuple[int, int]
    target_kind: Literal[
        "section", "section_range", "table", "footnote", "article",
        "district", "agency", "self_section", "self_table",
    ]
    target: str
    cited_title: str | None  # text of the trailing parenthetical, if any
    resolution: Resolution


IssueType = Literal["contradiction", "xref", "ambiguity", "trip"]
Origin = Literal["deterministic", "structured", "model_finder"]


def _readings_iff_ambiguity(type: IssueType, readings: tuple[str, str] | None) -> None:
    if (type == "ambiguity") != (readings is not None):
        raise ValueError("readings are required for ambiguities and only for them")


class Candidate(BaseModel):
    id: str
    type: IssueType
    origin: Origin
    quotes: list[Quote]  # unverified as proposed
    claim: str  # one neutral sentence
    readings: tuple[str, str] | None
    payload: dict  # type-specific (xref id, rule ids, stats)

    @model_validator(mode="after")
    def _readings(self) -> Candidate:
        _readings_iff_ambiguity(self.type, self.readings)
        return self


class Verdict(BaseModel):
    candidate_id: str
    quote_failures: list[str]
    # not_run: the quote gate failed, so no skeptic was asked.
    # skipped: deterministic xref statuses that skip the skeptic by rule (design §6.3).
    skeptic: Literal["upheld", "refuted", "uncertain", "skipped", "not_run"]
    skeptic_reasoning: str | None
    reconciling_quotes: list[Quote]
    sections_retrieved: list[SectionId]

    @model_validator(mode="after")
    def _consistent(self) -> Verdict:
        if bool(self.quote_failures) != (self.skeptic == "not_run"):
            raise ValueError("skeptic is not_run exactly when the quote gate failed")
        if not all(is_verified(q) for q in self.reconciling_quotes):
            raise ValueError("reconciling quotes must be verified")
        return self


class Finding(BaseModel):
    id: str  # dedupe key hash
    type: IssueType
    origin: Origin
    quotes: list[Quote]
    claim: str
    readings: tuple[str, str] | None
    confidence: Literal["high", "medium", "low"]
    candidate_ids: list[str]  # merged duplicates
    verdict: Verdict
    neutrality_flags: list[str]

    @model_validator(mode="after")
    def _reportable(self) -> Finding:
        if not self.quotes or not all(is_verified(q) for q in self.quotes):
            raise ValueError("no quote, no flag: a Finding needs at least one verified quote")
        if self.verdict.skeptic not in ("upheld", "skipped"):
            raise ValueError(f"a {self.verdict.skeptic} candidate is not reportable")
        _readings_iff_ambiguity(self.type, self.readings)
        return self


class TraceEvent(BaseModel):  # one line per stage transition in trace.jsonl
    run_id: str
    candidate_id: str
    stage: str
    at: datetime
    data: dict  # prompts hash, tool calls, model output, reasons
