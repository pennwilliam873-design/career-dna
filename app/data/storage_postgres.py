"""PostgreSQL-backed implementation of the five storage operations.

Mirrors app/data/storage.py's function signatures and behaviour exactly
(including raising KeyError from update_client when the client doesn't
exist) so app/data/storage_selector.py can swap between the two without
any caller-visible difference. Only used when STORAGE_BACKEND=postgres.

Every write happens inside app.db.session.session_scope(), which commits
on success and rolls back on any exception — partial writes never reach
the database. ORM rows are never returned to callers; everything goes
through app/db/mappers.py before crossing back into the ClientRecord API
shape FastAPI expects.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import mappers
from app.db.models import (
    ActionItem as ActionItemORM,
    Client as ClientORM,
    Opportunity as OpportunityORM,
    SessionNote as SessionNoteORM,
    TargetContact as TargetContactORM,
)
from app.db.session import session_scope
from app.models.client import ClientRecord

logger = logging.getLogger(__name__)


def _loaded_query():
    return select(ClientORM).options(
        selectinload(ClientORM.opportunities),
        selectinload(ClientORM.target_contacts),
        selectinload(ClientORM.session_notes),
        selectinload(ClientORM.action_items),
    )


def _get_row(session: Session, client_id: str) -> Optional[ClientORM]:
    return session.execute(
        _loaded_query().where(ClientORM.id == client_id)
    ).scalars().first()


def list_clients() -> List[ClientRecord]:
    with session_scope() as session:
        rows = (
            session.execute(_loaded_query().order_by(ClientORM.created_at, ClientORM.id))
            .scalars()
            .all()
        )
        return [mappers.client_row_to_record(row) for row in rows]


def get_client(client_id: str) -> Optional[ClientRecord]:
    with session_scope() as session:
        row = _get_row(session, client_id)
        return mappers.client_row_to_record(row) if row is not None else None


def create_client(record: ClientRecord) -> ClientRecord:
    with session_scope() as session:
        row = ClientORM(id=record.id, **mappers.client_record_to_columns(record))
        session.add(row)
        session.flush()
        _sync_children(session, record.id, record)
        session.flush()
        return mappers.client_row_to_record(_get_row(session, record.id))


def update_client(record: ClientRecord) -> ClientRecord:
    with session_scope() as session:
        row = session.get(ClientORM, record.id)
        if row is None:
            raise KeyError(f"Client {record.id} not found")

        # Matches app/data/storage.py's update_client: always bump
        # updated_at to "now" at write time, trusting the rest of the
        # incoming record as-is (the caller always supplies the full
        # record via get_client -> mutate -> update_client).
        record.updated_at = datetime.now(timezone.utc).isoformat()

        for key, value in mappers.client_record_to_columns(record).items():
            setattr(row, key, value)

        _sync_children(session, record.id, record)
        session.flush()
        return mappers.client_row_to_record(_get_row(session, record.id))


def delete_client(client_id: str) -> bool:
    with session_scope() as session:
        row = session.get(ClientORM, client_id)
        if row is None:
            return False
        session.delete(row)
        return True


def _sync_rows(
    session: Session,
    orm_class,
    client_id: str,
    incoming_items,
    kwargs_builder: Callable,
) -> None:
    """Upserts incoming_items by id, deletes rows no longer present, and
    sets sort_order from each item's position in incoming_items."""
    existing = {
        row.id: row
        for row in session.execute(
            select(orm_class).where(orm_class.client_id == client_id)
        ).scalars()
    }
    incoming_ids = {item.id for item in incoming_items}

    for existing_id, row in existing.items():
        if existing_id not in incoming_ids:
            session.delete(row)

    for sort_order, item in enumerate(incoming_items):
        kwargs = kwargs_builder(item, sort_order)
        row = existing.get(item.id)
        if row is None:
            session.add(orm_class(**kwargs))
        else:
            for key, value in kwargs.items():
                if key not in ("id", "client_id"):
                    setattr(row, key, value)


def _sync_children(session: Session, client_id: str, record: ClientRecord) -> None:
    _sync_rows(
        session,
        OpportunityORM,
        client_id,
        record.opportunities,
        lambda opp, sort_order: mappers.opportunity_to_orm_kwargs(opp, client_id, sort_order),
    )
    # Flush now: target_contacts/action_items below may reference an
    # opportunity inserted in the line above via a plain FK column value
    # (not an ORM relationship), so SQLAlchemy has no object-graph link to
    # infer insert order from. Without this flush, a brand-new opportunity
    # referenced by a brand-new contact/action in the same call can violate
    # the foreign key, since both inserts would otherwise be free to land
    # in either order within the same flush.
    session.flush()

    valid_opportunity_ids = {o.id for o in record.opportunities}

    def target_contact_kwargs(tc, sort_order):
        resolved, dangling = mappers.resolve_related_opportunity_ref(
            tc.related_opportunity_id, valid_opportunity_ids
        )
        if dangling:
            logger.warning(
                "target_contact %s (client %s): dangling related_opportunity_id nulled",
                tc.id,
                client_id,
            )
        return mappers.target_contact_to_orm_kwargs(tc, client_id, sort_order, resolved)

    _sync_rows(session, TargetContactORM, client_id, record.target_contacts, target_contact_kwargs)

    _sync_rows(
        session,
        SessionNoteORM,
        client_id,
        record.session_notes,
        lambda note, sort_order: mappers.session_note_to_orm_kwargs(note, client_id, sort_order),
    )

    def action_item_kwargs(item, sort_order):
        resolved, dangling = mappers.resolve_related_opportunity_ref(
            item.related_opportunity, valid_opportunity_ids
        )
        if dangling:
            logger.warning(
                "action_item %s (client %s): dangling related_opportunity nulled",
                item.id,
                client_id,
            )
        return mappers.action_item_to_orm_kwargs(item, client_id, sort_order, resolved)

    _sync_rows(session, ActionItemORM, client_id, record.action_items, action_item_kwargs)
