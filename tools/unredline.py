"""Extract and reverse-apply the April 2025 Planning Department redline (design §4.2).

Deleted text is red and inserted text is green. Color is the signal: on page 31 strike
lines miss most insertions and table borders cross unchanged text. Both layers sit in
native stream order, so a page's pre-correction text is its unchanged plus deleted
characters, and its post-correction text is unchanged plus inserted.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pdfplumber
import yaml

_DELETED_RGB = (1.0, 0.0, 0.0)
_INSERTED_RGB = (0.2196, 0.4627, 0.1137)
_COLOR_TOL = 0.05
_CONTEXT = 60
_ARTICLE = re.compile(r"Article (\d+[A-Z]*):")
# Over a page's per-char kinds: d deleted, i inserted, w unchanged whitespace, k other.
# An edit is deletions then insertions, bridging whitespace gaps but never unchanged text.
_EDIT = re.compile(r"d(?:w*d)*(?:w*i(?:w*i)*)?|i(?:w*i)*")


@dataclass(frozen=True)
class Edit:
    page: int
    article: str | None
    deleted_text: str
    inserted_text: str
    context_before: str  # post-correction text just before inserted_text
    context_after: str


class ColorSpaceError(RuntimeError):
    pass


class ApplyError(RuntimeError):
    pass


def _char_kind(char: dict) -> str:
    color = char.get("non_stroking_color")
    if color is None:
        return "keep"
    if not isinstance(color, (tuple, list)) or len(color) != 3:
        raise ColorSpaceError(f"non-RGB fill color: {color!r}")
    for kind, rgb in (("del", _DELETED_RGB), ("ins", _INSERTED_RGB)):
        if all(abs(float(a) - b) <= _COLOR_TOL for a, b in zip(color, rgb)):
            return kind
    return "keep"


def _page_edits(chars: list[dict], page: int, article: str | None) -> tuple[list[Edit], str | None]:
    texts = [c["text"] for c in chars]
    kinds = [_char_kind(c) for c in chars]
    codes = "".join(k[0] if k != "keep" else "w" if t.isspace() else "k" for k, t in zip(kinds, texts))
    post_at = [0]
    for k in kinds:
        post_at.append(post_at[-1] + (k != "del"))
    post = "".join(t for t, k in zip(texts, kinds) if k != "del")
    headings = [(m.start(), m.group(1)) for m in _ARTICLE.finditer("".join(texts))]

    edits = []
    for m in _EDIT.finditer(codes):
        a, b = m.span()
        start, end = post_at[a], post_at[b]
        edits.append(Edit(
            page=page,
            article=next((art for at, art in reversed(headings) if at <= a), article),
            deleted_text="".join(t for t, k in zip(texts[a:b], kinds[a:b]) if k != "ins"),
            inserted_text=post[start:end],
            context_before=post[max(0, start - _CONTEXT):start],
            context_after=post[end:end + _CONTEXT],
        ))
    return edits, headings[-1][1] if headings else article


def extract_edits(pdf: Path) -> list[Edit]:
    edits: list[Edit] = []
    article = None
    with pdfplumber.open(pdf) as doc:
        for page_no, page in enumerate(doc.pages, start=1):
            found, article = _page_edits(page.chars, page_no, article)
            edits += found
    return edits


def _find_all(text: str, needle: str) -> list[int]:
    hits, i = [], text.find(needle) if needle else -1
    while i != -1:
        hits.append(i)
        i = text.find(needle, i + 1)
    return hits


def apply_reverse(post: str, edits: list[Edit]) -> str:
    """Restore pre-correction text. Each edit must match exactly once, with its context,
    in the original `post`; all spans are found first, then rebuilt in one pass."""
    spans: list[tuple[int, int, str]] = []
    failures: list[str] = []
    for e in edits:
        hits = _find_all(post, e.context_before + e.inserted_text + e.context_after)
        if len(hits) != 1:
            failures.append(f"page {e.page}: {e.inserted_text!r} -> {e.deleted_text!r} matched "
                            f"{len(hits)} times with its context, expected once")
            continue
        start = hits[0] + len(e.context_before)
        spans.append((start, start + len(e.inserted_text), e.deleted_text))
    spans.sort()
    failures += [f"edits overlap at {a[0]}:{a[1]} and {b[0]}:{b[1]}"
                 for a, b in zip(spans, spans[1:]) if b[0] < a[1] or b[0] == a[0]]
    if failures:
        raise ApplyError("reverse-apply failed:\n" + "\n".join(failures))
    out, cursor = [], 0
    for start, end, deleted in spans:
        out += [post[cursor:start], deleted]
        cursor = end
    return "".join(out) + post[cursor:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract or reverse-apply a redline PDF.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    edits_cmd = sub.add_parser("edits", help="Print extracted edits as YAML.")
    edits_cmd.add_argument("pdf", type=Path)
    edits_cmd.add_argument("--pages", help="Comma-separated 1-based pages, e.g. 20,31,52.")
    apply_cmd = sub.add_parser("apply", help="Reverse-apply an edits YAML to post-correction text.")
    apply_cmd.add_argument("edits", type=Path)
    apply_cmd.add_argument("text", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "edits":
        edits = extract_edits(args.pdf)
        if args.pages:
            wanted = {int(p) for p in args.pages.split(",")}
            edits = [e for e in edits if e.page in wanted]
        yaml.safe_dump([asdict(e) for e in edits], sys.stdout, sort_keys=False,
                       allow_unicode=True, width=100)
        return 0
    edits = [Edit(**d) for d in yaml.safe_load(args.edits.read_text(encoding="utf-8"))]
    try:
        sys.stdout.write(apply_reverse(args.text.read_text(encoding="utf-8"), edits))
    except ApplyError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
