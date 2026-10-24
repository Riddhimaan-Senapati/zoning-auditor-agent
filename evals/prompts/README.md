# Per-prompt regression sets

Each model role has a small regression set, so a prompt change shows up as a measured
"7 of 10 to 9 of 10" instead of a guess (design §9.4, Requirement 19).

`auditor prompt-eval <role> --build-dir <corpus> --run-dir <run>` loads
`evals/prompts/<role>.jsonl`, runs the role on each case against the corpus in
`--build-dir`, scores with the role's comparator, prints `k of n` with a one-line diff per
failing case, and prints what this invocation spent. `--run-dir` must sit under
`AUDITOR_RUNS_ROOT` (default `runs/`), whose `spend.jsonl` files feed the total cap. Model
calls are cached in `AUDITOR_CACHE_DIR` (default `llm_cache/`), so a rerun of an unchanged
prompt replays at `$0`.

These sets exist to iterate on prompts. They are **not** an accuracy claim. In `results.md`
they appear as regression counts labeled "model-drafted labels".

## Case file

One JSON object per line in `evals/prompts/<role>.jsonl`, about 10 cases per role.

```json
{
  "id": "ep-001",
  "inputs": {"section_ids": ["53-21"], "candidate": null},
  "expected": {"item": "building_height_ft", "comparator": "max", "value": "35", "unit": "ft", "district": "EBR-3"},
  "rationale": "one sentence on why this is the right label",
  "drafted_by": "anthropic/claude-sonnet-5.5",
  "checked": false
}
```

- `id`: stable case id.
- `inputs`: what the role is run on. `section_ids` names the section(s) to read; `candidate`
  is the candidate object for the finder and skeptic roles, and is absent (or `null`) for
  extraction.
- `expected`: what the role should produce, interpreted per role.
  - extraction (`extract_prose`): the rule fields. The comparator checks `item`,
    `comparator`, `value` (as a number, so `"35.0"` matches `35`), `unit`, and `district`;
    a case passes when some produced rule matches the expected rule on all five.
  - finders (`find_contradiction`, `find_ambiguity`): whether a finding should exist, and
    which sections it is about.
  - skeptics (`skeptic_contradiction`, `skeptic_xref`, `skeptic_ambiguity`): `upheld` or
    `refuted`.
  - `judge_xref`: `ok` or `broken`.
- `rationale`: one sentence saying why the label is correct.
- `drafted_by`: the model id that drafted the case.
- `checked`: `true` once a human has spot-checked this case (see below).

## Drafting rule

- **Source.** Cases are drafted by the judge-tier model from the `current` and `pre2025`
  text of Articles 53 and 65 **only**. Never draft from the planted set, and never from the
  sealed held-out set or any July 2026 material. Those live outside this repository by
  design, and nothing here may read them. The drafting prompt is separate from the role
  prompts.
- **Mix.** About 5 positives, 3 clear negatives, and 2 near-misses per set. A near-miss is an
  apparent conflict that a footnote resolves, or a reference whose cited title differs only
  in wording.
- **Spot-check.** A human checks 3 cases per set, plus every case where the role's output
  disagrees with the expected label (a disagreement is where a model-drafted label is most
  likely wrong). A checked case sets `checked: true`.
- **No leakage into prompts.** Role prompts in `src/auditor/prompts/` contain no examples
  from these sets. A test fails if any case's quoted text appears under that directory.
- **Committing.** Each prompt change is committed together with its before/after
  `prompt-eval` line.

The real case files are drafted later from the saved Articles 53 and 65, which do not exist
in the repo yet. This directory holds no real case files until then.
