"""Smoke tests for the dormant PostgreSQL foundation.

No live database is required: these confirm the SQLAlchemy models compile
to valid PostgreSQL DDL, and that the connectivity helper fails clearly
when DATABASE_URL is unset, without ever attempting a real connection.
"""
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.base import Base
from app.db.session import check_connectivity, get_engine

EXPECTED_TABLES = {
    "clients",
    "opportunities",
    "target_contacts",
    "session_notes",
    "action_items",
}


def test_expected_tables_are_registered():
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def test_models_compile_to_valid_postgres_ddl():
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        # Raises if the column/type definitions don't compile for postgres.
        str(CreateTable(table).compile(dialect=dialect))


def test_get_engine_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        get_engine()


def test_check_connectivity_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        check_connectivity()
