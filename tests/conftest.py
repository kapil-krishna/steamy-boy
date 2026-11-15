"""Shared fixtures. Integration tests get a fresh, migrated test database per session."""

from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from steamy_boy import db

TEST_DATABASE = "steamy_boy_test"


@pytest.fixture(scope="session")
def migrated_db_url() -> Iterator[str]:
    """Recreate the test database from scratch and apply all migrations to it.

    Skips (rather than fails) when Postgres isn't running, so unit tests work anywhere.
    """
    admin_url = make_conninfo(db.database_url(), dbname="postgres")
    try:
        admin = psycopg.connect(admin_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as error:
        pytest.skip(f"Postgres not reachable (run `docker compose up -d`): {error}")

    test_db = sql.Identifier(TEST_DATABASE)
    with admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(test_db))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(test_db))

    url = make_conninfo(db.database_url(), dbname=TEST_DATABASE)
    with db.connect(url) as conn:
        db.migrate(conn)
    yield url


@pytest.fixture
def conn(migrated_db_url: str) -> Iterator[psycopg.Connection]:
    with db.connect(migrated_db_url) as connection:
        yield connection
