from __future__ import annotations

import hashlib
from collections import Counter

from auditor.models import Candidate, Verdict, XRef

# Design §6.3: the statuses the code proves, which skip the skeptic.
_SKIP_SKEPTIC = frozenset({
    "self_mismatch", "missing", "undefined_district", "footnote_missing", "footnote_unused",
    "definition_mismatch",
})


def candidates(xrefs: list[XRef]) -> list[Candidate]:
    return [
        Candidate(
            id=hashlib.sha256(f"{x.quote.model_dump_json()}|{x.resolution.detail}".encode()).hexdigest()[:16],
            type="xref",
            origin="deterministic",
            quotes=[x.quote],
            claim=x.resolution.detail,
            readings=None,
            payload=x.resolution.model_dump(exclude={"detail"}),
        )
        for x in xrefs
        if x.resolution.status not in ("ok", "external_unchecked")
    ]


def funnel_counts(xrefs: list[XRef]) -> Counter[str]:
    return Counter(x.resolution.status for x in xrefs)


def skipped_verdict(candidate: Candidate) -> Verdict:
    if candidate.payload["status"] not in _SKIP_SKEPTIC:
        raise ValueError(f"{candidate.payload['status']} candidates go to the skeptic")
    return Verdict(candidate_id=candidate.id, quote_failures=[], skeptic="skipped",
                   skeptic_reasoning=None, reconciling_quotes=[], sections_retrieved=[])
