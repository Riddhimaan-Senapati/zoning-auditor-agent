import argparse


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="auditor",
        description="Boston Zoning Code Auditor. Independent prototype, not a City of Boston service.",
    )
    parser.add_subparsers(dest="command", required=True)
    args = parser.parse_args(argv)
    args.run(args)
