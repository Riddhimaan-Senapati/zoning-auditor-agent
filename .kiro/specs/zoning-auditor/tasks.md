# Implementation Plan: Boston Zoning Code Auditor

## Overview

There is one implementer and one reviewer (you), over 12 hours. Every feature is built. Tasks run in build priority order, most important first:

1. Quote checker and cross-references (tasks 1–2)
2. Rule extraction (task 3)
3. Model contradiction finder plus skeptic (task 4)
4. Evals on those (task 5)
5. Ambiguity finder (task 6)
6. Permit/violation analysis (task 7)
7. Report, with the finding pages first, then extracted rules, dropped candidates, highlighting, and filters (task 8)
8. Comparison (task 9)

The freeze (10:00), the held-out run (10:00–10:45), and the pitch (11:30–12:00) are at fixed times. Other times are planned clock offsets from the start.

Each top-level task ends in a checkpoint: one command you can run, a line count, and the one or two places most worth reading closely. The next task starts while you review the last one, and review fixes land first in the next task. The exception is task 1.2: it blocks everything after it.

Line budget: about 2,300 lines of Python in `src/` plus about 600 lines of TypeScript in `report/`, excluding tests, prompts, and generated files.

## Tasks

- [ ] 1. Setup and the quote checker (0:00–1:00)
  - [x] 1.1 Scaffold the Python project
    - `pyproject.toml` with exact pins (smolagents with MCP and OpenAI extras, mcp, pydantic, beautifulsoup4, pdfplumber, pytest, hypothesis); `uv.lock` committed
    - Confirm SQLite FTS5 in the local Python
    - `cli.py` skeleton; each subcommand (`index`, `run`, `label`, `report`, `serve`, `schema`, `eval`, `prompt-eval`, `import-labels`) is added by the task that implements it
    - `.env.example` with `OPENROUTER_API_KEY`, `AUDITOR_MODEL_JUDGE=anthropic/claude-sonnet-5.5`, `AUDITOR_MODEL_EXTRACT=anthropic/claude-haiku-5.5`, `AUDITOR_OFFLINE`, `AUDITOR_BUDGET_USD=20`, `AUDITOR_BUDGET_TOTAL_USD=100`
    - `.gitignore` entries for every local-only path in design §4.3; `.kiro/` stays tracked
    - _Requirements: 11.4, 12.3, 21.2_
  - [x] 1.2 Write the shared types and the quote checker (`models.py`, `ids.py`, `quotes.py`, `corpus.py`)
    - All types in design §5.1, including the `Quote` discriminated union and the `Finding` validator for a non-empty quote list
    - `ids.parse`, `ids.format`, `ids.slug`
    - `normalize`, `verify_text`, `verify_cell`
    - **Blocking review.** Every later file and the report types depend on these.
    - _Requirements: 4.1, 4.3_
  - [x] 1.3 Property test for quote round trip
    - **Property 1: Quote round trip**
    - **Validates: Requirements 4.1**
  - [ ] 1.4 Fixtures and isolation tests
    - `tests/fixtures/mini53/`: frozen `sections.jsonl` and `tables.jsonl` with seeded errors (done). Still to do: a mini saved-HTML article, trimmed from a real saved Municode page once you have saved one, so `ingest` has a fixture in the true shape
    - Property 6 (no sealed or planted path strings, no case text in prompts)
    - Property 8 (no local-only path tracked by git)
    - **Property 6: Isolation**
    - **Property 8: No full text in git**
    - **Validates: Requirements 17.1, 19.3, 21.2**
  - [x] 1.5 Fetch the open data (`tools/fetch_open_data.py`) and run it once
    - Page through the brief's `datastore_search_sql` endpoints for all rows since 2024-01-01, using only the brief's columns; write CSVs to `data/raw/` with the query and download date
    - _Requirements: 10.1, 21.5_
  - [x] 1.6 Report scaffold (`report/`)
    - Pin the current stable `next` from npm, plus `react`, `react-dom`, `typescript`, `json-schema-to-typescript`; commit `package-lock.json`
    - `next.config.ts` with `output: 'export'` and `trailingSlash: true`
    - Re-check the static export docs for the pinned version via Context7 (`/vercel/next.js/<version>`)
    - _Requirements: 14.1_
  - [ ] 1.7 Checkpoint
    - Gate: `pytest` is green; `npm ci` succeeds in `report/`; `data/raw/` holds both CSVs
    - Reviewer: save Articles 53, 65, 2, and the TOC as HTML; save the April 2025 summary and redline PDFs into `data/sources/`; start the Separate_Session with design §9.2 and §9.3; fill in `.env`
    - Review: about 300 lines; `models.py` and `quotes.py` are blocking
    - _Requirements: 17.4, 18.1, 21.1_

