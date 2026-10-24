# mini53 fixture — seeded errors

A tiny synthetic Article 53 (11 sections + 2 table-footnote sections, 2 tables) in the
`Section`/`Table` shape `Corpus` loads. Errors are modeled on the April 2025 Article 53
corrections (design §2); phrasing is short and synthetic, not copied from the real code.

Status values are the `Resolution.status` / finding dispositions in design §5.3 and §6.4.

| # | Error | Location | Quote / cell | Expected status |
|---|-------|----------|--------------|-----------------|
| 1 | Stale cross-reference: cited title does not match the target heading. Target `53-8` exists but is titled "Regulations Applicable on Tidelands"; the matching heading "Waterfront Yard Area Requirements" is at `53-10.4`. | `53-29.4` | "Section 53-8 (Waterfront Yard Area Requirements)" | `title_mismatch` (title_match_id = `53-10.4`) — §5.3(d) |
| 2 | Self-reference mismatch: "this Section 53-27" inside `53-29.4`, which is not 53-27 nor an ancestor of it. | `53-29.4` | "this Section 53-27" | `self_mismatch` — §5.3(a) |
| 3 | Undefined district code: body says "EBR-1" but `53-4` establishes only EBR-2.5, EBR-3, EBR-4. | `53-29.4` | "EBR-1" | `undefined_district` — §5.3(e) |
| 4 | Table footnote mark with no footnote: EBR-4 height cell carries mark (5) but Table H has no footnote 5. | `53:TableH` | EBR-4 / "Building Height Maximum \| Feet" cell "see fn", mark "5" | `footnote_missing` — §5.3(f) |
| 5 | Footnote nothing references: Table H defines footnote 9 but no cell mark or applicable-footnotes entry uses it. | `53:TableH:fn9` | footnote "9" | `footnote_unused` — §5.3(f) |
| 6 | Clean reference that resolves correctly: cites `53-10.4` with its real title. | `53-19` | "Section 53-10.4 (Waterfront Yard Area Requirements)" | `ok` — §5.3 |
| 7 | Direct value conflict between table and prose: Table H gives EBR-3 max height 40 ft; prose `53-21` says 35 ft. | `53:TableH` row EBR-3 vs `53-21` | cell "40" vs prose "the maximum building height is 35 feet" | `contradiction` (building_height_ft) — §6.1 |

## Notes

- Errors 1–3 all live in `53-29.4`, which packs one line with three independent defects,
  mirroring the real §53-29.4 self-reference and the §53-4 district inconsistency.
- The clean footnote mark (3) on the EBR-3 height cell resolves to `53:TableH:fn3`, and
  Table A footnote (2) resolves to `53:TableA:fn2`; these are controls, not errors.
- Table A renames "Accessory Family Day Care Home" to "Accessory Child Care Home"
  (design §2 rows 5–9); it is seeded as corrected text, not an error to detect here.
