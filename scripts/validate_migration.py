#!/usr/bin/env python3
"""Deep field-by-field comparison between a source clients.json and what
PostgreSQL actually returns for the same client ids — via the exact same
storage_postgres adapter and mappers the running app uses.

This never writes anything; run it after migrate_json_to_postgres.py to
confirm the migration was lossless. Comparison covers every field
recursively (nested AI outputs, raw fallbacks, ids, null vs empty, legacy
fields, source arrays, operational list ordering). The only normalisation
applied is for representational differences that are semantically
identical: timestamp strings are compared as parsed datetimes (not
byte-for-byte), and dict key order is never significant (plain dict
equality already ignores it). List ordering and missing-vs-present field
differences are never normalised away.

Never prints field values — only field paths and redacted type/length
descriptors, to avoid ever surfacing CV text, advisor notes, or other
free-text client content.

Usage:
    python scripts/validate_migration.py --source data/clients.json
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate_json_to_postgres import (  # noqa: E402
    MigrationError,
    load_source,
    require_postgres_database_url,
)

from app.data import storage_postgres as pg  # noqa: E402
from app.models.client import ClientRecord  # noqa: E402

_MISSING = object()

# The only fields ever compared with anything other than strict equality:
# these are ISO timestamp strings that may legitimately render with
# different (but equivalent) formatting after a round trip through a
# PostgreSQL timestamptz column.
TIMESTAMP_LEAF_FIELDS = {
    "created_at",
    "updated_at",
    "positioning_generated_at",
    "cv_intelligence_generated_at",
    "market_radar_generated_at",
    "advisor_brief_generated_at",
    "advisor_brief_edited_at",
}


def _redact_repr(value: Any) -> str:
    """Describes a value's shape without ever revealing its content."""
    if value is _MISSING:
        return "<missing>"
    if value is None:
        return "None"
    if isinstance(value, bool):
        return f"bool({value})"
    if isinstance(value, (int, float)):
        return f"{type(value).__name__}({value})"
    if isinstance(value, str):
        return f"str(len={len(value)})"
    if isinstance(value, list):
        return f"list(len={len(value)})"
    if isinstance(value, dict):
        return f"dict(keys={sorted(value.keys())})"
    return type(value).__name__


def _leaf_name(path: str) -> str:
    return path.rsplit(".", 1)[-1].split("[")[0]


def _values_equal(leaf: str, expected: Any, actual: Any) -> bool:
    if leaf in TIMESTAMP_LEAF_FIELDS and expected is not None and actual is not None:
        return datetime.fromisoformat(expected) == datetime.fromisoformat(actual)
    return expected == actual


def _compare(path: str, expected: Any, actual: Any, mismatches: List[dict]) -> None:
    if expected is _MISSING or actual is _MISSING:
        mismatches.append(
            {
                "path": path,
                "issue": "missing_field",
                "expected": _redact_repr(expected),
                "actual": _redact_repr(actual),
            }
        )
        return

    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            _compare(
                f"{path}.{key}" if path else key,
                expected.get(key, _MISSING),
                actual.get(key, _MISSING),
                mismatches,
            )
        return

    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            mismatches.append(
                {
                    "path": path,
                    "issue": "list_length_mismatch",
                    "expected": _redact_repr(expected),
                    "actual": _redact_repr(actual),
                }
            )
            return
        for i, (e_item, a_item) in enumerate(zip(expected, actual)):
            _compare(f"{path}[{i}]", e_item, a_item, mismatches)
        return

    if not _values_equal(_leaf_name(path), expected, actual):
        mismatches.append(
            {
                "path": path,
                "issue": "value_mismatch",
                "expected": _redact_repr(expected),
                "actual": _redact_repr(actual),
            }
        )


def validate(source_path: Path) -> Dict[str, Any]:
    require_postgres_database_url()
    raw_records = load_source(source_path)

    child_counts = {
        "opportunities": 0,
        "target_contacts": 0,
        "session_notes": 0,
        "action_items": 0,
    }
    clients_checked = 0
    clients_passed = 0
    clients_failed = 0
    clients_missing_in_db: List[str] = []
    failures: List[dict] = []

    for raw in raw_records:
        client_id = raw.get("id")
        expected_record = ClientRecord(**raw)
        for key in child_counts:
            child_counts[key] += len(getattr(expected_record, key))

        clients_checked += 1
        actual_record = pg.get_client(client_id)

        if actual_record is None:
            clients_missing_in_db.append(client_id)
            clients_failed += 1
            continue

        mismatches: List[dict] = []
        _compare(
            "",
            expected_record.model_dump(mode="json"),
            actual_record.model_dump(mode="json"),
            mismatches,
        )

        if mismatches:
            clients_failed += 1
            failures.append({"client_id": client_id, "mismatches": mismatches})
        else:
            clients_passed += 1

    return {
        "clients_checked": clients_checked,
        "clients_passed": clients_passed,
        "clients_failed": clients_failed,
        "clients_missing_in_db": clients_missing_in_db,
        "child_counts_in_source": child_counts,
        "failures": failures,
    }


def _print_report(report: Dict[str, Any]) -> None:
    print("\n=== DEEP VALIDATION REPORT ===")
    print(f"Clients checked: {report['clients_checked']}")
    print(f"Clients passed:  {report['clients_passed']}")
    print(f"Clients failed:  {report['clients_failed']}")
    print("Child record counts (source):", report["child_counts_in_source"])
    if report["clients_missing_in_db"]:
        print("Missing from database entirely:")
        for cid in report["clients_missing_in_db"]:
            print(f"  - {cid}")
    for failure in report["failures"]:
        print(f"\nClient {failure['client_id']} — {len(failure['mismatches'])} mismatch(es):")
        for m in failure["mismatches"]:
            print(f"  - [{m['issue']}] {m['path']}: expected={m['expected']} actual={m['actual']}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Path to the source clients.json file used for migration.",
    )
    args = parser.parse_args()

    try:
        report = validate(args.source)
    except MigrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    _print_report(report)
    sys.exit(0 if report["clients_failed"] == 0 else 3)


if __name__ == "__main__":
    main()
