import argparse
import sys
from pathlib import Path

from auditor.label import import_labels, run_label
from auditor.prompt_eval import run_prompt_eval
from auditor.saved_pages import check_saved_dir


def _check_pages(args: argparse.Namespace) -> None:
    problems = [p for d in args.dirs for p in check_saved_dir(d)]
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(1)
    print("saved pages look complete")


def _label(args: argparse.Namespace) -> None:
    run_id = args.run_id or args.items.resolve().parent.name
    run_label(args.items, args.kind, args.out, run_id=run_id, sample=args.sample, seed=args.seed)


def _import_labels(args: argparse.Namespace) -> None:
    print(import_labels(args.labels, args.evals))


def _prompt_eval(args: argparse.Namespace) -> None:
    print(run_prompt_eval(args.role, evals_dir=args.evals, build_dir=args.build_dir, run_dir=args.run_dir))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="auditor",
        description="Boston Zoning Code Auditor. Independent prototype, not a City of Boston service.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check-pages", help="fail if a saved page holds no real code text")
    check.add_argument("dirs", nargs="+", type=Path)
    check.set_defaults(run=_check_pages)

    label = commands.add_parser("label", help="label rules, xrefs, or findings in the terminal")
    label.add_argument("items", type=Path, help="items .jsonl to label")
    label.add_argument("--kind", required=True, choices=("rules", "xrefs", "findings"))
    label.add_argument("--out", required=True, type=Path, help="labels.json to write")
    label.add_argument("--sample", type=int, default=None, help="label a sample of N items")
    label.add_argument("--seed", type=int, default=0, help="sample seed")
    label.add_argument("--run-id", default=None, help="override run id (default: items parent dir)")
    label.set_defaults(run=_label)

    imp = commands.add_parser("import-labels", help="copy a labels.json into evals/labels/")
    imp.add_argument("labels", type=Path, help="labels.json to import")
    imp.add_argument("--evals", type=Path, default=Path("evals"), help="evals root (default: ./evals)")
    imp.set_defaults(run=_import_labels)

    pe = commands.add_parser(
        "prompt-eval", help="run a model role's per-prompt regression set and print k of n"
    )
    pe.add_argument("role", help="model role, e.g. extract_prose")
    pe.add_argument("--evals", type=Path, default=Path("evals"), help="evals root (default: ./evals)")
    pe.add_argument("--build-dir", required=True, type=Path, help="corpus build dir the cases run against")
    pe.add_argument("--run-dir", required=True, type=Path, help="run dir under AUDITOR_RUNS_ROOT for spend.jsonl and trace.jsonl")
    pe.set_defaults(run=_prompt_eval)

    args = parser.parse_args(argv)
    args.run(args)
