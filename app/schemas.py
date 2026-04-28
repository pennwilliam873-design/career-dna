from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AchievementCategory(str, Enum):
    leadership = "leadership"
    financial = "financial"
    operational = "operational"
    other = "other"


class RiskFlag(str, Enum):
    misaligned_values = "misaligned_values"
    narrow_industry_exposure = "narrow_industry_exposure"
    overspecialised = "overspecialised"
    salary_gap = "salary_gap"
    avoidance_overlap = "avoidance_overlap"
    skill_decay = "skill_decay"


class UpskillingLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


InputSource = Literal[
    "cv",
    "achievement",
    "zone_of_genius",
    "conflict_marker",
    "never_again",
    "industry_curiosity",
    "lifestyle_preferences",
    "tools",
    "questionnaire",
]


# ---------------------------------------------------------------------------
# Layer 1 — Raw Input  (unchanged)
# ---------------------------------------------------------------------------

class RawInput(BaseModel):
    cv_text: str = Field(..., description="Full CV as plain text")
    top_achievements: List[str] = Field(..., min_length=1, max_length=3)
    tools: List[str] = Field(default_factory=list)
    zone_of_genius: str = Field(..., description="Self-described area of exceptional ability")
    conflict_marker: str = Field(..., description="How the person behaves under conflict")
    never_again: str = Field(..., description="Work situations they refuse to repeat")
    industry_curiosity: List[str] = Field(default_factory=list)
    lifestyle_preferences: List[str] = Field(default_factory=list)
    salary_floor: float = Field(..., ge=0, description="Minimum acceptable annual salary")
    upskilling_willingness: bool
    # Optional transition-analysis inputs
    target_role: Optional[str] = None
    target_sector: Optional[str] = None
    target_seniority: Optional[str] = None
    transition_goal: Optional[str] = None


# ---------------------------------------------------------------------------
# Inference primitives — weighting + traceability
# ---------------------------------------------------------------------------

class SignalTrace(BaseModel):
    """Pointer back to the exact input fragment that produced this inference."""
    source: InputSource
    excerpt: str = Field(..., description="Verbatim or paraphrased fragment from the source")


class WeightedSignal(BaseModel):
    """
    Base unit for every inferred value in the processed and output layers.
    Attach this to skills, traits, themes, motivators — anything inferred.
    """
    value: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    weight: float = Field(
        ..., ge=0.0, le=2.0,
        description="Importance multiplier. Achievements = 1.5, Zone of Genius = 1.8, CV bullets = 1.0",
    )
    source: InputSource
    traces: List[SignalTrace] = Field(
        default_factory=list,
        description="All input fragments that contributed to this signal",
    )


# ---------------------------------------------------------------------------
# Layer 2 — Processed (structured inference outputs)
# ---------------------------------------------------------------------------

class ExtractedRole(BaseModel):
    title: str
    organisation: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    sector: Optional[str] = None
    seniority: Optional[str] = None
    duration_months: Optional[int] = None


class ClassifiedAchievement(BaseModel):
    raw_text: str
    category: AchievementCategory
    impact_summary: Optional[str] = None
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    weight: float = Field(
        default=1.5,
        description="Top-3 achievements carry 1.5× base weight by default",
    )
    source: InputSource = "achievement"
    traces: List[SignalTrace] = Field(default_factory=list)


class ProcessedProfile(BaseModel):
    roles: List[ExtractedRole] = Field(default_factory=list)
    skills_inferred: List[WeightedSignal] = Field(default_factory=list)
    achievements_classified: List[ClassifiedAchievement] = Field(default_factory=list)
    personality_traits: List[WeightedSignal] = Field(default_factory=list)
    motivators: List[WeightedSignal] = Field(default_factory=list)
    stress_behaviours: List[WeightedSignal] = Field(default_factory=list)
    avoidance_patterns: List[WeightedSignal] = Field(default_factory=list)
    transferable_skills: List[WeightedSignal] = Field(default_factory=list)
    career_themes: List[WeightedSignal] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Layer 3 — Output (Career DNA Profile)
# ---------------------------------------------------------------------------

