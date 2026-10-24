import hashlib
import json

from auditor.models import SECTION_ID, CellQuote, RegulatedItem, TextQuote


def slug(id: str) -> str:
    if not SECTION_ID.match(id):
        raise ValueError(f"not a canonical section id: {id!r}")
    return id.replace(":", "__").replace(".", "_")


def rule_id(quote: TextQuote | CellQuote, district: str | None, use: str | None,
            item: RegulatedItem) -> str:
    key = json.dumps([quote.model_dump(mode="json"), district, use, item.value])
    return hashlib.sha256(key.encode()).hexdigest()[:16]
