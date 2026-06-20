"""Tests for GET /health.

These confirm the endpoint reports status/backend/connectivity only, never
leaks DATABASE_URL/credentials/paths, and behaves correctly for both
storage backends including failure cases.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.db.session import reset_engine_cache

    reset_engine_cache()
    yield
    reset_engine_cache()


def test_health_json_backend_default_is_healthy():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "storage_backend": "json", "storage_connected": True}


def test_health_explicit_json_backend_is_healthy(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "json")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["storage_backend"] == "json"
    assert response.json()["storage_connected"] is True


def test_health_postgres_backend_healthy(pg_database):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "storage_backend": "postgres", "storage_connected": True}


def test_health_postgres_backend_unreachable(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret-password@127.0.0.1:1/doesnotexist")
    from app.db.session import reset_engine_cache

    reset_engine_cache()

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "error", "storage_backend": "postgres", "storage_connected": False}

    raw_text = response.text
    assert "secret-password" not in raw_text
    assert "doesnotexist" not in raw_text
    assert "127.0.0.1" not in raw_text


def test_health_postgres_backend_without_database_url(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "storage_backend": "unconfigured",
        "storage_connected": False,
    }


def test_health_never_exposes_database_url_or_data_dir(pg_database, monkeypatch):
    monkeypatch.setenv("DATA_DIR", "/some/sensitive/looking/path")

    response = client.get("/health")
    raw_text = response.text

    assert "DATABASE_URL" not in raw_text
    assert "/some/sensitive/looking/path" not in raw_text
    assert pg_database not in raw_text
    # Only the three documented keys are present — no client counts, ids, etc.
    assert set(response.json().keys()) == {"status", "storage_backend", "storage_connected"}
