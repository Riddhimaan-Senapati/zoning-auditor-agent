from __future__ import annotations

import unicodedata

from pydantic import BaseModel

from auditor.corpus import Corpus
from auditor.models import CellQuote, TextQuote

_FOLD = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",
}


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return " ".join("".join(_FOLD.get(c, c) for c in s).split())


class QuoteError(BaseModel):
    reason: str


def _starts_cluster(ch: str) -> bool:
    # NFKC composes a base with following combining marks, and Hangul L+V(+T) jamo.
    return unicodedata.combining(ch) == 0 and not 0x1160 <= ord(ch) <= 0x11FF


def _clusters(s: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for i, ch in enumerate(s):
        if out and not _starts_cluster(ch):
            out[-1] = (out[-1][0], out[-1][1] + ch)
        else:
            out.append((i, ch))
    return out


def _normalize_map(s: str) -> tuple[str, list[int]]:
    """normalize(s), plus for each output char the index in s of the cluster it came from."""
    chars: list[str] = []
    origin: list[int] = []
    for i, cluster in _clusters(s):
        for c in unicodedata.normalize("NFKC", cluster):
            chars.append(_FOLD.get(c, c))
            origin.append(i)
    out: list[str] = []
    src: list[int] = []
    pending_space = False
    for c, i in zip(chars, origin):
        if c.isspace():
            pending_space = bool(out)
            continue
        if pending_space:
            out.append(" ")
            src.append(i)
            pending_space = False
        out.append(c)
        src.append(i)
    return "".join(out), src


def _cluster_end(s: str, start: int) -> int:
    end = start + 1
    while end < len(s) and not _starts_cluster(s[end]):
        end += 1
    return end


def verify_text(q: TextQuote, corpus: Corpus) -> TextQuote | QuoteError:
    section = corpus.section(q.section_id)
    if section is None:
        return QuoteError(reason=f"unknown section {q.section_id}")
    needle = normalize(q.text)
    if not needle:
        return QuoteError(reason="empty quote")
    norm, src = _normalize_map(section.text)
    pos = norm.find(needle)
    if pos == -1:
        return QuoteError(reason="quote not found in section text")
    start, end = src[pos], _cluster_end(section.text, src[pos + len(needle) - 1])
    if normalize(section.text[start:end]) != needle:
        # The match starts or ends inside one source cluster, e.g. "f" out of "ﬁ".
        return QuoteError(reason="quote splits a source character")
    return q.model_copy(update={"span": (start, end)})


def verify_cell(q: CellQuote, corpus: Corpus) -> CellQuote | QuoteError:
    table = corpus.table(q.table_id)
    if table is None:
        return QuoteError(reason=f"unknown table {q.table_id}")
    if q.column not in table.columns:
        return QuoteError(reason=f"unknown column {q.column!r}")
    labels = [r.label for r in table.rows]
    if q.row_label not in labels:
        return QuoteError(reason=f"unknown row {q.row_label!r}")
    row, col = labels.index(q.row_label), table.columns.index(q.column)
    if normalize(table.rows[row].cells[col].text) != normalize(q.text):
        return QuoteError(reason="cell text does not match")
    return q.model_copy(update={"position": (row, col)})
