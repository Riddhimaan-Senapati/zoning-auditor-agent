# Design Document: Boston Zoning Code Auditor

Requirements are in `requirements.md` and the build plan is in `tasks.md`. Section numbers (§N) are kept from the original spec so cross-references resolve.

## Overview

Hackachusetts 2026, Civic action track. 12-hour build.

The auditor reads selected articles of the Boston Zoning Code and produces a reviewable report of problems: contradictions, broken or stale cross-references, ambiguities, and provisions linked to permit and violation patterns. Every finding carries exact quotes with section citations. It never edits the code and never recommends; staff judge.

It identifies itself everywhere it renders output as: "Independent prototype built at Hackachusetts 2026. Not a City of Boston service. Findings are unreviewed until confirmed by staff."

## Source Verification and Scope

### 1. What I verified, and what I could not

| Claim in brief | Result | Source |
|---|---|---|
| Boston zoning runs under its own enabling act, not G.L. c. 40A | Confirmed. Chapter 665 of the Acts of 1956, as amended. Mass.gov says "The City of Boston operates under its own enabling act." | mass.gov/info-details/housing-choice-legislation; natlawreview.com (Porter v. Board of Appeal); boston.gov hosts the act text: boston.gov/sites/default/files/file/2020/02/Zoning%20Commission.pdf |
| April 2025 "Correcting Zoning Code Errors": 15 errors, 20 articles | Confirmed. I downloaded the summary (12 pp.) and the draft redline (77 pp.) from bostonplans.org and read them. | bostonplans.org/documents/zoning/clerical-errors,-corrections,-and-minor-text-amend/… (summary "(4-25)" and "draft-redlined-text-amendm") |
| Somerville rewrote its code recently | Confirmed. New Somerville Zoning Ordinance (SZO) adopted Dec 12, 2019, first overhaul since 1990. Its text states it is enacted under G.L. c. 40A, which makes it a clean contrast for the transferability note. | somervillema.gov news, 2019-12; online.encodeplus.com/regs/somerville-ma (SZO §1 text) |
| Municode terms of use | I could not read them: municode.com and library.municode.com return HTTP 403 to non-browser clients, and Municode publishes no API. **Decided:** no automated access. You save the needed article pages by hand in a browser, and ingestion reads those saved HTML files. | review decision |
| Starter zips in `data/raw/` | Not available. **Decided:** `tools/fetch_open_data.py` pulls all rows since 2024-01-01 from the brief's live URLs, once. | review decision |

A later correction round exists: bostonplans.org lists July 2026 office hours for a new "Draft Text Amendment to Correct Existing Zoning Code Errors". I have not read it, and I won't. It is the sealed held-out test set (§9.2).

A second summary URL also exists (`…/zoningcodecorrectionssummaryofupdates`). I haven't opened it, and I don't know which round it belongs to. At task 1, someone who is not developing the auditor opens it and records only its date. That job goes to the separate session (§9.2). If it predates April 2025, it joins the development set. If it is the July 2026 round, it is sealed.

### 2. Demo scope: which articles

#### Selection rule and result

Rule (from review): pick the pair of articles with the most errors documented in the city's correction summaries, as long as the text parses cleanly.

Two clarifications make the rule usable:
- **Development rounds only.** The July 2026 round is held out, so it can't influence which articles we pick. Otherwise its errors would be in the demo articles by construction.
- **Count errors the auditor's issue types can detect, in the city's own unit.** Formatting fixes (Article 26: bullet order, capitalization, figure placement) and the TA 454 missing footnotes (only visible by comparing all 17 affected articles) are documented but not testable here. "The city's unit" means one line-item fix in the summary, not each repeated instance.

Counts from the April 2025 summary and redline:

| Article | In-scope documented errors (city items) | Instances | Notes |
|---|---|---|---|
| **53 East Boston** | **5**: §53-4 district names; Table A fn 2; accessory-use rename; Tables H–M footnote refs; §53-29.4 self-reference | 26 | mixed classes |
| **65 Dorchester** | **2**: Table C mislabeled rear-yard columns; missing rows for 2F-3000 and 3F-D-4000 | ~4 | the dimensional tables exercise features 0 and 1 |
| 50 Roxbury | 1: "see Article 2A" (article no longer exists) | 11 | one copy-pasted error; trivial for the TOC check |
| 51, 66, 68 | 1 each: footnote reference / citation | 1–2 | 68 has the wrong-article "67-32" |
| 8, 60, 79 | 1 each | 1–3 | 8 is citywide and large |
| 26 | 0 in scope (3 formatting) | n/a | |

**Result: Article 53 + Article 65**, provided both parse cleanly from the saved format. If 65 doesn't parse cleanly, the fallback is 68: it ties the remaining articles at 1 and contributes the only wrong-article citation.

Counting raw instances instead would pick 53 + 50. I rejected that because 50's 11 instances are a single repeated error that one regex catches, which would inflate recall without testing anything new.

**Article 53** dominates the April 2025 corrections. From the redline:

| # | Location (pre-correction) | Error | Class |
|---|---|---|---|
| 1–3 | §53-4 ¶1–3 | Headings define "EBR-2.5", "EBR-3", "EBR-4", but the body text says "EBR-1", "EBR-2", "EBR-3" | reference to an undefined district code / internal inconsistency |
| 4 | Table A fn 2 | Footnote rewritten for clarity (EBR-3 occupancy) | ambiguity |
| 5–9 | Tables A–E | "Accessory Family Day Care Home" renamed to "…Child Care Home" to match the citywide childcare definitions | stale term (detectable only if definitions are indexed) |
| 10–25 | Footnotes of Tables H, I, J, K, M | 16 section references off by two after renumbering, e.g. "Sections 53-6 through 53-8 (Regulations Applicable on Tidelands…)" → "53-8 through 53-10"; "53-17" → "53-19" (CFROD); "53-19" → "53-21" (Table 2); "53-12.3" → "53-14.3"; "53-15.3" → "53-17.3"; "53-26" → "53-28" | stale cross-reference: the target exists, but its heading doesn't match the cited title |
| 26 | §53-29.4 | "except as otherwise provided in this Section 53-27" inside §53-29 | self-reference mismatch |
| 27 | Table L | Missing Text Amendment 454 affordable-housing parking footnote | cross-article consistency; **out of scope** with two articles |

That is 26 in-scope instances in one article. They touch 5 of the summary's line items, 4 of them in scope. Most are cross-references, which tests feature 2 the hardest, as the brief predicted. Rows 1–3 and 26 can be caught deterministically.

Possible residual error: in the redline, Table K fn 1 reads "Notwithstanding any contrary provision of this **Table I**", inside Table K, and it was not marked for correction. If it still appears in the current Municode text, it makes a good demo moment: an error the city's own pass missed. Confirm it against the current text before claiming it.

**Article 65** adds dimensional-table richness for features 0 and 1, plus documented errors of different types:
- Table C has mislabeled rear-yard columns.
- Dimensional rows are missing for the mapped subdistricts 2F-3000 and 3F-D-4000. This can be caught deterministically as "district established but has no dimensional row", if §65's establishment section lists them.
- Table F is missing the TA 454 footnote.

Both articles are neighborhood articles with a bounded geography: East Boston is ZIP 02128; Dorchester is 02121, 02122, 02124, and 02125. That lets feature 4 filter permits and violations to the area the article actually governs, which makes the heuristic much tighter.

The wrong-article class (the "67-32" error in Article 68) is still covered by deterministic rule §5.3(c), and by planted cases if 68 isn't loaded.

#### Reference-only corpus (indexed, not audited)
- **Article 2 definitions (included).** Indexed so that `get_definition` and the skeptics can use them; never audited, and no findings are raised against it. This puts rows 5–9 of the table above in reach.
- A code-wide table of contents (article and section numbers plus headings only). This lets the tool resolve references to other articles, e.g. "Article 2A (which no longer exists)" from the Article 50 correction. You save it from Municode's TOC by hand.

