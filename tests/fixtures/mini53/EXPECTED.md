# mini53 fixture — seeded errors

A tiny synthetic Article 53 (15 sections + 3 table-footnote sections, 3 tables) in the
`Section`/`Table` shape `Corpus` loads. Errors are modeled on the April 2025 Article 53
corrections (design §2); phrasing is short and synthetic, not copied from the real code.

Status values are the `Resolution.status` / finding dispositions in design §5.3 and §6.4.
`resolve.resolve_corpus` runs every check and `find_xrefs.candidates` turns each status
other than `ok` and `external_unchecked` into one deterministic candidate, located by a
verified quote, whose claim is the resolution's detail. `test_find_xrefs.py` asserts the
exact `(status, location, claim)` list below.

| # | Rule | Error | Location | Quote / cell | Expected status |
|---|------|-------|----------|--------------|-----------------|
| 1 | §5.3(d) | Stale cross-reference: `53-8` exists but is titled "Regulations Applicable on Tidelands"; the matching heading "Waterfront Yard Area Requirements" is at `53-10.4`. | `53-29.4` | "Section 53-8 (Waterfront Yard Area Requirements)" | `title_mismatch` (title_match_id = `53-10.4`) |
| 2 | §5.3(a) | Self-reference mismatch: "this Section 53-27" inside `53-29.4`, which is not 53-27 nor an ancestor. | `53-29.4` | "this Section 53-27" | `self_mismatch` |
| 3 | §5.3(e) | Undefined district code: body says "EBR-1", which `53-4` does not establish. | `53-29.4` | "EBR-1" | `undefined_district` |
| 4 | §5.3(a) | Self-table mismatch: "this Table I" inside `53:TableK:fn1`; the claim names the containing Table K (finding 8). | `53:TableK:fn1` | "this Table I" | `self_mismatch` |
| 5 | §5.3(g) | Scope mismatch: "Table 2 in Section 53-19", but `53:Table2` sits under Section 53-21. | `53-31` | "Table 2 in Section 53-19" | `scope_mismatch` |
| 6 | §5.3(f) | Table footnote mark with no footnote: EBR-4 height cell carries mark (5) but Table H has no footnote 5. | `53:TableH` | EBR-4 / "Building Height Maximum \| Feet" cell "see fn", mark "5" | `footnote_missing` |
| 7 | §5.3(f) | Footnote nothing references: Table H defines footnote 9 but no cell mark, header mark, or applicable-footnotes entry uses it. | `53:TableH:fn9` | footnote "9" | `footnote_unused` |
| 8 | §5.3(h) | Definition mismatch: `53-4.1` heading defines `("EBR-3") Subdistricts.` but the body regulates EBR-4 of the same family. | `53-4.1` | the defining paragraph | `definition_mismatch` |
| 9 | §5.3(i) | Undefined use term: Table A row "Accessory Family Day Care Home" is a stale use name not among the defined terms. | `53:TableA` | row label "Accessory Family Day Care Home" | `undefined_term` |
| 10 | §5.3(j) | District without a row: `53-5` establishes EBR-5, which has no row in any dimensional table (Table H). | `53-5` | "EBR-5" | `district_without_row` |

## Controls (resolve cleanly, produce no candidate)

- `53-19` cites `53-10.4` with its real title "Waterfront Yard Area Requirements" → `ok`.
- The clean footnote mark (3) on the EBR-3 height cell resolves to `53:TableH:fn3`, and
  Table A footnote (2) resolves to `53:TableA:fn2`.
- Established districts EBR-2.5, EBR-3, EBR-4 each have a row in Table H → no (j) candidate.
- "this Section 53-27" inside `53-27` itself resolves to its container → `ok`.

## Which candidates skip the skeptic (design §6.3)

- Skip (facts the code proves): (a) self_mismatch, (b) missing, (e) undefined_district,
  (f) footnote_missing / footnote_unused, (h) definition_mismatch.
- Go to `skeptic_xref`: (c) cross_article_shadow, (d) title_mismatch, (g) scope_mismatch,
  (i) undefined_term, (j) district_without_row.

## Not a cross-reference candidate

- Direct value conflict between Table H (EBR-3 max height 40 ft) and prose `53-21`
  (35 ft) is a `contradiction` (building_height_ft), produced by the contradiction
  finder, not `find_xrefs`.
