"""CRUD integration tests for app/data/storage_postgres.py against a real
PostgreSQL database (no mocked SQLAlchemy).

Child entities are exercised through full-record updates (get -> mutate ->
update_client), exactly the pattern app/main.py uses today, so these tests
double as confirmation that the adapter is a drop-in replacement.
"""
from __future__ import annotations

import pytest

from app.data import storage_postgres as pg
from app.models.client import ClientProfile, ClientRecord, Opportunity, TargetContact


def test_create_client(pg_database):
    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Create Me")))
    assert created.id
    assert created.profile.name == "Create Me"


def test_list_clients(pg_database):
    pg.create_client(ClientRecord(profile=ClientProfile(name="A")))
    pg.create_client(ClientRecord(profile=ClientProfile(name="B")))

    clients = pg.list_clients()
    assert {c.profile.name for c in clients} == {"A", "B"}


def test_get_client_not_found_returns_none(pg_database):
    assert pg.get_client("00000000-0000-0000-0000-000000000000") is None


def test_update_profile(pg_database):
    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Original")))
    fetched = pg.get_client(created.id)
    fetched.profile.name = "Updated"
    updated = pg.update_client(fetched)

    assert updated.profile.name == "Updated"
    assert pg.get_client(created.id).profile.name == "Updated"


def test_update_client_raises_keyerror_when_missing(pg_database):
    ghost = ClientRecord(profile=ClientProfile(name="Ghost"))
    with pytest.raises(KeyError):
        pg.update_client(ghost)


def test_delete_client_returns_false_when_missing(pg_database):
    assert pg.delete_client("00000000-0000-0000-0000-000000000000") is False


def test_create_update_delete_opportunity_via_full_record_update(pg_database):
    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Opp Owner")))

    fetched = pg.get_client(created.id)
    fetched.opportunities = [Opportunity(title="New Opp", company="Acme")]
    updated = pg.update_client(fetched)
    assert len(updated.opportunities) == 1
    opp_id = updated.opportunities[0].id

    fetched2 = pg.get_client(created.id)
    fetched2.opportunities[0].status = "Contacted"
    updated2 = pg.update_client(fetched2)
    assert updated2.opportunities[0].status == "Contacted"
    assert updated2.opportunities[0].id == opp_id

    fetched3 = pg.get_client(created.id)
    fetched3.opportunities = []
    updated3 = pg.update_client(fetched3)
    assert updated3.opportunities == []


def test_create_update_delete_target_contact_via_full_record_update(pg_database):
    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Contact Owner")))

    fetched = pg.get_client(created.id)
    fetched.target_contacts = [TargetContact(name="Jane")]
    updated = pg.update_client(fetched)
    contact_id = updated.target_contacts[0].id

    fetched2 = pg.get_client(created.id)
    fetched2.target_contacts[0].status = "Contacted"
    updated2 = pg.update_client(fetched2)
    assert updated2.target_contacts[0].status == "Contacted"
    assert updated2.target_contacts[0].id == contact_id

    fetched3 = pg.get_client(created.id)
    fetched3.target_contacts = []
    assert pg.update_client(fetched3).target_contacts == []


def test_create_update_delete_session_note_via_full_record_update(pg_database):
    from app.models.client import SessionNote

    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Note Owner")))

    fetched = pg.get_client(created.id)
    fetched.session_notes = [SessionNote(title="First note")]
    updated = pg.update_client(fetched)
    note_id = updated.session_notes[0].id

    fetched2 = pg.get_client(created.id)
    fetched2.session_notes[0].notes = "Edited content"
    updated2 = pg.update_client(fetched2)
    assert updated2.session_notes[0].notes == "Edited content"
    assert updated2.session_notes[0].id == note_id

    fetched3 = pg.get_client(created.id)
    fetched3.session_notes = []
    assert pg.update_client(fetched3).session_notes == []


def test_create_update_delete_action_item_via_full_record_update(pg_database):
    from app.models.client import ActionItem

    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Action Owner")))

    fetched = pg.get_client(created.id)
    fetched.action_items = [ActionItem(action="Do the thing")]
    updated = pg.update_client(fetched)
    action_id = updated.action_items[0].id

    fetched2 = pg.get_client(created.id)
    fetched2.action_items[0].status = "Done"
    updated2 = pg.update_client(fetched2)
    assert updated2.action_items[0].status == "Done"
    assert updated2.action_items[0].id == action_id

    fetched3 = pg.get_client(created.id)
    fetched3.action_items = []
    assert pg.update_client(fetched3).action_items == []


def test_valid_related_opportunity_reference_preserved(pg_database):
    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Refs")))
    fetched = pg.get_client(created.id)
    fetched.opportunities = [Opportunity(title="Target Opp")]
    updated = pg.update_client(fetched)
    opp_id = updated.opportunities[0].id

    fetched2 = pg.get_client(created.id)
    fetched2.target_contacts = [TargetContact(name="Linked", related_opportunity_id=opp_id)]
    updated2 = pg.update_client(fetched2)

    assert updated2.target_contacts[0].related_opportunity_id == opp_id


def test_dangling_related_opportunity_reference_nulled(pg_database):
    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Dangling")))
    fetched = pg.get_client(created.id)
    fetched.target_contacts = [
        TargetContact(name="Orphan", related_opportunity_id="does-not-exist")
    ]
    updated = pg.update_client(fetched)

    assert updated.target_contacts[0].related_opportunity_id == ""


def test_cascade_deletion(pg_database):
    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Cascade")))
    fetched = pg.get_client(created.id)
    fetched.opportunities = [Opportunity(title="Will be cascaded")]
    pg.update_client(fetched)

    assert pg.delete_client(created.id) is True
    assert pg.get_client(created.id) is None

    from app.db.session import session_scope
    from app.db.models import Opportunity as OpportunityORM

    with session_scope() as session:
        remaining = session.query(OpportunityORM).filter_by(client_id=created.id).count()
    assert remaining == 0


def test_persistence_after_closing_and_reopening_session(pg_database):
    created = pg.create_client(ClientRecord(profile=ClientProfile(name="Persisted")))

    from app.db.session import get_engine, reset_engine_cache

    get_engine().dispose()
    reset_engine_cache()  # forces a brand-new engine/connection pool

    refetched = pg.get_client(created.id)
    assert refetched is not None
    assert refetched.profile.name == "Persisted"
