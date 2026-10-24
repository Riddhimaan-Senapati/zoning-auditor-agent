# Requirements Document

## Introduction

The Boston Zoning Code Auditor is a co-pilot for the city staff rewriting Boston's zoning code. It reads selected articles and produces a reviewable report of problems: contradictions, broken or stale cross-references, ambiguities, and provisions linked to permit and violation patterns. Every finding quotes the exact text it is about, with section numbers. The tool never edits the code and never recommends; staff judge.

It is built solo in 12 hours at Hackachusetts 2026 (Civic action track), with one implementer and one reviewer. The demo scope is Articles 53 and 65, with Article 2 and a code-wide table of contents as reference text. Every feature is built, in the priority order in `tasks.md`. The design is in `design.md` and the build plan is in `tasks.md`.

## Glossary

- **Auditor**: the Python system as a whole, run as `auditor`.
- **Corpus**: one set of saved article files the Auditor runs on: `current`, `pre2025`, planted, or held-out.
- **Index**: the deterministic stage that parses the Corpus into Sections, Tables, XRefs, and a search index.
- **Section**: one numbered unit of code text, a table footnote, or a table note, with a canonical id such as `53-29.4` or `53:TableH:fn3`.
- **XRef**: one reference found in a Section, with its deterministic Resolution.
- **Rule**: one structured rule record (district, use, regulated item, value and unit or status, conditions, quote).
- **Quote**: a TextQuote (a character span in a Section) or a CellQuote (table, row label, column, cell text).
- **Quote_Verifier**: the code that checks a Quote verbatim against the Corpus after fixed normalization.
- **Finder**: a component that proposes Candidates of one issue type.
- **Candidate**: a proposed issue, with its Quotes, before verification.
- **Skeptic**: a separate agent prompt that argues against a Candidate.
- **Finding**: a Candidate that passed the Quote_Verifier and was upheld by the Skeptic, or that skipped the Skeptic by rule.
- **Findings_Store**: the component that deduplicates Findings and writes the trace and funnel.
- **Funnel**: counts per issue type of candidates, quote-passed, upheld, and reported.
- **Agent_Runner**: the wrapper that runs one smolagents `ToolCallingAgent` with MCP tools and parses its answer.
- **Spend_Meter**: the part of the Agent_Runner that records OpenRouter's reported cost for every live model call and enforces caps.
- **Report**: the Next.js static site built from one run's `report_data.json`.
- **Reviewer**: a planning staff member (and, during the hackathon, the developer) using the Report.
- **Eval_Runner**: `auditor eval`, which writes `evals/results.md`.
- **Separate_Session**: an agent session that never develops the Auditor and builds the planted and held-out sets.
- **Sealed_Folder**: `../zoning-auditor-sealed/heldout/`, outside the repo, holding the held-out corpus and key.
- **Dev_Key**: the ground-truth file built from the April 2025 corrections.

## Requirements

### Requirement 1: Identity, read-only operation, and neutrality

**User Story:** As a Reviewer, I want the tool to say plainly what it is and to stay read-only and neutral, so that I can trust it as an inspection aid and not mistake it for a city service or an advocate.

#### Acceptance Criteria

1. THE Report SHALL display on every page the text "Independent prototype built at Hackachusetts 2026. Not a City of Boston service. Findings are unreviewed until confirmed by staff."
2. THE rule exports (CSV and JSON) SHALL carry the same self-identification text.
3. THE Auditor SHALL NOT modify any Corpus file, and every MCP tool SHALL be read-only.
4. THE Auditor SHALL NOT produce recommendations. Model-written claims, readings, and summaries SHALL describe problems and options only.
5. WHEN a model-written claim, reading, or summary matches the neutrality lint list, THE Auditor SHALL attach a neutrality flag to the Finding. The Report SHALL show the flag.

### Requirement 2: Deterministic index

**User Story:** As a Reviewer, I want the code parsed into numbered sections, tables, and a table of every cross-reference, so that every finding can point to exact locations.

#### Acceptance Criteria

