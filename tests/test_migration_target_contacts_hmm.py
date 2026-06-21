"""Verifies the Hidden Market Map migration (revision 7d2f9a4c1b6e) is safe
against rows that existed *before* it ran — the exact shape of production
target_contacts rows today.

Downgrades the already-migrated test database to the prior revision,
inserts a row using the pre-Hidden-Market-Map schema/status vocabulary
with raw SQL (bypassing the ORM, which only knows the new shape), then
upgrades back to head and asserts the row survived with its status
remapped and every new column populated with a safe default.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]

_PRE_HMM_REVISION = "caae59d21165"


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


@pytest.mark.parametrize(
    "old_status,expected_new_status",
    [
        ("Not contacted", "To assess"),
        ("Warm path identified", "Ready for outreach"),
        ("Responded", "Active conversation"),
        ("Contacted", "Contacted"),
        ("Parked", "Parked"),
        ("Some Custom Status An Advisor Typed", "Some Custom Status An Advisor Typed"),
    ],
)
def test_pre_migration_status_values_backfilled_safely(
    pg_database, old_status, expected_new_status
):
    cfg = _alembic_config()
    command.downgrade(cfg, _PRE_HMM_REVISION)

    from app.db.session import get_engine, reset_engine_cache

    reset_engine_cache()
    engine = get_engine()
    with engine.begin() as conn:
        client_id = conn.execute(
            text(
                "INSERT INTO clients (id, created_at, updated_at) "
                "VALUES (gen_random_uuid(), now(), now()) RETURNING id"
            )
        ).scalar()
        contact_id = conn.execute(
            text(
                "INSERT INTO target_contacts (id, client_id, name, status, sort_order, "
                "created_at, updated_at) "
                "VALUES (gen_random_uuid(), :client_id, 'Pre-migration Contact', "
                ":status, 0, now(), now()) RETURNING id"
            ),
            {"client_id": client_id, "status": old_status},
        ).scalar()
    engine.dispose()
    reset_engine_cache()

    command.upgrade(cfg, "head")
    reset_engine_cache()

    from app.data import storage_postgres as pg

    fetched = pg.get_client(str(client_id))
    contact = next(c for c in fetched.target_contacts if c.id == str(contact_id))

    assert contact.status == expected_new_status
    assert contact.network_source == "Unknown"
    assert contact.relationship_owner == "Unknown"
    assert contact.advisor_only is True
    assert contact.client_shareable is False
    assert contact.warm_path_status == "Unknown"
