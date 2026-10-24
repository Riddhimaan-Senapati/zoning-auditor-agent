from __future__ import annotations

import json
import os
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from auditor.find_xrefs import xref_id
from auditor.models import XRef

Kind = Literal["rules", "xrefs", "findings"]

_ANSWER = {"c": "confirmed", "r": "rejected", "u": "unsure"}
_PROMPT = "[c]onfirmed / [r]ejected / [u]nsure / [q]uit, then optional note: "


@dataclass(frozen=True)
class Item:
    id: str
    lines: tuple[str, ...]
    source: str | None = None  # rules only; the sample is stratified by it


def _quote(q: dict) -> str:
    where = f"{q['table_id']} / {q['row_label']} / {q['column']}" if q.get("kind") == "cell" else q.get("section_id", "?")
    return f'"{q.get("text", "")}" @ {where}'


def _rule_item(rec: dict) -> Item:
    lines = [
        f"district: {rec.get('district')}",
        f"use:      {rec.get('use')}",
        f"item:     {rec.get('item')}",
        f"rule:     {rec.get('comparator')} {rec.get('value')} {rec.get('unit') or ''}".rstrip(),
    ]
    if rec.get("status") is not None:
        lines.append(f"status:   {rec['status']}")
    if rec.get("conditions"):
        lines.append(f"conditions: {'; '.join(rec['conditions'])}")
    return Item(id=rec["id"], source=rec["source"], lines=(*lines, f"quote:    {_quote(rec['quote'])}"))


def _xref_item(rec: dict) -> Item:
    res = rec["resolution"]
    lines = [f"status:   {res['status']}", f"claim:    {res['detail']}"]
    if res.get("resolved_id"):
        lines.append(f"resolved: {res['resolved_id']}")
    return Item(id=xref_id(XRef.model_validate(rec)), lines=(*lines, f"quote:    {_quote(rec['quote'])}"))


def _finding_item(rec: dict) -> Item:
    lines = [f"type:     {rec.get('type')}", f"claim:    {rec.get('claim')}"]
    if rec.get("readings"):
        lines += [f"reading A: {rec['readings'][0]}", f"reading B: {rec['readings'][1]}"]
    lines += [f"quote:    {_quote(q)}" for q in rec.get("quotes") or []]
    return Item(id=rec["id"], lines=tuple(lines))


_PARSERS: dict[Kind, Callable[[dict], Item]] = {"rules": _rule_item, "xrefs": _xref_item, "findings": _finding_item}


def load_items(path: Path, kind: Kind) -> list[Item]:
    with path.open(encoding="utf-8") as f:
        return [_PARSERS[kind](json.loads(ln)) for ln in f if ln.strip()]


def select_sample(items: list[Item], kind: Kind, n: int | None, seed: int) -> list[Item]:
    """Seeded sample in file order. Rules split table/prose, table taking the odd one; a short
    stratum is backfilled from the rest. n=None takes every item."""
    if n is None or n >= len(items):
        return items
    rng = random.Random(seed)
    if kind != "rules":
        return sorted(rng.sample(items, n), key=items.index)
    picked: list[Item] = []
    for stratum, want in (("table", n - n // 2), ("prose", n // 2)):
        pool = [it for it in items if it.source == stratum]
        picked += rng.sample(pool, min(want, len(pool)))
    rest = [it for it in items if it not in picked]
    picked += rng.sample(rest, n - len(picked))
    return sorted(picked, key=items.index)


def run_label(items_path: Path, kind: Kind, out: Path, *, run_id: str, sample: int | None = None,
              seed: int = 0, clock: Callable[[], datetime] = datetime.now,
              read: Callable[[str], str] | None = None, write: Callable[[str], None] | None = None) -> int:
    """Ask c/r/u plus a note for each sampled item, rewriting `out` after every answer and
    skipping items it already holds. Returns the count labeled this run."""
    read, write = read or input, write or print
    doc = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"run_id": run_id, "kind": kind, "labels": {}}
    if (doc["run_id"], doc["kind"]) != (run_id, kind):
        raise ValueError(f"{out} holds {doc['kind']} labels for run {doc['run_id']}, not {kind} for {run_id}")
    labels: dict[str, dict] = doc["labels"]
    items = select_sample(load_items(items_path, kind), kind, sample, seed)
    labeled = 0
    while (item := next((it for it in items if it.id not in labels), None)) is not None:
        write(f"\n--- {kind} item {len([it for it in items if it.id in labels]) + 1} of {len(items)} ---")
        for line in item.lines:
            write(line)
        answer = read(_PROMPT).strip()
        choice, _, note = answer.partition(" ")
        choice = choice.lower()
        if choice in ("q", "quit"):
            write(f"stopped. {labeled} labeled this run, {len(labels)} of {len(items)} total.")
            return labeled
        if choice not in _ANSWER:
            write(f"'{answer}' is not c, r, u, or q. Try again.")
            continue
        labels[item.id] = {"kind": _ANSWER[choice], "note": note.strip(), "at": clock().isoformat()}
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, out)
        labeled += 1
    write(f"done. {labeled} labeled this run, {len(labels)} of {len(items)} total.")
    return labeled


def import_labels(labels_path: Path, evals_root: Path) -> Path:
    """Copy a labels.json to evals/labels/<kind>-<run_id>.json."""
    doc = json.loads(labels_path.read_text(encoding="utf-8"))
    dest = evals_root / "labels" / f"{doc['kind']}-{doc['run_id']}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(labels_path.read_text(encoding="utf-8"), encoding="utf-8")
    return dest
