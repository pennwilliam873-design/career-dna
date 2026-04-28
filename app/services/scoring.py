from __future__ import annotations

from typing import List, Tuple

from app.schemas import (
    AdaptiveDNA, AspirationalDNA, CareerDNAProfile, ClassifiedAchievement,
    ExtractedRole, FunctionalDNA, KeyTension, PivotDirection, ProcessedProfile,
    RawInput, RiskFlagDetail, SignalTrace, StrandScore, UpskillingLevel,
    WeightedSignal,
)

# ---------------------------------------------------------------------------
# Placeholder score — used until scoring logic is implemented
# ---------------------------------------------------------------------------

_PLACEHOLDER_SCORE = StrandScore(score=0.5, rationale="Pending full scoring implementation.", signal_count=0)


# ---------------------------------------------------------------------------
# DNA strand construction
# ---------------------------------------------------------------------------

def build_functional_dna(processed: ProcessedProfile, raw: RawInput) -> FunctionalDNA:
    top_skills = _top_n(processed.skills_inferred, 10)
    domain     = _derive_domain_expertise(processed.roles)
    leadership = _extract_leadership_signal(processed.achievements_classified)
    tools      = [t.strip() for t in raw.tools if t.strip()]

    return FunctionalDNA(
        core_skills=top_skills,
        domain_expertise=domain,
        leadership_style=leadership,
        notable_achievements=processed.achievements_classified,
        tools_and_technologies=tools,
        career_trajectory=None,                         # filled by pattern engine
        strength_score=_score_functional(processed),
    )


def build_adaptive_dna(processed: ProcessedProfile, raw: RawInput) -> AdaptiveDNA:
    zog_signal = _build_zog_signal(raw.zone_of_genius)
    conflict   = _top_n(processed.stress_behaviours, 1)

    return AdaptiveDNA(
        personality_traits=processed.personality_traits,
        motivators=processed.motivators,
        stress_behaviours=processed.stress_behaviours,
        avoidance_patterns=processed.avoidance_patterns,
        conflict_style=conflict[0] if conflict else None,
        zone_of_genius=zog_signal,
        alignment_score=_score_adaptive(processed),
    )


def build_aspirational_dna(processed: ProcessedProfile, raw: RawInput) -> AspirationalDNA:
    from app.services.signal_generator import SOURCE_WEIGHT, _build_list_signals, SignalTrace

    industry_sigs  = _build_list_signals(raw.industry_curiosity,  "industry_curiosity",   0.80, 1.0)
    lifestyle_sigs = _build_list_signals(raw.lifestyle_preferences,"lifestyle_preferences", 0.75, 1.0)

    return AspirationalDNA(
        industry_interests=industry_sigs,
        lifestyle_requirements=lifestyle_sigs,
        salary_floor=raw.salary_floor,
        upskilling_willingness=raw.upskilling_willingness,
        career_goals=[],
        clarity_score=_score_aspirational(raw),
    )


# ---------------------------------------------------------------------------
# Pivot candidate construction
# ---------------------------------------------------------------------------

def build_pivot_candidates(raw: RawInput) -> List[PivotDirection]:
    """
    Create a base PivotDirection per industry curiosity item.
    Scores are stubs — scoring engine fills them.
    """
    return [
        PivotDirection(
            title=industry,
            rationale="",
            transferable_skills_used=[],
            gap_areas=[],
            fit_score=0.0,
            risk_score=0.0,
            required_upskilling_level=UpskillingLevel.medium,
            traces=[SignalTrace(source="industry_curiosity", excerpt=industry)],
        )
        for industry in raw.industry_curiosity
        if industry.strip()
    ]


# ---------------------------------------------------------------------------
# Scoring stubs — to be implemented per scoring_engine.py design
# ---------------------------------------------------------------------------

