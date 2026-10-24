"""Isolation properties 6 and 8 (design §4.3, §9.2, §9.4; requirements 17.1, 19.3, 21.2)."""

import json

import pytest
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Joined so this source file does not itself contain the literal forbidden strings.
FORBIDDEN = ("zoning-auditor-" + "sealed", "zoning-auditor-" + "planted")

# Property 8: paths whose contents hold full code text or bulk data.
LOCAL_ONLY = (
    "data/corpus",
    "data/comparison",
    "data/sources",
    "data/raw",
    "build",
    "runs",
    "llm_cache",
)

# The spec documents the sealed and planted folder names by design (requirement 17.1).
SPEC_PREFIX = ".kiro/specs/"


def _git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


def _candidate_paths() -> list[str]:
    tracked = _git("ls-files")
    untracked = _git("ls-files", "--others", "--exclude-standard")
    return tracked + untracked


def test_property_6a_no_forbidden_folder_names_in_repo():
    offenders = []
    for rel in _candidate_paths():
        if rel.startswith(SPEC_PREFIX):
            continue
        path = REPO / rel
        try:
            text = path.read_text(errors="ignore")
        except (OSError, UnicodeError):
            continue
        for needle in FORBIDDEN:
            if needle in text:
                offenders.append((rel, needle))
    assert not offenders, f"forbidden folder names leaked: {offenders}"


def _strings_in(obj, acc: list[str]) -> None:
    if isinstance(obj, str):
        if len(obj) >= 20:
            acc.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            _strings_in(value, acc)
    elif isinstance(obj, list):
        for item in obj:
            _strings_in(item, acc)


def test_property_6b_no_case_text_in_prompt_files():
    cases_dir = REPO / "evals" / "prompts"
    prompts_dir = REPO / "src" / "auditor" / "prompts"
    if not cases_dir.is_dir() or not prompts_dir.is_dir():
        pytest.skip("no per-prompt cases or prompt files yet")

    quoted: list[str] = []
    for jsonl in sorted(cases_dir.glob("*.jsonl")):
        for line in jsonl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            _strings_in(json.loads(line), quoted)
    if not quoted:
        return

    prompt_texts = {
        p: p.read_text(errors="ignore")
        for p in prompts_dir.rglob("*")
        if p.is_file()
    }
    leaks = [
        (p.relative_to(REPO).as_posix(), text[:40])
        for text in quoted
        for p, body in prompt_texts.items()
        if text in body
    ]
    assert not leaks, f"prompt files contain per-case quoted text: {leaks}"


def test_property_8_local_only_paths_untracked_and_ignored():
    tracked = _git("ls-files")
    leaked = [
        rel
        for rel in tracked
        for base in LOCAL_ONLY
        if rel == base or rel.startswith(base + "/")
    ]
    assert not leaked, f"local-only paths are tracked by git: {leaked}"

    not_ignored = []
    for base in LOCAL_ONLY:
        probe = f"{base}/probe.html"
        result = subprocess.run(
            ["git", "check-ignore", probe], cwd=REPO, capture_output=True, text=True
        )
        if result.returncode != 0:
            not_ignored.append(probe)
    assert not not_ignored, f".gitignore does not cover: {not_ignored}"
