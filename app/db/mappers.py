"""Explicit mapping between SQLAlchemy ORM rows and the existing Pydantic
`ClientRecord` API shape.

FastAPI must never see an ORM object directly — every read from Postgres
goes through `client_row_to_record`, and every write goes through the
`*_to_orm_kwargs` helpers here. This is the only module that needs to know
about both representations at once.

Dangling related-opportunity references (a contact/action pointing at an
opportunity id that no longer exists in the same client) are resolved by
`resolve_related_opportunity_ref` BEFORE calling the kwargs builders here —
the caller (storage adapter or migration script) decides what to log; this
module only does the structural mapping.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from app.db.models import (
    ActionItem as ActionItemORM,
    Client as ClientORM,
    Opportunity as OpportunityORM,
    SessionNote as SessionNoteORM,
    TargetContact as TargetContactORM,
)
from app.models.client import (
    ActionItem,
    AdvisorBrief,
    ClientProfile,
    ClientRecord,
    CVIntelligence,
    MarketRadarOutput,
    Opportunity,
    PositioningOutput,
    RadarSource,
    SessionNote,
    TargetContact,
)

PROFILE_FIELDS = (
    "name",
    "current_role",
    "location",
    "target_geography",
    "desired_next_move",
    "timeframe",
    "roles_wanted",
    "roles_not_wanted",
    "constraints",
    "relationship_assets",
    "advisor_notes",
    "cv_text",
)


def iso_to_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def dt_to_iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def opt_str_to_fk(value: str) -> Optional[str]:
    """Pydantic's "" (no reference) -> SQL NULL."""
    return value if value else None


def fk_to_opt_str(value: Optional[str]) -> str:
    """SQL NULL -> Pydantic's "" (no reference)."""
    return value or ""


def resolve_related_opportunity_ref(
    candidate_id: str, valid_opportunity_ids: Iterable[str]
) -> tuple[Optional[str], bool]:
    """Returns (fk_value_to_store, was_dangling).

    A blank candidate is not dangling — it simply means "no reference".
    A non-blank candidate that isn't among this client's current
    opportunity ids is dangling and must be nulled rather than inserted,
    since the database enforces the foreign key.
    """
    if not candidate_id:
        return None, False
    if candidate_id in valid_opportunity_ids:
        return candidate_id, False
    return None, True


def profile_to_columns(profile: ClientProfile) -> dict:
    return {f"profile_{field}": getattr(profile, field) for field in PROFILE_FIELDS}


def columns_to_profile(row: ClientORM) -> ClientProfile:
    return ClientProfile(
        **{field: getattr(row, f"profile_{field}") for field in PROFILE_FIELDS}
    )


def _blob_to_json(model) -> Optional[dict]:
    return model.model_dump(mode="json") if model is not None else None


def client_record_to_columns(record: ClientRecord) -> dict:
    """All Client-row columns derived from a ClientRecord, except `id`."""
    return {
        "created_at": iso_to_dt(record.created_at),
        "updated_at": iso_to_dt(record.updated_at),
        **profile_to_columns(record.profile),
        "cv_intelligence": _blob_to_json(record.cv_intelligence),
        "cv_intelligence_raw": record.cv_intelligence_raw,
        "cv_intelligence_generated_at": iso_to_dt(record.cv_intelligence_generated_at),
        "positioning": _blob_to_json(record.positioning),
        "positioning_raw": record.positioning_raw,
        "positioning_generated_at": iso_to_dt(record.positioning_generated_at),
        "market_radar": _blob_to_json(record.market_radar),
        "market_radar_raw": record.market_radar_raw,
        "market_radar_generated_at": iso_to_dt(record.market_radar_generated_at),
        "market_radar_is_complete": record.market_radar_is_complete,
        "market_radar_scan_warning": record.market_radar_scan_warning,
        "advisor_brief": _blob_to_json(record.advisor_brief),
        "advisor_brief_raw": record.advisor_brief_raw,
        "advisor_brief_generated_at": iso_to_dt(record.advisor_brief_generated_at),
        "advisor_brief_is_edited": record.advisor_brief_is_edited,
        "advisor_brief_edited_at": iso_to_dt(record.advisor_brief_edited_at),
    }


