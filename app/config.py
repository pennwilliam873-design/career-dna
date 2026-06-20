"""Storage backend selection.

STORAGE_BACKEND controls which persistence layer is active and defaults to
"json". It must be explicitly set to "postgres" to activate the database
path. The mere presence of DATABASE_URL never switches storage on its own:
Railway provisions DATABASE_URL as soon as a Postgres plugin is attached,
before any data has been migrated, so activation has to be an explicit
opt-in rather than inferred from which env vars happen to be set.
"""
from __future__ import annotations

import os

VALID_STORAGE_BACKENDS = {"json", "postgres"}


class StorageConfigError(RuntimeError):
    """STORAGE_BACKEND is invalid, or postgres was selected without DATABASE_URL."""


def get_storage_backend() -> str:
    backend = os.getenv("STORAGE_BACKEND", "json").strip()

    if backend not in VALID_STORAGE_BACKENDS:
        raise StorageConfigError(
            f"Invalid STORAGE_BACKEND={backend!r}. "
            f"Must be one of {sorted(VALID_STORAGE_BACKENDS)}."
        )

    if backend == "postgres" and not os.getenv("DATABASE_URL"):
        raise StorageConfigError(
            "STORAGE_BACKEND=postgres requires DATABASE_URL to be set."
        )

    return backend


def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")
