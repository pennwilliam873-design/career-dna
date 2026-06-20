"""SQLAlchemy engine/session management for the PostgreSQL backend.

Only used when STORAGE_BACKEND=postgres (see app/config.py and
app/data/storage_postgres.py). Creating an engine requires DATABASE_URL to
be set; it does not require STORAGE_BACKEND=postgres, since that decision
belongs to app/config.py, not to this module.
"""
from __future__ import annotations

import functools
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_database_url


@functools.lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set; cannot create a database engine.")
    return create_engine(database_url, pool_pre_ping=True)


def reset_engine_cache() -> None:
    """Test helper: forces a fresh engine on the next get_engine() call.

    Needed when DATABASE_URL changes within the same process (e.g. between
    test sessions) — the cached engine would otherwise keep pointing at a
    stale connection target.
    """
    get_engine.cache_clear()


def get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db() -> Iterator[Session]:
    """FastAPI-style dependency generator. Not wired into any route yet."""
    session: Session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional unit of work: commits on success, rolls back and
    re-raises on any error, and always closes the session."""
    session: Session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_connectivity() -> bool:
    """Run a trivial query against DATABASE_URL. For local/manual verification only."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