1. WHEN the Index runs on a Corpus, THE Index SHALL produce Sections with canonical ids, headings, parent ids, and text, without calling a model.
2. WHEN a Corpus file contains a table, THE Index SHALL produce a Table with column header paths, row labels, cells, cell footnote marks, and footnote ids.
3. THE Index SHALL extract every reference matching the grammar in design §5.3, including section ranges, "this Section" and "this Table" self-references, footnote marks, district codes, and agency names.
4. THE Index SHALL build a full-text search index over the Sections.
5. THE Index SHALL include Article 2 and the table of contents as reference text, and THE Auditor SHALL NOT raise Findings against reference text.

### Requirement 3: Structured rule extraction (feature 0)

**User Story:** As a Reviewer, I want the selected articles converted into structured, cited rule records, so that I can query and export the rules and the tool can compare them.

#### Acceptance Criteria

1. WHEN a Table column maps to a regulated item, THE Auditor SHALL produce Rules from that Table in code, without calling a model.
2. WHEN a table cell does not parse as a number, "N/A", or "none", THE Auditor SHALL set `needs_review` and keep the raw cell text. It SHALL NOT guess a value.
3. WHEN a Table column has no mapping, THE Auditor SHALL produce Rules with item `other` and `needs_review` set.
4. WHEN the prose extractor returns a Rule draft, THE Quote_Verifier SHALL check its Quote. IF the Quote fails, THEN THE Auditor SHALL drop the draft and log it.
5. THE Auditor SHALL set `needs_review` on a prose Rule whenever its value, unit, district, or condition is not stated in the quoted text.
6. THE Auditor SHALL export all Rules as `rules.csv` and `rules.json`, with quote text, section id, and source link.

### Requirement 4: No quote, no flag

**User Story:** As a Reviewer, I want every finding backed by exact quotes, so that I can check each claim against the code text myself.

#### Acceptance Criteria

1. THE Quote_Verifier SHALL accept a Quote only if its normalized text is an exact substring of the normalized Section text, or an exact match of the cited table cell. Normalization is NFKC, straight quotes, hyphen and dash folding, and whitespace collapse, and nothing more. A quote that starts or ends inside one source character's expansion (for example "f" out of the ligature "ﬁ") SHALL be rejected.
2. IF any Quote of a Candidate fails verification, THEN THE Auditor SHALL discard the Candidate and record the failing strings in the trace.
3. THE Auditor SHALL NOT report a Finding with zero Quotes.
4. THE Skeptic's reconciling Quotes SHALL pass the same verification before they count as evidence.

### Requirement 5: Contradictions (feature 1)

**User Story:** As a Reviewer, I want pairs of provisions that cannot both be followed shown side by side, so that I can decide whether the code needs a fix.

#### Acceptance Criteria

1. WHEN two or more Rules share district, use, and regulated item and their values or statuses differ, THE structured Finder SHALL propose a contradiction Candidate, unless code shows their conditions are disjoint. A disjointness removal SHALL be logged.
2. THE model Finder SHALL see at most 5 Sections per call, retrieved by shared district, use, or regulated item, and SHALL NOT receive a whole article.
3. THE model Finder SHALL examine each unordered set of Sections at most once per run.
4. WHEN a contradiction Candidate passes the Quote_Verifier, THE Skeptic SHALL judge whether both provisions can be followed and whether an exception, footnote, overlay, or definition reconciles them.

### Requirement 6: Broken or stale cross-references (feature 2)

**User Story:** As a Reviewer, I want references to missing, moved, or renamed sections, tables, articles, districts, or agencies flagged, so that I can correct them.

#### Acceptance Criteria

1. THE Index SHALL resolve each XRef deterministically against the Section index and the table of contents, with the statuses in design §5.3.
2. WHEN an XRef cites a title that does not match the target heading, THE Auditor SHALL report the section whose heading does match, if one exists, as a fact and not as a fix.
3. WHEN an XRef has status `self_mismatch`, `missing`, `undefined_district`, `footnote_missing`, or `footnote_unused`, THE Auditor SHALL report it without calling the Skeptic.
4. WHEN an XRef has status `cross_article_shadow` or `title_mismatch`, THE Skeptic SHALL review it before it is reported.
5. WHEN an XRef has status `needs_judgment`, THE Auditor SHALL send it to the `judge_xref` agent with the cited rows of `agency_renames.csv`.
6. WHEN an XRef targets an article that is neither loaded nor in the table of contents, THE Auditor SHALL count it in the Funnel as `external_unchecked` and SHALL NOT report it.

