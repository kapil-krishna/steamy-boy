import time
from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any

import psycopg
import pytest
from steam_payloads import news_item_json, review_json

from steamy_boy.ingest import ingest_news, ingest_reviews
from steamy_boy.retry import RetryableError
from steamy_boy.steam.client import FIRST_PAGE_CURSOR, ReviewFilter
from steamy_boy.steam.models import NewsItem, ReviewsPage

pytestmark = pytest.mark.integration

APP_ID = 2742830
OCT_2026 = 1_793_000_000  # well before "now", so older than any run's cutoff


class FakeSteam:
    """Serves synthetic data the way Steam does: newest first, one page at a time.

    Reviews page with a cursor (the offset as text) and repeat the cursor at the end. News
    pages backwards by date. `fail_on_call` raises a non-retryable error on that call
    (1-based); `retryable_failures` raises `RetryableError` on the first N calls.
    """

    def __init__(
        self,
        reviews: Sequence[dict[str, Any]] = (),
        news: Sequence[dict[str, Any]] = (),
        *,
        page_size: int = 2,
        fail_on_call: int | None = None,
        retryable_failures: int = 0,
    ) -> None:
        self.reviews = sorted(reviews, key=lambda r: r["timestamp_updated"], reverse=True)
        self.news = sorted(news, key=lambda n: n["date"], reverse=True)
        self.page_size = page_size
        self.fail_on_call = fail_on_call
        self.retryable_failures = retryable_failures
        self.review_calls = 0

    def fetch_reviews_page(
        self,
        app_id: int,
        *,
        cursor: str = FIRST_PAGE_CURSOR,
        review_filter: ReviewFilter = ReviewFilter.UPDATED,
    ) -> ReviewsPage:
        assert review_filter is ReviewFilter.UPDATED
        self.review_calls += 1
        if self.review_calls == self.fail_on_call:
            raise RuntimeError("simulated crash")
        if self.retryable_failures:
            self.retryable_failures -= 1
            raise RetryableError("HTTP 429")

        offset = 0 if cursor == FIRST_PAGE_CURSOR else int(cursor)
        chunk = self.reviews[offset : offset + self.page_size]
        next_cursor = str(offset + len(chunk)) if chunk else cursor
        return ReviewsPage.model_validate(
            {
                "reviews": chunk,
                "cursor": next_cursor,
                "query_summary": {"num_reviews": len(chunk), "total_reviews": len(self.reviews)},
            }
        )

    def fetch_news(
        self, app_id: int, *, count: int, end_date: datetime | None = None
    ) -> list[NewsItem]:
        items = [n for n in self.news if end_date is None or n["date"] <= int(end_date.timestamp())]
        return [NewsItem.model_validate(n) for n in items[:count]]


def no_sleep(_: float) -> None:
    pass


def make_reviews(count: int) -> list[dict[str, Any]]:
    """Reviews 1..count, with review 1 the most recently edited."""
    return [review_json(str(i), timestamp_updated=OCT_2026 - i * 60) for i in range(1, count + 1)]


def run(conn: psycopg.Connection, steam: FakeSteam, **kwargs: Any):
    return ingest_reviews(conn, steam, APP_ID, sleep=no_sleep, **kwargs)


def stored_ids(conn: psycopg.Connection) -> set[int]:
    rows = conn.execute("SELECT recommendation_id FROM reviews WHERE deleted_at IS NULL")
    return {row[0] for row in rows}


@pytest.fixture(autouse=True)
def empty_tables(conn: psycopg.Connection) -> Iterator[None]:
    conn.execute("TRUNCATE reviews, news_items, ingest_runs")
    yield


# --- Reviews: first run and refresh (R1, R2) -------------------------------------------


def test_first_run_stores_every_review_across_pages(conn):
    result = run(conn, FakeSteam(make_reviews(5)))

    assert stored_ids(conn) == {1, 2, 3, 4, 5}
    assert (result.pages, result.fetched, result.written) == (3, 5, 5)
    assert (result.steam_total, result.stored) == (5, 5)


def test_second_run_with_no_changes_writes_nothing_and_stops_after_one_page(conn):
    steam = FakeSteam(make_reviews(6))
    run(conn, steam)
    steam.review_calls = 0

    result = run(conn, steam)

    assert result.written == 0
    assert steam.review_calls == 1