def _score_functional(processed: ProcessedProfile) -> StrandScore:
    ach_as_signals = [
        WeightedSignal(
            value=a.raw_text[:80],
            confidence_score=a.confidence_score,
            weight=a.weight,
            source=a.source,
            traces=a.traces,
        )
        for a in processed.achievements_classified
    ]
    signals = processed.skills_inferred + processed.transferable_skills + ach_as_signals
    if not signals:
        return StrandScore(score=0.3, rationale="No functional signals found.", signal_count=0)
    score = sum(s.confidence_score * s.weight for s in signals) / sum(s.weight for s in signals)
    return StrandScore(
        score=round(min(score, 1.0), 3),
        rationale=f"Weighted blend of {len(signals)} functional signals: skills, achievements, and transferable capabilities.",
        signal_count=len(signals),
    )


def _score_adaptive(processed: ProcessedProfile) -> StrandScore:
    signals = (
        processed.personality_traits
        + processed.motivators
        + processed.stress_behaviours
        + processed.avoidance_patterns
    )
    if not signals:
        return StrandScore(score=0.3, rationale="No adaptive signals found.", signal_count=0)
    score = sum(s.confidence_score * s.weight for s in signals) / sum(s.weight for s in signals)
    return StrandScore(
        score=round(min(score, 1.0), 3),
        rationale=f"Weighted blend of {len(signals)} adaptive signals: traits, motivators, stress behaviours, and avoidance patterns.",
        signal_count=len(signals),
    )


def _score_aspirational(raw: RawInput) -> StrandScore:
    industry_score   = min(len(raw.industry_curiosity) / 3, 1.0) * 0.35
    lifestyle_score  = min(len(raw.lifestyle_preferences) / 3, 1.0) * 0.30
    salary_score     = 0.20 if raw.salary_floor > 0 else 0.0
    upskill_score    = 0.15 if raw.upskilling_willingness else 0.05
    score = industry_score + lifestyle_score + salary_score + upskill_score
    signal_count = (
        len(raw.industry_curiosity)
        + len(raw.lifestyle_preferences)
        + (1 if raw.salary_floor > 0 else 0)
    )
    return StrandScore(
        score=round(min(score, 1.0), 3),
        rationale="Clarity blend of industry interests, lifestyle preferences, salary floor, and upskilling willingness.",
        signal_count=signal_count,
    )


def detect_tensions(
    functional: FunctionalDNA,
    adaptive: AdaptiveDNA,
    aspirational: AspirationalDNA,
) -> List[KeyTension]:
    tensions: List[KeyTension] = []

    # Strong capability but unclear direction
    if (
        functional.strength_score.score > 0.7
        and aspirational.clarity_score.score < 0.4
    ):
        tensions.append(KeyTension(
            label="Expertise without direction",
            strand_a="Functional",
            strand_b="Aspirational",
            severity_score=0.65,
            explanation="Strong functional capabilities exist but career direction lacks clarity.",
            implication="Risk of defaulting to familiar roles rather than making intentional career moves.",
        ))

    # High stress / avoidance load against low alignment
    if (
        adaptive.alignment_score.score < 0.45
        and len(adaptive.stress_behaviours) + len(adaptive.avoidance_patterns) >= 2
    ):
        tensions.append(KeyTension(
            label="Misaligned work-style demands",
            strand_a="Adaptive",
            strand_b="Functional",
            severity_score=0.55,
            explanation="Stress behaviours and avoidance patterns suggest friction with current domain demands.",
            implication="Sustained performance may be at risk; prioritise roles that reduce known stress triggers.",
        ))

    # No pivot targets despite aspirational signal
    if aspirational.clarity_score.score > 0.5 and not aspirational.industry_interests:
        tensions.append(KeyTension(
            label="Aspiration without target",
            strand_a="Aspirational",
            strand_b="Functional",
            severity_score=0.40,
            explanation="Aspirational strand shows engagement but industry interests are unspecified.",
            implication="Without concrete targets, pivot planning cannot be grounded in transferable skills.",
        ))

    return tensions


