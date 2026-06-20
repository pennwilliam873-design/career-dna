"""Tests that app/data/storage_selector.py dispatches to the correct
backend implementation — not just that app/config.py reports the right
backend name (that's covered by tests/test_storage_config.py).

Dispatch is tested by substituting each backend module's functions with a
recorder, rather than via JSON file side effects: app/data/storage.py
computes its file path once at import time (an existing, intentional
Stage 1 design choice we're told to leave untouched), so a test can't
reliably redirect it via DATA_DIR after the fact.
"""
from __future__ import annotations

import pytest

from app.config import StorageConfigError
from app.data import storage_selector
from app.models.client import ClientProfile, ClientRecord


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_default_backend_dispatches_to_json_module(monkeypatch):
    calls = []
    monkeypatch.setattr(storage_selector._json_storage, "list_clients", lambda: calls.append("json") or [])
    monkeypatch.setattr(
        storage_selector._postgres_storage, "list_clients", lambda: calls.append("postgres") or []
    )

    storage_selector.list_clients()

    assert calls == ["json"]


def test_explicit_json_dispatches_to_json_module(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "json")
    calls = []
    monkeypatch.setattr(storage_selector._json_storage, "list_clients", lambda: calls.append("json") or [])
    monkeypatch.setattr(
        storage_selector._postgres_storage, "list_clients", lambda: calls.append("postgres") or []
    )

    storage_selector.list_clients()

    assert calls == ["json"]


def test_database_url_alone_still_dispatches_to_json_module(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    calls = []
    monkeypatch.setattr(storage_selector._json_storage, "list_clients", lambda: calls.append("json") or [])
    monkeypatch.setattr(
        storage_selector._postgres_storage, "list_clients", lambda: calls.append("postgres") or []
    )

    storage_selector.list_clients()

    assert calls == ["json"]


def test_explicit_postgres_dispatches_to_postgres_module(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    calls = []
    monkeypatch.setattr(storage_selector._json_storage, "list_clients", lambda: calls.append("json") or [])
    monkeypatch.setattr(
        storage_selector._postgres_storage, "list_clients", lambda: calls.append("postgres") or []
    )

    storage_selector.list_clients()

    assert calls == ["postgres"]


def test_explicit_postgres_without_database_url_fails_clearly(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")

    with pytest.raises(StorageConfigError):
        storage_selector.list_clients()


def test_explicit_postgres_end_to_end_against_real_database(pg_database):
    """One real (non-mocked) check that the dispatch path actually reaches
    a live PostgreSQL database when STORAGE_BACKEND=postgres."""
    from app.data import storage_postgres as pg

    created = storage_selector.create_client(ClientRecord(profile=ClientProfile(name="Via Selector")))
    direct = pg.get_client(created.id)

    assert direct is not None
    assert direct.profile.name == "Via Selector"