def client_row_to_record(row: ClientORM) -> ClientRecord:
    """Builds a full ClientRecord from a Client row.

    Assumes row.opportunities / target_contacts / session_notes /
    action_items are already loaded and ordered by sort_order (the ORM
    relationship's order_by handles this, but callers that issue their own
    queries must order explicitly too — see app/data/storage_postgres.py).
    """
    return ClientRecord(
        id=row.id,
        created_at=dt_to_iso(row.created_at),
        updated_at=dt_to_iso(row.updated_at),
        profile=columns_to_profile(row),
        positioning=PositioningOutput.model_validate(row.positioning)
        if row.positioning is not None
        else None,
        positioning_raw=row.positioning_raw,
        positioning_generated_at=dt_to_iso(row.positioning_generated_at),
        cv_intelligence=CVIntelligence.model_validate(row.cv_intelligence)
        if row.cv_intelligence is not None
        else None,
        cv_intelligence_raw=row.cv_intelligence_raw,
        cv_intelligence_generated_at=dt_to_iso(row.cv_intelligence_generated_at),
        market_radar=MarketRadarOutput.model_validate(row.market_radar)
        if row.market_radar is not None
        else None,
        market_radar_raw=row.market_radar_raw,
        market_radar_generated_at=dt_to_iso(row.market_radar_generated_at),
        market_radar_is_complete=row.market_radar_is_complete,
        market_radar_scan_warning=row.market_radar_scan_warning,
        opportunities=[orm_to_opportunity(o) for o in row.opportunities],
        target_contacts=[orm_to_target_contact(c) for c in row.target_contacts],
        session_notes=[orm_to_session_note(n) for n in row.session_notes],
        action_items=[orm_to_action_item(a) for a in row.action_items],
        advisor_brief=AdvisorBrief.model_validate(row.advisor_brief)
        if row.advisor_brief is not None
        else None,
        advisor_brief_raw=row.advisor_brief_raw,
        advisor_brief_generated_at=dt_to_iso(row.advisor_brief_generated_at),
        advisor_brief_is_edited=row.advisor_brief_is_edited,
        advisor_brief_edited_at=dt_to_iso(row.advisor_brief_edited_at),
    )


def opportunity_to_orm_kwargs(opp: Opportunity, client_id: str, sort_order: int) -> dict:
    return dict(
        id=opp.id,
        client_id=client_id,
        title=opp.title,
        company=opp.company,
        pathway=opp.pathway,
        source_type=opp.source_type,
        source_section=opp.source_section,
        confidence=opp.confidence,
        priority=opp.priority,
        status=opp.status,
        fit_rationale=opp.fit_rationale,
        evidence=opp.evidence,
        relationship_route=opp.relationship_route,
        next_action=opp.next_action,
        advisor_note=opp.advisor_note,
        sources=[s.model_dump(mode="json") for s in opp.sources],
        created_at=iso_to_dt(opp.created_at),
        updated_at=iso_to_dt(opp.updated_at),
        sort_order=sort_order,
    )


def orm_to_opportunity(row: OpportunityORM) -> Opportunity:
    return Opportunity(
        id=row.id,
        title=row.title,
        company=row.company,
        pathway=row.pathway,
        source_type=row.source_type,
        source_section=row.source_section,
        confidence=row.confidence,
        priority=row.priority,
        status=row.status,
        fit_rationale=row.fit_rationale,
        evidence=row.evidence,
        relationship_route=row.relationship_route,
        next_action=row.next_action,
        advisor_note=row.advisor_note,
        sources=[RadarSource(**s) for s in (row.sources or [])],
        created_at=dt_to_iso(row.created_at),
        updated_at=dt_to_iso(row.updated_at),
    )