### Requirement 7: Ambiguities (feature 3)

**User Story:** As a Reviewer, I want rules that a reasonable applicant could read two ways stated with both readings, so that I can decide whether to clarify them.

#### Acceptance Criteria

1. THE ambiguity Finder SHALL return the quoted span and two readings, each a full sentence a reasonable applicant could hold.
2. THE ambiguity Finder SHALL propose a Candidate only when the two readings lead to different outcomes for some applicant.
3. WHEN an ambiguity Candidate passes the Quote_Verifier, THE Skeptic SHALL judge whether one reading is unreasonable given the code and its definitions.

### Requirement 8: Skeptical verification

**User Story:** As a Reviewer, I want each model-found issue argued against before it reaches me, so that I spend my time on survivors.

#### Acceptance Criteria

1. THE Skeptic SHALL be a separate prompt from the Finder that proposed the Candidate.
2. THE Skeptic SHALL return `upheld`, `refuted`, or `uncertain`, with its reasoning and the Sections it retrieved.
3. IF the Skeptic returns `refuted` without verified reconciling Quotes or verified structural evidence, THEN THE Auditor SHALL record the verdict as `uncertain`.
4. THE Auditor SHALL report only Candidates with verdict `upheld`, or `skipped` under Requirement 6.3.
5. THE Auditor SHALL derive confidence from the path that produced the Finding, per design §6.4. A model SHALL NOT state a confidence value.

### Requirement 9: Findings store, trace, and funnel

**User Story:** As a Reviewer, I want duplicates merged and every finding's path inspectable, so that I see each problem once and can audit how it got there.

#### Acceptance Criteria

1. WHEN two Candidates have the same issue type and the same set of (location, normalized quote) pairs, THE Findings_Store SHALL merge them into one Finding that keeps both candidate ids.
2. THE Findings_Store SHALL append one trace event per stage transition per Candidate: candidate, quote check, skeptic reasoning, kept or rejected, and why.
3. THE Findings_Store SHALL compute the Funnel from the trace alone, and THE Report and THE Eval_Runner SHALL use that same computation.

### Requirement 10: Where people trip (feature 4)

**User Story:** As a Reviewer, I want permit and violation patterns linked to the zoning provisions that govern that kind of work, so that I can see where applicants may be confused.

#### Acceptance Criteria

1. THE Auditor SHALL read violations and permits only from files in `data/raw/`, downloaded once, and SHALL NOT fetch them at run time.
2. THE Auditor SHALL filter the data to the ZIP codes the audited article governs.
3. THE Auditor SHALL map permit work types to regulated items only through `data/worktype_map.csv`, where each row has a rationale.
4. THE Auditor SHALL label every trip Finding "Heuristic. Violations data is building-code enforcement. This links patterns to provisions as evidence of possible confusion, not proof."
5. Each trip Finding SHALL include the quoted zoning provisions, the counts, the query parameters, and the download date.

### Requirement 11: Agent framework and models

**User Story:** As the developer, I want models used only where judgment is needed, through a swappable framework, so that every assertion traces to a tool output.

#### Acceptance Criteria

1. THE Agent_Runner SHALL use smolagents `ToolCallingAgent` and SHALL NOT use `CodeAgent`.
2. THE Agent_Runner SHALL expose tools to agents only through the MCP server in design §5.6.
3. THE Agent_Runner SHALL parse each agent's final answer into a pydantic model. IF parsing fails, THEN THE Agent_Runner SHALL return an AgentFailure, which the harness records as a rejected Candidate.
4. THE Agent_Runner SHALL reach models through OpenRouter's OpenAI-compatible API with smolagents `OpenAIModel`, and SHALL select the model per role from two tiers, `judge` and `extract`, set by environment variables.
5. Every role prompt SHALL include the fixed preamble in design §5.5 and SHALL NOT contain examples from the per-prompt datasets.

