"""Tests for the Hidden Market Map "extract from notes" feature.

Two layers:
- Service-level (`extract_network_from_notes`): mocks the Anthropic client
  directly (no network, no DB) and checks parsing/validation behaviour.
- Endpoint-level (`POST /clients/{id}/target-contacts/extract-from-notes`):
  uses a real Postgres-backed client (via `pg_database`) and monkeypatches
  the service entry point app.main imports, so these tests prove the route
  wiring, validation, and — most importantly — that suggestions are never
  auto-saved, without needing a real LLM call.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.client import ClientProfile, ClientRecord, TargetContact
from app.services.notes_extraction import (
    NotesExtractionResult,
    SuggestedNetworkContact,
    extract_network_from_notes,
)

client = TestClient(app)


# ── Fakes for the Anthropic SDK shape used by notes_extraction.py ──────────

class _FakeToolBlock:
    type = "tool_use"

    def __init__(self, input_dict):
        self.input = input_dict


class _FakeResponse:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, response):
        self._response = response

    def create(self, **kwargs):
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def _patch_anthropic(monkeypatch, response):
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **kw: _FakeAnthropicClient(response))


_SAMPLE_CONTACT = {
    "name": "Sarah",
    "current_title": "",
    "company": "Lendlease",
    "network_source": "Client Network",
    "relationship_owner": "Client",
    "relationship_to_client": "Former colleague at Lendlease",
    "relationship_to_advisor": "",
    "relationship_strength": "Dormant",
    "role_in_search": "Bridge contact",
    "target_company": "Qantas",
    "target_sector": "",
    "bridge_to": "Qantas transformation network",
    "warm_path_status": "Possible warm path",
    "ask_type": "Market intelligence",
    "suggested_approach": "Reconnect warmly and ask what she's seeing in transformation hiring.",
    "opportunity_path_hypothesis": "Client -> Sarah -> Qantas transformation network",
    "next_action": "Client to confirm Sarah's current role and reconnect if appropriate.",
    "next_action_owner": "Client",
    "status": "To assess",
    "advisor_only": True,
    "client_shareable": False,
    "approved_for_outreach": False,
    "include_in_advisor_brief": False,
    "include_in_weekly_plan": False,
    "missing_information": ["Full name and current role need confirmation"],
    "follow_up_questions": ["Is Sarah definitely at Qantas now, or still at Lendlease?"],
    "confidence": "Medium",
    "evidence_from_notes": "Client mentioned Sarah from Lendlease, now possibly at Qantas in transformation.",
}


# ── Service-level tests ─────────────────────────────────────────────────────

def test_extract_raises_on_empty_notes():
    record = ClientRecord(profile=ClientProfile(name="Empty Notes"))
    with pytest.raises(ValueError):
        extract_network_from_notes(record, "   ")


def test_extract_parses_tool_use_response(monkeypatch):
    record = ClientRecord(profile=ClientProfile(name="Parsing"))
    fake_response = _FakeResponse(content=[_FakeToolBlock({
        "suggested_contacts": [_SAMPLE_CONTACT],
        "network_insights": ["Strongest path is through dormant former-colleague ties."],
        "recommended_follow_up_questions": ["Has the client spoken to anyone else at Qantas?"],
    })])
    _patch_anthropic(monkeypatch, fake_response)

    result = extract_network_from_notes(record, "Client mentioned Sarah from Lendlease...")

    assert isinstance(result, NotesExtractionResult)
    assert len(result.suggested_contacts) == 1
    c = result.suggested_contacts[0]
    assert isinstance(c, SuggestedNetworkContact)
    assert c.name == "Sarah"
    assert c.network_source == "Client Network"
    assert c.relationship_strength == "Dormant"
    assert c.role_in_search == "Bridge contact"
    assert c.bridge_to == "Qantas transformation network"
    assert c.missing_information == ["Full name and current role need confirmation"]
    assert c.confidence == "Medium"
    assert result.network_insights == ["Strongest path is through dormant former-colleague ties."]
    assert result.recommended_follow_up_questions == ["Has the client spoken to anyone else at Qantas?"]


def test_extract_skips_contacts_with_no_name(monkeypatch):
    record = ClientRecord(profile=ClientProfile(name="No Name"))
    bad_contact = {**_SAMPLE_CONTACT, "name": ""}
    fake_response = _FakeResponse(content=[_FakeToolBlock({
        "suggested_contacts": [bad_contact],
        "network_insights": [],
        "recommended_follow_up_questions": [],
    })])
    _patch_anthropic(monkeypatch, fake_response)

    result = extract_network_from_notes(record, "some notes")

    assert result.suggested_contacts == []


def test_extract_returns_empty_result_when_no_tool_use_block(monkeypatch):
    record = ClientRecord(profile=ClientProfile(name="No Tool Use"))
    fake_response = _FakeResponse(content=[], stop_reason="end_turn")
    _patch_anthropic(monkeypatch, fake_response)

    result = extract_network_from_notes(record, "some notes")

    assert result.suggested_contacts == []
    assert result.network_insights == []


def test_extract_raises_runtime_error_on_anthropic_failure(monkeypatch):
    import anthropic

    class _Boom:
        def __init__(self, *a, **kw):
            raise RuntimeError("network down")

    monkeypatch.setattr(anthropic, "Anthropic", _Boom)
    record = ClientRecord(profile=ClientProfile(name="Boom"))

    with pytest.raises(RuntimeError):
        extract_network_from_notes(record, "some notes")


# ── Endpoint-level tests (route wiring, validation, no auto-save) ──────────

def test_endpoint_rejects_empty_notes(pg_database):
    from app.data import storage_postgres as pg

    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Endpoint Empty")))

    response = client.post(
        f"/clients/{created.id}/target-contacts/extract-from-notes", json={"notes": "   "}
    )

    assert response.status_code == 422


def test_endpoint_404_for_missing_client(pg_database):
    response = client.post(
        "/clients/00000000-0000-0000-0000-000000000000/target-contacts/extract-from-notes",
        json={"notes": "Client mentioned Sarah."},
    )
    assert response.status_code == 404


def test_endpoint_returns_suggestions_without_saving(pg_database, monkeypatch):
    from app.data import storage_postgres as pg

    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Endpoint Suggestions")))

    fake_result = NotesExtractionResult(
        suggested_contacts=[SuggestedNetworkContact(name="Sarah", company="Lendlease")],
        network_insights=["Dormant former-colleague tie is the strongest lead."],
        recommended_follow_up_questions=["Confirm Sarah's current employer."],
    )
    monkeypatch.setattr("app.main.extract_network_from_notes", lambda record, notes: fake_result)

    response = client.post(
        f"/clients/{created.id}/target-contacts/extract-from-notes",
        json={"notes": "Client mentioned Sarah from Lendlease, now possibly at Qantas."},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["suggested_contacts"]) == 1
    assert body["suggested_contacts"][0]["name"] == "Sarah"
    assert body["network_insights"] == ["Dormant former-colleague tie is the strongest lead."]
    assert body["recommended_follow_up_questions"] == ["Confirm Sarah's current employer."]

    # Nothing was persisted — the client's target_contacts list is untouched.
    refetched = pg.get_client(created.id)
    assert refetched.target_contacts == []


def test_endpoint_surfaces_extraction_failure_as_500(pg_database, monkeypatch):
    from app.data import storage_postgres as pg

    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Endpoint Failure")))

    def _boom(record, notes):
        raise RuntimeError("Claude is down")

    monkeypatch.setattr("app.main.extract_network_from_notes", _boom)

    response = client.post(
        f"/clients/{created.id}/target-contacts/extract-from-notes",
        json={"notes": "Client mentioned Sarah."},
    )

    assert response.status_code == 500


def test_existing_contacts_still_load_after_extraction_feature_added(pg_database):
    """Regression guard: adding the extraction endpoint must not disturb the
    existing target-contacts read/write path."""
    from app.data import storage_postgres as pg

    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Still Loads")))
    fetched = pg.get_client(created.id)
    fetched.target_contacts = [TargetContact(name="Existing Contact", company="Acme")]
    pg.update_client(fetched)

    response = client.get(f"/clients/{created.id}")
    assert response.status_code == 200
    contacts = response.json()["target_contacts"]
    assert len(contacts) == 1
    assert contacts[0]["name"] == "Existing Contact"
