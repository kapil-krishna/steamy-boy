-- Reviews from IUserReviewsService/GetAppReviews (D9).
-- There is no reviewer Steam ID column, by design (D8, R4).
CREATE TABLE reviews (
    recommendation_id               bigint           PRIMARY KEY,
    app_id                          integer          NOT NULL,
    language                        text             NOT NULL,
    review_text                     text             NOT NULL,
    voted_up                        boolean          NOT NULL,
    created_at                      timestamptz      NOT NULL,
    updated_at                      timestamptz      NOT NULL,
    playtime_at_review_minutes      integer,
    playtime_forever_minutes        integer          NOT NULL,
    playtime_last_two_weeks_minutes integer          NOT NULL,
    author_last_played_at           timestamptz,
    author_num_reviews              integer          NOT NULL,
    votes_up                        integer          NOT NULL,
    votes_funny                     integer          NOT NULL,
    weighted_vote_score             double precision NOT NULL,
    comment_count                   integer          NOT NULL,
    steam_purchase                  boolean          NOT NULL,
    received_for_free               boolean          NOT NULL,
    refunded                        boolean          NOT NULL,
    written_during_early_access     boolean          NOT NULL,
    primarily_steam_deck            boolean          NOT NULL,
    developer_response              text,
    developer_responded_at          timestamptz,
    ingested_at                     timestamptz      NOT NULL DEFAULT now()
);

CREATE INDEX reviews_app_id_updated_at_idx ON reviews (app_id, updated_at);

-- Raw posts from ISteamNews/GetNewsForApp: patch notes mixed with announcements and
-- press (K2). Filtering and BBCode cleaning come at M3 (R3).
CREATE TABLE news_items (
    gid          text        PRIMARY KEY,
    app_id       integer     NOT NULL,
    title        text        NOT NULL,
    url          text        NOT NULL,
    author       text        NOT NULL,
    contents     text        NOT NULL,
    feed_label   text        NOT NULL,
    feed_name    text        NOT NULL,
    feed_type    integer     NOT NULL,
    published_at timestamptz NOT NULL,
    tags         text[]      NOT NULL DEFAULT '{}',
    ingested_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX news_items_app_id_published_at_idx ON news_items (app_id, published_at);