### Requirement 12: Spend metering and caps

**User Story:** As the developer, I want token spend logged per run and hard-capped, so that I notice early if a run gets expensive.

#### Acceptance Criteria

1. WHEN a live model call returns, THE Spend_Meter SHALL append its role, model, input and output tokens, and the cost OpenRouter reports in `usage.cost` to the run's `spend.json`. IF a live response lacks `usage.cost`, THEN THE Spend_Meter SHALL raise an error.
2. WHEN a call is served from the cache, THE Spend_Meter SHALL log it at $0 with `cached: true`.
3. IF a live call would start after the per-run cap or the total cap is reached, THEN THE Spend_Meter SHALL raise BudgetExceeded. THE Auditor SHALL then write partial outputs and mark the Funnel as truncated.
4. THE Eval_Runner SHALL write one spend row per eval run in `results.md`.

### Requirement 13: Offline operation

**User Story:** As a presenter, I want the demo to work with no network, so that venue Wi-Fi cannot break it.

#### Acceptance Criteria

1. THE Agent_Runner SHALL cache every model call on disk, keyed by model id, messages, and tool schemas.
2. WHILE `AUDITOR_OFFLINE=1` is set, THE Agent_Runner SHALL serve calls only from the cache, and a cache miss SHALL be an error.
3. THE Report SHALL load no remote resources: no CDN, no remote fonts, no remote images.
4. THE Auditor SHALL run the demo end to end from cached, pre-indexed files with the network disabled.

### Requirement 14: Report

**User Story:** As a Reviewer, I want an interactive report with findings grouped by type, the quoted passages side by side, and links into the code text, so that I can judge each finding quickly.

#### Acceptance Criteria

1. THE Report SHALL be a Next.js static export built from one run's `report_data.json`, with no Node server at view time.
2. THE Report SHALL include the funnel page, the findings-by-type pages, the finding detail pages, the code-text pages with quote highlighting, the extracted-rules page, the dropped-candidates page, the review page, and client-side filters on the findings lists.
3. THE finding detail page SHALL show the claim, all Quotes side by side with section ids, ambiguity readings, confidence, review flags, the verification path, and the Reviewer controls.
4. THE finding detail page SHALL link each Quote to its highlighted, anchored location on the code-text page, and SHALL link each cited Section to its source page.
5. THE code-text page SHALL show only Sections that a Finding or Rule cites.
6. WHEN `report_data.json` has a schema hash different from the generated TypeScript types, THE Report build SHALL fail with the message "run `auditor schema`".
7. THE Report SHALL be keyboard navigable, use semantic landmarks, announce decisions through an `aria-live` region, and never use color as the only signal.
8. WHERE the Report is served over HTTP, THE server SHALL bind to 127.0.0.1 only and serve static files only.

### Requirement 15: Review decisions as labeled data

**User Story:** As a Reviewer, I want to mark each finding confirmed, rejected, or unsure, so that my decisions become labeled data.

#### Acceptance Criteria

1. WHEN a Reviewer chooses confirmed, rejected, or unsure, THE Report SHALL store the decision, a note, and a timestamp in localStorage under a key that includes the run id.
2. WHEN a Reviewer exports labels, THE Report SHALL download `labels.json` with the run id and every decision.
3. WHEN `auditor import-labels` receives a `labels.json`, THE Auditor SHALL copy it into `evals/labels/` for the Eval_Runner.
4. WHEN `auditor label` runs on a run directory, THE Auditor SHALL present findings, rules, or xrefs one at a time in the terminal and write the same `labels.json` schema as the Report.

### Requirement 16: Eval suite and summary table

**User Story:** As a judge or Reviewer, I want measured accuracy reported as counts, so that I can see how well the tool works on small samples.

#### Acceptance Criteria