### 3. Sources and formats

| Source | How obtained | Used for | Terms |
|---|---|---|---|
| Boston Zoning Code, current text of Articles 53, 65 (+2, TOC) | You save the pages by hand in a browser as **HTML** into `data/corpus/current/` and `data/corpus/reference/`. HTML keeps `<table>` elements, section anchors, and links. | Clean-text runs, false-alarm eval | No automated access to Municode (decided). Saved pages stay local (§4.3). |
| Pre-correction text, development set | Reverse-apply the April 2025 Planning Department redline PDF to the saved current text (§4.2). Municode version history is not used (decided). | Dev eval (§9.1) | bostonplans.org public documents |
| Pre-correction text, held-out set | Built during the day by the separate session into `../zoning-auditor-sealed/` (§9.2) | Held-out eval | bostonplans.org |
| April 2025 summary + redline PDFs | Manual download (done once for this spec) | Dev ground truth | public |
| Violations, permits | `tools/fetch_open_data.py` pages through the brief's `datastore_search_sql` endpoints for all rows since 2024-01-01 and writes CSVs to `data/raw/` once. It selects only the brief's columns, so no street addresses are pulled. The brief's `LIMIT 100` is replaced by paging, because 100 rows is too few for per-work-type counts. | Feature 4 | Analyze Boston open data. License noted from the dataset page at download. |
| Somerville SZO | You save the relevant articles by hand from the encodeplus viewer. The report shows only quoted excerpts, with a citation and a link; full text is never republished. | Feature 5 | You check encodeplus's terms when saving. If they prohibit saving and quoting, use Cambridge as the Massachusetts city (decided). |
| Out-of-state city | **Minneapolis (Title 20) by default**, saved by hand from Municode. It is the tie-break pick, and I infer its saved HTML will reuse the Boston ingest without a new parser. Portland, OR (Title 33) is the alternative. Excerpts only, cited and linked, as for Somerville. | Feature 5 | If the chosen city's terms prohibit saving and quoting, switch to the other city (decided). |
| Boston.gov / Mass.gov pages | Linked from the report only, never copied | Context | n/a |

`ingest.py` reads Municode saved HTML only, for Boston and Minneapolis alike. Somerville's encodeplus HTML gets its own small adapter that produces the same `Section` and `Table` types. PDFs are read only by `tools/unredline.py`.

## Architecture

### 4. Architecture

#### 4.1 Shape

Plain Python drives every stage. Models are called only inside narrow, single-purpose steps. Each step is a smolagents `ToolCallingAgent` that sees a handful of sections, can call read-only retrieval tools over MCP, and must end with a JSON answer that the harness parses with pydantic.

```
corpus (HTML) ──► ingest ──► index ─────────┬──────────────► find ──► verify ──► findings ──► report_data.json ──► report/ (Next.js static export)
                    │          sections     │  structured      │       quote check   dedupe                              labels.json
                    │          tables       │  deterministic   │       skeptic       trace                                │
                    │          xrefs        │  model finders   │       (agent)       funnel                               ▼
                    │          FTS index    │  (agents)        │                                                        evals
                    └──► extract ──► rules ─┘
                         tables: code
                         prose: agent + quote check
                                               MCP server (read-only tools) ◄── every agent
```

Changes from the suggested architecture, with reasons:

1. **No top-level "auditor agent" deciding what to do.** The harness is the auditor; agents are leaf calls. A planning agent adds nondeterminism and cost and makes the funnel harder to count. The deliverable is still an auditor that runs end to end (`auditor run`).
2. **Two quote types, both verified by code.** A `TextQuote` is a character span in a section. A `CellQuote` is a (table, row label, column header, cell text) tuple checked against the parsed table. A table value like "35" is meaningless as a text span; the row and column are the citation.
3. **Confidence comes from the path, not from the model.** The model never states a confidence number. Confidence is a function of how the finding was produced (§6.4).
4. **Cross-reference checks compare titles, not just existence.** In Article 53 every stale target *exists*: §53-8 is a real section, just not the Tidelands section the citation names. The parenthetical title after a reference ("(Regulations Applicable on Tidelands…)") is the signal, and comparing it to target headings is deterministic.
5. **LLM response cache.** Every model call is cached on disk, keyed by (model id, messages, tool schemas). This makes the demo replay offline and makes eval reruns free.
6. **The report is a Next.js static export.** Python writes one `report_data.json` per run, with its shape defined by pydantic. TypeScript types are generated from that schema. `next build` with `output: 'export'` turns it into static files. Next.js documents static exports as needing only a static file server, with no Node server (read via Context7, Next.js v16.2.9 docs). Review decisions live in localStorage and are exported as `labels.json`. The only process involved is a loopback-only static file server; there is no write endpoint, so no auth question (§8).

#### 4.2 Pre-correction corpus

All pre-correction text comes from the Planning Department redline PDFs. `tools/unredline.py` builds it:
- pdfplumber reads the redline and classifies each character by fill color. Measured on the April 2025 redline: deletions are red (1, 0, 0) and 93% carry a strike line; insertions are green (0.22, 0.46, 0.11) and almost never underlined (about 4%). Line geometry alone fails, because table borders cross the midline of about 6% of unchanged characters. Runs are grouped in pdfplumber's native character order, which keeps overlapping deleted and inserted layers contiguous.
- This produces a list of (article, location, inserted text → deleted text) edits.
- The script applies them in reverse to the current article text and fails loudly if any inserted string is not found exactly once.
- The output is hand-spot-checked against the redline images for every edit in Articles 53 and 65.

Text extraction alone cannot tell struck from inserted text (pypdf prints both, e.g. "Section 67-32 Section 68-33"), so per-character color is required.

Risk: Article 53 may have been amended between June 2025 and now for unrelated reasons. Reverse-applying the redline then gives "current text minus the corrections", not the true historical text. That is acceptable for the eval as long as the report says so.

#### 4.3 Directory and artifact layout

Stages communicate through files, so each stage can be tested against fixtures before the stage upstream of it is real.

```
data/
  raw/                         # open-data CSVs from fetch_open_data.py (local only)
  sources/                     # redline and summary PDFs, saved by hand (local only)
  corpus/                      # saved HTML (local only)
    current/        53.html 65.html …         # audited as clean text
    pre2025/        53.html 65.html …         # dev eval input (April 2025 round)
    reference/      02.html toc.html          # indexed, not audited
  comparison/somerville/ minneapolis|portland/   # saved HTML (local only)
  worktype_map.csv             # hand-curated: permit worktype → regulated items (feature 4)
  agency_renames.csv           # hand-curated with citations (feature 2)
build/<corpus>/                # gitignored, reproducible
  sections.jsonl tables.jsonl xrefs.jsonl rules.jsonl search.sqlite
runs/<corpus>/<run_id>/        # local only
  candidates.jsonl trace.jsonl findings.json report_data.json export/rules.csv export/rules.json
  report/                      # built static site for this run (copied from report/out)
  spend.jsonl                  # tokens + USD per role and model, written as the run goes
llm_cache/                     # local only; the offline demo replays from it on this machine
evals/
  ground_truth/city_2025_04.yaml
  prompts/<role>.jsonl         # ~10 cases per role (§9.4)
  labels/                      # hand labels: extraction sample, false alarms, ambiguities, xrefs
  results.md                   # the summary table
src/auditor/ …                 # §5
report/                        # Next.js app (§8); package-lock.json committed
  src/generated/               # report-data.schema.json + report-data.ts, generated by `auditor schema`
tools/unredline.py tools/fetch_open_data.py
tests/

../zoning-auditor-planted/     # outside the repo; written by the separate session (§9.3)
../zoning-auditor-sealed/      # outside the repo; held-out set, unopened until task 10 (§9.2)
```

