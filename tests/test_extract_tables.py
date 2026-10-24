"""extract_tables tests built on the real Article 65 Table C shape. Header strings are
copied from the April 2025 redline (pp. 39–45) and the row values are the redline's own
(1F-3000, 1F-5000, 1F-7000 of the One-Family subdistrict). Tests assert the exact rules
produced, so an extraction bug shows as a wrong literal, not a vague failure
(principle-test-behavior-not-implementation)."""

from __future__ import annotations

from decimal import Decimal

from auditor.corpus import Corpus
from auditor.extract_tables import rules_from_table
from auditor.models import Cell, RegulatedItem, SourceRef, Table, TableRow
from conftest import MINI53

# The 12 value-column headers of Article 65 Table C, verbatim from the redline, with the
# Building Height column already split into its Stories and Feet subcolumns as the table
# prints them. The leading "Subdistrict / Use" column is the row-header column.
TABLE_C_COLUMNS = [
    "Subdistrict / Use",
    "Lot Area, Minimum for Dwell. Unit(s) Specified (Sq. Ft.)",
    "Additional Lot Area for Ea. Addt\u2019l Dwell. Unit (Sq. Ft.)",
    "Lot Width Minimum (Feet)",
    "Lot Frontage Minimum (Feet)",
    "Floor Area Ratio Maximum",
    "Building Height Maximum Stories (1)",
    "Building Height Maximum Feet (1)",
    "Usable Open Space Minimum Sq. Ft. Per Dwelling Unit (2)",
    "Front Yard Minimum Depth (Feet) (3)",
    "Side Yard Minimum Width (Feet) (4)",
    "Rear Yard Minimum Depth (Feet)",
    "Rear Yard Maximum Occupancy by Accessory Building (Percent)",
]


def _row(label: str, values: list[str]) -> TableRow:
    head, _, use = label.partition(" / ")
    cells = [Cell(text=use or head, footnote_marks=[])]
    cells += [Cell(text=v, footnote_marks=[]) for v in values]
    return TableRow(label=label, cells=cells)


def _table_c(extra_rows: list[TableRow] | None = None) -> Table:
    rows = [
        # 1F-3000, 1 Family Detached: 3,000 / N/A / 40 / 40 / 0.5 / 2 ½ / 35 / 750 / 15 / 10 / 20 / 25
        _row("1F-3000 / 1 Family Detached",
             ["3,000", "N/A", "40", "40", "0.5", "2 \u00bd", "35", "750", "15", "10", "20", "25"]),
        # 1F-5000, 1 Family Detached: 5,000 / N/A / 40 / 40 / 0.5 / 2 ½ / 35 / 1250 / 15 / 10 / 20 / 25
        _row("1F-5000 / 1 Family Detached",
             ["5,000", "N/A", "40", "40", "0.5", "2 \u00bd", "35", "1250", "15", "10", "20", "25"]),
        # 1F-5000, Any other Dwelling or Use: usable open space is 'none' here.
        _row("1F-5000 / Any other Dwelling or Use",
             ["5,000", "N/A", "50", "50", "0.5", "2 \u00bd", "35", "none", "15", "10", "40", "25"]),
    ]
    rows += extra_rows or []
    return Table(
        id="65:TableC", article="65", title="Table C - Dorchester - Dimensional Regulations",
        columns=TABLE_C_COLUMNS, rows=rows, footnotes={}, applicable_footnotes=[],
        source=SourceRef(file="65.html", anchor="t-C"),
    )


def _corpus(table: Table) -> Corpus:
    return Corpus([], [table])


def _by(rules, district, use, item):
    out = [r for r in rules if r.district == district and r.use == use and r.item == item]
    assert len(out) == 1, f"expected exactly one rule for {district}/{use}/{item}, got {len(out)}"
    return out[0]


def test_one_family_detached_5000_produces_the_exact_dimensional_rules():
    table = _table_c()
    rules = rules_from_table(table, _corpus(table))
    d, u = "1F-5000", "1 Family Detached"

    lot_area = _by(rules, d, u, RegulatedItem.lot_area_min)
    assert (lot_area.value, lot_area.unit, lot_area.comparator) == (Decimal("5000"), "sqft", "min")
    assert lot_area.needs_review is False

    far = _by(rules, d, u, RegulatedItem.far)
    assert (far.value, far.unit, far.comparator) == (Decimal("0.5"), "ratio", "max")

    stories = _by(rules, d, u, RegulatedItem.building_height_stories)
    assert (stories.value, stories.unit, stories.comparator) == (Decimal("2.5"), "stories", "max")

    height_ft = _by(rules, d, u, RegulatedItem.building_height_ft)
    assert (height_ft.value, height_ft.unit) == (Decimal("35"), "ft")

    open_space = _by(rules, d, u, RegulatedItem.usable_open_space_min)
    assert (open_space.value, open_space.unit) == (Decimal("1250"), "sqft")

    occ = _by(rules, d, u, RegulatedItem.rear_yard_occupancy_max)
    assert (occ.value, occ.unit, occ.comparator) == (Decimal("25"), "percent", "max")


def test_na_and_none_cells_record_no_rule():
    table = _table_c()
    rules = rules_from_table(table, _corpus(table))
    # 'Additional Lot Area' is N/A for every 1-family row, so no lot_area_per_unit rule.
    assert not [r for r in rules if r.item == RegulatedItem.lot_area_per_unit]
    # 'Usable Open Space' is 'none' for the "Any other Dwelling or Use" row.
    assert not [
        r for r in rules
        if r.use == "Any other Dwelling or Use" and r.item == RegulatedItem.usable_open_space_min
    ]


