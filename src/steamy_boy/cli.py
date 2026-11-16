"""The `steamy-boy` command line."""

import argparse
import logging

from steamy_boy import db, ingest
from steamy_boy.steam.client import SteamClient, make_http_client

R1_TOLERANCE = 0.01
"""R1: the stored count must be within 1% of Steam's `total_reviews`."""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="steamy-boy")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="apply pending database migrations")
    ingest_cmd = commands.add_parser("ingest", help="load a game's reviews and news from Steam")
    ingest_cmd.add_argument("--app-id", type=int, required=True, help="Steam app ID")
    ingest_cmd.add_argument(
        "--full",
        action="store_true",
        help="fetch every review and mark ones Steam no longer returns as deleted",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "migrate":
        with db.connect() as conn:
            applied = db.migrate(conn)
        print(f"Applied: {', '.join(applied)}" if applied else "Database is up to date.")
    elif args.command == "ingest":
        with db.connect() as conn, make_http_client() as http:
            steam = SteamClient(http)
            reviews = ingest.ingest_reviews(conn, steam, args.app_id, full=args.full)
            news = ingest.ingest_news(conn, steam, args.app_id)
        print(reviews_summary(reviews))
        print(f"News: {news.pages} pages, {news.fetched} fetched, {news.written} new.")


def reviews_summary(result: ingest.ReviewsResult) -> str:
    lines = [f"Reviews: {result.pages} pages, {result.fetched} fetched, {result.written} written."]
    if result.marked_deleted:
        lines.append(f"Marked {result.marked_deleted} as deleted (no longer on Steam).")
    if result.deletion_skipped:
        lines.append("Too many reviews missing from Steam, so none were marked deleted.")
    if result.steam_total:
        gap = abs(result.stored - result.steam_total) / result.steam_total
        verdict = "OK" if gap <= R1_TOLERANCE else "MORE THAN 1% OFF"
        lines.append(
            f"Stored {result.stored:,} of Steam's {result.steam_total:,} ({gap:.1%} gap): {verdict}"
        )
    return "\n".join(lines)