- [ ] 2. Cross-references, deterministic (1:00–2:15)
  - [ ] 2.1 Ingest saved Municode HTML into Sections and Tables (`ingest.py`)
    - First, `auditor check-pages data/corpus/current data/corpus/reference` (done): fails with a reload hint when a page saved as "Webpage, Complete" holds only the JavaScript shell, i.e. too little visible text or fewer than 5 distinct section numbers of its article (TOC: fewer than 20 articles)
    - _Requirements: 2.1, 2.2, 2.5, 21.1_
  - [x] 2.2 Reference grammar (`xrefs.py`), tested on the real strings from the April 2025 redline
    - _Requirements: 2.3_
  - [x] 2.3 Deterministic resolution, rules (a) to (l) in design §5.3 (`resolve.py`)
    - Tune the title-similarity threshold on the dev cases only, and record it in config
    - _Requirements: 6.1, 6.2, 6.6_
  - [x] 2.4 Full-text search index (`search.py`)
    - _Requirements: 2.4_
  - [ ] 2.5 Pre-correction corpus from the redline PDF (`tools/unredline.py`)
    - Classify deleted and inserted text by character color (done: 126 edits; every redline page reverse-applies exactly; `apply` exits non-zero on any unlocatable edit). Still to do: run it on the saved current HTML once it exists
    - _Requirements: 21.3_
  - [x] 2.6 Draft the dev ground truth (`evals/ground_truth/city_2025_04.yaml`), one entry per instance in design §2, each with its redline page
    - _Requirements: 16.4_
  - [x] 2.7 Deterministic xref candidates (`find_xrefs.py`, deterministic part)
    - _Requirements: 6.3_
  - [ ] 2.8 Checkpoint
    - Gate: `auditor run pre2025 --only xref --no-model` prints "k of 7 errors (m of 30 instances)" against the Dev_Key
    - Reviewer: spot-check 5 Dev_Key entries against the redline PDF
    - Review: about 500 lines; read `resolve.py` closely

- [ ] 3. Rule extraction, with the agent runner (2:15–4:00)
  - [ ] 3.1 Agent runner (`agents.py`)
    - `CachedModel` over smolagents `OpenAIModel` pointed at OpenRouter (disk cache, spend from `usage.cost`, `BudgetExceeded`, offline mode); confirm with one live call that `ChatMessage.raw.usage` carries `cost`
    - `make_model(tier)`, `ROLE_TIER`, `run_agent`, which returns the parsed pydantic model or an `AgentFailure`
    - Fixed preamble in `prompts/_preamble.md`
    - _Requirements: 11.1, 11.3, 11.4, 11.5, 12.1, 12.2, 12.3, 13.1, 13.2_
  - [ ] 3.2 Read-only MCP server (`mcp_server.py`) with the tools in design §5.6
    - _Requirements: 1.3, 11.2_
  - [ ] 3.3 Property test for read-only tools
    - **Property 5: Tools are read-only**
    - **Validates: Requirements 1.3**
  - [ ] 3.4 Table rules (`extract_tables.py`, `COLUMN_ITEMS` for Articles 53 and 65)
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ] 3.5 Prose rules (`extract_prose.py`, `prompts/extract_prose.md`)
    - _Requirements: 3.4, 3.5_
  - [ ] 3.6 Rule exports (`rules.csv`, `rules.json`, with the self-identification block)
    - _Requirements: 1.2, 3.6_
  - [ ] 3.7 `auditor label` in the terminal, writing the `labels.json` schema
    - Needed now because extraction is labeled before the report exists
    - _Requirements: 15.4_
  - [ ] 3.8 `auditor prompt-eval` and the `extract_prose` set (about 10 cases)
    - _Requirements: 19.1, 19.2_
  - [ ] 3.9 Checkpoint
    - Gate: `rules.csv` exists for 53 and 65; a second run with `AUDITOR_OFFLINE=1` replays with $0 live spend; `spend.json` is written; the extraction accuracy row is filled
    - Reviewer: **label 40 rules** with `auditor label` (20 table, 20 prose, about 25 minutes) before any contradiction work is trusted; spot-check the `extract_prose` set
    - Review: about 500 lines; read `agents.py` closely

