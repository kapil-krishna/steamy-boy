"""Load a game's Steam reviews and news posts into Postgres (R1, R2, raw R3).

Reviews come most-recently-edited first and are saved a page at a time with an upsert, so
a crash loses at most one page and re-running is always safe. A normal run stops once it
reaches reviews older than the last *finished* run. A full run reads every page, then
soft-deletes stored reviews that Steam no longer returns (D13).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Protocol

import psycopg

from steamy_boy import store
from steamy_boy.retry import call_with_retry
from steamy_boy.steam.client import FIRST_PAGE_CURSOR, ReviewFilter
from steamy_boy.steam.models import NewsItem, ReviewsPage

logger = logging.getLogger(__name__)

OVERLAP = timedelta(hours=1)
"""How far before the last finished run to re-check. Covers Steam's response cache (up to
10 minutes, D9) and clock differences. The upserts make re-reading the overlap harmless."""

PAUSE_SECONDS = 1.0
"""Pause between requests, to stay under Steam's anonymous rate limit (K1)."""

NEWS_PAGE_SIZE = 100

MAX_DELETE_FRACTION = 0.05
"""A full run refuses to soft-delete more than this share of a game's reviews, so a Steam
glitch (such as an empty response) can't mark everything deleted."""


class SteamSource(Protocol):
    """What ingest needs from Steam. `SteamClient` fits it; tests pass a fake."""

    def fetch_reviews_page(
        self, app_id: int, *, cursor: str = ..., review_filter: ReviewFilter = ...
    ) -> ReviewsPage: ...

    def fetch_news(
        self, app_id: int, *, count: int, end_date: datetime | None = None
    ) -> list[NewsItem]: ...


@dataclass(frozen=True)
class ReviewsResult:
    pages: int
    fetched: int
    written: int
    """Rows inserted or changed. Zero on a refresh when nothing changed on Steam (R2)."""
    steam_total: int | None
    """`total_reviews` as Steam reported it on the first page, for the R1 check."""
    stored: int
    """Reviews stored for this game, excluding soft-deleted ones."""
    marked_deleted: int = 0
    deletion_skipped: bool = False
    """True when a full run found too many missing reviews and marked none (see
    `MAX_DELETE_FRACTION`)."""


@dataclass(frozen=True)
class NewsResult:
    pages: int
    fetched: int
    written: int


def ingest_reviews(
    conn: psycopg.Connection,
    steam: SteamSource,
    app_id: int,
    *,
    full: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    max_delete_fraction: float = MAX_DELETE_FRACTION,
) -> ReviewsResult:
    """Fetch new and edited reviews (or every review, if `full`) and upsert them."""
    cutoff = None if full else _incremental_cutoff(conn, app_id, "reviews")
    run_id = store.start_run(conn, app_id, "reviews", full)

    seen: set[int] = set()
    steam_total: int | None = None
    pages = fetched = written = 0
    cursor = FIRST_PAGE_CURSOR

    while True:
        if pages:
            sleep(PAUSE_SECONDS)
        # partial(f, a, b=c) is a ready-to-call f(a, b=c), like a lambda but it captures
        # the current cursor value rather than the variable.
        fetch = partial(
            steam.fetch_reviews_page, app_id, cursor=cursor, review_filter=ReviewFilter.UPDATED
        )
        page = call_with_retry(fetch, sleep=sleep)
        if cursor == FIRST_PAGE_CURSOR and page.query_summary is not None:
            steam_total = page.query_summary.total_reviews
        if not page.reviews:
            break

        pages += 1
        fetched += len(page.reviews)
        seen.update(review.recommendation_id for review in page.reviews)
        written += store.upsert_reviews(conn, app_id, page.reviews)
        logger.info("Reviews page %d: %d fetched, %d written", pages, fetched, written)

        oldest = min(review.timestamp_updated for review in page.reviews)
        if cutoff is not None and oldest < cutoff:
            break  # newest edits come first, so everything after this is already stored
        if page.cursor is None or page.cursor == cursor:
            break  # Steam repeats the cursor at the end of the results
        cursor = page.cursor

    marked_deleted, deletion_skipped = 0, False
    if full:
        marked_deleted, deletion_skipped = _soft_delete_missing(
            conn, app_id, seen, max_delete_fraction
        )

    store.finish_run(conn, run_id, written)
    return ReviewsResult(
        pages=pages,
        fetched=fetched,
        written=written,
        steam_total=steam_total,
        stored=store.count_stored_reviews(conn, app_id),
        marked_deleted=marked_deleted,
        deletion_skipped=deletion_skipped,
    )


def ingest_news(
    conn: psycopg.Connection,
    steam: SteamSource,
    app_id: int,
    *,
    sleep: Callable[[float], None] = time.sleep,
    page_size: int = NEWS_PAGE_SIZE,
) -> NewsResult:
    """Fetch news posts newer than the last finished run (or all of them) and store new ones.

    `GetNewsForApp` has no cursor, so this pages backwards by date. Each page asks for
    posts at or before the oldest one seen so far, so the boundary post comes back again
    and is skipped by the insert.
    """
    cutoff = _incremental_cutoff(conn, app_id, "news")
    run_id = store.start_run(conn, app_id, "news", full=False)

    pages = fetched = written = 0
    end_date: datetime | None = None

    while True:
        if pages:
            sleep(PAUSE_SECONDS)
        fetch = partial(steam.fetch_news, app_id, count=page_size, end_date=end_date)
        items = call_with_retry(fetch, sleep=sleep)
        if not items:
            break

        pages += 1
        fetched += len(items)
        written += store.insert_news(conn, app_id, items)
        logger.info("News page %d: %d fetched, %d written", pages, fetched, written)

        oldest = min(item.date for item in items)
        if cutoff is not None and oldest < cutoff:
            break
        if end_date is not None and oldest >= end_date:
            break  # no older posts came back: we've reached the end
        end_date = oldest

    store.finish_run(conn, run_id, written)
    return NewsResult(pages=pages, fetched=fetched, written=written)


def _incremental_cutoff(
    conn: psycopg.Connection, app_id: int, source: store.Source
) -> datetime | None:
    """Where a normal run stops: the start of the last finished run, minus the overlap.
    None means no run has finished yet, so fetch everything."""
    last_start = store.last_finished_run_start(conn, app_id, source)
    return last_start - OVERLAP if last_start is not None else None


def _soft_delete_missing(
    conn: psycopg.Connection, app_id: int, seen: set[int], max_fraction: float
) -> tuple[int, bool]:
    """After a complete full run, mark stored reviews Steam didn't return as deleted.

    Returns (how many were marked, whether the safety limit stopped it).
    """
    with conn.transaction():
        missing = store.find_missing_reviews(conn, app_id, seen)
        if not missing:
            return 0, False

        stored = store.count_stored_reviews(conn, app_id)
        if len(missing) > max_fraction * stored:
            logger.warning(
                "Full run: %d of %d stored reviews are missing from Steam, more than %.0f%%. "
                "Not marking any as deleted; check Steam's response before re-running.",
                len(missing),
                stored,
                max_fraction * 100,
            )
            return 0, True

        store.mark_reviews_deleted(conn, missing)
        return len(missing), False
