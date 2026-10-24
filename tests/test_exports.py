"""exports tests: the exact CSV header, the JSON top-level keys, and the verbatim
self-identification string that Req 1.2 pins."""

from __future__ import annotations

import csv
import json
from decimal import Decimal

from auditor.exports import SELF_IDENTIFICATION, write_rules
from auditor.models import CellQuote, RegulatedItem, Rule, TextQuote

EXPECTED_CSV_HEADER = [
    "id", "district", "use", "item", "comparator", "value", "unit", "status",
    "conditions", "footnotes", "needs_review", "review_reason", "quote_text",
    "section_table_id", "source_link",
]

_CELL = CellQuote(table_id="65:TableC", row_label="1F-5000 / 1 Family Detached",
                  column="Lot Area, Minimum for Dwell. Unit(s) Specified (Sq. Ft.)",
                  text="5,000", position=(1, 1))


def _dim_rule() -> Rule:
    return Rule(
        id="abc123", district="1F-5000", use="1 Family Detached",
        item=RegulatedItem.lot_area_min, comparator="min", value=Decimal("5000"),
        unit="sqft", status=None, conditions=[], footnotes=[], quote=_CELL,
        source="table", review_reason=None,
    )


def _review_rule() -> Rule:
    text_quote = TextQuote(section_id="53-1", text="hello", span=(0, 5))
    return Rule(
        id="def456", district=None, use=None, item=RegulatedItem.other,
        comparator="exact", value=None, unit=None, status=None, conditions=["corner lot"],
        footnotes=["53:TableH:fn3"], quote=text_quote, source="table",
        review_reason="column header is not mapped",
    )



def test_csv_header_is_exact(tmp_path):
    write_rules([_dim_rule()], tmp_path, {})
    with (tmp_path / "rules.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == EXPECTED_CSV_HEADER


def test_csv_one_row_per_rule_with_expected_values(tmp_path):
    links = {"65:TableC": "https://example.test/65#t-C"}
    write_rules([_dim_rule(), _review_rule()], tmp_path, links)
    with (tmp_path / "rules.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2

    dim = rows[0]
    assert dim["id"] == "abc123"
    assert dim["district"] == "1F-5000"
    assert dim["item"] == "lot_area_min"
    assert dim["value"] == "5000"
    assert dim["unit"] == "sqft"
    assert dim["needs_review"] == "false"
    assert dim["quote_text"] == "5,000"
    assert dim["section_table_id"] == "65:TableC"
    assert dim["source_link"] == "https://example.test/65#t-C"

    review = rows[1]
    assert review["item"] == "other"
    assert review["needs_review"] == "true"
    assert review["review_reason"] == "column header is not mapped"
    assert review["conditions"] == "corner lot"
    assert review["footnotes"] == "53:TableH:fn3"
    assert review["section_table_id"] == "53-1"
    assert review["source_link"] == ""  # no link supplied for 53-1


def test_json_top_level_keys_and_self_identification(tmp_path):
    write_rules([_dim_rule()], tmp_path, {})
    doc = json.loads((tmp_path / "rules.json").read_text(encoding="utf-8"))
    assert set(doc) == {"self_identification", "generated_at", "rules"}
    assert doc["self_identification"] == SELF_IDENTIFICATION
    assert isinstance(doc["generated_at"], str) and doc["generated_at"]
    assert len(doc["rules"]) == 1


def test_json_rule_carries_fields_and_source_link(tmp_path):
    links = {"65:TableC": "https://example.test/65#t-C"}
    write_rules([_dim_rule()], tmp_path, links)
    doc = json.loads((tmp_path / "rules.json").read_text(encoding="utf-8"))
    rule = doc["rules"][0]
    assert rule["id"] == "abc123"
    assert rule["item"] == "lot_area_min"
    assert rule["value"] == "5000"
    assert rule["needs_review"] is False
    assert rule["source_link"] == "https://example.test/65#t-C"
    assert rule["quote"]["kind"] == "cell"


def test_empty_rule_list_still_writes_both_files_with_header(tmp_path):
    write_rules([], tmp_path, {})
    with (tmp_path / "rules.csv").open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows == [EXPECTED_CSV_HEADER]
    doc = json.loads((tmp_path / "rules.json").read_text(encoding="utf-8"))
    assert doc["rules"] == []
    assert doc["self_identification"] == SELF_IDENTIFICATION
