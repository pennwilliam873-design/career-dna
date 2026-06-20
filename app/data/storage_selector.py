"""Dispatches the five storage operations to the JSON or PostgreSQL
implementation, based on STORAGE_BACKEND (app/config.py).

This is the only module app/main.py imports from for persistence — the
backend is resolved fresh on every call (not cached at import time), so
switching STORAGE_BACKEND takes effect on the next request without
restarting anything. DATABASE_URL alone never selects postgres; only an
explicit STORAGE_BACKEND=postgres does.
"""
from __future__ import annotations

from typing import List, Optional

from app.config import get_storage_backend
from app.data import storage as _json_storage
from app.data import storage_postgres as _postgres_storage
from app.models.client import ClientRecord


def _backend():
    return _postgres_storage if get_storage_backend() == "postgres" else _json_storage


def list_clients() -> List[ClientRecord]:
    return _backend().list_clients()


def get_client(client_id: str) -> Optional[ClientRecord]:
    return _backend().get_client(client_id)


def create_client(record: ClientRecord) -> ClientRecord:
    return _backend().create_client(record)


def update_client(record: ClientRecord) -> ClientRecord:
    return _backend().update_client(record)


def delete_client(client_id: str) -> bool:
    return _backend().delete_client(client_id)
