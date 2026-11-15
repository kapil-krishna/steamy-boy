"""Database connections and the migration runner (D5).

Migrations are the numbered `.sql` files in `steamy_boy/migrations`, applied in filename
order. Each runs in its own transaction together with its row in `schema_migrations`,
so a failed migration leaves nothing half-applied. Never edit an applied migration:
add a new file instead.
"""

import os
from importlib.resources import files

import psycopg

DEFAULT_DATABASE_URL = "postgresql://steamy_boy:steamy_boy@localhost:5432/steamy_boy"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def connect(url: str | None = None) -> psycopg.Connection:
    """Open an autocommit connection. Group statements with `with conn.transaction():`."""
    return psycopg.connect(url or database_url(), autocommit=True)


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply pending migrations in order. Returns the names of those applied."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    text        PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

    migration_files = sorted(
        (f for f in files("steamy_boy.migrations").iterdir() if f.name.endswith(".sql")),
        key=lambda f: f.name,
    )
    newly_applied = []
    for migration in migration_files:
        if migration.name in applied:
            continue
        with conn.transaction():
            conn.execute(migration.read_text())  # type: ignore[arg-type]  # trusted repo file
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (migration.name,))
        newly_applied.append(migration.name)
    return newly_applied
