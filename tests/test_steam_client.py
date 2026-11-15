import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from steam_payloads import news_item_json, review_json, reviews_response

from steamy_boy.retry import RetryableError
from steamy_boy.steam.client import ReviewFilter, SteamClient

Handler = Callable[[httpx.Request], httpx.Response]


def client_with(handler: Handler) -> SteamClient:
    return SteamClient(httpx.Client(transport=httpx.MockTransport(handler)))


def respond(status: int = 200, body: object = None, headers: dict[str, str] | None = None):
    """A handler that records each request and returns a fixed response."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=body if body is not None else {}, headers=headers)

    return handler, requests


def test_fetch_reviews_page_sends_the_query_as_input_json():
    handler, requests = respond(body=reviews_response())

    client_with(handler).fetch_reviews_page(
        2742830, cursor="abc", review_filter=ReviewFilter.RECENT
    )

    query = json.loads(requests[0].url.params["input_json"])
    assert query == {
        "appid": 2742830,
        "filter": 1,
        "language": "english",
        "review_type": "all",
        "purchase_type": "all",
        "num_per_page": 100,
        "cursor": "abc",
    }


def test_fetch_reviews_page_parses_reviews_and_cursor():
    handler, _ = respond(body=reviews_response(review_json("1"), review_json("2"), cursor="c2"))

    page = client_with(handler).fetch_reviews_page(2742830)

    assert [r.recommendation_id for r in page.reviews] == [1, 2]
    assert page.cursor == "c2"
    assert page.query_summary is not None
    assert page.query_summary.total_reviews == 5116


def test_fetch_reviews_page_handles_an_empty_response():
    handler, _ = respond(body={"response": {}})

    page = client_with(handler).fetch_reviews_page(2742830)

    assert page.reviews == []
    assert page.cursor is None


def test_rate_limit_is_retryable_and_carries_retry_after():
    handler, _ = respond(status=429, headers={"Retry-After": "12"})

    with pytest.raises(RetryableError) as raised:
        client_with(handler).fetch_reviews_page(2742830)

    assert raised.value.retry_after == 12.0


@pytest.mark.parametrize("retry_after", [None, "Wed, 21 Oct 2026 07:28:00 GMT"])
def test_retry_after_is_none_when_missing_or_not_seconds(retry_after):
    headers = {"Retry-After": retry_after} if retry_after else None
    handler, _ = respond(status=429, headers=headers)

    with pytest.raises(RetryableError) as raised:
        client_with(handler).fetch_reviews_page(2742830)

    assert raised.value.retry_after is None


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_errors_are_retryable(status):
    handler, _ = respond(status=status)

    with pytest.raises(RetryableError):
        client_with(handler).fetch_reviews_page(2742830)


def test_network_errors_are_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(RetryableError):
        client_with(handler).fetch_reviews_page(2742830)


def test_other_client_errors_are_not_retryable():
    handler, _ = respond(status=400)

    with pytest.raises(httpx.HTTPStatusError):
        client_with(handler).fetch_reviews_page(2742830)


def test_fetch_news_sends_paging_params_and_parses_items():
    body = {"appnews": {"appid": 2742830, "newsitems": [news_item_json("9")], "count": 1}}
    handler, requests = respond(body=body)
    end = datetime.fromtimestamp(1_793_000_000, UTC)

    items = client_with(handler).fetch_news(2742830, count=50, end_date=end)

    params = requests[0].url.params
    assert (params["appid"], params["count"], params["maxlength"]) == ("2742830", "50", "0")
    assert params["enddate"] == "1793000000"
    assert [item.gid for item in items] == ["9"]


def test_fetch_news_omits_enddate_by_default():
    handler, requests = respond(body={"appnews": {"newsitems": []}})

    assert client_with(handler).fetch_news(2742830, count=10) == []
    assert "enddate" not in requests[0].url.params
