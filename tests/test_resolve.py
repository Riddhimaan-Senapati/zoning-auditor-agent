from __future__ import annotations

from auditor.corpus import Corpus
from auditor.models import Cell, Section, SourceRef, Table, TableRow
from auditor.resolve import resolve_corpus

J_FN1 = ("Notwithstanding any contrary provision of this Table J, the provisions of Sections 53-6 "
         "through 53-8 (concerning regulations applicable on Tidelands) apply to any Lot located on "
         "Tidelands subject to Chapter 91 of the Massachusetts General Laws.")
K_FN1 = J_FN1.replace("this Table J", "this Table I")
TIDELANDS = [
    ("53-6", "Height and Setback Controls"),
    ("53-7", "Floor Area Ratios"),
    ("53-8", "Regulations Applicable on Tidelands and in Waterfront Subdistricts"),
    ("53-9", "Regulations Applicable on Filled Tidelands"),
    ("53-10", "Regulations Applicable on Flowed Tidelands"),
]


def _sec(id: str, heading: str = "h", text: str = "x", parent: str | None = None) -> Section:
    article = id.split("-")[0].split(":")[0]
    return Section(id=id, article=article, heading=heading, text=text, parent=parent or article,
                   kind="section", source=SourceRef(file="f", anchor="a"))


def _table(id: str, columns: list[str], rows: list[tuple[str, list[tuple[str, list[str]]]]],
           footnotes: dict[str, str] | None = None, applicable: list[str] | None = None,
           title: str = "Table") -> Table:
    return Table(id=id, article=id.split(":")[0], title=title, columns=columns,
                 rows=[TableRow(label=label, cells=[Cell(text=t, footnote_marks=m) for t, m in cells])
                       for label, cells in rows],
                 footnotes=footnotes or {}, applicable_footnotes=applicable or [],
                 source=SourceRef(file="f", anchor="a"))


def _run(sections, tables=(), toc=None, established=None, table_sections=None,
         defined=frozenset(), use=(), articles=("53",)):
    corpus = Corpus(list(sections), list(tables))
    return resolve_corpus(corpus, toc or {}, articles=list(articles),
                          established=established or {a: set() for a in articles},
                          table_sections=table_sections or {t.id: "53-1" for t in tables},
                          defined_terms=set(defined), use_tables=list(use))


def _statuses(xrefs) -> list[tuple[str, str]]:
    return [(x.quote.text, x.resolution.status) for x in xrefs]


def test_toc_targets_resolve_against_their_toc_heading():
    toc = {"80B-2": "Development Review Procedures"}
    cite = lambda text, toc: _statuses(_run([_sec("53-19", text=text)], toc=toc))  # noqa: E731
    assert cite("See Section 80B-2 for details.", toc) == [("Section 80B-2", "ok")]
    assert cite("See Section 80B-2 (Large Project Review).", toc) == [("Section 80B-2", "title_mismatch")]
    assert cite("See Section 80B-99 for details.", toc) == [("Section 80B-99", "missing")]
    assert cite("See Section 80B-99 for details.", {"80B": "Development Review"}) == [("Section 80B-99", "missing")]
    assert cite("See Section 80B-2 and Article 80B.", {}) == [
        ("Section 80B-2", "external_unchecked"), ("Article 80B", "external_unchecked")]
    assert cite("See Section 53-999 and Article 53.", {}) == [("Section 53-999", "missing"), ("Article 53", "ok")]


def test_title_mismatch_names_the_section_whose_heading_matches():
    (x,) = _run([_sec("53-8", "Regulations Applicable on Tidelands"),
                 _sec("53-10.4", "Waterfront Yard Area Requirements"),
                 _sec("53-29.4", text="lots shall meet Section 53-8 (Waterfront Yard Area Requirements).")])
    assert x.resolution.model_dump() == {
        "status": "title_mismatch", "resolved_id": "53-8", "title_match_id": "53-10.4",
        "detail": 'Section 53-29.4 cites Section 53-8 as "Waterfront Yard Area Requirements", but '
                  'Section 53-8 is titled "Regulations Applicable on Tidelands". Section 53-10.4 is '
                  'titled "Waterfront Yard Area Requirements".'}