def score_pivots(
    pivots: List[PivotDirection],
    functional: FunctionalDNA,
    adaptive: AdaptiveDNA,
    aspirational: AspirationalDNA,
) -> List[PivotDirection]:
    if not pivots:
        return pivots

    skill_values = {s.value.lower() for s in functional.core_skills}
    base_fit = functional.strength_score.score
    upskill_bonus = 0.10 if aspirational.upskilling_willingness else 0.0
    n_pivots = len(pivots)

    scored: List[PivotDirection] = []
    for i, pivot in enumerate(pivots):
        # Fit: blend of functional strength + modest decay for later pivots
        rank_penalty = (i / n_pivots) * 0.15
        fit = round(max(base_fit - rank_penalty + upskill_bonus, 0.0), 3)

        # Risk: inverse of fit, tempered by adaptive alignment
        risk = round(min(1.0 - fit * adaptive.alignment_score.score, 1.0), 3)

        # Surface any transferable skills as a courtesy
        transferable = [s for s in functional.core_skills if s.value.lower() in skill_values][:3]

        scored.append(pivot.model_copy(update={
            "fit_score": fit,
            "risk_score": risk,
            "transferable_skills_used": transferable,
        }))

    return scored


# ---------------------------------------------------------------------------
# Public orchestration entry point
# ---------------------------------------------------------------------------

def run_scoring_engine(
    processed: ProcessedProfile,
    raw: RawInput,
) -> Tuple[FunctionalDNA, AdaptiveDNA, AspirationalDNA, List[KeyTension], List[PivotDirection]]:
    """
    Build DNA strands, score them, detect tensions, and score pivots.
    Scoring sub-functions raise NotImplementedError until implemented.
    """
    functional  = build_functional_dna(processed, raw)
    adaptive    = build_adaptive_dna(processed, raw)
    aspirational = build_aspirational_dna(processed, raw)
    pivots      = build_pivot_candidates(raw)
    tensions    = detect_tensions(functional, adaptive, aspirational)
    scored_pivots = score_pivots(pivots, functional, adaptive, aspirational)

    return functional, adaptive, aspirational, tensions, scored_pivots


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _top_n(signals: List[WeightedSignal], n: int) -> List[WeightedSignal]:
    return sorted(signals, key=lambda s: s.confidence_score * s.weight, reverse=True)[:n]


def _derive_domain_expertise(roles: List[ExtractedRole]) -> List[WeightedSignal]:
    seen: dict[str, int] = {}
    for role in roles:
        if role.sector:
            seen[role.sector] = seen.get(role.sector, 0) + 1

    signals = []
    for sector, count in seen.items():
        signals.append(
            WeightedSignal(
                value=sector,
                confidence_score=min(0.5 + 0.1 * count, 1.0),
                weight=1.0,
                source="cv",
                traces=[SignalTrace(source="cv", excerpt=f"Sector: {sector} ({count} roles)")],
            )
        )
    return sorted(signals, key=lambda s: s.confidence_score, reverse=True)


def _extract_leadership_signal(
    achievements: List[ClassifiedAchievement],
) -> WeightedSignal | None:
    from app.schemas import AchievementCategory
    leaders = [a for a in achievements if a.category == AchievementCategory.leadership]
    if not leaders:
        return None
    best = max(leaders, key=lambda a: a.confidence_score * a.weight)
    return WeightedSignal(
        value=best.impact_summary or best.raw_text[:80],
        confidence_score=best.confidence_score,
        weight=best.weight,
        source="achievement",
        traces=best.traces,
    )


def _build_zog_signal(zone_of_genius: str) -> WeightedSignal | None:
    if not zone_of_genius.strip():
        return None
    return WeightedSignal(
        value=zone_of_genius.strip()[:200],
        confidence_score=0.85,
        weight=1.8,
        source="zone_of_genius",
        traces=[SignalTrace(source="zone_of_genius", excerpt=zone_of_genius[:120])],
    )


def _build_list_signals(items, source, confidence, weight):
    from app.services.signal_generator import _build_list_signals as _impl
    return _impl(items, source, confidence, weight)
