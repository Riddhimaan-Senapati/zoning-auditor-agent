from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from auditor.models import CellQuote, Rule, TextQuote

SELF_IDENTIFICATION = (
    "Independent prototype built at Hackachusetts 2026. Not a City of Boston service. "
    "Findings are unreviewed until confirmed by staff."
)

CSV_HEADER = [
    "id", "district", "use", "item", "comparator", "value", "unit", "status",
    "conditions", "footnotes", "needs_review", "review_reason", "quote_text",
    "section_table_id", "source_link",
]


def cited_id(quote: TextQuote | CellQuote) -> str:
    return quote.table_id if isinstance(quote, CellQuote) else quote.section_id


def write_rules(rules: list[Rule], out_dir: Path, source_links: dict[str, str]) -> None:
    """Write rules.csv and rules.json; source_links maps a section or table id to its URL."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "rules.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        for r in rules:
            writer.writerow({
                "id": r.id,
                "district": r.district or "",
                "use": r.use or "",
                "item": r.item.value,
                "comparator": r.comparator,
                "value": "" if r.value is None else str(r.value),
                "unit": r.unit or "",
                "status": r.status or "",
                "conditions": " | ".join(r.conditions),
                "footnotes": " | ".join(r.footnotes),
                "needs_review": "true" if r.needs_review else "false",
                "review_reason": r.review_reason or "",
                "quote_text": r.quote.text,
                "section_table_id": cited_id(r.quote),
                "source_link": source_links.get(cited_id(r.quote), ""),
            })
    doc = {
        "self_identification": SELF_IDENTIFICATION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rules": [r.model_dump(mode="json") | {"source_link": source_links.get(cited_id(r.quote), "")}
                  for r in rules],
    }
    (out_dir / "rules.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
