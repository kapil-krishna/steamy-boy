"""SQL for the tables ingest writes: reviews, news posts and ingest runs.

The repository layer: plain functions that take a connection and run one query each. The
rules about *when* to call them (checkpoints, the delete safety limit) live in `ingest`.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Literal

import psycopg

from steamy_boy.steam.models import NewsItem, SteamReview

Source = Literal["reviews", "news"]


# --- Ingest runs (the checkpoint, D13) -------------------------------------------------


def last_finished_run_start(
    conn: psycopg.Connection, app_id: int, source: Source
) -> datetime | None:
    """When the most recent *finished* run started. None if no run has finished."""
    row = conn.execute(
        """
        SELECT max(started_at) FROM ingest_runs
        WHERE app_id = %s AND source = %s AND finished_at IS NOT NULL
        """,
        (app_id, source),
    ).fetchone()
    return row[0] if row else None


def start_run(conn: psycopg.Connection, app_id: int, source: Source, full: bool) -> int:
    row = conn.execute(
        "INSERT INTO ingest_runs (app_id, source, full_refresh) VALUES (%s, %s, %s) RETURNING id",
        (app_id, source, full),
    ).fetchone()
    assert row is not None
    return row[0]


def finish_run(conn: psycopg.Connection, run_id: int, rows_written: int) -> None:
    conn.execute(
        "UPDATE ingest_runs SET finished_at = now(), rows_written = %s WHERE id = %s",
        (rows_written, run_id),
    )


# --- Reviews ---------------------------------------------------------------------------

# Insert a new review. For one we already have, update it only if Steam's copy was edited
# since (or it was soft-deleted and has come back). An unchanged review matches no row in
# the WHERE, so nothing is written (R2). EXCLUDED is the row we tried to insert.
_UPSERT_REVIEW = """
INSERT INTO reviews (
    recommendation_id, app_id, language, review_text, voted_up, created_at, updated_at,
    playtime_at_review_minutes, playtime_forever_minutes, playtime_last_two_weeks_minutes,
    author_last_played_at, author_num_reviews, votes_up, votes_funny, weighted_vote_score,
    comment_count, steam_purchase, received_for_free, refunded, written_during_early_access,
    primarily_steam_deck, developer_response, developer_responded_at
) VALUES (
    %(recommendation_id)s, %(app_id)s, %(language)s, %(review_text)s, %(voted_up)s,
    %(created_at)s, %(updated_at)s, %(playtime_at_review_minutes)s,
    %(playtime_forever_minutes)s, %(playtime_last_two_weeks_minutes)s,
    %(author_last_played_at)s, %(author_num_reviews)s, %(votes_up)s, %(votes_funny)s,
    %(weighted_vote_score)s, %(comment_count)s, %(steam_purchase)s, %(received_for_free)s,
    %(refunded)s, %(written_during_early_access)s, %(primarily_steam_deck)s,
    %(developer_response)s, %(developer_responded_at)s
)
ON CONFLICT (recommendation_id) DO UPDATE SET
    language = EXCLUDED.language,
    review_text = EXCLUDED.review_text,
    voted_up = EXCLUDED.voted_up,
    updated_at = EXCLUDED.updated_at,
    playtime_at_review_minutes = EXCLUDED.playtime_at_review_minutes,
    playtime_forever_minutes = EXCLUDED.playtime_forever_minutes,
    playtime_last_two_weeks_minutes = EXCLUDED.playtime_last_two_weeks_minutes,
    author_last_played_at = EXCLUDED.author_last_played_at,
    author_num_reviews = EXCLUDED.author_num_reviews,
    votes_up = EXCLUDED.votes_up,
    votes_funny = EXCLUDED.votes_funny,
    weighted_vote_score = EXCLUDED.weighted_vote_score,
    comment_count = EXCLUDED.comment_count,
    steam_purchase = EXCLUDED.steam_purchase,
    received_for_free = EXCLUDED.received_for_free,
    refunded = EXCLUDED.refunded,
    written_during_early_access = EXCLUDED.written_during_early_access,
    primarily_steam_deck = EXCLUDED.primarily_steam_deck,
    developer_response = EXCLUDED.developer_response,
    developer_responded_at = EXCLUDED.developer_responded_at,
    deleted_at = NULL,
    ingested_at = now()