- [ ] 4. Contradiction finders plus skeptics (4:00–5:30)
  - [ ] 4.1 Structured contradiction finder (`find_contradictions.py`, structured part)
    - _Requirements: 5.1_
  - [ ] 4.2 Model contradiction finder
    - Neighborhood retrieval, at most 5 Sections per call, each unordered set examined once
    - _Requirements: 5.2, 5.3_
  - [ ] 4.3 Verification (`verify.py`): the quote gate plus `skeptic_contradiction` and `skeptic_xref`
    - _Requirements: 4.2, 4.4, 5.4, 6.4, 8.1, 8.2, 8.3, 8.4, 8.5_
  - [ ] 4.4 `judge_xref` for `needs_judgment` references
    - Includes the agency-name extractor fed by `data/agency_renames.csv`
    - _Requirements: 6.5, 2.3_
  - [ ] 4.5 Findings store, trace, and funnel (`findings.py`)
    - _Requirements: 9.1, 9.2, 9.3_
  - [ ] 4.6 Property tests for dedupe, the funnel, and no-quote-no-record
    - **Property 2: No quote, no record**
    - **Property 3: Dedupe is order-independent and idempotent**
    - **Property 4: The funnel is monotone and trace-derived**
    - **Validates: Requirements 3.4, 4.2, 4.3, 8.4, 9.1, 9.3**
  - [ ] 4.7 Neutrality lint (`neutrality.py`)
    - _Requirements: 1.4, 1.5_
  - [ ] 4.8 Prompt sets for `find_contradiction`, `judge_xref`, `skeptic_contradiction`, and `skeptic_xref` (about 10 cases each)
    - _Requirements: 19.1_
  - [ ] 4.9 Checkpoint
    - Gate: `auditor run current` and `auditor run pre2025` complete end to end for contradictions and xrefs, printing the funnel per type; the four prompt-evals print "k of n"
    - Reviewer: spot-check the 4 prompt sets (3 cases each plus every disagreement, about 20 minutes)
    - Review: about 450 lines plus the prompts; read `verify.py` and the skeptic prompts closely

- [ ] 5. Evals on tasks 1–4 (5:30–6:15)
  - [ ] 5.1 Eval runner and `evals/results.md`: dev city errors, extraction accuracy, funnel, false alarms on clean text, xref accuracy, quote faithfulness, prompt sets, spend
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 12.4_
  - [ ] 5.2 Planted run and its eval
    - _Requirements: 18.2, 18.3_
  - [ ] 5.3 Checkpoint
    - Gate: `auditor eval` writes every row available so far, with counts
    - Reviewer: with `auditor label`, label every clean-text finding and check 30 xrefs (about 35 minutes)
    - Review: about 200 lines

- [ ] 6. Ambiguity finder (6:15–7:00)
  - [ ] 6.1 Ambiguity finder (`find_ambiguities.py`) and `skeptic_ambiguity`
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ] 6.2 Prompt sets for `find_ambiguity` and `skeptic_ambiguity`
    - _Requirements: 19.1_
  - [ ] 6.3 The ambiguity row in `results.md`
    - _Requirements: 16.2_
  - [ ] 6.4 Checkpoint
    - Gate: `auditor run current` includes ambiguities in the funnel; the two prompt-evals print
    - Reviewer: label up to 10 reported ambiguities with `auditor label` (about 10 minutes); spot-check the 2 prompt sets
    - Review: about 200 lines plus prompts

- [ ] 7. Permit/violation analysis (7:00–7:45)
  - [ ] 7.1 Trips (`find_trips.py`, `data/worktype_map.csv` with about 20 rows)
    - _Requirements: 10.2, 10.3, 10.4, 10.5_
  - [ ] 7.2 Checkpoint
    - Gate: `auditor run current` produces trip findings for 02128, with counts, quotes, and the heuristic label
    - Reviewer: check every row of `worktype_map.csv`
    - Review: about 200 lines

