from __future__ import annotations

import re

# Design §6.6: words a neutral prototype never writes in its own voice, applied only
# outside quoted text (the audited code may itself say "should" or "density"). Each term
# matches its inflections ("recommend" catches "recommends"), and the term, not the surface
# form, is what gets flagged.
_TERMS = ["should", "recommend", "we suggest", "better", "worse", "density", "affordab"]
_LINT = re.compile("|".join(rf"(?P<t{i}>\b{re.escape(t)}\w*)" for i, t in enumerate(_TERMS)),
                   re.IGNORECASE)

# Quoted runs: "double" or 'single'. Straight quotes only, matching how claims are written.
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")


def flags(text: str) -> list[str]:
    """The lint terms that appear outside any quoted run of `text`, in order, without
    repeats. A term inside a quote never flags: the code is allowed to say it."""
    outside = _QUOTED.sub(" ", text)
    seen: list[str] = []
    for m in _LINT.finditer(outside):
        term = _TERMS[int(m.lastgroup[1:])]
        if term not in seen:
            seen.append(term)
    return seen
