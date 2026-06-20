"""Unit tests for the two check_connectivity() implementations that back
GET /health — locking in two specific safety properties:

  - the JSON implementation is strictly read-only (never creates, modifies,
    renames, or deletes anything on disk).
  - the PostgreSQL implementation has a bounded connection timeout, so an
    unreachable (not just refused) host can't hang a health check.

app/data/storage.py resolves its data path once at import time from
DATA_DIR (an existing, intentional Stage 1 design choice — see Stage 2
notes on the same topic). monkeypatch.setattr on the already-imported
module's path variables is used here instead of reloading the module or
re-setting the env var, since monkeypatch guarantees clean, ordering-safe
restoration after each test either way.
"""
from __future__ import annotations

import os
import time

import pytest

from app.data import storage


def test_json_connectivity_check_creates_nothing_when_data_dir_missing_but_parent_exists(tmp_path, monkeypatch):
    # Realistic "fresh deploy, no write has happened yet" case: tmp_path
    # (the parent) exists, but the data directory itself doesn't.
    missing_dir = tmp_path / "data"
    monkeypatch.setattr(storage, "_DATA_DIR", missing_dir)
    monkeypatch.setattr(storage, "_CLIENTS_FILE", missing_dir / "clients.json")

    before = list(tmp_path.rglob("*"))
    result = storage.check_connectivity()
    after = list(tmp_path.rglob("*"))

    assert after == before, "check_connectivity() created filesystem entries"
    assert not missing_dir.exists(), "check_connectivity() created the data directory"
    assert result is True


def test_json_connectivity_check_creates_nothing_when_path_is_deeply_absent(tmp_path, monkeypatch):
    # Even the immediate parent is missing — unhealthy, but still must not
    # create anything as a side effect of checking.
    missing_dir = tmp_path / "does" / "not" / "exist"
    monkeypatch.setattr(storage, "_DATA_DIR", missing_dir)
    monkeypatch.setattr(storage, "_CLIENTS_FILE", missing_dir / "clients.json")

    before = list(tmp_path.rglob("*"))
    result = storage.check_connectivity()
    after = list(tmp_path.rglob("*"))

    assert after == before, "check_connectivity() created filesystem entries"
    assert not missing_dir.exists()
    assert result is False


def test_json_connectivity_check_does_not_modify_existing_file(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    clients_file = data_dir / "clients.json"
    original_content = '[{"id": "untouched"}]'
    clients_file.write_text(original_content, encoding="utf-8")
    original_mtime = clients_file.stat().st_mtime_ns

    monkeypatch.setattr(storage, "_DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "_CLIENTS_FILE", clients_file)

    result = storage.check_connectivity()

    assert result is True
    assert clients_file.read_text(encoding="utf-8") == original_content
    assert clients_file.stat().st_mtime_ns == original_mtime


def test_json_connectivity_check_reports_unhealthy_for_unwritable_parent(tmp_path, monkeypatch):
    unwritable_parent = tmp_path / "locked"
    unwritable_parent.mkdir()
    os.chmod(unwritable_parent, 0o500)  # read+execute only, no write
    missing_data_dir = unwritable_parent / "data"

    monkeypatch.setattr(storage, "_DATA_DIR", missing_data_dir)
    monkeypatch.setattr(storage, "_CLIENTS_FILE", missing_data_dir / "clients.json")

    try:
        result = storage.check_connectivity()
        assert result is False
        assert not missing_data_dir.exists()
    finally:
        os.chmod(unwritable_parent, 0o700)  # restore so pytest can clean up tmp_path


def test_postgres_connectivity_check_has_bounded_timeout_against_unreachable_host(monkeypatch):
    # 10.255.255.1 is a non-routable address commonly used to simulate a
    # host that silently drops packets, rather than actively refusing the
    # connection (which fails fast and wouldn't prove a timeout exists).
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@10.255.255.1:5432/doesnotexist")
    from app.db.session import check_connectivity, reset_engine_cache

    reset_engine_cache()

    start = time.time()
    with pytest.raises(Exception):
        check_connectivity()
    elapsed = time.time() - start

    reset_engine_cache()
    assert elapsed < 15, f"connection attempt took {elapsed:.1f}s — timeout is not bounded"
