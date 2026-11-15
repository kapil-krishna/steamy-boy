"""The `steamy-boy` command line. `ingest` is added once the refresh exists."""

import argparse

from steamy_boy import db


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="steamy-boy")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply pending database migrations")

    args = parser.parse_args(argv)
    if args.command == "migrate":
        with db.connect() as conn:
            applied = db.migrate(conn)
        print(f"Applied: {', '.join(applied)}" if applied else "Database is up to date.")
