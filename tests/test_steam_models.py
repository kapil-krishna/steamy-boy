from datetime import UTC, datetime

from steam_payloads import news_item_json, review_json

from steamy_boy.steam.models import NewsItem, SteamReview


def test_steam_id_is_dropped_at_parse_time():
    review = SteamReview.model_validate(review_json())

    assert "steamid" not in review.author.model_dump()
    assert "steamid" not in str(review.model_dump())


def test_review_fields_are_parsed():
    review = SteamReview.model_validate(review_json("239649014"))

    assert review.recommendation_id == 239649014
    assert review.author.playtime_at_review == 600
    assert review.timestamp_updated == datetime.fromtimestamp(1_793_500_000, UTC)
    assert review.timestamp_updated.tzinfo is not None


def test_optional_fields_default_when_steam_omits_them():
    payload = review_json()
    del payload["author"]["playtime_at_review"]
    del payload["refunded"]

    review = SteamReview.model_validate(payload)

    assert review.author.playtime_at_review is None
    assert review.refunded is False
    assert review.developer_response is None


def test_weighted_vote_score_accepts_steams_string_form():
    review = SteamReview.model_validate(review_json(weighted_vote_score="0.523809"))

    assert review.weighted_vote_score == 0.523809


def test_news_item_without_tags_gets_an_empty_list():
    payload = news_item_json()
    del payload["tags"]

    assert NewsItem.model_validate(payload).tags == []
