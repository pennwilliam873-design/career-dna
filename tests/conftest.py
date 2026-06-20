"""Shared pytest fixtures.

postgres_test_url spins up a real, disposable PostgreSQL 16 instance for
the whole test session via pgserver (the same no-Docker approach as
scripts/local_postgres.py), migrated to head once. pg_database points
DATABASE_URL/STORAGE_BACKEND at it for a single test and truncates all
tables afterwards, so tests stay isolated without re-running migrations
per test.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_db_engine_cache():
    """Prevents a cached engine from one test leaking into the next, which
    would otherwise make get_engine()/check_connectivity() tests that
    expect a RuntimeError flaky depending on test order."""
    from app.db.session import reset_engine_cache

    reset_engine_cache()
    yield
    reset_engine_cache()


@pytest.fixture(scope="session")
def postgres_test_url() -> Iterator[str]:
    import pgserver

    pgdata = Path(tempfile.mkdtemp(prefix="nianova_pytest_pg_"))
    server = pgserver.get_server(pgdata, cleanup_mode="delete")
    url = server.get_uri()

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    from app.db.session import reset_engine_cache

    reset_engine_cache()

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(cfg, "head")

    yield url

    reset_engine_cache()
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous
    server.cleanup()


@pytest.fixture()
def pg_database(postgres_test_url, monkeypatch) -> Iterator[str]:
    """Per-test real Postgres: DATABASE_URL + STORAGE_BACKEND=postgres for
    the duration of the test, all tables truncated afterwards."""
    monkeypatch.setenv("DATABASE_URL", postgres_test_url)
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    from app.db.session import reset_engine_cache

    reset_engine_cache()

    yield postgres_test_url

    from app.db.session import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE clients, opportunities, target_contacts, "
                "session_notes, action_items CASCADE"
            )
        )
    engine.dispose()