def test_district_and_use_come_from_the_row_label():
    table = _table_c()
    rules = rules_from_table(table, _corpus(table))
    districts = {r.district for r in rules}
    uses = {r.use for r in rules}
    assert districts == {"1F-3000", "1F-5000"}
    assert uses == {"1 Family Detached", "Any other Dwelling or Use"}




def test_rule_quote_is_a_verified_cell_quote():
    table = _table_c()
    rules = rules_from_table(table, _corpus(table))
    r = _by(rules, "1F-5000", "1 Family Detached", RegulatedItem.lot_area_min)
    assert r.quote.kind == "cell"
    assert r.quote.table_id == "65:TableC"
    assert r.quote.position is not None  # set only by verify_cell
    assert r.quote.text == "5,000"




def test_non_numeric_cell_gets_a_review_reason_and_no_value():
    bad = _row("1F-9000 / 1 Family Detached",
               ["see note", "N/A", "40", "40", "0.5", "2 \u00bd", "35", "750", "15", "10", "20", "25"])
    table = _table_c(extra_rows=[bad])
    rules = rules_from_table(table, _corpus(table))
    r = _by(rules, "1F-9000", "1 Family Detached", RegulatedItem.lot_area_min)
    assert r.value is None
    assert r.unit is None
    assert r.needs_review is True
    assert "see note" in r.review_reason


def test_unknown_header_yields_item_other_with_a_review_reason():
    cols = TABLE_C_COLUMNS + ["Solar Access Minimum (Hours)"]
    rows = [
        TableRow(
            label="1F-5000 / 1 Family Detached",
            cells=[Cell(text="1 Family Detached", footnote_marks=[])]
            + [Cell(text=v, footnote_marks=[]) for v in
               ["5,000", "N/A", "40", "40", "0.5", "2 \u00bd", "35", "1250", "15", "10", "20", "25", "4"]],
        )
    ]
    table = Table(
        id="65:TableC", article="65", title="t", columns=cols, rows=rows,
        footnotes={}, applicable_footnotes=[], source=SourceRef(file="65.html", anchor="t-C"),
    )
    rules = rules_from_table(table, Corpus([], [table]))
    other = [r for r in rules if r.item == RegulatedItem.other]
    assert len(other) == 1
    assert other[0].review_reason is not None
    assert "Solar Access Minimum (Hours)" in other[0].review_reason


# --- Use table (A/C/F status rules) -----------------------------------------------------

def _use_table() -> Table:
    return Table(
        id="53:TableA", article="53", title="Table A: Use Regulations",
        columns=["Use", "EBR-3", "EBR-4"],
        rows=[
            TableRow(label="Single-family dwelling", cells=[
                Cell(text="Single-family dwelling", footnote_marks=[]),
                Cell(text="A", footnote_marks=[]), Cell(text="A", footnote_marks=[])]),
            TableRow(label="Accessory Child Care Home", cells=[
                Cell(text="Accessory Child Care Home", footnote_marks=[]),
                Cell(text="C", footnote_marks=["2"]), Cell(text="F", footnote_marks=[])]),
        ],
        footnotes={"2": "53:TableA:fn2"}, applicable_footnotes=["2"],
        source=SourceRef(file="53.html", anchor="t-A"),
    )


def test_use_table_produces_status_rules_with_district_from_the_column():
    table = _use_table()
    rules = rules_from_table(table, Corpus([], [table]))
    assert len(rules) == 4  # 2 uses x 2 districts

    sfd_ebr3 = _by(rules, "EBR-3", "Single-family dwelling", RegulatedItem.use_permission)
    assert sfd_ebr3.comparator == "status"
    assert sfd_ebr3.status == "A"
    assert sfd_ebr3.value is None and sfd_ebr3.unit is None

    childcare_ebr4 = _by(rules, "EBR-4", "Accessory Child Care Home", RegulatedItem.use_permission)
    assert childcare_ebr4.status == "F"

    childcare_ebr3 = _by(rules, "EBR-3", "Accessory Child Care Home", RegulatedItem.use_permission)
    assert childcare_ebr3.status == "C"
    assert childcare_ebr3.footnotes == ["53:TableA:fn2"]
    assert childcare_ebr3.quote.position is not None


def test_fixture_table_h_pipe_headers_map_to_items():
    corpus = Corpus.load(MINI53)
    rules = rules_from_table(corpus.table("53:TableH"), corpus)
    ebr3 = [(r.item, r.value, r.unit, r.footnotes) for r in rules if r.district == "EBR-3"]
    assert ebr3 == [
        (RegulatedItem.building_height_ft, Decimal("40"), "ft", ["53:TableH:fn3"]),
        (RegulatedItem.lot_area_min, Decimal("4000"), "sqft", []),
    ]


def test_cells_parse_only_plain_quantities():
    cells = {"A": "\u00bd", "B": "1e3", "C": "Infinity", "D": "NaN", "E": "2,500", "F": "1,0000"}
    table = Table(
        id="65:TableC", article="65", title="t", columns=["Subdistrict", "Building Height Maximum Feet"],
        rows=[TableRow(label=k, cells=[Cell(text=k, footnote_marks=[]), Cell(text=v, footnote_marks=[])])
              for k, v in cells.items()],
        footnotes={}, applicable_footnotes=[], source=SourceRef(file="65.html", anchor="t-C"),
    )
    rules = rules_from_table(table, Corpus([], [table]))
    assert {r.district: r.value for r in rules} == {
        "A": Decimal("0.5"), "B": None, "C": None, "D": None, "E": Decimal("2500"), "F": None}
