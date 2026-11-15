"""Synthetic Steam API payloads shaped like real responses. No real review data (see AGENTS.md)."""

from typing import Any


def review_json(recommendation_id: str = "1001", **overrides: Any) -> dict[str, Any]:
    review: dict[str, Any] = {
        "recommendationid": recommendation_id,
        "author": {
            "steamid": "76561190000000001",
            "num_reviews": 3,
            "playtime_forever": 900,
            "playtime_last_two_weeks": 60,
            "playtime_at_review": 600,
            "last_played": 1_794_000_000,
        },
        "language": "english",
        "review": "Synthetic review text.",
        "timestamp_created": 1_793_000_000,
        "timestamp_updated": 1_793_500_000,
        "voted_up": True,
        "votes_up": 2,
        "votes_funny": 0,
        "weighted_vote_score": 0.52,
        "comment_count": 0,
        "steam_purchase": True,
        "received_for_free": False,
        "refunded": False,
        "written_during_early_access": False,
        "primarily_steam_deck": False,
    }
    review.update(overrides)
    return review


def reviews_response(*reviews: dict[str, Any], cursor: str = "next-cursor") -> dict[str, Any]:
    return {
        "response": {
            "query_summary": {"num_reviews": len(reviews), "total_reviews": 5116},
            "reviews": list(reviews),
            "cursor": cursor,
        }
    }


def news_item_json(gid: str = "2001", **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "gid": gid,
        "title": "Patch 1.2.3",
        "url": "https://store.steampowered.com/news/app/2742830",
        "is_external_url": True,
        "author": "dev-account",
        "contents": "[list][*]Fixed a crash[/list]",
        "feedlabel": "Community Announcements",
        "date": 1_793_815_227,
        "feedname": "steam_community_announcements",
        "feed_type": 1,
        "appid": 2742830,
        "tags": ["patchnotes"],
    }
    item.update(overrides)
    return item
