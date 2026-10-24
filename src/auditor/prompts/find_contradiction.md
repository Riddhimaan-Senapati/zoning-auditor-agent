You examine a small set of zoning code sections for a contradiction: two provisions that
cannot both be followed at once.

You are given a list of section ids. Read each one with the tools (`get_section`,
`get_table`), and read any definition, footnote, or cross-referenced section you need to
understand a provision (`get_definition`, `resolve_reference`). A contradiction is two
provisions that set an incompatible requirement for the same thing: a different maximum and
minimum that cannot both hold, a use allowed by one provision and forbidden by another, two
different values stated for the same regulated item in the same district.

Report only a genuine conflict. Two provisions that govern different districts, different
uses, or different cases are not a contradiction. A provision and its stated exception,
footnote, or "notwithstanding" clause are not a contradiction. When a footnote or definition
reconciles two provisions, do not report them.

Return 0 to 3 candidates. For each candidate:

- `quotes`: the two provisions in conflict, each as one object with `section_id` and `text`.
  Copy `text` verbatim from the section's own text: the exact characters, including the
  number or permission that carries the conflict. Do not paraphrase, normalize, or join text
  across a gap.
- `claim`: one neutral sentence that names what conflicts and where. State the two values or
  statuses and the two locations. Do not say which is correct, which should change, or which
  is better.

If you find no contradiction among the sections, return an empty list.

Your final answer is a single JSON object `{"candidates": [ ... ]}` matching the schema, and
nothing else.
