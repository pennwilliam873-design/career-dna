from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas import CareerDNAProfile, KeyTension, PivotDirection, RiskFlagDetail
from app.services.pattern_detection import DetectedPattern, PatternType, PATTERN_ROUTING


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class InsightTier(str, Enum):
    headline   = "headline"
    primary    = "primary"
    supporting = "supporting"
    suppressed = "suppressed"


class RankedPattern(BaseModel):
    pattern: DetectedPattern
    importance_score: float
    tier: InsightTier
    cross_strand_count: int


class RankedTension(BaseModel):
    tension: KeyTension
    importance_score: float
    tier: InsightTier
    is_actionable: bool


class RankedPivot(BaseModel):
    pivot: PivotDirection
    importance_score: float
    tier: InsightTier
    net_score: float


class SectionOrder(BaseModel):
    section: str
    position: int
    headline_insight: Optional[str] = None
    supporting_insights: List[str] = Field(default_factory=list)


class ExecutiveSummaryPlan(BaseModel):
    sentence_1_pattern:  Optional[RankedPattern] = None
    sentence_2_tension:  Optional[RankedTension] = None
    sentence_3_pivot:    Optional[RankedPivot]   = None
    sentence_4_risk:     Optional[RiskFlagDetail] = None
    overall_tier:        InsightTier = InsightTier.primary


class PrioritisedInsightSet(BaseModel):
    ranked_patterns:   List[RankedPattern]
    ranked_tensions:   List[RankedTension]
    ranked_pivots:     List[RankedPivot]
    selected_themes:   List[RankedPattern]
    selected_tensions: List[RankedTension]
    selected_pivots:   List[RankedPivot]
    exec_summary_plan: ExecutiveSummaryPlan
    section_order:     List[SectionOrder]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_SUPPRESSION_THRESHOLD = 0.40

_CAREER_THEME_TYPES = {
    pt for pt, dest in PATTERN_ROUTING.items() if dest == "career_themes"
}

_SECTION_NAMES = [
    "executive_summary",
    "career_themes",
    "functional_dna",
    "adaptive_dna",
    "tensions",
    "pivot_paths",
    "risk_flags",
]


def _pattern_tier(score: float) -> InsightTier:
    if score >= 0.80:
        return InsightTier.headline
    if score >= 0.60:
        return InsightTier.primary
    if score >= _SUPPRESSION_THRESHOLD:
        return InsightTier.supporting
    return InsightTier.suppressed


def _rank_pattern(p: DetectedPattern) -> RankedPattern:
    importance = round(p.confidence_score * p.weight, 4)
    return RankedPattern(
        pattern=p,
        importance_score=importance,
        tier=_pattern_tier(importance),
        cross_strand_count=1,
    )


def _rank_tension(t: KeyTension) -> RankedTension:
    importance = round(t.severity_score, 4)
    tier = _pattern_tier(importance)
    return RankedTension(
        tension=t,
        importance_score=importance,
        tier=tier,
        is_actionable=importance >= 0.50 and bool(t.implication),
    )


def _rank_pivot(p: PivotDirection) -> RankedPivot:
    net = round((p.fit_score or 0.0) - (p.risk_score or 0.0), 4)
    importance = round(max(net, 0.0), 4)
    return RankedPivot(
        pivot=p,
        importance_score=importance,
        tier=_pattern_tier(importance),
        net_score=net,
    )


def build_prioritised_set(
    profile: CareerDNAProfile,
    patterns: List[DetectedPattern],
) -> PrioritisedInsightSet:
    # --- Rank patterns ---
    ranked_patterns = sorted(
        [_rank_pattern(p) for p in patterns],
        key=lambda r: r.importance_score,
        reverse=True,
    )

    # --- Rank tensions ---
    ranked_tensions = sorted(
        [_rank_tension(t) for t in (profile.key_tensions or [])],
        key=lambda r: r.importance_score,
        reverse=True,
    )

    # --- Rank pivots ---
    ranked_pivots = sorted(
        [_rank_pivot(p) for p in (profile.pivot_directions or [])],
        key=lambda r: r.importance_score,
        reverse=True,
    )

    # --- Select top items (suppress below threshold) ---
    active_patterns  = [r for r in ranked_patterns  if r.tier != InsightTier.suppressed]
    active_tensions  = [r for r in ranked_tensions  if r.tier != InsightTier.suppressed]
    active_pivots    = [r for r in ranked_pivots    if r.tier != InsightTier.suppressed]

    selected_themes   = [r for r in active_patterns if r.pattern.pattern_type in _CAREER_THEME_TYPES][:4]
    selected_tensions = active_tensions[:3]
    selected_pivots   = active_pivots[:3]

    # --- Executive summary plan ---
    top_pattern = active_patterns[0]  if active_patterns  else None
    top_tension = active_tensions[0]  if active_tensions  else None
    top_pivot   = active_pivots[0]    if active_pivots    else None
    top_risk    = (profile.risk_flags or [None])[0] if profile.risk_flags else None

    overall_tier = (
        InsightTier.headline  if top_pattern and top_pattern.tier == InsightTier.headline else
        InsightTier.primary   if top_pattern else
        InsightTier.supporting
    )

    exec_plan = ExecutiveSummaryPlan(
        sentence_1_pattern=top_pattern,
        sentence_2_tension=top_tension,
        sentence_3_pivot=top_pivot,
        sentence_4_risk=top_risk,
        overall_tier=overall_tier,
    )

    # --- Section order ---
    section_order = [
        SectionOrder(
            section=name,
            position=idx + 1,
            headline_insight=(
                active_patterns[0].pattern.label if idx == 0 and active_patterns else None
            ),
            supporting_insights=(
                [r.pattern.label for r in active_patterns[:3]] if idx == 0 else []
            ),
        )
        for idx, name in enumerate(_SECTION_NAMES)
    ]

    return PrioritisedInsightSet(
        ranked_patterns=ranked_patterns,
        ranked_tensions=ranked_tensions,
        ranked_pivots=ranked_pivots,
        selected_themes=selected_themes,
        selected_tensions=selected_tensions,
        selected_pivots=selected_pivots,
        exec_summary_plan=exec_plan,
        section_order=section_order,
    )