def test_lowercase_tidelands_ranges_on_tables_j_and_k_are_stale_after_renumbering():
    sections = [_sec(id, heading) for id, heading in TIDELANDS] + [
        _sec("53:TableJ:fn1", text=J_FN1, parent="53:TableJ"),
        _sec("53:TableK:fn1", text=K_FN1, parent="53:TableK"),
        _sec("53:TableL:fn1", text=J_FN1.replace("53-6 through 53-8", "53-8 through 53-10")
             .replace("this Table J", "this Table L"), parent="53:TableL")]
    xrefs = _run(sections)
    assert _statuses(xrefs) == [
        ("this Table J", "ok"), ("Sections 53-6 through 53-8", "title_mismatch"),
        ("this Table I", "self_mismatch"), ("Sections 53-6 through 53-8", "title_mismatch"),
        ("this Table L", "ok"), ("Sections 53-8 through 53-10", "ok")]
    assert xrefs[1].resolution.detail == (
        'Table J footnote 1 cites Sections 53-6 through 53-8 as "concerning regulations applicable on '
        'Tidelands", but Section 53-6 in that range is titled "Height and Setback Controls". Section 53-9 '
        'is titled "Regulations Applicable on Filled Tidelands".')
    assert xrefs[2].resolution.detail == 'Table K footnote 1 says "this Table I", but it sits in Table K.'


def test_range_with_an_absent_endpoint_is_missing():
    assert _statuses(_run([_sec("53-6"), _sec("53-1", text="Sections 53-6 through 53-99 apply.")])) == [
        ("Sections 53-6 through 53-99", "missing")]


def test_self_section_reference_must_name_the_section_or_an_ancestor():
    assert _statuses(_run([_sec("53-27"), _sec("53-29"), _sec("53-29.4", parent="53-29",
                                                               text="this Section 53-27 and this Section 53-29")])) == [
        ("this Section 53-27", "self_mismatch"), ("this Section 53-29", "ok")]


def test_scoped_table_and_missing_table():
    table = _table("53:Table2", ["Use"], [("Dwelling", [("Dwelling", [])])])
    xrefs = _run([_sec("53-1", text="Table 2 in Section 53-19, Table 2 in Section 53-21, and Table Q.")],
                 [table], table_sections={"53:Table2": "53-21"})
    assert _statuses(xrefs) == [("Table 2 in Section 53-19", "scope_mismatch"),
                                ("Table 2 in Section 53-21", "ok"), ("Table Q", "missing")]
    assert xrefs[0].resolution.detail == (
        "Section 53-1 cites Table 2 in Section 53-19, but Table 2 is under Section 53-21.")


def test_districts_must_be_established():
    assert _statuses(_run([_sec("53-1", text="EBR-1 and EBR-3 lots")], established={"53": {"EBR-3"}})) == [
        ("EBR-1", "undefined_district"), ("EBR-3", "ok"), ("EBR-3", "district_without_row")]


def test_footnote_marks_and_unused_footnotes_are_scoped_to_their_table():
    h = _table("53:TableH", ["Subdistrict", "Height (2)", "Lot Area (7)"],
               [("EBR-3", [("EBR-3", []), ("40", ["1"]), ("4000", ["5"])])],
               footnotes={"1": "53:TableH:fn1", "2": "53:TableH:fn2"})
    i = _table("53:TableI", ["Subdistrict", "Height"], [("EBR-3", [("EBR-3", []), ("35", [])])],
               footnotes={"1": "53:TableI:fn1", "4": "53:TableI:fn4"}, applicable=["4"])
    fns = [_sec(id, text=f"{id} text", parent=id.rsplit(":", 1)[0])
           for id in ("53:TableH:fn1", "53:TableH:fn2", "53:TableI:fn1", "53:TableI:fn4")]
    xrefs = _run(fns, [h, i])
    assert [(x.quote.model_dump().get("column"), x.quote.text, x.resolution.status) for x in xrefs] == [
        ("Height (2)", "40", "ok"),
        ("Lot Area (7)", "4000", "footnote_missing"),
        ("Height (2)", "40", "ok"),
        ("Lot Area (7)", "4000", "footnote_missing"),
        (None, "53:TableI:fn1 text", "footnote_unused"),
    ]
    assert [x.resolution.detail for x in xrefs if x.resolution.status != "ok"] == [
        'Row "EBR-3", column "Lot Area (7)" of Table H carries footnote mark (5), and Table H has no footnote 5.',
        'Column header "Lot Area (7)" of Table H carries footnote mark (7), and Table H has no footnote 7.',
        "Table I footnote 1 is not referenced by any cell, column header, or Applicable Footnotes line of Table I.",
    ]


