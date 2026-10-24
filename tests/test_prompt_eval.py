from __future__ import annotations

import json

from auditor.agents import AgentFailure
from auditor.extract_prose import Extraction
from auditor.prompt_eval import Case, CaseScore, run_prompt_eval, score_extract_prose
from conftest import MINI53, call
from test_extract_prose import CORPUS, _run

HEIGHT = {"item": "building_height_ft", "comparator": "max", "value": "35", "unit": "ft", "district": "EBR-3"}
PASS_CASE = Case("ep-pass", {"section_ids": ["53-21"]}, HEIGHT)
FAIL_CASE = Case("ep-fail", {"section_ids": ["53-21"]}, HEIGHT | {"item": "far", "value": "0.5", "unit": "ratio"})


def _draft(value: str = "35") -> dict:
    return {"section_id": "53-21", "quote_text": CORPUS.section("53-21").text, "item": "building_height_ft",
            "comparator": "max", "value": value, "unit": "ft", "district": "EBR-3"}


def test_prompt_eval_prints_k_of_n_with_diff_and_this_runs_spend(script, run_dir, tmp_path):
    run_dir.mkdir(parents=True)
    (run_dir / "spend.jsonl").write_text(json.dumps(
        {"role": "x", "model": "m", "input_tokens": 0, "output_tokens": 0, "usd": "7", "cached": False}) + "\n")
    evals = tmp_path / "evals"
    (evals / "prompts").mkdir(parents=True)
    (evals / "prompts" / "extract_prose.jsonl").write_text(
        "".join(json.dumps({"id": c.id, "inputs": c.inputs, "expected": c.expected}) + "\n"
                for c in (PASS_CASE, FAIL_CASE)))
    script(call("final_answer", {"answer": {"drafts": [_draft()]}}, cost="0.25"))
    report = run_prompt_eval("extract_prose", evals_dir=evals, build_dir=MINI53, run_dir=run_dir)
    lines = report.splitlines()
    assert lines[0] == "1 of 2"
    assert lines[1].startswith("  FAIL ep-fail: expected {'item': 'far'")
    assert lines[-1] == "spend: $0.25"  # the second case replays the first from cache


def test_value_compares_as_a_number(script, run_dir):
    out = _run(script, run_dir, {"drafts": [_draft("35.0")]})
    assert score_extract_prose(PASS_CASE, out) == CaseScore("ep-pass", True, "")


def test_no_rules_and_agent_failure_diffs():
    assert score_extract_prose(PASS_CASE, Extraction(rules=[], dropped=[])).diff.endswith("got no rules")
    failure = AgentFailure(role="extract_prose", reason="bad json", raw="x")
    assert score_extract_prose(PASS_CASE, failure) == CaseScore("ep-pass", False, "agent failed: bad json")
