import json
from datetime import datetime
from pathlib import Path

import pytest

from auditor.cli import main
from auditor.find_xrefs import candidates
from auditor.label import import_labels, load_items, run_label, select_sample
from test_find_xrefs import _xrefs


def _text_quote(section_id: str, text: str) -> dict:
    return {"kind": "text", "section_id": section_id, "text": text, "span": [0, len(text)]}


def _rule(rule_id: str, source: str) -> dict:
    return {
        "id": rule_id,
        "district": "EBR-3",
        "use": None,
        "item": "building_height_ft",
        "comparator": "max",
        "value": "35",
        "unit": "ft",
        "status": None,
        "conditions": [],
        "footnotes": [],
        "quote": _text_quote("53-1", f"text for {rule_id}"),
        "source": source,
        "review_reason": None,
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


class _Clock:
    """A clock that returns a fixed stamp per call, in order, so labels get literal `at`s."""

    def __init__(self, stamps: list[str]) -> None:
        self._stamps = [datetime.fromisoformat(s) for s in stamps]
        self._i = 0

    def __call__(self) -> datetime:
        stamp = self._stamps[self._i]
        self._i += 1
        return stamp


class _Input:
    def __init__(self, answers: list[str]) -> None:
        self._answers = iter(answers)

    def __call__(self, _prompt: str = "") -> str:
        return next(self._answers)


def test_label_quit_then_resume_writes_exact_file(tmp_path):
    items = tmp_path / "rules.jsonl"
    _write_jsonl(items, [_rule("r1", "table"), _rule("r2", "prose"), _rule("r3", "table")])
    out = tmp_path / "labels.json"

    # First run: label two, then quit on the third.
    clock1 = _Clock(["2026-10-24T10:00:00", "2026-10-24T10:01:00"])
    n = run_label(
        items, "rules", out, run_id="run42",
        clock=clock1, read=_Input(["c looks right", "r wrong unit", "q"]), write=lambda _s: None,
    )
    assert n == 2
    after_quit = json.loads(out.read_text())
    assert after_quit == {
        "run_id": "run42",
        "kind": "rules",
        "labels": {
            "r1": {"kind": "confirmed", "note": "looks right", "at": "2026-10-24T10:00:00"},
            "r2": {"kind": "rejected", "note": "wrong unit", "at": "2026-10-24T10:01:00"},
        },
    }

    # Second run: the two already-labeled items are skipped; only r3 is presented.
    clock2 = _Clock(["2026-10-24T11:00:00"])
    presented: list[str] = []
    n = run_label(
        items, "rules", out, run_id="run42",
        clock=clock2, read=_Input(["u not sure"]),
        write=lambda s: presented.append(s),
    )
    assert n == 1
    assert any("item 3 of 3" in line for line in presented)
    assert json.loads(out.read_text()) == {
        "run_id": "run42",
        "kind": "rules",
        "labels": {
            "r1": {"kind": "confirmed", "note": "looks right", "at": "2026-10-24T10:00:00"},
            "r2": {"kind": "rejected", "note": "wrong unit", "at": "2026-10-24T10:01:00"},
            "r3": {"kind": "unsure", "note": "not sure", "at": "2026-10-24T11:00:00"},
        },
    }


def test_stratified_seeded_sample_is_half_table_half_prose(tmp_path):
    items = tmp_path / "rules.jsonl"
    records = [_rule(f"t{i}", "table") for i in range(5)] + [_rule(f"p{i}", "prose") for i in range(5)]
    _write_jsonl(items, records)
    loaded = load_items(items, "rules")

    picked = select_sample(loaded, "rules", 4, seed=7)
    ids = [it.id for it in picked]
    table_ids = [i for i in ids if i.startswith("t")]
    prose_ids = [i for i in ids if i.startswith("p")]
    assert len(table_ids) == 2 and len(prose_ids) == 2
    # Seeded: the exact ids are fixed. Re-running with the same seed reproduces them.
    assert ids == [it.id for it in select_sample(loaded, "rules", 4, seed=7)]
    # Order follows the file, not the draw.
    assert ids == sorted(ids, key=[it.id for it in loaded].index)
    # The literal selection for seed=7.
    assert ids == ["t1", "t2", "p0", "p3"]


def test_odd_sample_gives_table_the_extra(tmp_path):
    items = tmp_path / "rules.jsonl"
    _write_jsonl(items, [_rule(f"t{i}", "table") for i in range(3)] + [_rule(f"p{i}", "prose") for i in range(3)])
    loaded = load_items(items, "rules")
    picked = select_sample(loaded, "rules", 3, seed=1)
    ids = [it.id for it in picked]
    assert sum(i.startswith("t") for i in ids) == 2
    assert sum(i.startswith("p") for i in ids) == 1


def test_import_labels_destination_path(tmp_path):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"run_id": "run42", "kind": "xrefs", "labels": {}}), encoding="utf-8")
    evals = tmp_path / "evals"

    dest = import_labels(labels, evals)
    assert dest == evals / "labels" / "xrefs-run42.json"
    assert json.loads(dest.read_text()) == {"run_id": "run42", "kind": "xrefs", "labels": {}}


