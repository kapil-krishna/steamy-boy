-- Soft delete (D13): set by `ingest --full` when Steam no longer returns a review.
-- Analysis excludes these by default with `WHERE deleted_at IS NULL`.
ALTER TABLE reviews ADD COLUMN deleted_at timestamptz;

-- One row per ingest run. A run is the checkpoint for the next incremental run only
-- once `finished_at` is set, so a crashed run never makes the next one stop early (D13).
CREATE TABLE ingest_runs (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_id       integer     NOT NULL,
    source       text        NOT NULL CHECK (source IN ('reviews', 'news')),
    full_refresh boolean     NOT NULL,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    rows_written integer
);

CREATE INDEX ingest_runs_app_id_source_idx ON ingest_runs (app_id, source, started_at);
