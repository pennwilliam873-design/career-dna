"""SQLAlchemy engine/session management for the (currently dormant)
PostgreSQL backend.

Nothing here is imported by app/main.py yet. It exists so the postgres
storage backend can be built and tested locally ahead of Stage 2, without
touching the live JSON-backed application. Creating an engine requires
DATABASE_URL to be set; it does not require STORAGE_BACKEND=postgres,
since that decision belongs to app/config.py, not to this module.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_database_url


def get_engine() -> Engine:
    database_url = get_database_url()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set; cannot create a database engine.")
    return create_engine(database_url, pool_pre_ping=True)


def get_sessionmaker() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db():
    """FastAPI-style dependency generator. Not wired into any route yet."""
    session: Session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def check_connectivity() -> bool:
    """Run a trivial query against DATABASE_URL. For local/manual verification only."""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
