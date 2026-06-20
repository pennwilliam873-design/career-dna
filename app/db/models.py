"""SQLAlchemy models for the hybrid relational + JSONB schema.

These mirror the Pydantic models in app/models/client.py closely enough to
support a lossless JSON -> PostgreSQL migration later (Stage 2). Operational,
frequently-mutated entities (clients, opportunities, target contacts, session
notes, action items) are relational tables with real columns. The four
AI-generated structured outputs (cv_intelligence, positioning, market_radar,
advisor_brief) stay as JSONB blobs on the client row, matching how the app
already treats them today: written wholesale by one service call, read
wholesale by the frontend, never queried by sub-field.

Dormant: nothing in app/main.py imports this module yet. It only becomes
live once Stage 2 wires up a postgres-backed storage layer behind
STORAGE_BACKEND=postgres (see app/config.py).
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=False), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Mirrors ClientProfile (app/models/client.py) as flat columns — small,
    # stable field set that rarely changes shape.
    profile_name = Column(Text, nullable=False, default="")
    profile_current_role = Column(Text, nullable=False, default="")
    profile_location = Column(Text, nullable=False, default="")
    profile_target_geography = Column(Text, nullable=False, default="")
    profile_desired_next_move = Column(Text, nullable=False, default="")
    profile_timeframe = Column(Text, nullable=False, default="")
    profile_roles_wanted = Column(Text, nullable=False, default="")
    profile_roles_not_wanted = Column(Text, nullable=False, default="")
    profile_constraints = Column(Text, nullable=False, default="")
    profile_relationship_assets = Column(Text, nullable=False, default="")
    profile_advisor_notes = Column(Text, nullable=False, default="")
    profile_cv_text = Column(Text, nullable=False, default="")

    cv_intelligence = Column(JSONB, nullable=True)
    cv_intelligence_raw = Column(Text, nullable=True)
    cv_intelligence_generated_at = Column(DateTime(timezone=True), nullable=True)

    positioning = Column(JSONB, nullable=True)
    positioning_raw = Column(Text, nullable=True)
    positioning_generated_at = Column(DateTime(timezone=True), nullable=True)

    market_radar = Column(JSONB, nullable=True)
    market_radar_raw = Column(Text, nullable=True)
    market_radar_generated_at = Column(DateTime(timezone=True), nullable=True)
    market_radar_is_complete = Column(Boolean, nullable=True)
    market_radar_scan_warning = Column(Text, nullable=True)

    advisor_brief = Column(JSONB, nullable=True)
    advisor_brief_raw = Column(Text, nullable=True)
    advisor_brief_generated_at = Column(DateTime(timezone=True), nullable=True)
    advisor_brief_is_edited = Column(Boolean, nullable=True)
    advisor_brief_edited_at = Column(DateTime(timezone=True), nullable=True)

    opportunities = relationship(
        "Opportunity", back_populates="client", cascade="all, delete-orphan"
    )
    target_contacts = relationship(
        "TargetContact", back_populates="client", cascade="all, delete-orphan"
    )
    session_notes = relationship(
        "SessionNote", back_populates="client", cascade="all, delete-orphan"
    )
    action_items = relationship(
        "ActionItem", back_populates="client", cascade="all, delete-orphan"
    )


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(UUID(as_uuid=False), primary_key=True)
    client_id = Column(
        UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )

    title = Column(Text, nullable=False, default="")
    company = Column(Text, nullable=False, default="")
    pathway = Column(Text, nullable=False, default="")
    source_type = Column(Text, nullable=False, default="")
    source_section = Column(Text, nullable=False, default="")
    confidence = Column(Text, nullable=False, default="")
    priority = Column(Text, nullable=False, default="Medium")
    status = Column(Text, nullable=False, default="Monitor")
    fit_rationale = Column(Text, nullable=False, default="")
    evidence = Column(Text, nullable=False, default="")
    relationship_route = Column(Text, nullable=False, default="")
    next_action = Column(Text, nullable=False, default="")
    advisor_note = Column(Text, nullable=False, default="")
    sources = Column(JSONB, nullable=False, default=list)

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    client = relationship("Client", back_populates="opportunities")


class TargetContact(Base):
    __tablename__ = "target_contacts"

    id = Column(UUID(as_uuid=False), primary_key=True)
    client_id = Column(
        UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    related_opportunity_id = Column(
        UUID(as_uuid=False), ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True
    )

    name = Column(Text, nullable=False, default="")
    title = Column(Text, nullable=False, default="")
    company = Column(Text, nullable=False, default="")
    linkedin_url = Column(Text, nullable=False, default="")
    source_url = Column(Text, nullable=False, default="")
    why_relevant = Column(Text, nullable=False, default="")
    suggested_angle = Column(Text, nullable=False, default="")
    confidence = Column(Text, nullable=False, default="Medium")
    status = Column(Text, nullable=False, default="Not contacted")
    notes = Column(Text, nullable=False, default="")

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    client = relationship("Client", back_populates="target_contacts")


class SessionNote(Base):
    __tablename__ = "session_notes"

    id = Column(UUID(as_uuid=False), primary_key=True)
    client_id = Column(
        UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )

    date = Column(Text, nullable=False, default="")
    title = Column(Text, nullable=False, default="")
    notes = Column(Text, nullable=False, default="")
    advisor_only = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    client = relationship("Client", back_populates="session_notes")


class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(UUID(as_uuid=False), primary_key=True)
    client_id = Column(
        UUID(as_uuid=False), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    # Mirrors ActionItem.related_opportunity (a plain string in the Pydantic
    # model today) as a real FK here, since this column is purely additive.
    related_opportunity_id = Column(
        UUID(as_uuid=False), ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True
    )

    action = Column(Text, nullable=False, default="")
    owner = Column(Text, nullable=False, default="Advisor")
    due_date = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="To do")
    advisor_note = Column(Text, nullable=False, default="")

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    client = relationship("Client", back_populates="action_items")