def test_label_cli_drives_input_and_derives_run_id(tmp_path, monkeypatch, capsys):
    run_dir = tmp_path / "current" / "run99"
    run_dir.mkdir(parents=True)
    items = run_dir / "findings.json"
    _write_jsonl(items, [
        {"id": "f1", "type": "contradiction", "origin": "structured", "quotes": [_text_quote("53-1", "a")],
         "claim": "X contradicts Y", "readings": None, "confidence": "high", "candidate_ids": [],
         "verdict": {}, "neutrality_flags": []},
    ])
    out = tmp_path / "labels.json"
    monkeypatch.setattr("builtins.input", _Input(["c clear case"]))

    main(["label", str(items), "--kind", "findings", "--out", str(out)])

    doc = json.loads(out.read_text())
    assert doc["run_id"] == "run99"
    assert doc["kind"] == "findings"
    assert doc["labels"]["f1"]["kind"] == "confirmed"
    assert doc["labels"]["f1"]["note"] == "clear case"
    assert doc["labels"]["f1"]["at"]  # a real timestamp was stamped


def test_import_labels_cli_prints_destination(tmp_path, capsys):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"run_id": "r1", "kind": "rules", "labels": {}}), encoding="utf-8")
    main(["import-labels", str(labels), "--evals", str(tmp_path / "evals")])
    assert (tmp_path / "evals" / "labels" / "rules-r1.json").read_text()
    assert capsys.readouterr().out.strip().endswith("rules-r1.json")


def test_short_stratum_is_backfilled(tmp_path):
    items = tmp_path / "rules.jsonl"
    _write_jsonl(items, [_rule(f"t{i}", "table") for i in range(5)] + [_rule("p0", "prose")])
    ids = [it.id for it in select_sample(load_items(items, "rules"), "rules", 4, seed=7)]
    assert len(ids) == 4
    assert "p0" in ids


def test_label_refuses_an_out_file_of_another_kind_or_run(tmp_path):
    items = tmp_path / "rules.jsonl"
    _write_jsonl(items, [_rule("r1", "table")])
    out = tmp_path / "labels.json"
    out.write_text(json.dumps({"run_id": "run42", "kind": "xrefs", "labels": {"x": {}}}))
    with pytest.raises(ValueError, match="holds xrefs labels for run run42, not rules for run42"):
        run_label(items, "rules", out, run_id="run42", read=_Input(["c"]), write=lambda _s: None)
    assert json.loads(out.read_text())["kind"] == "xrefs"


def test_xref_labels_key_to_the_candidate_id(tmp_path):
    xrefs = [x for x in _xrefs() if x.resolution.status not in ("ok", "external_unchecked")]
    items = tmp_path / "xrefs.jsonl"
    items.write_text("".join(x.model_dump_json() + "\n" for x in xrefs))
    assert len(xrefs) == 10
    assert [it.id for it in load_items(items, "xrefs")] == [c.id for c in candidates(xrefs)]
