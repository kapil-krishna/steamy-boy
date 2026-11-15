"""Pydantic models for Steam API responses: the validation boundary for Steam data.

Each model declares only the fields we keep. Pydantic ignores undeclared fields, so
`author.steamid` is dropped here and never reaches the rest of the code (D8, R4).
Unix timestamps are parsed into timezone-aware UTC datetimes.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _SteamModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class ReviewAuthor(_SteamModel):
    """The review author's play stats. Deliberately has no `steamid` field (D8)."""

    num_reviews: int
    playtime_forever: int
    """Minutes played in total, as of now."""
    playtime_last_two_weeks: int
    playtime_at_review: int | None = None
    """Minutes played when the review was written. Missing on some older reviews."""
    last_played: datetime | None = None


class SteamReview(_SteamModel):
    recommendation_id: int = Field(alias="recommendationid")
    author: ReviewAuthor
    language: str
    review: str
    timestamp_created: datetime
    timestamp_updated: datetime
    voted_up: bool
    votes_up: int
    votes_funny: int
    weighted_vote_score: float
    comment_count: int
    steam_purchase: bool
    received_for_free: bool
    refunded: bool = False
    written_during_early_access: bool
    primarily_steam_deck: bool = False
    developer_response: str | None = None
    timestamp_dev_responded: datetime | None = None


class QuerySummary(_SteamModel):
    num_reviews: int
    """Reviews on this page."""
    total_reviews: int | None = None
    """Reviews matching the query in total. Reported on the first page."""
    total_positive: int | None = None
    total_negative: int | None = None


class ReviewsPage(_SteamModel):
    """One page of `GetAppReviews` results (the body of its `response` envelope)."""

    reviews: list[SteamReview] = []
    cursor: str | None = None
    """Pass this back to get the next page. Steam may repeat it at the end of the results."""
    query_summary: QuerySummary | None = None


class NewsItem(_SteamModel):
    """One post from `GetNewsForApp`: a patch note, announcement or press item. Raw BBCode."""

    gid: str
    title: str
    url: str
    author: str = ""
    contents: str
    feedlabel: str
    feedname: str
    feed_type: int
    date: datetime
    tags: list[str] = []