def test_definition_mismatch_and_its_control():
    xrefs = _run([_sec("53-4", text='East Boston Residential-3 ("EBR-3") Subdistricts. EBR-2 Subdistricts '
                                    'allow three. East Boston Residential-4 (“EBR-4”) Subdistricts. EBR-4 '
                                    'Subdistricts allow four.')])
    assert _statuses(xrefs) == [('("EBR-3") Subdistricts. EBR-2', "definition_mismatch"),
                                ("(“EBR-4”) Subdistricts. EBR-4", "ok")]
    assert xrefs[0].resolution.detail == (
        "Section 53-4 defines EBR-3, but the paragraph that follows regulates EBR-2.")


def test_definition_mismatch_also_reads_district_headings():
    xrefs = _run([_sec("26-2", text='Squares + Streets 2 ("S2") Districts. S1 Districts allow mixed use.')],
                 articles=("26",))
    assert _statuses(xrefs) == [('("S2") Districts. S1', "definition_mismatch")]


def test_use_table_rows_must_be_defined_terms():
    a = _table("53:TableA", ["Use", "EBR-3"], [("Accessory Family Child Care Home", [("Accessory Family Child Care Home", []), ("C", [])]),
                                               ("Accessory Family Day Care Home", [("Accessory Family Day Care Home", []), ("C", [])])])
    assert _statuses(_run([_sec("53-1")], [a], defined={"Accessory Family Child Care Home"}, use=["53:TableA"])) == [
        ("Accessory Family Child Care Home", "ok"), ("Accessory Family Day Care Home", "undefined_term")]


def test_established_district_without_a_dimensional_row():
    dim = _table("65:TableC", ["Subdistrict", "Lot Area"], [("2F-5000", [("2F-5000", []), ("5000", [])])],
                 title="Table C: Dimensional Regulations")
    use = _table("65:TableA", ["Use", "2F-3000"], [("2F-3000", [("2F-3000", []), ("A", [])])],
                 title="Table A: Use Regulations")
    xrefs = _run([_sec("65-4", text="Subdistricts 2F-3000 and 2F-5000 are established.")], [dim, use],
                 established={"65": {"2F-3000", "2F-5000"}}, table_sections={"65:TableC": "65-9", "65:TableA": "65-8"},
                 articles=("65",))
    assert [x.resolution.status for x in xrefs] == ["ok", "ok", "district_without_row", "ok"]
    assert xrefs[2].resolution.detail == (
        "District 2F-3000 is established in Article 65, but no dimensional table of Article 65 has a row for it.")


def test_cross_article_shadow_from_article_68():
    xrefs = _run([_sec("68-10", text="Parking shall meet Section 67-32 (Off-Street Parking and Loading Requirements)."),
                  _sec("68-33", "Off-Street Parking and Loading Requirements")],
                 toc={"67-32": "General Dimensional Regulations"}, articles=("68",))
    assert [(x.resolution.status, x.resolution.title_match_id) for x in xrefs] == [("cross_article_shadow", "68-33")]


def test_ligature_in_a_heading_matches_the_cited_title():
    assert _statuses(_run([_sec("53-19", "O\ufb00-Street Parking Requirements"),
                           _sec("53-20", text="per Section 53-19 (Off-Street Parking Requirements).")])) == [
        ("Section 53-19", "ok")]
