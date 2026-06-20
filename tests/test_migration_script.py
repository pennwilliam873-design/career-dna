"""Tests for scripts/migrate_json_to_postgres.py and
scripts/validate_migration.py against a real PostgreSQL database.
"""
from __future__ import annotations

import json

import pytest

from scripts import migrate_json_to_postgres as migrate_mod
from scripts import validate_migration as validate_mod


def _write_json(tmp_path, records):
    path = tmp_path / "clients.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def _client(client_id, name, **overrides):
    record = {
        "id": client_id,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "profile": {"name": name},
        "opportunities": [],
        "target_contacts": [],
        "session_notes": [],
        "action_items": [],
    }
    record.update(overrides)
    return record


def test_dry_run_writes_nothing(pg_database, tmp_path):
    source = _write_json(tmp_path, [_client("11111111-1111-1111-1111-111111111111", "Dry Run Client")])

    summary = migrate_mod.run(source, dry_run=True)

    assert summary["migrated_count"] == 1
    from app.data import storage_postgres as pg

    assert pg.get_client("11111111-1111-1111-1111-111111111111") is None


def test_run_twice_no_duplicates(pg_database, tmp_path):
    source = _write_json(tmp_path, [_client("22222222-2222-2222-2222-222222222222", "Idempotent Client")])

    first = migrate_mod.run(source, dry_run=False)
    second = migrate_mod.run(source, dry_run=False)

    assert first["migrated_count"] == 1
    assert second["migrated_count"] == 0
    assert second["already_present_skipped"] == ["22222222-2222-2222-2222-222222222222"]

    from app.db.session import session_scope
    from app.db.models import Client as ClientORM

    with session_scope() as session:
        assert session.query(ClientORM).count() == 1


def test_dangling_reference_detected_and_nulled(pg_database, tmp_path):
    client_id = "33333333-3333-3333-3333-333333333333"
    source = _write_json(
        tmp_path,
        [
            _client(
                client_id,
                "Dangling Client",
                opportunities=[
                    {
                        "id": "aaaaaaaa-0000-0000-0000-000000000001",
                        "title": "Real Opp",
                        "created_at": "2026-01-01T00:00:01+00:00",
                        "updated_at": "2026-01-01T00:00:01+00:00",
                    }
                ],
                target_contacts=[
                    {
                        "id": "bbbbbbbb-0000-0000-0000-000000000001",
                        "name": "Orphan Contact",
                        "related_opportunity_id": "no-such-id",
                        "created_at": "2026-01-01T00:00:02+00:00",
                        "updated_at": "2026-01-01T00:00:02+00:00",
                    }
                ],
            )
        ],
    )

    summary = migrate_mod.run(source, dry_run=False)

    assert len(summary["dangling_references"]) == 1
    assert summary["dangling_references"][0]["resolution"] == "nulled"

    from app.data import storage_postgres as pg

    migrated = pg.get_client(client_id)
    assert migrated.target_contacts[0].related_opportunity_id == ""


def test_validates_and_skips_malformed_records_but_migrates_valid_ones(pg_database, tmp_path):
    good_id = "44444444-4444-4444-4444-444444444444"
    source = _write_json(
        tmp_path,
        [
            _client(good_id, "Valid Client"),
            {
                "id": "55555555-5555-5555-5555-555555555555",
                "profile": "this-should-be-an-object-not-a-string",
            },
        ],
    )

    summary = migrate_mod.run(source, dry_run=False)

    assert summary["validated_count"] == 1
    assert len(summary["validation_errors"]) == 1
    assert summary["validation_errors"][0]["id"] == "55555555-5555-5555-5555-555555555555"
    assert summary["migrated_ids"] == [good_id]


def test_unrecognized_top_level_field_is_flagged_not_silently_dropped(pg_database, tmp_path):
    client_id = "66666666-6666-6666-6666-666666666666"
    source = _write_json(
        tmp_path, [_client(client_id, "Has Extra Field", mystery_field="unexpected")]
    )

    summary = migrate_mod.run(source, dry_run=False)

    assert len(summary["unrecognized_fields"]) == 1
    assert summary["unrecognized_fields"][0]["fields"] == ["mystery_field"]
    # Still migrates the rest of the record — an unrecognized field is
    # informational drift, not a validation failure.
    assert summary["migrated_count"] == 1


def test_never_modifies_source_file(pg_database, tmp_path):
    source = _write_json(tmp_path, [_client("77777777-7777-7777-7777-777777777777", "Untouched")])
    original_bytes = source.read_bytes()

    migrate_mod.run(source, dry_run=False)

    assert source.read_bytes() == original_bytes


def test_refuses_non_postgres_database_url(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///somefile.db")
    source = _write_json(tmp_path, [_client("88888888-8888-8888-8888-888888888888", "Wrong DB")])

    with pytest.raises(migrate_mod.MigrationError):
        migrate_mod.run(source, dry_run=True)


def test_requires_database_url(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    source = _write_json(tmp_path, [_client("99999999-9999-9999-9999-999999999999", "No DB URL")])

    with pytest.raises(migrate_mod.MigrationError):
        migrate_mod.run(source, dry_run=True)


def test_validate_migration_reports_zero_mismatches_after_clean_migration(pg_database, tmp_path):
    source = _write_json(tmp_path, [_client("aaaaaaaa-1111-1111-1111-111111111111", "Clean")])
    migrate_mod.run(source, dry_run=False)

    report = validate_mod.validate(source)

    assert report["clients_checked"] == 1
    assert report["clients_passed"] == 1
    assert report["clients_failed"] == 0


def test_validate_migration_reports_mismatch_when_data_diverges(pg_database, tmp_path):
    client_id = "bbbbbbbb-2222-2222-2222-222222222222"
    source = _write_json(tmp_path, [_client(client_id, "Will Diverge")])
    migrate_mod.run(source, dry_run=False)

    # Mutate the database directly so it no longer matches the source.
    from app.db.session import session_scope
    from app.db.models import Client as ClientORM

    with session_scope() as session:
        row = session.get(ClientORM, client_id)
        row.profile_name = "Diverged In Database"

    report = validate_mod.validate(source)

    assert report["clients_failed"] == 1
    paths = {m["path"] for m in report["failures"][0]["mismatches"]}
    assert "profile.name" in paths
