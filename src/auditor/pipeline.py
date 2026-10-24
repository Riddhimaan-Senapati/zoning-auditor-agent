from __future__ import annotations

import json
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from auditor import find_xrefs
from auditor.corpus import Corpus
from auditor.exports import cited_id, write_rules
from auditor.extract_tables import rules_from_table
from auditor.find_contradictions import model_candidates, structured_candidates
from auditor.findings import build, funnel
from auditor.judge_xref import agency_xrefs, judge, load_renames
from auditor.models import Candidate, Finding, Quote, Rule, Section, Table, Verdict
from auditor.quotes import normalize
from auditor.resolve import resolve_corpus
from auditor.verify import verify

ARTICLES_CONFIG = Path(__file__).resolve().parents[2] / "config" / "articles.toml"

Only = str | None  # "xref", "contradiction", or None for both


@dataclass
class Funnel:
    """The per-type funnel from findings.funnel, plus the eval line when a key is given."""

    per_type: dict[str, dict[str, int]]
    eval_line: str | None


def _load(build_dir: Path) -> tuple[list[Section], list[Table]]:
    def rows(name: str) -> list[str]:
        return [ln for ln in (build_dir / name).read_text(encoding="utf-8").splitlines() if ln.strip()]
    return ([Section.model_validate_json(ln) for ln in rows("sections.jsonl")],
            [Table.model_validate_json(ln) for ln in rows("tables.jsonl")])


def _article_config(articles: Iterable[str]) -> dict:
    with ARTICLES_CONFIG.open("rb") as fh:
        table = tomllib.load(fh)["article"]
    if missing := [a for a in articles if a not in table]:
        raise ValueError(f"config/articles.toml has no entry for article(s) {missing}; add them")
    return {a: table[a] for a in articles}


def _needs_model(candidate: Candidate) -> bool:
    """A candidate verify() would send to the skeptic: everything but a deterministic xref
    whose status the code already proves (design §6.3)."""
    return not (candidate.type == "xref"
                and candidate.payload.get("status") in find_xrefs._SKIP_SKEPTIC)


def _no_model_verdict(candidate: Candidate) -> Verdict:
    """A candidate whose verification would need a model, when the model is off: the quote
    gate did not fail, but no skeptic was asked, so the verdict is honestly uncertain."""
    return Verdict(candidate_id=candidate.id, quote_failures=[], skeptic="uncertain",
                   skeptic_reasoning="skeptic not run (--no-model)", reconciling_quotes=[],
                   sections_retrieved=[])


def run(build_dir: Path, name: str, *, only: Only = None, no_model: bool = False,
        key: Path | None = None, runs_root: Path, run_id: str | None = None) -> Funnel:
    """Audit one built corpus end to end (design §4.1). Deterministic xrefs and table rules
    run always; prose rules, model contradictions and judge_xref run unless no_model. Every
    candidate is verified (the quote gate in code, the skeptic by model), deduplicated into
    Findings, and written under runs/<name>/<run_id>/ with the rule exports. Returns the
    per-type funnel and, when a key is given, the design §9.1 eval line."""
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = runs_root / name / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    sections, tables = _load(build_dir)
    corpus = Corpus(sections, tables)
    articles = sorted({s.article for s in sections})
    cfg = _article_config(articles)

    # Table rules always; prose rules need a model and are skipped under --no-model.
    rules = [r for t in tables for r in rules_from_table(t, corpus)]
    rules_by_id = {r.id: r for r in rules}
    _write_rules_jsonl(run_dir, rules)
    write_rules(rules, run_dir, source_links={})

    candidates: list[Candidate] = []
    if only in (None, "xref"):
        candidates += find_xrefs.candidates(resolve_corpus(
            corpus, toc={}, articles=articles,
            established={a: set(cfg[a]["established"]) for a in articles},
            table_sections={tid: sec for a in articles for tid, sec in cfg[a]["table_sections"].items()},
            defined_terms={t for a in articles for t in cfg[a]["defined_terms"]},
            use_tables=[u for a in articles for u in cfg[a]["use_tables"]]))
        if not no_model:
            renames = load_renames()
            for section in sections:
                for xref in agency_xrefs(section, renames):
                    if (c := judge(xref, build_dir=build_dir, run_dir=run_dir)) is not None:
                        candidates.append(c)
    if only in (None, "contradiction"):
        candidates += structured_candidates(rules)[0]
        if not no_model:
            candidates += model_candidates(sections, rules, build_dir=build_dir, run_dir=run_dir)[0]

    pairs = [(c, _no_model_verdict(c)) if no_model and _needs_model(c)
             else verify(c, corpus, build_dir=build_dir, run_dir=run_dir)
             for c in candidates]

    findings = build(pairs, run_id, run_dir, rules_by_id)
    _write_findings_json(run_dir, run_id, findings)

    eval_line = _eval_line(findings, key, articles) if key is not None else None
    return Funnel(per_type=funnel(run_dir), eval_line=eval_line)


def _eval_line(findings: list[Finding], key: Path, articles: Iterable[str]) -> str:
    """Design §9.1 counting, over the key filtered to the corpus's articles. The headline
    unit is one summary_item (error), found when one in-scope instance matched; an instance
    matches when a verified quote of a same-article finding overlaps its normalized pre_text."""
    present = set(articles)
    entries = [e for e in yaml.safe_load(key.read_text(encoding="utf-8"))
               if e.get("in_scope") and str(e["article"]) in present]
    quotes_by_article: dict[str, list[str]] = {}
    for f in findings:
        for q in f.quotes:
            quotes_by_article.setdefault(_article_of(q), []).append(normalize(q.text))

    found = [_instance_found(e, quotes_by_article) for e in entries]
    errors: dict[str, bool] = {}
    for entry, hit in zip(entries, found):
        errors[entry["summary_item"]] = errors.get(entry["summary_item"], False) or hit
    return (f"{sum(errors.values())} of {len(errors)} errors "
            f"({sum(found)} of {len(entries)} instances)")


def _instance_found(entry: dict, quotes_by_article: dict[str, list[str]]) -> bool:
    pre = normalize(entry["pre_text"])
    return any(pre in q or q in pre for q in quotes_by_article.get(str(entry["article"]), []))


def _article_of(quote: Quote) -> str:
    return cited_id(quote).split("-")[0].split(":")[0]


def _write_rules_jsonl(run_dir: Path, rules: list[Rule]) -> None:
    (run_dir / "rules.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in rules), encoding="utf-8")


def _write_findings_json(run_dir: Path, run_id: str, findings: list[Finding]) -> None:
    doc = {"run_id": run_id, "findings": [f.model_dump(mode="json") for f in findings]}
    (run_dir / "findings.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
