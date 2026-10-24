from __future__ import annotations

import re
from decimal import Decimal

from auditor.corpus import Corpus
from auditor.ids import rule_id
from auditor.models import CellQuote, RegulatedItem, Rule, Table, TableRow
from auditor.quotes import QuoteError, normalize, verify_cell

# Keys are headers after _norm_header. Built from the real Article 65 Table C headers
# (redline pp. 39-45) and the Article 53 Table H-M vocabulary.
COLUMN_ITEMS = {
    "lot area, minimum for dwell. unit s specified sq. ft.": (RegulatedItem.lot_area_min, "min", "sqft"),
    "additional lot area for ea. addt'l dwell. unit sq. ft.": (RegulatedItem.lot_area_per_unit, "min", "sqft"),
    "lot width minimum feet": (RegulatedItem.lot_width_min, "min", "ft"),
    "lot frontage minimum feet": (RegulatedItem.lot_frontage_min, "min", "ft"),
    "floor area ratio maximum": (RegulatedItem.far, "max", "ratio"),
    "maximum floor area ratio": (RegulatedItem.far, "max", "ratio"),
    "usable open space minimum sq. ft. per dwelling unit": (RegulatedItem.usable_open_space_min, "min", "sqft"),
    "front yard minimum depth feet": (RegulatedItem.front_yard_min, "min", "ft"),
    "side yard minimum width feet": (RegulatedItem.side_yard_min, "min", "ft"),
    "rear yard minimum depth feet": (RegulatedItem.rear_yard_min, "min", "ft"),
    "rear yard maximum occupancy by accessory building percent": (
        RegulatedItem.rear_yard_occupancy_max, "max", "percent"),
    "building height maximum stories": (RegulatedItem.building_height_stories, "max", "stories"),
    "building height maximum feet": (RegulatedItem.building_height_ft, "max", "ft"),
    "minimum lot area square feet": (RegulatedItem.lot_area_min, "min", "sqft"),
}

_STATUS = {"a": "A", "c": "C", "f": "F"}
_NO_REQUIREMENT = {"n/a", "none"}
_FOOTNOTE_MARK = re.compile(r"\(\s*\d+\s*\)")
_NUMBER = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)?\s*(?:(\d+)\u2044([1-9]\d*))?")


def _norm_header(header: str) -> str:
    stripped = _FOOTNOTE_MARK.sub(" ", normalize(header))
    return normalize(re.sub(r"[|()]", " ", stripped)).casefold()


def _parse_number(raw: str) -> Decimal | None:
    m = _NUMBER.fullmatch(normalize(raw))
    if m is None or not any(m.groups()):
        return None
    whole, num, den = m.groups()
    value = Decimal(whole.replace(",", "")) if whole else Decimal(0)
    return value + Decimal(num) / Decimal(den) if num else value


def _cell_rule(table: Table, corpus: Corpus, row: TableRow, col: int, district: str | None,
               use: str | None, **fields) -> Rule:
    cell = row.cells[col]
    q = verify_cell(CellQuote(table_id=table.id, row_label=row.label, column=table.columns[col],
                              text=cell.text), corpus)
    if isinstance(q, QuoteError):
        raise ValueError(f"cell quote failed for {table.id} [{row.label!r}, {table.columns[col]!r}]: {q.reason}")
    return Rule(id=rule_id(q, district, use, fields["item"]), district=district, use=use, quote=q,
                source="table", conditions=[],
                footnotes=[table.footnotes[m] for m in cell.footnote_marks if m in table.footnotes],
                **fields)


def _is_use_table(table: Table) -> bool:
    texts = {normalize(c.text).casefold() for r in table.rows for c in r.cells[1:]} - {""}
    return bool(texts) and texts <= _STATUS.keys()


def _use_rules(table: Table, corpus: Corpus) -> list[Rule]:
    return [
        _cell_rule(table, corpus, row, col, normalize(table.columns[col]) or None, normalize(row.label) or None,
                   item=RegulatedItem.use_permission, comparator="status", value=None, unit=None,
                   status=_STATUS[status], review_reason=None)
        for row in table.rows
        for col in range(1, len(table.columns))
        if (status := normalize(row.cells[col].text).casefold()) in _STATUS
    ]


def _dimensional_rules(table: Table, corpus: Corpus) -> list[Rule]:
    rules: list[Rule] = []
    for row in table.rows:
        if not any(normalize(c.text) for c in row.cells[1:]):
            continue
        district, _, use = (normalize(part) or None for part in row.label.partition("/"))
        for col in range(1, len(table.columns)):
            raw = row.cells[col].text
            mapped = COLUMN_ITEMS.get(_norm_header(table.columns[col]))
            if mapped is None:
                rules.append(_cell_rule(
                    table, corpus, row, col, district, use, item=RegulatedItem.other, comparator="exact",
                    value=None, unit=None, status=None,
                    review_reason=f"column header is not mapped to a regulated item: {table.columns[col]!r}"))
            elif normalize(raw).casefold() not in _NO_REQUIREMENT:
                item, comparator, unit = mapped
                value = _parse_number(raw)
                rules.append(_cell_rule(
                    table, corpus, row, col, district, use, item=item, comparator=comparator, value=value,
                    unit=unit if value is not None else None, status=None,
                    review_reason=None if value is not None else f"cell text does not parse as a number: {raw!r}"))
    return rules


def rules_from_table(table: Table, corpus: Corpus) -> list[Rule]:
    """Status rules for a use table (A/C/F cells), numeric rules per COLUMN_ITEMS otherwise."""
    return _use_rules(table, corpus) if _is_use_table(table) else _dimensional_rules(table, corpus)
