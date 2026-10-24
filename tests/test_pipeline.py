"""Pipeline behavior on the mini53 fixture, with the model off (design §4.1, §9.1).

--no-model runs the deterministic xref checks and the table-rule extraction, and skips
every model call (prose rules, the model contradiction finder, judge_xref, and the
skeptic). The six xref statuses the code itself proves (design §6.3) still become findings;
the four that need the skeptic, and any structured contradiction, stay uncertain and are
not reported. So the reported set and the funnel below are fully determined, no model
needed, which is what lets this test assert them literally."""

from __future__ import annotations

import json
from pathlib import Path

from auditor.pipeline import run

MINI53 = Path(__file__).parent / "fixtures" / "mini53"


def _location(quote: dict) -> str:
    return quote.get("table_id") if quote.get("kind") == "cell" else quote.get("section_id")


def _reported(run_dir: Path) -> set[tuple[str, str]]:
    doc = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    return {(f["type"], _location(f["quotes"][0])) for f in doc["findings"]}


def _run_dir(runs_root: Path, name: str) -> Path:
    (child,) = list((runs_root / name).iterdir())
    return child


def test_no_model_funnel_is_exact(tmp_path: Path):
    result = run(MINI53, "mini53", no_model=True, runs_root=tmp_path / "runs")
    # Ten deterministic xref candidates; all quotes verify; six skip the skeptic and are
    # reported; the other four stay uncertain with the model off. No contradiction row:
    # the EBR-3 height conflict needs the prose rule, which needs a model.
    assert result.per_type == {
        "xref": {"candidates": 10, "quote_passed": 10, "upheld": 6, "reported": 6},
    }


def test_no_model_reported_findings_are_exact(tmp_path: Path):
    run(MINI53, "mini53", no_model=True, runs_root=tmp_path / "runs")
    assert _reported(_run_dir(tmp_path / "runs", "mini53")) == {
        ("xref", "53-4.1"),        # definition_mismatch
        ("xref", "53-29.4"),       # self_mismatch + undefined_district both cite here
        ("xref", "53:TableK:fn1"),  # self_mismatch "this Table I"
        ("xref", "53:TableH"),     # footnote_missing (EBR-4 height mark 5)
        ("xref", "53:TableH:fn9"),  # footnote_unused
    }


def test_only_xref_and_only_contradiction_partition_the_candidates(tmp_path: Path):
    both = run(MINI53, "mini53", no_model=True, runs_root=tmp_path / "both").per_type
    xref = run(MINI53, "mini53", only="xref", no_model=True, runs_root=tmp_path / "x").per_type
    contra = run(MINI53, "mini53", only="contradiction", no_model=True, runs_root=tmp_path / "c").per_type
    assert xref == both == {"xref": {"candidates": 10, "quote_passed": 10, "upheld": 6, "reported": 6}}
    # With the model off there is no prose rule, so no structured contradiction pair forms.
    assert contra == {}


def test_run_writes_the_four_artifacts_and_exports(tmp_path: Path):
    run(MINI53, "mini53", no_model=True, runs_root=tmp_path / "runs")
    run_dir = _run_dir(tmp_path / "runs", "mini53")
    for name in ("findings.json", "rules.jsonl", "trace.jsonl", "rules.csv", "rules.json"):
        assert (run_dir / name).exists(), name
    # rules.jsonl holds the table rules the run extracted (Table H dimensional + Table A use).
    rules = [json.loads(ln) for ln in (run_dir / "rules.jsonl").read_text().splitlines() if ln.strip()]
    assert rules and all(r["source"] == "table" for r in rules)


# A tiny synthetic key: two summary items in article 53, one with two instances. The
# §9.1 count is asserted literally. The pipeline filters the key to the corpus's articles,
# so the article-99 entry is dropped before counting; an instance is found when a reported
# finding's verified quote (same article) overlaps the entry's normalized pre_text.
_SYNTHETIC_KEY = """
- id: hit-ebr1
  article: "53"
  pre_text: "EBR-1"
  class: undefined_term_or_district
  in_scope: true
  summary_item: "district names"
- id: hit-self
  article: "53"
  pre_text: "Section 53-27"
  class: xref_self_mismatch
  in_scope: true
  summary_item: "self reference"
- id: miss-nothere
  article: "53"
  pre_text: "no finding quotes this phrase"
  class: contradiction
  in_scope: true
  summary_item: "self reference"
- id: out-of-scope-ignored
  article: "53"
  pre_text: "EBR-1"
  class: out_of_scope
  in_scope: false
  summary_item: "out of scope"
- id: wrong-article-dropped
  article: "99"
  pre_text: "EBR-1"
  class: undefined_term_or_district
  in_scope: true
  summary_item: "other article"
"""


def test_eval_line_counts_errors_and_instances_literally(tmp_path: Path):
    key = tmp_path / "key.yaml"
    key.write_text(_SYNTHETIC_KEY, encoding="utf-8")
    result = run(MINI53, "mini53", no_model=True, runs_root=tmp_path / "runs", key=key)
    # In-scope article-53 items: "district names" (1 instance, found via "EBR-1"), and
    # "self reference" (2 instances: "Section 53-27" found, the nonsense phrase not). So
    # one summary item is fully found and one is partly found -> 2 of 2 errors, 2 of 3
    # instances. The out-of-scope and article-99 entries never count.
    assert result.eval_line == "2 of 2 errors (2 of 3 instances)"


def test_no_key_gives_no_eval_line(tmp_path: Path):
    result = run(MINI53, "mini53", no_model=True, runs_root=tmp_path / "runs")
    assert result.eval_line is None