1. THE Eval_Runner SHALL write one summary table in `evals/results.md`, reporting counts such as "9 of 15", with percentages only alongside counts.
2. THE Eval_Runner SHALL report every eval in design §9: held-out city errors, dev city errors, extraction accuracy, verification funnel, planted contradictions, false alarms on clean text, cross-reference accuracy, quote faithfulness, ambiguities, per-prompt datasets, spend, and comparison faithfulness.
3. THE Eval_Runner SHALL label the dev city-errors row "development set: prompts were tuned against this".
4. WHEN matching a Finding to a ground-truth entry, THE Eval_Runner SHALL require a verified Quote that overlaps the entry's `pre_text` in the same article, plus a type that fits the entry's class.

### Requirement 17: Held-out isolation

**User Story:** As a judge, I want the headline number measured on errors the developer never tuned against, so that it isn't inflated.

#### Acceptance Criteria

1. No file outside `.kiro/specs/` SHALL contain the strings `zoning-auditor-sealed` or `zoning-auditor-planted`. The held-out and planted paths SHALL reach the Auditor only as command-line arguments.
2. WHEN `auditor run --final` is invoked, THE Auditor SHALL refuse to run unless HEAD is exactly the `heldout-freeze` tag, the working tree is clean, and the Sealed_Folder contains `READY`.
3. WHEN a second `--final` run happens at the same tag, THE Eval_Runner SHALL label its row "post-hoc" and keep the first run as the headline.
4. THE Separate_Session SHALL build the Sealed_Folder to the contract in design §9.2 and SHALL NOT write into the repository.

### Requirement 18: Planted contradictions

**User Story:** As a judge, I want recall and precision measured on known contradictions, so that feature 1 has a measured result.

#### Acceptance Criteria

1. THE Separate_Session SHALL write 12 planted contradictions (5 direct, 4 behind an exception, 3 across articles) and their key to `../zoning-auditor-planted/`.
2. THE Auditor SHALL run on the planted corpus with the same command as any other Corpus.
3. THE Eval_Runner SHALL report recall broken down by difficulty, and precision with non-plant Findings judged by the Reviewer.

### Requirement 19: Per-prompt datasets

**User Story:** As the developer, I want a small regression set per prompt, so that prompt changes show measured effects.

#### Acceptance Criteria

1. THE repository SHALL hold about 10 cases per model role in `evals/prompts/<role>.jsonl`, drafted by a model from the `current` and `pre2025` text of Articles 53 and 65 only.
2. WHEN `auditor prompt-eval <role>` runs, THE Auditor SHALL print "k of n" with diffs for failing cases.
3. A test SHALL fail if any case's quoted text appears in `src/auditor/prompts/`.

### Requirement 20: Comparison with other codes (feature 5)

**User Story:** As a Reviewer, I want to see how two other jurisdictions word the equivalent rule for an issue already flagged, as options, so that I have drafting reference points.

#### Acceptance Criteria

1. THE Auditor SHALL compare only Findings already reported under features 1 to 4.
2. Each comparison SHALL quote verified text from the other jurisdiction's code with a citation.
3. A separate support check SHALL confirm that the quoted text supports the summary, and a failed check SHALL drop the comparison.
4. Each comparison SHALL carry the cited transferability note in design §10 and SHALL say plainly when the tool cannot judge transferability.
5. THE Report SHALL title comparisons "How other codes word this (options, not recommendations)".

### Requirement 21: Source handling

**User Story:** As the developer, I want code text handled within each host's terms, so that the project neither scrapes nor republishes it.

#### Acceptance Criteria

1. THE Auditor SHALL read Boston and comparison code text only from HTML files saved by hand in a browser, and no component SHALL make requests to Municode or a comparison-code host.
2. THE repository SHALL NOT track saved code pages, source PDFs, open-data CSVs, `build/`, `runs/`, or `llm_cache/`.
3. THE Auditor SHALL build pre-correction text only from Planning Department redline PDFs.
4. WHEN the Report shows comparison-code text, THE Report SHALL show only the quoted excerpt, with its citation and a link to the source page.
5. THE open-data fetch SHALL select only the brief's columns and SHALL run once, writing to `data/raw/`.
