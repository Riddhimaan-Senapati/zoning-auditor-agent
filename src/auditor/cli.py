import argparse
import sys
from pathlib import Path

from auditor.saved_pages import check_saved_dir


def _check_pages(args: argparse.Namespace) -> None:
    problems = [p for d in args.dirs for p in check_saved_dir(d)]
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(1)
    print("saved pages look complete")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="auditor",
        description="Boston Zoning Code Auditor. Independent prototype, not a City of Boston service.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-pages", help="fail if a saved page holds no real code text")
    check.add_argument("dirs", nargs="+", type=Path)
    check.set_defaults(run=_check_pages)
    args = parser.parse_args(argv)
    args.run(args)
