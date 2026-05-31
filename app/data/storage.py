"""
JSON file-based client storage.

Structured behind a thin interface so the read/write backend can later
be swapped for Supabase or Postgres without touching the API layer.

Data directory is controlled by the DATA_DIR env var (default: ./data).
On Railway the container filesystem is ephemeral across deploys; set up
a persistent volume and point DATA_DIR at it, or migrate to Supabase,
when you need durability.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from app.models.client import ClientRecord

_DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
_CLIENTS_FILE = _DATA_DIR / "clients.json"


def _ensure_file() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _CLIENTS_FILE.exists():
        _CLIENTS_FILE.write_text("[]", encoding="utf-8")


def _read_all() -> List[dict]:
    _ensure_file()
    return json.loads(_CLIENTS_FILE.read_text(encoding="utf-8"))


def _write_all(records: List[dict]) -> None:
    _ensure_file()
    _CLIENTS_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def list_clients() -> List[ClientRecord]:
    return [ClientRecord(**r) for r in _read_all()]


def get_client(client_id: str) -> Optional[ClientRecord]:
    for r in _read_all():
        if r.get("id") == client_id:
            return ClientRecord(**r)
    return None


def create_client(record: ClientRecord) -> ClientRecord:
    records = _read_all()
    records.append(record.model_dump(mode="json"))
    _write_all(records)
    return record


def update_client(record: ClientRecord) -> ClientRecord:
    records = _read_all()
    for i, r in enumerate(records):
        if r.get("id") == record.id:
            record.updated_at = datetime.now(timezone.utc).isoformat()
            records[i] = record.model_dump(mode="json")
            _write_all(records)
            return record
    raise KeyError(f"Client {record.id} not found")


def delete_client(client_id: str) -> bool:
    records = _read_all()
    filtered = [r for r in records if r.get("id") != client_id]
    if len(filtered) == len(records):
        return False
    _write_all(filtered)
    return True
