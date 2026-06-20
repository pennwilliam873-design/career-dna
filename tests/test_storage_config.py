"""Behavioural tests for app/config.py's storage backend selection.

These exist to lock in the explicit-opt-in rule: STORAGE_BACKEND is the only
thing that activates PostgreSQL. DATABASE_URL configures the connection but
must never switch storage on by its mere presence, since Railway provisions
DATABASE_URL as soon as a Postgres plugin is attached — before any data has
been migrated.
"""
import pytest

from app.config import StorageConfigError, get_storage_backend


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_no_storage_backend_set_defaults_to_json():
    assert get_storage_backend() == "json"


def test_storage_backend_json_is_explicit_json(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "json")
    assert get_storage_backend() == "json"


def test_storage_backend_postgres_without_database_url_raises(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    with pytest.raises(StorageConfigError):
        get_storage_backend()


def test_database_url_alone_does_not_activate_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    assert get_storage_backend() == "json"


def test_storage_backend_postgres_with_database_url_succeeds(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    assert get_storage_backend() == "postgres"


def test_invalid_storage_backend_value_raises(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "mysql")
    with pytest.raises(StorageConfigError):
        get_storage_backend()
