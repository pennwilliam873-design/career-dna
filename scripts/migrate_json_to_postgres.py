#!/usr/bin/env python3
"""One-time migration of a clients.json file into PostgreSQL.

Source and destination are both explicit and independent of the running
app's configuration:
  - Source is whatever file --source points at. Never DATA_DIR, never
    influenced by STORAGE_BACKEND.
  - Destination is the database at DATABASE_URL. The script refuses to run
    if DATABASE_URL is unset or doesn't point at PostgreSQL.

Usage:
    python scripts/migrate_json_to_postgres.py --source data/clients.json --dry-run
    python scripts/migrate_json_to_postgres.py --source data/clients.json

Idempotent: a client already present in the destination (matched by id) is
skipped, never duplicated or overwritten, so this is safe to re-run.

Each client and all of its child records (opportunities, target contacts,
session notes, action items) are inserted in a single transaction — if
anything about one client fails, that client is rolled back; other clients
already committed in earlier iterations are unaffected.

Dangling related-opportunity references (a contact/action item pointing at
an opportunity id that isn't among that same client's opportunities) are
always nulled, never used to reject an otherwise-valid client — rejecting
would mean silently dropping real client data over one stale cross
reference, which is worse than nulling it and reporting it. Both are
logged so they can be reviewed.

Never prints CV text, advisor notes, session note content, or any other
free-text client data — only counts, ids, and field paths.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_database_url  # noqa: E402
from app.data import storage_postgres as pg  # noqa: E402
from app.db.models import Client as ClientORM  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.models.client import ClientRecord  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_json_to_postgres")

KNOWN_TOP_LEVEL_FIELDS = set(ClientRecord.model_fields.keys())


class MigrationError(RuntimeError):
    pass


def require_postgres_database_url() -> str:
    database_url = get_database_url()
    if not database_url:
        raise MigrationError(
            "DATABASE_URL must be set. This script never infers a destination "
            "from STORAGE_BACKEND — it always migrates into DATABASE_URL."
        )
    drivername = make_url(database_url).drivername
    if not drivername.startswith("postgresql"):
        raise MigrationError(
            f"Refusing to run: DATABASE_URL scheme is {drivername!r}, not PostgreSQL."
        )
    return database_url


def load_source(source_path: Path) -> List[dict]:
    if not source_path.exists():
        raise MigrationError(f"Source file not found: {source_path}")
    data = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise MigrationError("Source JSON must be a list of client records.")
    return data


def _existing_client_ids() -> Set[str]:
    with session_scope() as session:
        return set(session.execute(select(ClientORM.id)).scalars().all())


def run(source_path: Path, dry_run: bool) -> Dict[str, Any]:
    database_url = require_postgres_database_url()
    logger.info(
        "Destination: %s", make_url(database_url).render_as_string(hide_password=True)
    )
    logger.info("Source: %s (read-only; never modified)", source_path)

    raw_records = load_source(source_path)
    logger.info("Found %d client record(s) in source.", len(raw_records))

    already_present = _existing_client_ids()

    validated: List[ClientRecord] = []
    validation_errors: List[dict] = []
    unrecognized_fields: List[dict] = []

    for raw in raw_records:
        client_id = raw.get("id", "<missing id>")

        extra_keys = set(raw.keys()) - KNOWN_TOP_LEVEL_FIELDS
        if extra_keys:
            unrecognized_fields.append({"id": client_id, "fields": sorted(extra_keys)})
            logger.warning(
                "Client %s has unrecognized top-level field(s), not migrated: %s",
                client_id,
                sorted(extra_keys),
            )

        try:
            validated.append(ClientRecord(**raw))
        except ValidationError as exc:
            errors = [
                {"loc": ".".join(str(p) for p in e["loc"]), "type": e["type"]}
                for e in exc.errors()
            ]
            validation_errors.append({"id": client_id, "errors": errors})
            logger.warning("Client %s failed validation: %s", client_id, errors)

    to_migrate = [r for r in validated if r.id not in already_present]
    skipped_existing = [r.id for r in validated if r.id in already_present]

    migrated_ids: List[str] = []
    dangling_refs: List[dict] = []
    child_counts = {
        "opportunities": 0,
        "target_contacts": 0,
        "session_notes": 0,
        "action_items": 0,
    }

    for record in to_migrate:
        opportunity_ids = {o.id for o in record.opportunities}

        for tc in record.target_contacts:
            if tc.related_opportunity_id and tc.related_opportunity_id not in opportunity_ids:
                dangling_refs.append(
                    {
                        "client_id": record.id,
                        "entity": "target_contact",
                        "id": tc.id,
                        "resolution": "nulled",
                    }
                )
        for ai in record.action_items:
            if ai.related_opportunity and ai.related_opportunity not in opportunity_ids:
                dangling_refs.append(
                    {
                        "client_id": record.id,
                        "entity": "action_item",
                        "id": ai.id,
                        "resolution": "nulled",
                    }
                )

        child_counts["opportunities"] += len(record.opportunities)
        child_counts["target_contacts"] += len(record.target_contacts)
        child_counts["session_notes"] += len(record.session_notes)
        child_counts["action_items"] += len(record.action_items)

        if not dry_run:
            pg.create_client(record)  # single transaction per client (see module docstring)
        migrated_ids.append(record.id)

    return {
        "dry_run": dry_run,
        "source_client_count": len(raw_records),
        "validated_count": len(validated),
        "validation_errors": validation_errors,
        "unrecognized_fields": unrecognized_fields,
        "already_present_skipped": skipped_existing,
        "migrated_count": len(migrated_ids),
        "migrated_ids": migrated_ids,
        "child_counts": child_counts,
        "dangling_references": dangling_refs,
    }


def _print_summary(summary: Dict[str, Any]) -> None:
    mode = "DRY RUN (no writes performed)" if summary["dry_run"] else "MIGRATION COMPLETE"
    print(f"\n=== {mode} ===")
    print(f"Source client records found:   {summary['source_client_count']}")
    print(f"Passed Pydantic validation:    {summary['validated_count']}")
    print(f"Failed validation (skipped):   {len(summary['validation_errors'])}")
    for err in summary["validation_errors"]:
        print(f"  - client {err['id']}: {err['errors']}")
    print(f"Unrecognized top-level fields: {len(summary['unrecognized_fields'])}")
    for entry in summary["unrecognized_fields"]:
        print(f"  - client {entry['id']}: {entry['fields']}")
    print(f"Already in database (skipped): {len(summary['already_present_skipped'])}")
    for cid in summary["already_present_skipped"]:
        print(f"  - {cid}")
    action = "Would migrate" if summary["dry_run"] else "Migrated"
    print(f"{action}: {summary['migrated_count']} client(s)")
    for cid in summary["migrated_ids"]:
        print(f"  - {cid}")
    print("Child records:", summary["child_counts"])
    print(f"Dangling related-opportunity references: {len(summary['dangling_references'])}")
    for ref in summary["dangling_references"]:
        print(f"  - client {ref['client_id']}: {ref['entity']} {ref['id']} -> {ref['resolution']}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Path to the source clients.json file (required; never inferred from DATA_DIR).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report only; do not write to the database.",
    )
    args = parser.parse_args()

    try:
        summary = run(args.source, args.dry_run)
    except MigrationError as exc:
        logger.error(str(exc))
        sys.exit(1)

    _print_summary(summary)
    if summary["validation_errors"]:
        sys.exit(2)  # ran, but some records were not migrated


if __name__ == "__main__":
    main()