**What git holds.** Code, specs, configs, the hand-curated CSVs, `evals/` (keys hold only short `pre_text` excerpts), and generated report types. Everything marked "local only" is in `.gitignore`: saved code pages, PDFs, open-data CSVs, `build/`, `runs/`, and `llm_cache/`. All of these hold full code text or bulk data, and pushing them would republish it. A test fails if `git ls-files` lists any path under them (Property 8).

## Components and Interfaces

### 5. Module layout and interfaces

Python 3.12, managed with `uv`. Dependencies, all pinned to exact versions at task 1: `smolagents` (with its MCP and OpenAI extras; models are reached through OpenRouter's OpenAI-compatible API), `mcp`, `pydantic`, `beautifulsoup4`, `pdfplumber` (tools only), `pytest`, `hypothesis` (dev only, for the Correctness Properties). Search uses SQLite FTS5 from the stdlib; M0 confirms that FTS5 is compiled into the local Python. CLI uses `argparse`.

The report uses Node (v24.18.0 is installed locally, measured) and npm, with exact versions pinned in `report/package.json`: `next`, `react`, `react-dom`, `typescript`, `json-schema-to-typescript`. Context7 lists v16.2.9 as the newest indexed Next.js docs. Task 1 pins the current stable release from npm and reads the docs for that version. No UI kit and no Tailwind; styling is CSS Modules.

```
src/auditor/
  models.py            # every shared type (reviewed and frozen at task 1)
  ids.py               # canonical ID parse/format
  quotes.py            # normalize(), verify_text(), verify_cell()
  corpus.py            # Corpus: load build/<corpus>/*.jsonl, lookups
  ingest.py            # HTML → Section, Table
  xrefs.py             # extract references from text
  resolve.py           # deterministic reference resolution
  search.py            # FTS5 build + query
  extract_tables.py    # Table → Rule (no model)
  extract_prose.py     # Section → Rule via agent
  agents.py            # model factory, CachedModel, run_agent() → pydantic
  prompts/             # one .md per agent role
  mcp_server.py        # FastMCP, read-only tools
  find_contradictions.py
  find_xrefs.py
  find_ambiguities.py
  find_trips.py
  verify.py            # quote gate + skeptic agent
  findings.py          # dedupe, funnel, trace writer
  report_data.py       # run → ReportData (pydantic) → report_data.json; also writes its JSON Schema
  neutrality.py        # output lint
  cli.py
  compare.py           # feature 5
```

#### 5.1 Core types (`models.py`)

`src/auditor/models.py` is authoritative. It differs from the sketch below in these ways, all from the Task 1 review:
- **`SectionId` is validated** against the canonical id pattern; `ids.py` holds only `slug`.
- **`TextQuote.span: tuple[int, int] | None`** replaces `start`/`end`, and `CellQuote.position: tuple[int, int] | None` records (row, column). Both are set only by the quote checker. `is_verified(q)` reads them.
- **`Rule.needs_review` is derived** from `review_reason`. Item `other`, and numeric rules missing a value or unit, must carry a reason. A rule's quote must be verified.
- **`Verdict.quote_check` is gone.** The quote gate failed exactly when `quote_failures` is non-empty, and then `skeptic` is `not_run`. Reconciling quotes must be verified.
- **`Finding` enforces reportability.** It needs at least one verified quote and a verdict of `upheld` or `skipped`. `readings` are present for ambiguities and only for them, on both `Finding` and `Candidate`.
- **`Table` must be rectangular**, with unique column headers and row labels. `Corpus` rejects duplicate ids.
- **`Reference` and `XRef`.** `Reference` is a union of one small model per kind (`SectionRef`, `RangeRef`, `TableRef`, `DistrictRef`, and so on), told apart by class. Each is located by a verified quote. `XRef` is a verified quote plus a `Resolution`, which is what every rule emits, including the rules that don't start from a reference: (f) unused footnotes, (h), (i), and (j). `Resolution.detail` is the neutral, code-written claim. A header footnote mark is quoted by the row-0 cell under that header.

```python
SectionId = NewType("SectionId", str)   # "53-29.4", "53:TableH", "53:TableH:fn3"
DistrictCode = NewType("DistrictCode", str)  # "EBR-3", "2F-3000"

class Section(BaseModel):
    id: SectionId
    article: str                     # "53"
    heading: str                     # "Application of Dimensional Requirements"
    text: str                        # normalized display text
    parent: SectionId | None
    kind: Literal["article", "section", "subsection", "table_footnote", "table_note"]
    source: SourceRef                # file, anchor/page

class Table(BaseModel):
    id: SectionId                    # "53:TableH"
    article: str
    title: str
    columns: list[str]               # full header path joined, e.g. "Building Height Maximum | Feet"
    rows: list[TableRow]             # label + cells
    footnotes: dict[str, SectionId]  # "3" → "53:TableH:fn3"
    applicable_footnotes: list[str]  # from "Applicable Footnotes: (1), (5)"

class TableRow(BaseModel):
    label: str                       # "EBR-3 / Corner Lot" (row-header path)
    cells: list[Cell]

class Cell(BaseModel):
    text: str
    footnote_marks: list[str]        # "(4)" → ["4"]

class TextQuote(BaseModel):
    kind: Literal["text"] = "text"
    section_id: SectionId
    text: str
    start: int; end: int             # offsets into Section.text, set by quotes.verify_text

class CellQuote(BaseModel):
    kind: Literal["cell"] = "cell"
    table_id: SectionId
    row_label: str; column: str; text: str

Quote = Annotated[TextQuote | CellQuote, Field(discriminator="kind")]

class RegulatedItem(StrEnum):
    use_permission = auto(); building_height_ft = auto(); building_height_stories = auto()
    far = auto(); lot_area_min = auto(); lot_area_per_unit = auto(); lot_width_min = auto()
    lot_frontage_min = auto(); front_yard_min = auto(); side_yard_min = auto()
    rear_yard_min = auto(); rear_yard_occupancy_max = auto(); usable_open_space_min = auto()
    lot_coverage_max = auto(); parking_ratio = auto(); loading = auto(); dwelling_units_max = auto()
    other = auto()                   # always needs_review

class Rule(BaseModel):
    id: str                          # stable hash of (quote, district, use, item)
    district: DistrictCode | None    # None = article-wide
    use: str | None                  # use or dwelling type as written in the code
    item: RegulatedItem
    comparator: Literal["max", "min", "exact", "status"]
    value: Decimal | None
    unit: Literal["ft", "stories", "sqft", "ratio", "percent", "spaces_per_unit",
                  "spaces_per_1000sqft", "units", "units_per_acre"] | None
    status: Literal["A", "C", "F"] | None   # use tables: allowed / conditional / forbidden
    conditions: list[str]            # verbatim condition fragments
    footnotes: list[SectionId]
    quote: Quote                     # required
    source: Literal["table", "prose"]
    needs_review: bool
    review_reason: str | None

class XRef(BaseModel):
    id: str
    source_id: SectionId
    raw: str                         # "Section 53-8.4"
    span: tuple[int, int]
    target_kind: Literal["section", "section_range", "table", "footnote", "article",
                         "district", "agency", "self_section", "self_table"]
    target: str
    cited_title: str | None          # text of the trailing parenthetical, if any
    resolution: Resolution

class Resolution(BaseModel):
    status: Literal["ok", "missing", "title_mismatch", "self_mismatch",
                    "cross_article_shadow", "undefined_district", "footnote_missing",
                    "footnote_unused", "external_unchecked", "needs_judgment"]
    resolved_id: SectionId | None
    title_match_id: SectionId | None # a section whose heading matches cited_title
    detail: str                      # code-generated, factual
```

Findings and their path:

```python
IssueType = Literal["contradiction", "xref", "ambiguity", "trip"]
Origin = Literal["deterministic", "structured", "model_finder"]

class Candidate(BaseModel):
    id: str
    type: IssueType
    origin: Origin
    quotes: list[Quote]              # unverified as proposed
    claim: str                       # one neutral sentence
    readings: tuple[str, str] | None # ambiguity only
    payload: dict                    # type-specific (xref id, rule ids, stats)

class Verdict(BaseModel):
    candidate_id: str
    quote_check: Literal["pass", "fail"]
    quote_failures: list[str]
    skeptic: Literal["upheld", "refuted", "uncertain", "skipped"]
    skeptic_reasoning: str | None
    reconciling_quotes: list[Quote]  # exceptions the skeptic found (verified too)
    sections_retrieved: list[SectionId]

class Finding(BaseModel):
    id: str                          # dedupe key hash
    type: IssueType
    origin: Origin
    quotes: list[Quote]              # all verified; len ≥ 1 (validator)
    claim: str
    readings: tuple[str, str] | None
    confidence: Literal["high", "medium", "low"]
    candidate_ids: list[str]         # merged duplicates
    verdict: Verdict
    neutrality_flags: list[str]

class TraceEvent(BaseModel):         # one line per stage transition in trace.jsonl
    run_id: str; candidate_id: str; stage: str; at: datetime
    data: dict                       # prompts hash, tool calls, model output, reasons
```

`Finding` has a model validator that rejects an empty `quotes` list. `findings.py` builds a `Finding` only from a `Verdict` with `quote_check == "pass"` and `skeptic in {"upheld", "skipped"}`. Each issue type has exactly one place where `skipped` is allowed (§6.3).

#### 5.2 Quote verification (`quotes.py`)

```python
def normalize(s: str) -> str          # NFKC (folds ligatures like "ﬁ"), curly→straight quotes,
                                      # hyphen/dash variants U+2010–U+2014, U+2212 →"-", collapse whitespace, strip.
def verify_text(q: TextQuote, corpus: Corpus) -> TextQuote | QuoteError   # sets start/end
def verify_cell(q: CellQuote, corpus: Corpus) -> CellQuote | QuoteError
```

"Verbatim" means an exact substring match after `normalize`, and nothing looser. No fuzzy matching: a quote that is off by one word fails. The quote-faithfulness eval measures the same function.

#### 5.3 Index (`ingest.py`, `xrefs.py`, `resolve.py`, `search.py`)

```python
def ingest(html_path: Path) -> tuple[list[Section], list[Table]]
def extract_xrefs(section: Section) -> list[XRef]       # resolution unset
def resolve(xrefs: list[XRef], corpus: Corpus, toc: Toc) -> list[XRef]
def build_search(sections: list[Section], db: Path) -> None
def search(db: Path, query: str, k: int) -> list[SectionId]
```

The reference grammar is a set of regexes, tested on real strings from the redline. Each kind of reference has its own typed variant (`Reference` is a discriminated union on `kind`), so resolution never re-parses a target string.
- Single sections: "Section 53-29.14", "Section 80B-3.1a", "Section 23-9.a".
- Lists: "Sections 53-8 and 53-10", "Sections A, B, and C", "Section 80B-2 or 80E-2". Each listed section becomes its own reference.
- Ranges: "Sections 53-8 through 53-10".
- Articles: "Article 2A".
- Tables: "Table H", and table-in-section scope, "Table 2 in Section 53-21".
- Self-references: "this Section 53-29.13" and "this Table I", with either case of "this".
- Footnote marks: "(3)" in table cells and in column headers, and "Applicable Footnotes: (1), (5)".
- District codes: tokens in a district family the article establishes. A family is the prefix before the first "-" or "/" ("EBR", "2F"), or the letters of a one-part code ("S" for "S0").
- Agency names: from `agency_renames.csv`. Added with `judge_xref` (task 4.4); there is no agency extractor before then.
- Cited titles: a parenthetical immediately after the reference counts only if it reads as a title, meaning it has at least two words and is not "(as amended …)". Case doesn't matter, because the code writes "(concerning regulations applicable on Tidelands)" in lowercase. Single letters and numbers in parentheses, like "(a)" or "(3)", are not titles.

Resolution rules run in this order. All are deterministic.
- (a) **self_mismatch**: "this Section X" where X is not the containing section or an ancestor of it; "this Table X" where X is not the containing table. The claim names the containing section or table.
- (b) **missing**: the target's article is loaded or listed in the TOC, and the target section does not exist there.
- (c) **cross_article_shadow**: the target is in article M, the source is in article N ≠ M, and article N has a section whose heading matches `cited_title`. This catches "Section 67-32" cited from Article 68.
- (d) **title_mismatch**: the target exists (loaded, or listed in the TOC), `cited_title` is present, and its similarity to the target heading is below a threshold. `title_match_id` records the best-scoring section whose heading does match, if any. Similarity is token-set Jaccard on `normalize`d words. The threshold is provisional until ingest gives real headings, and is re-tuned on the dev set then. For a range, the cited title must match the heading of every section in the range at the endpoints' depth. This is provisional: check it against the real Article 53 headings after ingest, because a correct range whose sections have different headings would be flagged.
- (e) **undefined_district**: a token in an established family that the article does not establish.
- (f) **footnote_missing / footnote_unused**: a cell or header mark with no footnote, or a footnote that no cell, header, or "Applicable Footnotes" line references.
- (g) **scope_mismatch**: "Table N in Section X" where the article's Table N is not under Section X. The detail names where Table N is.
- (h) **definition_mismatch**: a paragraph whose heading defines a district code, e.g. `East Boston Residential-3 ("EBR-3") Subdistricts.`, but whose body uses a different code of the same family as its subject. This catches §53-4 rows 1–3 of §2.
- (i) **undefined_term**: a use name in a use-table row label that is not a defined use term. Defined terms come from Article 2 definitions plus the use names in Article 8 Table A. This catches rows 5–9 of §2.
- (j) **district_without_row**: a district the article establishes that has no row in any of the article's dimensional tables. This catches Article 65's missing 2F-3000 and 3F-D-4000 rows.
- (k) **external_unchecked**: the target's article is neither loaded nor in the TOC. A target listed in the TOC but not loaded is checked against its TOC heading under (d), and is otherwise ok.
- (l) **needs_judgment**: agency names in the rename table (task 4.4).

Not covered by any deterministic rule, so left to the model finders and the dev eval:
- the Table A fn 2 ambiguity (row 4 of §2);
- references with no cited title whose target exists, e.g. "Section 53-15.3" in Table K fn 3;
- column headers mislabeled relative to sibling tables (Article 65 Table C).

#### 5.4 Extraction (`extract_tables.py`, `extract_prose.py`)

```python
def rules_from_table(table: Table, corpus: Corpus) -> list[Rule]       # no model
def rules_from_section(section: Section, runner: AgentRunner) -> list[Rule]
```

Tables: a hand-written `COLUMN_ITEMS` mapping takes normalized column headers to `(RegulatedItem, comparator, unit)` for the two articles' header vocabularies. Any unmapped column produces rules with `item=other, needs_review=True`. A cell that does not parse as a number or N/A/none produces `needs_review=True` with the raw text preserved; we never guess a value. Use tables produce `status` rules.

Prose: the agent sees one section plus its definitions, returns `list[RuleDraft]` (Rule without id/quote offsets), and each draft's quote goes through `verify_text`. A draft whose quote fails is dropped and logged ("no quote, no record"). The model is told to set `needs_review` whenever the value, unit, district, or condition is not stated in the quoted text itself.

Exports: `export/rules.csv` and `export/rules.json`. The CSV has one row per rule, with quote text, section id, and a Municode link column. The JSON carries the self-identification and source metadata block.

#### 5.5 Agent runner (`agents.py`)

```python
class CachedModel(Model):        # wraps any smolagents Model; caches generate() on disk; meters spend
def make_model(tier: Literal["judge", "extract"]) -> Model
    # smolagents OpenAIModel(api_base="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    # env: AUDITOR_MODEL_JUDGE, AUDITOR_MODEL_EXTRACT (OpenRouter ids); AUDITOR_OFFLINE=1 → cache-only, miss = error
def run_agent(role: str, task: str, inputs: dict, out: type[T], max_steps: int = 6) -> T | AgentFailure

class BudgetExceeded(Exception)  # raised before a live call that would start past the cap
```

As built in task 3 (authoritative over the sketch above):
- `make_model(role, run_dir)` picks the tier from `ROLE_TIER`. `run_agent(role, task, out, *, build_dir, run_dir, max_steps)` returns `T | AgentFailure`, with no `inputs` argument; the task string carries the inputs.
- `BudgetExceeded`, an offline cache miss, and a missing `usage.cost` propagate out of `run_agent` as themselves. smolagents wraps model errors, so `run_agent` unwraps them.
- `AUDITOR_RUNS_ROOT` (default `runs/`) and `AUDITOR_CACHE_DIR` (default `llm_cache/`) are settings. A run dir outside the runs root is refused, so the day cap always sums every run.
- Each agent run appends one `TraceEvent` to `run_dir/trace.jsonl`, with the tool calls, their arguments, and their outputs (truncated).
- The MCP server process gets only the environment it needs, not the API key.
- The pinned stack is mcp 1.30.0 with mcpadapt 0.1.20. mcpadapt still imports the mcp 1.x client name, so mcp 2.x breaks smolagents' MCP tools.

Model tiers. Each role has a fixed tier in a `ROLE_TIER` dict, so swapping a model means changing one env var:
- `extract`: `extract_prose` and `compare_match`. Default is a Haiku-class model.
- `judge`: every finder, every skeptic, `judge_xref`, and `compare_support`. Default is a Sonnet-class model.
- Model ids (decided): `anthropic/claude-haiku-5.5` for `extract` and `anthropic/claude-sonnet-5.5` for `judge`. These are OpenRouter ids, checked against OpenRouter's public models list (both support tool calling). Set in `.env.example` at task 1.

Spend:
- `CachedModel` reads `usage.cost` from each live response. OpenRouter returns the cost charged in credits on every non-streaming response, with no extra parameters (OpenRouter usage-accounting docs, read via Context7). smolagents keeps the raw response on `ChatMessage.raw` (checked in smolagents 1.26.0 source). There is no local price table. Agents run non-streaming so the cost is always present; a live response without `usage.cost` is an error.
- It appends `{role, model, input_tokens, output_tokens, usd, cached: bool}` to `runs/…/spend.jsonl`.
- Cache hits are logged at $0, so a replayed run shows its true cost: zero.
- `AUDITOR_BUDGET_USD=20` is a hard cap per run, and `AUDITOR_BUDGET_TOTAL_USD=100` is a cap for the day, on your current API account, summed from every `spend.jsonl`. On the next live call past either cap, `CachedModel` raises `BudgetExceeded`. The harness then stops the run, writes partial outputs, and marks the funnel as truncated. Nothing silently skips work.
- A spend line goes to stderr after every 25 live calls and at the end of the run, and `results.md` gets one spend row per eval run.

- `run_agent` builds a `ToolCallingAgent` with the MCP tool collection, the role prompt from `prompts/<role>.md`, and `max_steps`.
- It parses the final answer with `out.model_validate_json`. A parse failure returns `AgentFailure`, which the harness logs as a rejected candidate, never a crash.
- Every tool call and its output goes to the trace.
- Roles: `extract_prose`, `find_contradiction`, `find_ambiguity`, `judge_xref`, `skeptic_contradiction`, `skeptic_xref`, `skeptic_ambiguity`, `compare_match`, `compare_support`.
- Every prompt includes a fixed preamble: answer only from tool outputs and the given text; never compute values not present in quotes; describe, don't recommend; take no position on density, housing, or any policy outcome.

#### 5.6 MCP server (`mcp_server.py`)

FastMCP over stdio, started by `run_agent`. Every tool is read-only and backed by `Corpus`; no tool writes anything.

| Tool | Signature | Returns |
|---|---|---|
| `get_section` | `(section_id: str)` | heading, text, parent, children ids |
| `get_table` | `(table_id: str)` | title, columns, rows, footnote ids |
| `search_sections` | `(query: str, k: int = 5)` | ids + headings + 200-char snippets |
| `related_sections` | `(section_id: str, k: int = 5)` | ids sharing district/use/item via rules |
| `get_rules` | `(district: str \| None, use: str \| None, item: str \| None)` | Rule records |
| `get_definition` | `(term: str)` | definition text + id from Article 2 |
| `resolve_reference` | `(text: str, from_section: str)` | Resolution |

### 6. Finders and verification

#### 6.1 Candidate generation

**Contradictions** (`find_contradictions.py`)
- Structured: group rules by `(district, use, item)` and flag a group whose values or statuses differ. Before flagging, code removes pairs whose `conditions` are disjoint by a simple, explicit check: both have conditions, and those conditions name different subdistrict variants (Corner Lot vs Mid-Block Lot) or different unit-count bands. Removed pairs are logged, not silently dropped.
- Model finder: for each section that yields rules or has prose obligations ("shall", "no … shall", "may not"), retrieve up to 4 neighbors via `related_sections`, falling back to `search_sections` on the heading. The `find_contradiction` agent sees at most 5 sections and returns 0–3 candidates with quotes. Pairs are deduped by unordered section set before calling, so each neighborhood is examined once.
- Budget: log the number of finder calls; target ≤ 150 per article.

**Cross-references** (`find_xrefs.py`)
- Every `XRef` with status (a)–(f) becomes a deterministic candidate. Its claim is code-generated text, e.g. "§53-29.4 refers to 'this Section 53-27' but appears in Section 53-29." `title_match_id`, when present, is shown as a fact ("A section titled '…' exists at §53-10"), not as a fix.
- (h) `needs_judgment` goes to the `judge_xref` agent, e.g. whether "Boston Redevelopment Authority" refers to a renamed body in this context. The agent sees `agency_renames.csv` rows, each with its citation.
- (g) is counted in the funnel but produces no candidate.

**Ambiguities** (`find_ambiguities.py`)
- The `find_ambiguity` agent runs per section (plus its definitions). It must return the quoted span and two readings, each a full sentence a reasonable applicant could hold, plus what each reading implies in the code's own terms. Ambiguity is not "unclear writing in general": the prompt requires the two readings to yield different outcomes for some applicant.

**Where people trip** (`find_trips.py`). See §7.

#### 6.2 Verification (`verify.py`)

```python
def verify(c: Candidate, corpus: Corpus, runner: AgentRunner) -> Verdict
```

1. **Quote gate (code).** Every quote goes through `verify_text`/`verify_cell`. Any failure means `quote_check="fail"`; the candidate stops here and is logged with the failing strings.
2. **Skeptic (agent).** A separate role prompt that argues against the candidate. It asks: Can both provisions be followed at once? Does an exception, footnote, "notwithstanding" clause, overlay, or definition reconcile them? Is the reference actually correct given the article's structure? Is one of the two readings unreasonable? It may retrieve more sections via MCP. It returns `upheld | refuted | uncertain`, its reasoning, and any `reconciling_quotes`, which are quote-checked too. A `refuted` verdict without a verified reconciling quote or verified structural evidence is downgraded to `uncertain`, because the skeptic must also show its quotes.

#### 6.3 Which candidates skip the skeptic

Only the deterministic cross-reference statuses (a) self_mismatch, (b) missing, (e) undefined_district, (f) footnote integrity, and (h) definition_mismatch. These are facts the code proves about the text. (c) cross_article_shadow, (d) title_mismatch, (g) scope_mismatch, (i) undefined_term, and (j) district_without_row go to `skeptic_xref`: the skeptic can find, for example, that a cited title is a legitimate alias, that a term is defined in an article we haven't loaded, or that a district's dimensions sit in another table.

#### 6.4 Confidence (derived)

| Path | Confidence |
|---|---|
| deterministic (a)(b)(e)(f), quote pass | high |
| deterministic (c)(d) + skeptic upheld | high |
| structured contradiction + skeptic upheld | medium |
| model finder + skeptic upheld | medium |
| any rule involved has `needs_review` | low (shown with the review flag) |
| ambiguity + skeptic upheld | medium |
| trip | low (always labeled heuristic) |

Reported: `upheld`/`skipped`. The report's "Not reported" appendix lists `uncertain`, `refuted`, and quote failures, with reasons, so the whole funnel stays inspectable.

#### 6.5 Findings store (`findings.py`)

- Dedupe key: `type` plus the sorted set of `(section_id or table_id, normalized quote text)`. Two contradiction candidates found from either side of the same pair collapse into one finding, and the finding keeps both `candidate_ids`.
- The trace is append-only JSONL. `funnel(run) -> dict[IssueType, Funnel]` computes candidates → quote-passed → upheld → reported from the trace alone. The eval reads the same function, so the report and the eval cannot disagree.

#### 6.6 Neutrality lint (`neutrality.py`)

A regex list ("should", "recommend", "we suggest", "better", "worse", "density", "affordab…" outside quotes) runs over every model-written `claim`, reading, and summary. A hit adds `neutrality_flags`, which the report shows. It does not block the finding; a human decides. It also gets a line in the eval table.

### 7. Feature 4: where people trip

Inputs: full 2024+ CSV exports of violations and approved permits, downloaded once by `tools/fetch_open_data.py` into `data/raw/` and never fetched at runtime.

1. Filter to the article's ZIPs (§2).
2. Aggregate permits by `worktype` and violations by `description`. Then find violation descriptions matching "Failure to Obtain Permit" (exact strings listed after inspecting the data, not guessed) and join them to work types through the violation text where possible. If the description doesn't name a work type, the violation is counted only at the area level.
3. `data/worktype_map.csv` maps about 20 high-volume work types to `RegulatedItem`s (e.g. addition → setbacks, FAR, height; roof deck → height, roof structures; driveway/curb cut → parking). Each row has a one-line rationale. It is hand-curated and reviewable. A model may draft it, but a human commits it.
4. For each work type: the rules in the article for those items (quotes from `rules.jsonl`), the counts, and any reported findings touching the same items. The overlap with findings is the main signal.

Each trip finding is labeled in the UI and export: "Heuristic. Violations data is building-code enforcement. This links patterns to provisions as evidence of possible confusion, not proof." Quotes come from the zoning provisions; the counts come from the data, with query parameters and the download date.

### 8. Report and review (Next.js static export, `report/`)

The report is for planning staff reviewing findings, so the job of each page is to put the quoted passages and the code text one click apart. For whoever maintains it next, the deal is this: Python owns every fact, and the TypeScript side only renders.

#### 8.1 Data contract

`report_data.py` builds one `ReportData` model per run and writes `runs/…/report_data.json`. It contains:
- **`meta`**: the self-identification text, corpus, run id, commit, model ids, date, and `schema_hash`.
- **`funnel`**: per issue type.
- **`findings`**: each with verified quotes, verdict, path, and confidence.
- **`not_reported`**: each candidate with the stage and reason it stopped.
- **`rules`**.
- **`sections`**: every section any finding or rule cites, with id, `slug`, heading, text, `quote_spans`, and Municode URL.
- **`trips`**.

URL slugs come from `ids.slug()` in Python and ship in the data. TypeScript never re-derives an id or a slug.

**Types come from one schema.** `auditor schema` writes `report/src/generated/report-data.schema.json` from `ReportData.model_json_schema()`, then runs `json-schema-to-typescript` to produce `report-data.ts`, which exports the types and `SCHEMA_HASH`. Both generated files are committed and never edited by hand. Pydantic unions become TypeScript discriminated unions, e.g. `Quote` on `kind`, and components switch over them exhaustively with a `never` check.

**The boundary.** `report/src/lib/load.ts` reads `process.env.REPORT_DATA` once at build time. It fails the build if `meta.schema_hash !== SCHEMA_HASH`, with the message "run `auditor schema`". That is the only validation on the TypeScript side. Pydantic already validated the data when writing it, and the hash catches the one way this boundary breaks: Python and TypeScript drifting apart. Components trust the types.

#### 8.2 Build and view

- **Build.** `auditor report <run_dir>` runs `next build` in `report/` with `REPORT_DATA` set, then copies `report/out/` to `<run_dir>/report/`. `next.config.ts` sets `output: 'export'` and `trailingSlash: true`.
- **View.** `auditor serve <run_dir>` runs `python -m http.server 4173 --bind 127.0.0.1 --directory <run_dir>/report`.
- **Why a server at all.** The Next.js docs describe static exports as hosted on a static web server. I didn't find docs on opening them from `file://`. I'm guessing that the absolute `/_next/` asset paths break there; task 8 checks this. If `file://` works, `serve` is dropped.
- **Security.** The server binds to loopback only, serves read-only static files, and has no write routes. Nothing is reachable from the network, so it needs no auth.
- **Fixed port.** localStorage is scoped per origin, including the port. A fixed port keeps review state stable across sessions.
- **Offline.** No CDN, no remote fonts (system font stack, no `next/font/google`), and no `next/image`; the default image loader is unsupported in static export per the docs, and we have no images. The task 11 gate runs with Wi-Fi off.

#### 8.3 Routes

All routes are static. Dynamic segments use `generateStaticParams()` over `ReportData`, as static export requires per the docs.

| Route | Content | Build order |
|---|---|---|
| layout (every page) | Self-identification banner; corpus, run id, and date; skip link | 1 |
| `/` | Funnel per issue type (candidates → quote-verified → reported), with each count linking to its list; review progress; links to the `rules.csv` and `rules.json` downloads | 1 |
| `/findings/[type]/` | Findings of one type; client-side filters for confidence and review flag | 1 (filters 5) |
| `/finding/[id]/` | Claim; quotes side by side, each with section id, linking to `/code/[slug]/#q-<n>`; ambiguity readings; confidence and review flags; the path (candidate → quote check → skeptic reasoning, with the retrieved sections linked); for trips, the heuristic label, counts, and query parameters; the review panel | 1 |
| `/code/[slug]/` | Full section text with every reported quote highlighted and anchored, links back to findings, Municode link | 4 |
| `/rules/` | Extracted records, filterable by district, item, and `needs_review`; CSV and JSON downloads (copied into `public/` at build) | 2 |
| `/not-reported/` | Dropped candidates with stage and reason | 3 |
| `/review/` | Counts by decision; Export labels; Import labels (restores state from a file) | 1 (part of the review panel) |

**Build order.** Every route is built. Within the report, the order is:
1. The pages that carry findings: layout, `/`, `/findings/[type]/`, `/finding/[id]/`, and `/review/`.
2. `/rules/`.
3. `/not-reported/`.
4. `/code/` with highlighting.
5. Filters.

Until `/code/` exists, the finding detail page shows each cited section's full text in a `<details>` block plus its Municode link. Once `/code/` lands, that block is replaced by links into `/code/`, so there is never a build in which findings lack the code text (Requirement 14.4).

#### 8.4 Review state

- **One client component.** `ReviewPanel` uses a `useReview(findingId)` hook backed by localStorage key `auditor:<run_id>:labels`. Keying by run keeps runs from mixing.
- **Decision type.** `{kind: 'confirmed' | 'rejected' | 'unsure', note: string, at: string}`. An undecided finding has no entry, so "no decision" can't be represented any other way.
- **Export.** Downloads `labels.json` (`{run_id, labels: {finding_id: Decision}}`). `auditor import-labels` copies it into `evals/labels/`.

#### 8.5 Accessibility

- Semantic landmarks and headings; decision controls are `<button>`s.
- Quotes are `<blockquote cite>` and highlights are `<mark>`.
- Visible focus; full keyboard use.
- Decisions are announced through an `aria-live` region.
- Filters are labeled form controls.
- Color is never the only signal for confidence or decision.

#### 8.6 Size

About 600 lines of TypeScript, excluding generated files.

### 10. Feature 5: comparison with other codes

Built last in the priority order (`tasks.md`, task 9), before the freeze. It reads only reported findings, so it cannot change the held-out result.

- Index Somerville and the second city (Minneapolis by default, Portland if Minneapolis's terms prohibit saving and quoting; §3) for articles covering the same topics: residential dimensional standards, parking ratios, and accessory uses. They go through the same `ingest`/`extract` pipeline with a per-jurisdiction `COLUMN_ITEMS` map. Equivalent rules are matched by `RegulatedItem`, use, and a comparable district class; the `compare_match` agent sees candidate rules only.
- For each **reported** finding of type contradiction, ambiguity, or xref whose provision maps to a rule item:
  - quote the matched text, with its citation, verified verbatim against the other code's corpus;
  - write a one-sentence neutral summary;
  - run `compare_support`, a separate judge prompt that answers "does the quoted text support this summary? yes/no + why". A "no" drops the comparison.
  - attach a transferability note built from a fixed, cited template: "Boston's zoning is enacted under St. 1956, c. 665 (the Boston Zoning Enabling Act), not G.L. c. 40A [cite]. Somerville's ordinance is enacted under c. 40A [cite SZO §1]. Whether a similar provision is permitted under Boston's act needs legal review." For the out-of-state city: "This tool cannot judge transferability from [Minnesota/Oregon] law." The model may add one sentence on topic-specific concerns, or none.
- Comparisons are rendered as "How other codes word this (options, not recommendations)".

## Error Handling

Guards sit at boundaries only. Code inside the boundaries trusts the types (design §5.1).

| Boundary | Failure | Behavior |
|---|---|---|
| Corpus file → `ingest` | Unparseable table or section | `ingest` fails loudly with the file and anchor. A run never continues on half-parsed text. |
| Redline → `unredline` | An inserted string not found exactly once | The script exits non-zero and lists every failing edit |
| Model answer → `run_agent` | JSON that doesn't validate against the role's pydantic model | Returns `AgentFailure`; the trace records a rejected candidate, and the run continues |
| Model quote → `quotes.verify_*` | No exact match | `QuoteError`; the candidate or rule draft is dropped and logged (Requirements 3.4, 4.2) |
| Live call → `CachedModel` | Over a cap | `BudgetExceeded`; partial outputs are written and the funnel is marked truncated (Requirement 12.3) |
| Live call → `CachedModel` | Cache miss while offline | Error naming the role and cache key |
| `report_data.json` → `load.ts` | Schema hash mismatch | The build fails with "run `auditor schema`" (Requirement 14.6) |
| CLI → `--final` | Not at the `heldout-freeze` tag, a dirty tree, or no `READY` | Refuses, naming the unmet condition (Requirement 17.2) |

## Correctness Properties

Each property is a test over generated or fixture inputs. Property tests use `hypothesis`, pinned in the dev dependencies.

- **Property 1: Quote round trip.** For any Section and any substring `q` of its text, `verify_text` accepts `q`, and `normalize(section.text[start:end]) == normalize(q)`. For any string not in the normalized text, it rejects. `normalize` is idempotent. **Validates: Requirements 4.1**
- **Property 2: No quote, no record.** Every Rule in `rules.jsonl` and every Finding in `findings.json` has at least one Quote, and each one passes `verify_*` against its Corpus. This runs on every run's outputs, not only on fixtures. **Validates: Requirements 3.4, 4.2, 4.3**
- **Property 3: Dedupe is order-independent and idempotent.** For any list of Candidates, the Findings are the same under permutation and under duplicating any Candidate. A contradiction proposed from either side collapses to one Finding. **Validates: Requirements 9.1**
- **Property 4: The funnel is monotone and trace-derived.** Per issue type, reported ≤ upheld-or-skipped ≤ quote-passed ≤ candidates. Rebuilding the funnel from `trace.jsonl` gives the numbers shown in the report. **Validates: Requirements 9.3, 8.4**
- **Property 5: Tools are read-only.** After every MCP tool is called with generated arguments, the hash of every Corpus file and of `build/` is unchanged. **Validates: Requirements 1.3**
- **Property 6: Isolation.** No tracked file contains `zoning-auditor-sealed` or `zoning-auditor-planted`, and no prompt file contains a per-prompt case's quoted text. **Validates: Requirements 17.1, 19.3**
- **Property 7: Schema agreement.** `SCHEMA_HASH` in `report-data.ts` equals the hash of `ReportData.model_json_schema()`, and `load.ts` rejects any other hash. **Validates: Requirements 14.6**
- **Property 8: No full text in git.** `git ls-files` lists no path under `data/corpus/`, `data/comparison/`, `data/sources/`, `data/raw/`, `build/`, `runs/`, or `llm_cache/`. **Validates: Requirements 21.2**

## Testing Strategy and Evals

### 9. Evals (`evals/`, `auditor eval`)

One command produces `evals/results.md`: a single table that leads with counts. Percentages appear only next to counts.

| Eval | Input | Measure | Labeler |
|---|---|---|---|
| **City documented errors, held-out (headline)** | sealed folder (§9.2): pre-correction text of every article the July 2026 round touches | **errors found / in-scope errors**, counted per city summary line item; instances found / in-scope instances alongside; run **once**, at the frozen commit | automatic match against the sealed key |
| City documented errors, dev | `pre2025` corpus | **errors found / 7** (5 in Article 53, 2 in Article 65), counted per city summary line item; instances found / 30 alongside (26 in 53, 4 in 65); per row of §2. Labeled "development set: prompts were tuned against this" | automatic (§9.1) |
| Extraction accuracy | stratified sample of 40 rules (20 table, 20 prose) from `current` | per field: value, unit, district, use, conditions; share `needs_review` | you |
| Verification funnel | every run | per type: candidates, quote-passed, upheld, reported | automatic |
| Planted contradictions | planted folder (§9.3) | recall = plants hit / 12, broken down by difficulty; precision = (plant hits + non-plant findings judged real) / reported contradictions | automatic + you for non-plant |
| False alarms on clean text | `current` corpus | every reported finding: real / not real / unsure | you, via report labels |
| Cross-reference accuracy | 30 sampled xrefs + every non-ok xref | resolution status correct | you |
| Quote faithfulness | all findings, all runs | model-proposed quotes passing `verify_*` (before the gate); reported quotes passing (must be all) | automatic |
| Ambiguities | up to 10 reported | genuine / not | you |
| Per-prompt datasets | §9.4, about 10 cases per role | "k of n" per role at the frozen commit | automatic; labels model-drafted, spot-checked by you |
| Comparison faithfulness | ~20 comparisons | verbatim in the other code (auto); supports the summary (hand); same subject (hand). Measures accuracy, not desirability. | auto + you |
| Spend | every eval run | live calls, tokens, USD per tier; cache hits counted separately | automatic (`spend.jsonl`) |

Order matters. Extraction accuracy is labeled at task 3, before any contradiction is trusted, because extraction errors become false contradictions.

#### 9.1 Dev ground truth

`evals/ground_truth/city_2025_04.yaml` has one entry per instance in §2. Each entry gives the article, `section_id`, `pre_text`, `post_text`, class, `in_scope`, summary item, and redline page. The implementer drafts it from the April 2025 redline at task 2.

You spot-check 5 entries, plus every entry the auditor misses. A miss is either an auditor error or a key error, and checking misses is the cheapest way to tell which.

**Counting.** The headline unit is one city error, meaning one summary line item (`summary_item`), not one repeated instance. For example, the 16 renumbered footnote references in Tables H–M are one error. An error is found when at least one of its in-scope instances is matched. Instances are reported alongside. The April 2025 dev key has 7 in-scope errors (5 in Article 53, 2 in Article 65) across 30 instances, plus 2 out-of-scope TA 454 errors.

A finding **matches** an entry if one of its verified quotes overlaps `pre_text` (after `quotes.normalize`), the quote is in the same article, and the finding type fits the class. `section_id` is informational; matching does not depend on it, so the separate session doesn't need our exact ID conventions (§9.2).

#### 9.2 Held-out set: sealed folder contract

A separate session, not this one, builds the July 2026 held-out set during the day. You don't open it until the final run. This section is the contract that session works to; hand it §9.2 and §9.3 at the start of the day.

**Location.** `../zoning-auditor-sealed/heldout/`, a sibling of the repo, not inside it. Repo-wide searches by the implementer can't touch it, and git can't commit it.

**Contents:**
```
heldout/
  READY                  # empty file, written last
  MANIFEST.json          # articles, source URLs, save dates, method, session notes
  corpus/<article>.html  # one file per affected article, pre-correction text
  key.yaml               # list of entries, schema below
```
- **Corpus files** are Municode HTML saved the same way as `data/corpus/current/`, with the July 2026 corrections reverse-applied by hand or script. Struck text is restored and inserted text is removed. If the session needs current HTML for articles we haven't saved, it gives you a list of article numbers to save in a browser. That list is all you see.
- **`key.yaml` entries:** `id, article, location` (human-readable, e.g. "Table H fn 3"), `section_id` (best effort, e.g. `53-29.4` or `53:TableH:fn3`), `pre_text` (exact string from the corpus file), `post_text`, `class`, `in_scope`, `summary_item`, and `redline_page`.
- **`class`** is one of: `xref_missing`, `xref_title_mismatch`, `xref_self_mismatch`, `xref_wrong_article`, `undefined_term_or_district`, `footnote_integrity`, `contradiction`, `ambiguity`, `out_of_scope`.
- **`in_scope`** follows §2: false for formatting fixes and for errors visible only by comparing articles that aren't in the held-out corpus.
- **Self-check before writing `READY`.** Every `pre_text` occurs exactly once in its article file after normalization: NFKC, curly→straight quotes, hyphen and dash variants (U+2010–U+2014, U+2212)→"-", whitespace collapsed. The session records any failures in the manifest and fixes them.
- **The session also** opens the second summary URL (§1) and records its date in `MANIFEST.json`. If it is a pre-April-2025 round, it tells you so and you add it to the dev set. That is the only fact it reports back.
- **The session must not** write into the repo or describe the errors to you.

**How the auditor uses it.**
- `auditor run --final --corpus-dir ../zoning-auditor-sealed/heldout/corpus --name heldout` refuses to run unless HEAD is exactly the `heldout-freeze` tag, the working tree is clean, and `READY` exists.
- `auditor eval --final --key …/key.yaml` scores the run and writes the headline row with commit hash and run id.
- `--final` runs at most once per tag: a second run writes "post-hoc" on its row.
- `tests/test_isolation.py` fails if any file in the repo contains the string `zoning-auditor-sealed` or `zoning-auditor-planted`. Paths reach the auditor only as CLI arguments.

**After the run** you open the folder for the first time. If a key entry is mechanically broken (e.g. `pre_text` not in the corpus file), fix it and log the change. The results show the score both before and after the fix. No code or prompt changes after the run count toward the headline.

#### 9.3 Planted contradictions

The same separate session builds this set (approved). It writes to a different sibling, `../zoning-auditor-planted/`, because you open this one at task 5, not at the end.
- Input: `data/corpus/current/*.html`, copied by the session.
- Output: `corpus/*.html` and `key.yaml` with 12 plants: 5 direct value conflicts, 4 conflicts behind an exception, 3 across the two articles. Each entry gives the inserted span (exact text) and the provision it conflicts with (exact text).
- Inserted text imitates the surrounding drafting style and carries no markers.
- Dev runs read it with `auditor run --corpus-dir ../zoning-auditor-planted/corpus --name planted`; `auditor eval --key …` scores it.
- After task 5 the planted set is effectively development data, because we will have seen what it catches. The report says so.

#### 9.4 Per-prompt datasets

Each model role has a small regression set, so prompt changes show up as "7 of 10 → 9 of 10" instead of a guess.

- **Files.** `evals/prompts/<role>.jsonl`, about 10 cases per role. Roles: `extract_prose`, `find_contradiction`, `find_ambiguity`, `judge_xref`, `skeptic_contradiction`, `skeptic_xref`, `skeptic_ambiguity`. Stretch roles: `compare_match`, `compare_support`.
- **Case shape:** `{id, inputs: {section_ids…, candidate?}, expected: {...}, rationale, drafted_by, checked: bool}`.
- **What `expected` means per role:**
  - extraction: the rule fields.
  - finders: whether a finding should exist, and which sections it is about.
  - skeptics: `upheld` or `refuted`.
  - `judge_xref`: `ok` or `broken`.
- **Mix.** About 5 positives, 3 clear negatives, and 2 near-misses per set, e.g. an apparent conflict that a footnote resolves, or a reference whose title differs only in wording.
- **Source.** Drafted by the judge-tier model from the `current` and `pre2025` text of 53 and 65 only, never from the planted or sealed folders. The drafting prompt is separate from the role prompts.
- **Spot-check.** You check 3 cases per set, plus every case where the role's output disagrees with the expected label. Disagreements are where a model-drafted label is most likely wrong. Checked cases get `checked: true`.
- **No leakage into prompts.** Role prompts contain no examples from these sets. A test fails if any case's quoted text appears in `src/auditor/prompts/`.
- **Command.** `auditor prompt-eval <role>` prints k of n, with diffs for failures, and logs spend. It is cached, so reruns of an unchanged prompt are free. Each prompt change is committed together with its before/after prompt-eval line.
- **Not an accuracy claim.** These sets are for iterating on prompts. They appear in `results.md` as regression counts, labeled "model-drafted labels".

## Decisions and Open Items

### 12. Decisions and open items

Decided:
- **Scope.** Every feature is built, including comparison; there is no cut list. Work follows the priority order in `tasks.md`. The held-out run and the pitch keep their fixed times.
- **Build priority (most important first).**
  1. The quote checker and cross-references.
  2. Rule extraction.
  3. The model contradiction finder plus the skeptic.
  4. Evals on 1 to 3.
  5. The ambiguity finder.
  6. The permit/violation analysis.
  7. The report: the finding pages first, then extracted rules, dropped candidates, highlighting, and filters (§8.3).
  8. Comparison.
- **Solo build.** One implementer session, and you review everything (`tasks.md`).
- **Report.** A Next.js static export generated from `report_data.json`, served on loopback (§8).
- **Municode.** No automated access. You save pages by hand, and ingestion reads saved HTML (§3).
- **Pre-correction text.** Planning Department redline PDFs only; Municode version history is not used (§4.2).
- **Spend caps.** $20 per run and $100 per day, on your current API account (§5.5).
- **Open data.** No zips. The fetch script pulls all rows since 2024-01-01 from the live URLs (§3).
- **Comparison sites.** Saved by hand. The report shows cited, linked excerpts only, never full text. If the out-of-state city's terms prohibit that, switch to the other city. Minneapolis is the default (§3).
- **Artifacts.** Saved pages, PDFs, data, builds, runs, and the LLM cache stay local and out of git (§4.3).
- **Pitch.** 30 minutes for slides and rehearsal after the README (`tasks.md`, task 12).
- **Article 2.** Included as reference text, not audited (§2).
- **Planted set.** Built by the separate session (§9.3).
- **Held-out set.** The separate session builds it into `../zoning-auditor-sealed/` to the §9.2 contract. You don't open it until task 10. It runs once at the `heldout-freeze` tag.
- **Per-prompt sets.** About 10 cases per role, model-drafted, spot-checked (§9.4).
- **Articles.** 53 + 65, with 68 as fallback (§2).
- **Models.** Through OpenRouter, not LiteLLM: `anthropic/claude-sonnet-5.5` for finders and skeptics, `anthropic/claude-haiku-5.5` for extraction (§5.5). Spend comes from OpenRouter's reported cost.
- **Massachusetts fallback.** Cambridge, if Somerville's terms prohibit saving and quoting (§3).

Still open: none.
