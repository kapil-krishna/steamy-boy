import pytest

from steamy_boy import db

pytestmark = pytest.mark.integration


def test_all_migrations_are_recorded(conn):
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY 1")]

    assert versions == ["001_reviews_and_news.sql", "002_ingest_runs_and_soft_delete.sql"]


def test_migrate_is_idempotent(conn):
    assert db.migrate(conn) == []


def test_no_table_has_a_steam_id_column(conn):
    """R4: reviewers' Steam IDs are never stored. Guards every table, including future ones."""
    rows = conn.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND replace(column_name, '_', '') ILIKE '%steamid%'
        """
    ).fetchall()

    assert rows == []
