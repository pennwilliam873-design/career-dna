#!/usr/bin/env python3
"""Synthetic smoke test against a deployed ViaNova backend.

Exercises the public client-workspace HTTP API end-to-end using obviously
synthetic data, to validate a deployment (e.g. Railway staging) without
touching any real client data. Never calls an AI-generation endpoint (no
Anthropic or Tavily traffic) and never prints secrets, complete note/CV/
profile content — only endpoint status, counts, and pass/fail results.

Usage:
    python scripts/smoke_test_staging.py --base-url https://your-staging-host
    python scripts/smoke_test_staging.py --base-url ... --trial-key ... --no-cleanup

Inputs (flag, or environment variable fallback):
    --base-url   / SMOKE_TEST_BASE_URL   (required)
    --trial-key  / TRIAL_API_KEY          (optional — sent as X-Trial-Key)
    --cleanup / --no-cleanup              (default: cleanup enabled)

Every synthetic value is tagged with a unique run id so repeated runs
against the same environment never clash and are easy to distinguish from
real data if something is left behind.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional

import httpx

RUN_ID = f"smoketest-{int(time.time())}-{uuid.uuid4().hex[:6]}"


class SmokeTestFailure(RuntimeError):
    pass


def _step(label: str) -> None:
    print(f"[STEP] {label}")


def _ok(label: str) -> None:
    print(f"[ OK ] {label}")


class StagingClient:
    def __init__(self, base_url: str, trial_key: Optional[str]):
        headers = {"X-Trial-Key": trial_key} if trial_key else {}
        self._http = httpx.Client(base_url=base_url, headers=headers, timeout=30.0)

    def request(self, method: str, path: str, expected_status: int, **kwargs) -> Dict[str, Any]:
        response = self._http.request(method, path, **kwargs)
        if response.status_code != expected_status:
            raise SmokeTestFailure(
                f"{method} {path} -> {response.status_code} (expected {expected_status})"
            )
        return response.json() if response.content else {}

    def raw_get(self, path: str) -> httpx.Response:
        return self._http.get(path)

    def close(self) -> None:
        self._http.close()


def run(base_url: str, trial_key: Optional[str], cleanup: bool) -> None:
    client = StagingClient(base_url, trial_key)
    client_id = None
    try:
        _step("GET /health")
        health = client.request("GET", "/health", 200)
        print(
            f"       storage_backend={health.get('storage_backend')} "
            f"storage_connected={health.get('storage_connected')}"
        )
        _ok("health check")

        _step("POST /clients (create synthetic client)")
        created = client.request(
            "POST", "/clients", 201, json={"name": f"{RUN_ID} Synthetic Client"}
        )
        client_id = created["id"]
        _ok(f"created client {client_id}")

        _step("GET /clients/{id} (retrieve)")
        fetched = client.request("GET", f"/clients/{client_id}", 200)
        assert fetched["profile"]["name"] == f"{RUN_ID} Synthetic Client", "name mismatch on retrieve"
        _ok("retrieved client matches what was created")

        _step("PUT /clients/{id} (update profile)")
        profile = {
            "name": f"{RUN_ID} Synthetic Client",
            "current_role": "Synthetic Tester",
            "location": "Nowhere",
            "target_geography": "",
            "desired_next_move": "",
            "timeframe": "",
            "roles_wanted": "",
            "roles_not_wanted": "",
            "constraints": "",
            "relationship_assets": "",
            "advisor_notes": f"{RUN_ID} synthetic advisor note",
            "cv_text": f"{RUN_ID} synthetic cv text",
        }
        updated = client.request("PUT", f"/clients/{client_id}", 200, json={"profile": profile})
        assert updated["profile"]["current_role"] == "Synthetic Tester", "profile update did not persist"
        _ok("profile updated")

        _step("POST opportunities x2")
        opp1 = client.request(
            "POST",
            f"/clients/{client_id}/opportunities",
            201,
            json={"title": f"{RUN_ID} Opp One", "company": "Synthetic Co"},
        )["opportunities"][-1]
        opp2 = client.request(
            "POST",
            f"/clients/{client_id}/opportunities",
            201,
            json={"title": f"{RUN_ID} Opp Two", "company": "Synthetic Co"},
        )["opportunities"][-1]
        _ok(f"created 2 opportunities ({opp1['id']}, {opp2['id']})")

        _step("POST target contact linked to an opportunity")
        contact = client.request(
            "POST",
            f"/clients/{client_id}/target-contacts",
            201,
            json={"name": f"{RUN_ID} Contact", "related_opportunity_id": opp1["id"]},
        )["target_contacts"][-1]
        _ok(f"created target contact {contact['id']}")

        _step("POST session note")
        note = client.request(
            "POST",
            f"/clients/{client_id}/notes",
            201,
            json={"date": "2026-01-01", "title": f"{RUN_ID} Note", "notes": f"{RUN_ID} synthetic note body"},
        )["session_notes"][-1]
        _ok(f"created session note {note['id']}")

        _step("POST action items x2 (one linked to an opportunity)")
        action1 = client.request(
            "POST", f"/clients/{client_id}/actions", 201, json={"action": f"{RUN_ID} Action One"}
        )["action_items"][-1]
        action2 = client.request(
            "POST",
            f"/clients/{client_id}/actions",
            201,
            json={"action": f"{RUN_ID} Action Two", "related_opportunity": opp2["id"]},
        )["action_items"][-1]
        _ok(f"created 2 action items ({action1['id']}, {action2['id']})")

        _step("GET /clients/{id} (validate round trip, ordering, links)")
        full = client.request("GET", f"/clients/{client_id}", 200)

        actual_opp_order = [o["id"] for o in full["opportunities"]]
        assert actual_opp_order == [opp1["id"], opp2["id"]], (
            f"opportunity order not preserved: {actual_opp_order}"
        )
        assert len(full["target_contacts"]) == 1, "expected exactly 1 target contact"
        assert full["target_contacts"][0]["related_opportunity_id"] == opp1["id"], (
            "target contact's related_opportunity_id did not survive the round trip"
        )
        assert len(full["session_notes"]) == 1, "expected exactly 1 session note"
        actual_action_order = [a["id"] for a in full["action_items"]]
        assert actual_action_order == [action1["id"], action2["id"]], (
            f"action item order not preserved: {actual_action_order}"
        )
        assert full["action_items"][1]["related_opportunity"] == opp2["id"], (
            "action item's related_opportunity did not survive the round trip"
        )
        _ok("round trip, list ordering, and linked references all verified")

        _step("PUT one of each operational entity type")
        client.request(
            "PUT",
            f"/clients/{client_id}/opportunities/{opp1['id']}",
            200,
            json={"title": opp1["title"], "company": opp1["company"], "status": "Contacted"},
        )
        client.request(
            "PUT",
            f"/clients/{client_id}/target-contacts/{contact['id']}",
            200,
            json={
                "name": contact["name"],
                "related_opportunity_id": contact["related_opportunity_id"],
                "status": "Contacted",
            },
        )
        client.request(
            "PUT",
            f"/clients/{client_id}/notes/{note['id']}",
            200,
            json={"date": note["date"], "title": note["title"], "notes": note["notes"] + " (edited)"},
        )
        client.request(
            "PUT",
            f"/clients/{client_id}/actions/{action1['id']}",
            200,
            json={"action": action1["action"], "status": "Done"},
        )
        _ok("updated one of each entity type")

        _step("DELETE one action item and verify removal")
        client.request("DELETE", f"/clients/{client_id}/actions/{action2['id']}", 200)
        after_delete = client.request("GET", f"/clients/{client_id}", 200)
        remaining_action_ids = [a["id"] for a in after_delete["action_items"]]
        assert action2["id"] not in remaining_action_ids, "deleted action item is still present"
        _ok("deletion verified")

        print(f"\nSMOKE TEST PASSED (run_id={RUN_ID}, client_id={client_id})")

    finally:
        if client_id and cleanup:
            _step("DELETE /clients/{id} (cleanup)")
            client.request("DELETE", f"/clients/{client_id}", 200)
            gone = client.raw_get(f"/clients/{client_id}")
            if gone.status_code != 404:
                client.close()
                raise SmokeTestFailure(
                    f"client {client_id} still retrievable after cleanup (status {gone.status_code})"
                )
            _ok("cleanup verified — client no longer retrievable")
        elif client_id:
            print(f"[INFO] cleanup disabled — synthetic client {client_id} left in place for inspection")
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("SMOKE_TEST_BASE_URL"),
        help="Base URL of the deployed backend (or SMOKE_TEST_BASE_URL env var).",
    )
    parser.add_argument(
        "--trial-key",
        default=os.getenv("TRIAL_API_KEY"),
        help="X-Trial-Key header value, if required (or TRIAL_API_KEY env var).",
    )
    cleanup_group = parser.add_mutually_exclusive_group()
    cleanup_group.add_argument(
        "--cleanup",
        dest="cleanup",
        action="store_true",
        default=True,
        help="Delete the synthetic client at the end (default).",
    )
    cleanup_group.add_argument(
        "--no-cleanup",
        dest="cleanup",
        action="store_false",
        help="Leave the synthetic client in place for manual inspection.",
    )
    args = parser.parse_args()

    if not args.base_url:
        print("ERROR: --base-url or SMOKE_TEST_BASE_URL is required.", file=sys.stderr)
        sys.exit(1)

    try:
        run(args.base_url, args.trial_key, args.cleanup)
    except (SmokeTestFailure, AssertionError, httpx.HTTPError) as exc:
        print(f"\nSMOKE TEST FAILED: {exc}", file=sys.stderr)
        print(f"run_id={RUN_ID} base_url={args.base_url}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
