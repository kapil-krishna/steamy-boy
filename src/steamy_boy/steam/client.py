"""A thin client for the Steam endpoints in D9. One method call = one HTTP request.

The client doesn't retry. It classifies failures instead: rate limits (429), server
errors (5xx) and network errors raise `RetryableError`, and anything else raises
normally. Callers decide the retry policy by wrapping calls in `call_with_retry`.
"""

import json
from datetime import datetime
from enum import IntEnum
from typing import Any

import httpx

from steamy_boy.retry import RetryableError
from steamy_boy.steam.models import NewsItem, ReviewsPage

REVIEWS_URL = "https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/"
NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
USER_AGENT = "steamy-boy/0.1"
FIRST_PAGE_CURSOR = "*"


class ReviewFilter(IntEnum):
    """How `GetAppReviews` orders results. Only these two page through everything (D9)."""

    RECENT = 1
    """Newest created first."""
    UPDATED = 2
    """Most recently updated first."""


def make_http_client(timeout_seconds: float = 30.0) -> httpx.Client:
    return httpx.Client(timeout=timeout_seconds, headers={"User-Agent": USER_AGENT})


class SteamClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def fetch_reviews_page(
        self,
        app_id: int,
        *,
        cursor: str = FIRST_PAGE_CURSOR,
        review_filter: ReviewFilter = ReviewFilter.UPDATED,
        language: str = "english",
        per_page: int = 100,
    ) -> ReviewsPage:
        """Fetch one page of reviews. Start with cursor `"*"`, then pass back `page.cursor`."""
        query = {
            "appid": app_id,
            "filter": int(review_filter),
            "language": language,
            "review_type": "all",
            "purchase_type": "all",
            "num_per_page": per_page,
            "cursor": cursor,
        }
        body = self._get_json(REVIEWS_URL, {"input_json": json.dumps(query)})
        return ReviewsPage.model_validate(body.get("response", {}))

    def fetch_news(
        self, app_id: int, *, count: int, end_date: datetime | None = None
    ) -> list[NewsItem]:
        """Fetch up to `count` news posts, newest first, with full contents.

        Pass `end_date` to page backwards: only posts at or before it are returned.
        """
        params: dict[str, Any] = {"appid": app_id, "count": count, "maxlength": 0}
        if end_date is not None:
            params["enddate"] = int(end_date.timestamp())
        body = self._get_json(NEWS_URL, params)
        items = body.get("appnews", {}).get("newsitems", [])
        return [NewsItem.model_validate(item) for item in items]

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._http.get(url, params=params)
        except httpx.TransportError as error:  # timeouts, connection failures
            raise RetryableError(f"network error calling Steam: {error!r}") from error

        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableError(
                f"Steam returned HTTP {response.status_code}",
                retry_after=_retry_after_seconds(response),
            )
        response.raise_for_status()  # other 4xx: a bug on our side, so don't retry
        return response.json()


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Read `Retry-After` when it's a number of seconds. The HTTP-date form is ignored."""
    value = response.headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None