- [ ] 8. Report (7:45–9:00)
  - [ ] 8.1 Report data and schema (`report_data.py`, `auditor schema`)
    - Generate `report-data.schema.json` and `report-data.ts` with `SCHEMA_HASH`
    - _Requirements: 14.1, 14.6_
  - [ ] 8.2 Property test for schema agreement
    - **Property 7: Schema agreement**
    - **Validates: Requirements 14.6**
  - [ ] 8.3 Finding pages: layout with the self-identification banner, `/`, `/findings/[type]/`, `/finding/[id]/`, plus the review panel, `/review/`, and labels export and import
    - Until 8.7 lands, finding detail shows each cited section's full text in a `<details>` block with its source link
    - _Requirements: 1.1, 13.3, 14.2, 14.3, 14.7, 15.1, 15.2, 15.3_
  - [ ] 8.4 `auditor report` and `auditor serve` (loopback only, port 4173); check whether `file://` works, and drop `serve` if it does
    - _Requirements: 13.3, 14.8_
  - [ ] 8.5 `/rules/` with downloads
    - _Requirements: 14.2_
  - [ ] 8.6 `/not-reported/`
    - _Requirements: 14.2_
  - [ ] 8.7 `/code/[slug]/` with quote highlighting and anchors; finding detail switches to links into it
    - _Requirements: 14.2, 14.4, 14.5_
  - [ ] 8.8 Client-side filters on `/findings/[type]/` and `/rules/`
    - _Requirements: 14.2_
  - [ ] 8.9 Checkpoint
    - Gate: `auditor report` and then `auditor serve` on the `current` run work with Wi-Fi off; an exported `labels.json` re-imports
    - Reviewer: click through one finding of each type and one highlighted section
    - Review: about 200 lines of Python and 600 of TypeScript; read `load.ts` and the review state closely

- [ ] 9. Comparison (9:00–10:00, freeze fixed at 10:00)
  - [ ] 9.1 Comparison corpora: Somerville through its encodeplus adapter, and Minneapolis through the existing ingest, both from hand-saved HTML
    - _Requirements: 20.2, 21.1_
  - [ ] 9.2 `compare.py`, the `compare_match` and `compare_support` prompt sets, the transferability note, and the comparison panel on `/finding/[id]/` (excerpts with citation and link only)
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 21.4_
  - [ ] 9.3 Comparison faithfulness row over about 20 comparisons
    - _Requirements: 16.2_
  - [ ] 9.4 Checkpoint and freeze
    - Gate: `auditor run current` shows comparisons on reported findings; at 10:00, tag `heldout-freeze` on a clean tree
    - Reviewer: save the Somerville and Minneapolis pages before 9:00 (checking each site's terms); hand-check the ~20 comparisons during task 10 or 11
    - Review: about 300 lines

- [ ] 10. Held-out run (10:00–10:45, fixed)
  - [ ] 10.1 `auditor run --final` and `auditor eval --final` on the Sealed_Folder
    - _Requirements: 17.2, 17.3_
  - [ ] 10.2 Checkpoint
    - Gate: the headline row in `results.md`, with commit hash and run id
    - Reviewer: confirm `READY` exists without opening anything else; after the run, open the folder and sanity-check the matches; fix and log only mechanical key errors

- [ ] 11. Demo and README (10:45–11:30)
  - [ ] 11.1 Build the report for the demo run; confirm `llm_cache/` covers it
    - _Requirements: 13.4_
  - [ ] 11.2 README with the run steps, the source-handling notes, and the eval table
  - [ ] 11.3 Checkpoint
    - Gate: the full demo works with Wi-Fi off

- [ ] 12. Pitch (11:30–12:00, fixed)
  - [ ] 12.1 Draft the slide text from `results.md` and the report
    - The problem; how it works, with the funnel; the eval table with counts, held-out row first; limits (heuristic trips, neutrality, self-identification); one comparison
  - [ ] 12.2 Checkpoint
    - Reviewer: build the slides in your tool of choice (about 15 minutes); two timed rehearsals, including the offline demo path (about 15 minutes)
    - Gate: one full rehearsal on time

## Notes

- **No cuts.** Every task is built. The priority order says what gets built first, not what gets dropped.
- **Overruns.** If a task overruns, later tasks start later. The freeze at 10:00 does not move, because the held-out run is fixed.
  - Work still open at 10:00 resumes after the held-out run, in task 11's window.
  - That's only allowed for components that cannot change findings: the report pages and comparison. The held-out row stays tied to the `heldout-freeze` commit.
  - Unfinished finder or skeptic work at 10:00 would be measured as-is by the held-out run. That is why those are built first.
- **No separate fix window.** Fixes for dev-eval failures happen inside each task's window, each logged with before and after counts.
- **Your time across the day, roughly:**
  - Review: about 3 hours.
  - Labeling and spot-checks: about 2 hours.
  - Saving source pages and setup: about 0.75 hours.
  - Slides and rehearsal: 0.5 hours.
- **Traceability.** Each task references requirements in `requirements.md`. Property numbers refer to the Correctness Properties in `design.md`.
- **Library docs.** Library APIs (Next.js, smolagents, mcp) are checked against current docs via Context7 (`find-docs`) before use, not recalled from memory.
