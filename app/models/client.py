from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


class PositioningPathway(BaseModel):
    pathway: str = ""
    rationale: str = ""
    fit_level: str = ""
    stretch_risk: str = ""


class PositioningOutput(BaseModel):
    executive_positioning: str = ""
    leadership_archetype: str = ""
    core_strengths: List[str] = Field(default_factory=list)
    market_credibility: List[str] = Field(default_factory=list)
    positioning_risks: List[str] = Field(default_factory=list)
    narrative_to_lead: str = ""
    narrative_to_avoid: str = ""
    recommended_pathways: List[PositioningPathway] = Field(default_factory=list)
    advisor_only_notes: List[str] = Field(default_factory=list)


class LeadershipScale(BaseModel):
    team_size: str = ""
    revenue_or_pnl: str = ""
    geography: str = ""
    stakeholders: str = ""


class CVIntelligence(BaseModel):
    executive_summary: str = ""
    career_arc: str = ""
    core_capabilities: List[str] = Field(default_factory=list)
    signature_achievements: List[str] = Field(default_factory=list)
    leadership_scale: LeadershipScale = Field(default_factory=LeadershipScale)
    sector_experience: List[str] = Field(default_factory=list)
    role_patterns: List[str] = Field(default_factory=list)
    commercial_strengths: List[str] = Field(default_factory=list)
    transformation_strengths: List[str] = Field(default_factory=list)
    evidence_gaps: List[str] = Field(default_factory=list)
    under_positioned_assets: List[str] = Field(default_factory=list)
    cv_improvement_recommendations: List[str] = Field(default_factory=list)
    advisor_only_notes: List[str] = Field(default_factory=list)


class RadarSource(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class MarketRadarPathway(BaseModel):
    pathway: str = ""
    why_relevant: str = ""
    market_pull: str = ""
    fit_level: str = ""
    watchouts: str = ""


class TargetCompany(BaseModel):
    company: str = ""
    category: str = ""
    why_relevant: str = ""
    signal_or_trigger: str = ""
    entry_route: str = ""
    priority: str = ""
    sources: List[RadarSource] = Field(default_factory=list)


class Tier1Company(BaseModel):
    company: str = ""
    category: str = ""
    why_relevant: str = ""
    signal_or_trigger: str = ""
    entry_route: str = ""
    advisor_angle: str = ""
    priority: str = ""
    confidence: str = ""
    sources: List[RadarSource] = Field(default_factory=list)


class Tier2Company(BaseModel):
    company: str = ""
    category: str = ""
    why_relevant: str = ""
    likely_role_angle: str = ""
    trigger_or_rationale: str = ""
    priority: str = ""
    confidence: str = ""
    sources: List[RadarSource] = Field(default_factory=list)


class Tier3Company(BaseModel):
    company: str = ""
    category: str = ""
    why_it_may_be_relevant: str = ""
    confidence: str = ""
    notes: str = ""


class MarketRadarSignal(BaseModel):
    signal: str = ""
    signal_type: str = ""
    company: str = ""
    evidence_or_rationale: str = ""
    confidence: str = ""
    recommended_action: str = ""
    sources: List[RadarSource] = Field(default_factory=list)


class HiddenMarketHypothesis(BaseModel):
    hypothesis: str = ""
    trigger: str = ""
    why_client_fits: str = ""
    what_to_validate: str = ""
    confidence: str = ""
    sources: List[RadarSource] = Field(default_factory=list)


class RelationshipStrategy(BaseModel):
    target: str = ""
    relationship_angle: str = ""
    suggested_conversation: str = ""


class MarketRadarOutput(BaseModel):
    market_summary: str = ""
    priority_pathways: List[MarketRadarPathway] = Field(default_factory=list)
    target_companies: List[TargetCompany] = Field(default_factory=list)   # legacy; kept for backward compat
    tier1_companies: List[Tier1Company] = Field(default_factory=list)
    tier2_companies: List[Tier2Company] = Field(default_factory=list)
    tier3_companies: List[Tier3Company] = Field(default_factory=list)
    market_signals: List[MarketRadarSignal] = Field(default_factory=list)
    hidden_market_hypotheses: List[HiddenMarketHypothesis] = Field(default_factory=list)
    relationship_strategy: List[RelationshipStrategy] = Field(default_factory=list)
    advisor_only_notes: List[str] = Field(default_factory=list)
    next_research_actions: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)