_TARGET_CONTACT_HMM_FIELDS = (
    "network_source",
    "relationship_owner",
    "relationship_to_client",
    "relationship_to_advisor",
    "relationship_strength",
    "last_contacted_at",
    "role_in_search",
    "target_company",
    "target_sector",
    "linked_market_radar_company",
    "linked_market_radar_tier",
    "linked_opportunity_id",
    "linked_opportunity_title",
    "relevance_rationale",
    "opportunity_path_hypothesis",
    "can_make_intro",
    "bridge_to",
    "warm_path_status",
    "ask_type",
    "suggested_approach",
    "next_action",
    "next_action_owner",
    "next_action_due_date",
    "follow_up_date",
    "outreach_channel",
    "response_notes",
    "advisor_only",
    "advisor_notes",
    "client_shareable",
    "approved_for_outreach",
    "sensitive",
    "do_not_contact_yet",
    "include_in_advisor_brief",
    "include_in_weekly_plan",
)


def target_contact_to_orm_kwargs(
    tc: TargetContact,
    client_id: str,
    sort_order: int,
    related_opportunity_id: Optional[str],
) -> dict:
    return dict(
        id=tc.id,
        client_id=client_id,
        related_opportunity_id=related_opportunity_id,
        name=tc.name,
        title=tc.title,
        company=tc.company,
        linkedin_url=tc.linkedin_url,
        source_url=tc.source_url,
        why_relevant=tc.why_relevant,
        suggested_angle=tc.suggested_angle,
        confidence=tc.confidence,
        status=tc.status,
        notes=tc.notes,
        created_at=iso_to_dt(tc.created_at),
        updated_at=iso_to_dt(tc.updated_at),
        sort_order=sort_order,
        **{field: getattr(tc, field) for field in _TARGET_CONTACT_HMM_FIELDS},
    )


def orm_to_target_contact(row: TargetContactORM) -> TargetContact:
    return TargetContact(
        id=row.id,
        name=row.name,
        title=row.title,
        company=row.company,
        linkedin_url=row.linkedin_url,
        source_url=row.source_url,
        related_opportunity_id=fk_to_opt_str(row.related_opportunity_id),
        why_relevant=row.why_relevant,
        suggested_angle=row.suggested_angle,
        confidence=row.confidence,
        status=row.status,
        notes=row.notes,
        created_at=dt_to_iso(row.created_at),
        updated_at=dt_to_iso(row.updated_at),
        **{field: getattr(row, field) for field in _TARGET_CONTACT_HMM_FIELDS},
    )


def session_note_to_orm_kwargs(note: SessionNote, client_id: str, sort_order: int) -> dict:
    return dict(
        id=note.id,
        client_id=client_id,
        date=note.date,
        title=note.title,
        notes=note.notes,
        advisor_only=note.advisor_only,
        created_at=iso_to_dt(note.created_at),
        updated_at=iso_to_dt(note.updated_at),
        sort_order=sort_order,
    )


def orm_to_session_note(row: SessionNoteORM) -> SessionNote:
    return SessionNote(
        id=row.id,
        date=row.date,
        title=row.title,
        notes=row.notes,
        advisor_only=row.advisor_only,
        created_at=dt_to_iso(row.created_at),
        updated_at=dt_to_iso(row.updated_at),
    )


def action_item_to_orm_kwargs(
    item: ActionItem,
    client_id: str,
    sort_order: int,
    related_opportunity_id: Optional[str],
) -> dict:
    return dict(
        id=item.id,
        client_id=client_id,
        related_opportunity_id=related_opportunity_id,
        action=item.action,
        owner=item.owner,
        due_date=item.due_date,
        status=item.status,
        advisor_note=item.advisor_note,
        created_at=iso_to_dt(item.created_at),
        updated_at=iso_to_dt(item.updated_at),
        sort_order=sort_order,
    )


def orm_to_action_item(row: ActionItemORM) -> ActionItem:
    return ActionItem(
        id=row.id,
        action=row.action,
        owner=row.owner,
        due_date=row.due_date,
        status=row.status,
        related_opportunity=fk_to_opt_str(row.related_opportunity_id),
        advisor_note=row.advisor_note,
        created_at=dt_to_iso(row.created_at),
        updated_at=dt_to_iso(row.updated_at),
    )