WHERE reviews.updated_at < EXCLUDED.updated_at OR reviews.deleted_at IS NOT NULL
"""


def upsert_reviews(conn: psycopg.Connection, app_id: int, reviews: Iterable[SteamReview]) -> int:
    """Upsert one page in one transaction. Returns the number of rows inserted or changed."""
    written = 0
    with conn.transaction(), conn.cursor() as cur:
        for review in reviews:
            cur.execute(_UPSERT_REVIEW, _review_row(app_id, review))
            written += cur.rowcount
    return written


def _review_row(app_id: int, review: SteamReview) -> dict[str, object]:
    """Map Steam's field names to our columns. The author's Steam ID was already dropped
    by the model (D8)."""
    author = review.author
    return {
        "recommendation_id": review.recommendation_id,
        "app_id": app_id,
        "language": review.language,
        "review_text": review.review,
        "voted_up": review.voted_up,
        "created_at": review.timestamp_created,
        "updated_at": review.timestamp_updated,
        "playtime_at_review_minutes": author.playtime_at_review,
        "playtime_forever_minutes": author.playtime_forever,
        "playtime_last_two_weeks_minutes": author.playtime_last_two_weeks,
        "author_last_played_at": author.last_played,
        "author_num_reviews": author.num_reviews,
        "votes_up": review.votes_up,
        "votes_funny": review.votes_funny,
        "weighted_vote_score": review.weighted_vote_score,
        "comment_count": review.comment_count,
        "steam_purchase": review.steam_purchase,
        "received_for_free": review.received_for_free,
        "refunded": review.refunded,
        "written_during_early_access": review.written_during_early_access,
        "primarily_steam_deck": review.primarily_steam_deck,
        "developer_response": review.developer_response,
        "developer_responded_at": review.timestamp_dev_responded,
    }


def find_missing_reviews(conn: psycopg.Connection, app_id: int, seen: set[int]) -> list[int]:
    """IDs of stored, not-deleted reviews for this game that aren't in `seen`."""
    rows = conn.execute(
        """
        SELECT recommendation_id FROM reviews
        WHERE app_id = %s AND deleted_at IS NULL
          AND NOT (recommendation_id = ANY(%s::bigint[]))
        """,
        (app_id, list(seen)),
    )
    return [row[0] for row in rows]


def mark_reviews_deleted(conn: psycopg.Connection, recommendation_ids: list[int]) -> None:
    conn.execute(
        "UPDATE reviews SET deleted_at = now() WHERE recommendation_id = ANY(%s::bigint[])",
        (recommendation_ids,),
    )


def count_stored_reviews(conn: psycopg.Connection, app_id: int) -> int:
    """Reviews stored for this game, excluding soft-deleted ones."""
    row = conn.execute(
        "SELECT count(*) FROM reviews WHERE app_id = %s AND deleted_at IS NULL", (app_id,)
    ).fetchone()
    assert row is not None
    return row[0]


# --- News ------------------------------------------------------------------------------

# News posts have no edited timestamp, so a post we already have is skipped.
_INSERT_NEWS = """
INSERT INTO news_items (
    gid, app_id, title, url, author, contents, feed_label, feed_name, feed_type,
    published_at, tags
) VALUES (
    %(gid)s, %(app_id)s, %(title)s, %(url)s, %(author)s, %(contents)s, %(feed_label)s,
    %(feed_name)s, %(feed_type)s, %(published_at)s, %(tags)s
)
ON CONFLICT (gid) DO NOTHING
"""


def insert_news(conn: psycopg.Connection, app_id: int, items: Iterable[NewsItem]) -> int:
    written = 0
    with conn.transaction(), conn.cursor() as cur:
        for item in items:
            cur.execute(
                _INSERT_NEWS,
                {
                    "gid": item.gid,
                    "app_id": app_id,
                    "title": item.title,
                    "url": item.url,
                    "author": item.author,
                    "contents": item.contents,
                    "feed_label": item.feedlabel,
                    "feed_name": item.feedname,
                    "feed_type": item.feed_type,
                    "published_at": item.date,
                    "tags": item.tags,
                },
            )
            written += cur.rowcount
    return written