class StrandScore(BaseModel):
    """Aggregate quality score for a single DNA strand."""
    score: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(..., description="One-sentence justification for the score")
    signal_count: int = Field(..., description="Number of weighted signals that contributed")


class FunctionalDNA(BaseModel):
    core_skills: List[WeightedSignal]
    domain_expertise: List[WeightedSignal]
    leadership_style: Optional[WeightedSignal] = None
    notable_achievements: List[ClassifiedAchievement] = Field(default_factory=list)
    tools_and_technologies: List[str] = Field(default_factory=list)
    career_trajectory: Optional[str] = None
    strength_score: StrandScore


class AdaptiveDNA(BaseModel):
    personality_traits: List[WeightedSignal]
    motivators: List[WeightedSignal]
    stress_behaviours: List[WeightedSignal]
    avoidance_patterns: List[WeightedSignal]
    conflict_style: Optional[WeightedSignal] = None
    # Zone of Genius is preserved verbatim and injected at weight=1.8
    zone_of_genius: Optional[WeightedSignal] = None
    alignment_score: StrandScore


class AspirationalDNA(BaseModel):
    industry_interests: List[WeightedSignal]
    lifestyle_requirements: List[WeightedSignal]
    salary_floor: float
    upskilling_willingness: bool
    career_goals: List[WeightedSignal] = Field(default_factory=list)
    clarity_score: StrandScore


class KeyTension(BaseModel):
    label: str
    strand_a: str = Field(..., description="First strand in tension (e.g. Functional)")
    strand_b: str = Field(..., description="Second strand in tension (e.g. Aspirational)")
    severity_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str = Field(..., description="What the tension is and why it exists")
    implication: str = Field(..., description="What this means for career decisions")
    traces: List[SignalTrace] = Field(
        default_factory=list,
        description="Input signals that produced this tension",
    )


class RiskFlagDetail(BaseModel):
    flag: RiskFlag
    severity_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    traces: List[SignalTrace] = Field(default_factory=list)


class PivotDirection(BaseModel):
    title: str
    rationale: str
    transferable_skills_used: List[WeightedSignal] = Field(default_factory=list)
    gap_areas: List[str] = Field(default_factory=list)
    fit_score: float = Field(..., ge=0.0, le=1.0)
    risk_score: float = Field(..., ge=0.0, le=1.0)
    required_upskilling_level: UpskillingLevel
    traces: List[SignalTrace] = Field(default_factory=list)


class CareerDNAProfile(BaseModel):
    functional: FunctionalDNA
    adaptive: AdaptiveDNA
    aspirational: AspirationalDNA
    key_tensions: List[KeyTension] = Field(default_factory=list)
    pivot_directions: List[PivotDirection] = Field(default_factory=list)
    risk_flags: List[RiskFlagDetail] = Field(default_factory=list)

    # Aggregate scores — surfaced at profile level for dashboards / ranking
    functional_strength_score: float = Field(..., ge=0.0, le=1.0)
    adaptive_alignment_score: float = Field(..., ge=0.0, le=1.0)
    aspirational_clarity_score: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Layer 4 — Pivot Delta (target role transition analysis)
# ---------------------------------------------------------------------------

class TargetRoleProfile(BaseModel):
    role_name: str
    sector: Optional[str] = None
    seniority: Optional[str] = None
    core_skills: List[str] = Field(default_factory=list)
    credibility_markers: List[str] = Field(default_factory=list)
    leadership_signals: List[str] = Field(default_factory=list)
    commercial_signals: List[str] = Field(default_factory=list)
    language_markers: List[str] = Field(default_factory=list)
    common_objections: List[str] = Field(default_factory=list)


class PivotGap(BaseModel):
    gap_type: str
    label: str
    severity: float = Field(..., ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    implication: str
    recommended_action: str


class PivotDeltaReport(BaseModel):
    target_role: str
    overall_fit_score: float = Field(..., ge=0.0, le=1.0)
    strongest_matches: List[str] = Field(default_factory=list)
    priority_gaps: List[PivotGap] = Field(default_factory=list)
    narrative_repositioning: List[str] = Field(default_factory=list)
    ninety_day_actions: List[str] = Field(default_factory=list)