def test_edited_review_is_updated_in_place(conn):
    reviews = make_reviews(4)
    run(conn, FakeSteam(reviews))
    reviews[2] = review_json("3", review="Changed my mind.", timestamp_updated=int(time.time()))

    result = run(conn, FakeSteam(reviews))

    assert result.written == 1
    text = conn.execute("SELECT review_text FROM reviews WHERE recommendation_id = 3").fetchone()
    assert text == ("Changed my mind.",)
    assert result.stored == 4


def test_new_review_is_added_on_refresh(conn):
    reviews = make_reviews(3)
    run(conn, FakeSteam(reviews))
    reviews.append(review_json("99", timestamp_updated=int(time.time())))

    result = run(conn, FakeSteam(reviews))

    assert result.written == 1
    assert 99 in stored_ids(conn)


def test_a_crashed_run_does_not_stop_the_next_run_early(conn):
    """The trap D13 avoids: newest reviews are saved first, so a crash must not count as
    a checkpoint, or the next run would think the older reviews were already stored."""
    steam = FakeSteam(make_reviews(6), fail_on_call=2)
    with pytest.raises(RuntimeError):
        run(conn, steam)
    assert stored_ids(conn) == {1, 2}  # page 1 was committed before the crash

    steam.fail_on_call = None
    run(conn, steam)

    assert stored_ids(conn) == {1, 2, 3, 4, 5, 6}


def test_retryable_errors_are_retried(conn):
    run(conn, FakeSteam(make_reviews(2), retryable_failures=2))

    assert stored_ids(conn) == {1, 2}


def test_reviewer_steam_id_is_not_stored(conn):
    run(conn, FakeSteam(make_reviews(1)))

    row = conn.execute("SELECT row_to_json(reviews)::text FROM reviews").fetchone()
    assert row is not None
    assert "76561190000000001" not in row[0]


# --- Reviews: soft delete via a full run (D13) -----------------------------------------


def test_full_run_marks_reviews_missing_from_steam_as_deleted(conn):
    reviews = make_reviews(4)
    run(conn, FakeSteam(reviews))

    result = run(
        conn,
        FakeSteam([r for r in reviews if r["recommendationid"] != "2"]),
        full=True,
        max_delete_fraction=0.5,
    )

    assert result.marked_deleted == 1
    assert stored_ids(conn) == {1, 3, 4}
    deleted = conn.execute("SELECT deleted_at FROM reviews WHERE recommendation_id = 2").fetchone()
    assert deleted is not None and deleted[0] is not None  # kept, just marked


def test_deleted_review_that_reappears_is_restored(conn):
    reviews = make_reviews(4)
    run(conn, FakeSteam(reviews))
    run(conn, FakeSteam(reviews[1:]), full=True, max_delete_fraction=0.5)

    run(conn, FakeSteam(reviews), full=True)

    assert stored_ids(conn) == {1, 2, 3, 4}


def test_full_run_refuses_to_delete_more_than_the_safety_limit(conn):
    reviews = make_reviews(4)
    run(conn, FakeSteam(reviews))

    result = run(conn, FakeSteam(reviews[:1]), full=True)  # 3 of 4 missing: over 5%

    assert result.deletion_skipped
    assert result.marked_deleted == 0
    assert stored_ids(conn) == {1, 2, 3, 4}


def test_incremental_run_never_marks_deletions(conn):
    reviews = make_reviews(4)
    run(conn, FakeSteam(reviews))

    run(conn, FakeSteam(reviews[:1]))

    assert stored_ids(conn) == {1, 2, 3, 4}


# --- News -------------------------------------------------------------------------------


def make_news(count: int) -> list[dict[str, Any]]:
    return [news_item_json(str(i), date=OCT_2026 - i * 3600) for i in range(1, count + 1)]


def test_news_first_run_pages_back_and_stores_every_post_once(conn):
    result = ingest_news(conn, FakeSteam(news=make_news(5)), APP_ID, sleep=no_sleep, page_size=2)

    gids = [row[0] for row in conn.execute("SELECT gid FROM news_items ORDER BY gid")]
    assert gids == ["1", "2", "3", "4", "5"]
    assert result.written == 5


def test_news_second_run_writes_nothing(conn):
    steam = FakeSteam(news=make_news(5))
    ingest_news(conn, steam, APP_ID, sleep=no_sleep, page_size=2)

    result = ingest_news(conn, steam, APP_ID, sleep=no_sleep, page_size=2)

    assert result.written == 0
    assert result.pages == 1
