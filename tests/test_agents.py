from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from auditor.agents import AgentFailure, BudgetExceeded, CachedModel, run_agent
from conftest import MINI53, FakeModel, call, settings


def _cached(tmp: Path, inner: FakeModel, **over) -> CachedModel:
    return CachedModel(inner, role="find_contradiction", settings=settings(tmp, **over),
                       run_dir=tmp / "runs" / "current" / "r1")


def _spend_lines(tmp: Path) -> list[dict]:
    path = tmp / "runs" / "current" / "r1" / "spend.jsonl"
    return [json.loads(ln) for ln in path.read_text().splitlines()]


def test_miss_then_hit(tmp_path):
    inner = FakeModel(cost="0.0012")
    model = _cached(tmp_path, inner)
    assert model.generate([{"role": "user", "content": "hello"}]).content == '{"ok": true}'
    assert model.generate([{"role": "user", "content": "hello"}]).content == '{"ok": true}'
    assert inner.calls == 1
    assert [(ln["usd"], ln["cached"], ln["input_tokens"]) for ln in _spend_lines(tmp_path)] == [
        ("0.0012", False, 11), ("0", True, 11)]


def test_offline_miss_raises_naming_role(tmp_path):
    inner = FakeModel()
    with pytest.raises(RuntimeError, match="offline cache miss: role='find_contradiction'"):
        _cached(tmp_path, inner, offline=True).generate([{"role": "user", "content": "unseen"}])
    assert inner.calls == 0


def test_offline_hit_serves_cache_at_zero(tmp_path):
    _cached(tmp_path, FakeModel()).generate([{"role": "user", "content": "warm"}])
    msg = _cached(tmp_path, FakeModel(), offline=True).generate([{"role": "user", "content": "warm"}])
    assert msg.content == '{"ok": true}'
    assert _spend_lines(tmp_path)[-1] == {"role": "find_contradiction", "model": "fake/model",
                                          "input_tokens": 11, "output_tokens": 7, "usd": "0", "cached": True}


def test_missing_usage_cost_raises(tmp_path):
    with pytest.raises(RuntimeError, match="usage.cost"):
        _cached(tmp_path, FakeModel(cost=None)).generate([{"role": "user", "content": "nocost"}])


def test_budget_exceeded_per_run_cap(tmp_path):
    model = _cached(tmp_path, FakeModel(cost="5.00"), per_run="5")
    model.generate([{"role": "user", "content": "first"}])
    with pytest.raises(BudgetExceeded, match=r"per-run cap reached: \$5.00 >= \$5"):
        model.generate([{"role": "user", "content": "second"}])


def test_budget_exceeded_total_cap(tmp_path):
    sibling = tmp_path / "runs" / "other" / "r0"
    sibling.mkdir(parents=True)
    (sibling / "spend.jsonl").write_text(json.dumps(
        {"role": "x", "model": "m", "input_tokens": 0, "output_tokens": 0, "usd": "90", "cached": False}) + "\n")
    model = _cached(tmp_path, FakeModel(cost="15.00"), per_run="1000", total="100")
    model.generate([{"role": "user", "content": "a"}])
    with pytest.raises(BudgetExceeded, match=r"total cap reached: \$105.00 >= \$100"):
        model.generate([{"role": "user", "content": "b"}])


def test_run_dir_outside_runs_root_is_refused(tmp_path):
    with pytest.raises(ValueError, match="outside runs_root"):
        CachedModel(FakeModel(), role="find_contradiction", settings=settings(tmp_path), run_dir=tmp_path / "r")


class Answer(BaseModel):
    verdict: str
    note: str


def test_run_agent_round_trip_over_mcp_records_tool_outputs(script, run_dir, capsys):
    script(call("get_section", {"section_id": "53-21"}),
           call("final_answer", {"answer": {"verdict": "upheld", "note": "35 feet"}}))
    result = run_agent("find_contradiction", "Read 53-21.", Answer, build_dir=MINI53, run_dir=run_dir, max_steps=3)
    assert result == Answer(verdict="upheld", note="35 feet")
    trace = json.loads((run_dir / "trace.jsonl").read_text())
    assert trace["stage"] == "find_contradiction"
    get_section, final = trace["data"]["tool_calls"]
    assert get_section["arguments"] == {"section_id": "53-21"}
    assert "In the EBR-3 subdistrict the maximum building height is 35 feet." in get_section["output"]
    assert final["name"] == "final_answer"
    assert capsys.readouterr().err.strip() == "spend: $0.0010 this run, $0.0010 total, 2 live find_contradiction calls"


def test_run_agent_bad_json_is_agent_failure(script, run_dir):
    script(call("final_answer", {"answer": "not valid json for Answer"}))
    result = run_agent("find_contradiction", "Answer.", Answer, build_dir=MINI53, run_dir=run_dir, max_steps=2)
    assert isinstance(result, AgentFailure)
    assert (result.role, result.raw) == ("find_contradiction", "not valid json for Answer")


def test_budget_exceeded_propagates_out_of_run_agent(script, run_dir):
    script(per_run="0")
    with pytest.raises(BudgetExceeded, match="per-run cap reached"):
        run_agent("find_contradiction", "Answer.", Answer, build_dir=MINI53, run_dir=run_dir, max_steps=2)


def test_budget_exceeded_on_the_max_steps_final_call_propagates(script, run_dir):
    script(call("get_section", {"section_id": "53-21"}, cost="5"), per_run="5")
    with pytest.raises(BudgetExceeded, match=r"per-run cap reached: \$5 >= \$5"):
        run_agent("find_contradiction", "Answer.", Answer, build_dir=MINI53, run_dir=run_dir, max_steps=1)


def test_offline_miss_propagates_out_of_run_agent(script, run_dir):
    script(offline=True)
    with pytest.raises(RuntimeError, match="offline cache miss"):
        run_agent("find_contradiction", "Answer.", Answer, build_dir=MINI53, run_dir=run_dir, max_steps=2)
