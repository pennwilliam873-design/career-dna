#!/usr/bin/env python3
"""Manage a local embedded PostgreSQL instance for development and testing.

No Docker or Homebrew required: this runs a real PostgreSQL 16 binary
bundled by the `pgserver` package (see requirements-dev.txt), persisted in
.pgdata/ at the repo root so data survives restarts — the local-dev
equivalent of a Docker named volume.

The server is started detached (it keeps running after this script exits)
so that separate commands — alembic, pytest, the migration script, or the
FastAPI app itself — can each connect to it as independent processes.

Usage:
    python scripts/local_postgres.py start   # start (or reuse), prints DATABASE_URL
    python scripts/local_postgres.py stop    # stop the running server
    python scripts/local_postgres.py status  # print DATABASE_URL if running, else exit 1
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PGDATA_DIR = REPO_ROOT / ".pgdata"


def cmd_start() -> None:
    import pgserver

    PGDATA_DIR.mkdir(parents=True, exist_ok=True)
    # cleanup_mode=None: the server is never auto-stopped when this script's
    # process exits — it stays up for other processes to connect to.
    server = pgserver.get_server(PGDATA_DIR, cleanup_mode=None)
    print(server.get_uri())


def cmd_stop() -> None:
    import pgserver

    if not (PGDATA_DIR / "PG_VERSION").exists():
        print("No local Postgres data directory found; nothing to stop.")
        return
    try:
        pgserver.pg_ctl(["-w", "stop"], pgdata=PGDATA_DIR)
        print("Stopped.")
    except Exception as exc:  # pg_ctl raises CalledProcessError if not running
        print(f"Nothing to stop (server was not running): {exc}")


def cmd_status() -> None:
    import pgserver

    if not (PGDATA_DIR / "PG_VERSION").exists():
        print("Not initialised.")
        sys.exit(1)
    info = pgserver.postgres_server.PostmasterInfo.read_from_pgdata(PGDATA_DIR)
    if info is not None and info.is_running():
        print(info.get_uri())
    else:
        print("Not running.")
        sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"start", "stop", "status"}:
        print(__doc__)
        sys.exit(1)
    {"start": cmd_start, "stop": cmd_stop, "status": cmd_status}[sys.argv[1]]()


if __name__ == "__main__":
    main()