class ClientProfile(BaseModel):
    name: str = ""
    current_role: str = ""
    location: str = ""
    target_geography: str = ""
    desired_next_move: str = ""
    timeframe: str = ""
    roles_wanted: str = ""
    roles_not_wanted: str = ""
    constraints: str = ""
    relationship_assets: str = ""
    advisor_notes: str = ""
    cv_text: str = ""


class Opportunity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    company: str = ""
    pathway: str = ""
    source_type: str = ""           # "market_radar" | "manual"
    source_section: str = ""        # "target_companies" | "market_signals" | "hidden_market_hypotheses"
    confidence: str = ""            # "verified" | "inferred" | "hypothesis"
    priority: str = "Medium"        # "High" | "Medium" | "Low"
    status: str = "Monitor"
    fit_rationale: str = ""
    evidence: str = ""
    relationship_route: str = ""
    next_action: str = ""
    advisor_note: str = ""
    sources: List[RadarSource] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PriorityOpportunity(BaseModel):
    opportunity: str = ""
    why_it_matters: str = ""
    recommended_advisor_action: str = ""
    risk_or_watchout: str = ""


class AdvisorBrief(BaseModel):
    brief_summary: str = ""
    client_situation: str = ""
    session_focus: List[str] = Field(default_factory=list)
    key_positioning_insights: List[str] = Field(default_factory=list)
    priority_opportunities: List[PriorityOpportunity] = Field(default_factory=list)
    market_signals_to_discuss: List[str] = Field(default_factory=list)
    questions_to_ask_client: List[str] = Field(default_factory=list)
    advisor_challenges: List[str] = Field(default_factory=list)
    recommended_next_actions: List[str] = Field(default_factory=list)
    advisor_only_notes: List[str] = Field(default_factory=list)


class SessionNote(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str = ""
    title: str = ""
    notes: str = ""
    advisor_only: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ActionItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action: str = ""
    owner: str = "Advisor"          # "Advisor" | "Client" | "Both"
    due_date: str = ""
    status: str = "To do"           # "To do" | "In progress" | "Done" | "Parked"
    related_opportunity: str = ""
    advisor_note: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ClientRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    profile: ClientProfile = Field(default_factory=ClientProfile)
    positioning: Optional[PositioningOutput] = None
    positioning_raw: Optional[str] = None              # set when structured parse fails
    positioning_generated_at: Optional[str] = None
    cv_intelligence: Optional[CVIntelligence] = None
    cv_intelligence_raw: Optional[str] = None          # set when structured parse fails
    cv_intelligence_generated_at: Optional[str] = None
    market_radar: Optional[MarketRadarOutput] = None
    market_radar_raw: Optional[str] = None             # set when structured parse fails
    market_radar_generated_at: Optional[str] = None
    market_radar_is_complete: Optional[bool] = None
    market_radar_scan_warning: Optional[str] = None
    opportunities: List[Opportunity] = Field(default_factory=list)
    session_notes: List[SessionNote] = Field(default_factory=list)
    action_items:  List[ActionItem]  = Field(default_factory=list)
    advisor_brief: Optional[AdvisorBrief] = None
    advisor_brief_raw: Optional[str] = None
    advisor_brief_generated_at: Optional[str] = None
    advisor_brief_is_edited: Optional[bool] = None
    advisor_brief_edited_at: Optional[str] = None


class CreateClientRequest(BaseModel):
    name: str


class UpdateClientRequest(BaseModel):
    profile: ClientProfile


class MarketRadarRequest(BaseModel):
    manual_research: Optional[str] = None


class OpportunityRequest(BaseModel):
    title: str = ""
    company: str = ""
    pathway: str = ""
    source_type: str = ""
    source_section: str = ""
    confidence: str = ""
    priority: str = "Medium"
    status: str = "Monitor"
    fit_rationale: str = ""
    evidence: str = ""
    relationship_route: str = ""
    next_action: str = ""
    advisor_note: str = ""
    sources: List[RadarSource] = Field(default_factory=list)


class SessionNoteRequest(BaseModel):
    date: str = ""
    title: str = ""
    notes: str = ""
    advisor_only: bool = False


class ActionItemRequest(BaseModel):
    action: str = ""
    owner: str = "Advisor"
    due_date: str = ""
    status: str = "To do"
    related_opportunity: str = ""
    advisor_note: str = ""
