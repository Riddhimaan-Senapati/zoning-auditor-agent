from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from auditor.models import Section

_TOKEN = re.compile(r"\w+", re.UNICODE)


def build_search(sections: list[Section], db: Path) -> None:
    con = sqlite3.connect(db)
    try:
        # Drop first so a rebuild starts from scratch and is idempotent.
        con.execute("DROP TABLE IF EXISTS sections")
        con.execute(
            "CREATE VIRTUAL TABLE sections USING fts5(id UNINDEXED, heading, text)"
        )
        con.executemany(
            "INSERT INTO sections(id, heading, text) VALUES (?, ?, ?)",
            [(s.id, s.heading, s.text) for s in sections],
        )
        con.commit()
    finally:
        con.close()


def search(db: Path, query: str, k: int) -> list[tuple[str, str, str]]:
    match = _to_match(query)
    if match is None:
        return []
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT id, heading, text FROM sections "
            "WHERE sections MATCH ? ORDER BY bm25(sections) LIMIT ?",
            (match, k),
        ).fetchall()
    finally:
        con.close()
    return [(id, heading, _snippet(text)) for id, heading, text in rows]


def _snippet(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _to_match(query: str) -> str | None:
    # Agents pass free text, and FTS5 would read quotes, parens, hyphens, and colons as
    # syntax. Each whitespace chunk becomes one quoted phrase of its word tokens, so
    # "53-8" must match "53" followed by "8", and no input can raise.
    phrases = [" ".join(_TOKEN.findall(chunk)) for chunk in query.split()]
    phrases = [p for p in phrases if p]
    return " OR ".join(f'"{p}"' for p in phrases) or None
