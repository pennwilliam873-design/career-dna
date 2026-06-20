"""Tests for scripts/smoke_test_staging.py against a real running server
(a local uvicorn instance bound to an ephemeral port, backed by the real
PostgreSQL test database) — a true HTTP boundary, not a mocked transport,
so this exercises exactly the path a staging run would.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def running_server(pg_database, monkeypatch):
    """Runs the real app in a background thread on an ephemeral port,
    against the Postgres test database — the realistic staging target."""
    monkeypatch.setenv("TRIAL_API_KEY", "")  # open access, matches local/staging dev mode

    port = _free_port()
    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            httpx.get(f"{base_url}/health", timeout=1.0)
            break
        except httpx.TransportError:
            time.sleep(0.1)
    else:
        raise RuntimeError("server did not start in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=10)


def test_smoke_test_passes_against_real_server_with_cleanup(running_server, capsys):
    from scripts import smoke_test_staging as smoke_mod

    smoke_mod.run(running_server, trial_key=None, cleanup=True)

    output = capsys.readouterr().out
    assert "SMOKE TEST PASSED" in output
    # Never prints the synthetic note/CV body verbatim, only structural info.
    assert "synthetic note body" not in output
    assert "synthetic cv text" not in output


def test_smoke_test_no_cleanup_leaves_client_retrievable(running_server):
    from scripts import smoke_test_staging as smoke_mod
    from app.data import storage_postgres as pg

    smoke_mod.run(running_server, trial_key=None, cleanup=False)

    clients = pg.list_clients()
    synthetic = [c for c in clients if smoke_mod.RUN_ID in c.profile.name]
    assert len(synthetic) == 1

    # Manual cleanup since the test disabled it.
    pg.delete_client(synthetic[0].id)


def test_smoke_test_script_exits_nonzero_on_unreachable_server():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "smoke_test_staging.py"),
         "--base-url", "http://127.0.0.1:1"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "SMOKE TEST FAILED" in result.stderr or "SMOKE TEST FAILED" in result.stdout


def test_smoke_test_script_requires_base_url():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "smoke_test_staging.py")],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(REPO_ROOT),
        env={"PATH": "/usr/bin:/bin"},  # ensure SMOKE_TEST_BASE_URL isn't inherited
    )
    assert result.returncode != 0
    assert "base-url" in result.stderr.lower() or "base_url" in result.stderr.lower()
