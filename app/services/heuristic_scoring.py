from __future__ import annotations

from typing import Any, List, Optional

from app.schemas import (
    CareerDNAProfile, ExtractedRole, HeuristicScore, HeuristicScoreSet,
    PivotDeltaReport,
)
from app.services.trajectory_engine import CareerTrajectory


def _confidence(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Individual score builders
# ---------------------------------------------------------------------------

def _score_career_coherence(
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
    trajectory: Optional[CareerTrajectory],
) -> HeuristicScore:
    evidence: list[str] = []
    score = 50

    # Trajectory confidence adds coherence
    if trajectory:
        traj_boost = int(trajectory.confidence_score * 25)
        score += traj_boost
        evidence.append(f"Trajectory type: {trajectory.trajectory_type.replace('_', ' ')} ({int(trajectory.confidence_score * 100)}% confidence)")

    # Functional strength adds coherence
    fs = profile.functional_strength_score
    if fs >= 0.70:
        score += 15
        evidence.append("High functional signal density")
    elif fs >= 0.50:
        score += 7

    # Tension count reduces coherence
    n_tensions = len(profile.key_tensions)
    if n_tensions >= 3:
        score -= 15
        evidence.append(f"{n_tensions} cross-strand tensions identified")
    elif n_tensions >= 1:
        score -= 5

    score = max(10, min(100, score))
    explanation = (
        "Career history follows a coherent, legible pattern."
        if score >= 65 else
        "Career history has readable threads but lacks consistent narrative across all roles."
        if score >= 45 else
        "Career history is fragmented or unclear — narrative work required before approaching the market."
    )
    return HeuristicScore(
        score=score,
        confidence_level=_confidence(score),
        explanation=explanation,
        supporting_evidence=evidence,
    )


def _score_transferability(
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
) -> HeuristicScore:
    evidence: list[str] = []
    score = 40

    unique_sectors = len({r.sector or r.inferred_industry for r in roles if r.sector or r.inferred_industry})
    unique_functions = len({r.inferred_function for r in roles if r.inferred_function})

    if unique_sectors >= 3:
        score += 20
        evidence.append(f"Experience across {unique_sectors} sectors broadens market access")
    elif unique_sectors >= 2:
        score += 10
        evidence.append(f"Experience across {unique_sectors} sectors")

    if unique_functions >= 3:
        score += 15
        evidence.append(f"{unique_functions} distinct functions signal cross-functional range")
    elif unique_functions >= 2:
        score += 8

    transferable_count = len(profile.functional.core_skills)
    if transferable_count >= 8:
        score += 15
        evidence.append(f"{transferable_count} transferable skills identified")
    elif transferable_count >= 4:
        score += 8

    if profile.aspirational.upskilling_willingness:
        score += 5
        evidence.append("Upskilling willingness increases adaptability")

    n_skill_cats = len({cat for r in roles for cat in r.inferred_skills_by_category})
    if n_skill_cats >= 6:
        score += 12
        evidence.append(f"Skills evidenced across {n_skill_cats} distinct categories")
    elif n_skill_cats >= 4:
        score += 6
        evidence.append(f"Skills evidenced across {n_skill_cats} categories")

    score = max(10, min(100, score))
    explanation = (
        "Strong cross-context transferability — skills and experience travel well."
        if score >= 65 else
        "Moderate transferability — specific framing work required to bridge contexts."
        if score >= 45 else
        "Limited transferability signal — deep specialisation or narrow sector exposure detected."
    )
    return HeuristicScore(
        score=score,
        confidence_level=_confidence(score),
        explanation=explanation,
        supporting_evidence=evidence,
    )


def _score_market_alignment(
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
    pivot_delta: Optional[PivotDeltaReport],
    market_context_notes: Optional[str],
) -> HeuristicScore:
    evidence: list[str] = []
    score = 50

    if pivot_delta:
        fit_boost = int(pivot_delta.overall_fit_score * 35)
        score = 35 + fit_boost
        evidence.append(f"Target role fit score: {int(pivot_delta.overall_fit_score * 100)}%")
    else:
        evidence.append("No target role specified — market alignment assessed against general profile strength")

    if market_context_notes:
        score = min(score + 10, 100)
        evidence.append("External market context provided — alignment assessment is more grounded")
    else:
        evidence.append("No market context provided — alignment is estimated from profile signals only")

    # Industry curiosity alignment
    if profile.aspirational.industry_interests:
        score = min(score + 5, 100)
        evidence.append(f"{len(profile.aspirational.industry_interests)} industry interests declared")

    score = max(10, min(100, score))
    explanation = (
        "Profile is well-aligned with current market signals for the target context."
        if score >= 65 else
        "Partial market alignment — some repositioning or targeting work required."
        if score >= 45 else
        "Low market alignment signal. Provide a target role and market context for a sharper read."
    )
    return HeuristicScore(
        score=score,
        confidence_level="high" if (pivot_delta and market_context_notes) else "medium" if pivot_delta else "low",
        explanation=explanation,
        supporting_evidence=evidence,
    )


def _score_promotion_readiness(
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
    pivot_delta: Optional[PivotDeltaReport],
    trajectory: Optional[CareerTrajectory],
) -> HeuristicScore:
    evidence: list[str] = []
    score = 45

    if pivot_delta:
        fit = pivot_delta.overall_fit_score
        # Recalibrated anchor: fit=0.76 → ~38 base, leaving room for differentiation via bonuses
        score = int(fit * 50) + 25
        n_gaps = len(pivot_delta.priority_gaps)
        if n_gaps == 0:
            score = min(score + 15, 100)
            evidence.append("No material gaps to the target role")
        else:
            penalty = min(n_gaps * 8, 25)
            score = max(score - penalty, 10)
            evidence.append(f"{n_gaps} priority gap(s) identified relative to target role")

    _READINESS_TRAJECTORIES = {
        "operator_to_strategist", "corporate_climber", "linear_specialist", "strategic_generalist",
    }
    if trajectory and trajectory.trajectory_type in _READINESS_TRAJECTORIES:
        score = min(score + 8, 100)
        traj_label = trajectory.trajectory_type.replace("_", " ")
        evidence.append(f"Trajectory ({traj_label}) aligns with target-role expectations")

    n_achievements = len(profile.functional.notable_achievements)
    if n_achievements >= 3:
        score = min(score + 10, 100)
        evidence.append(f"{n_achievements} notable achievements provide proof-point depth")
    elif n_achievements >= 1:
        score = min(score + 5, 100)
        evidence.append("Achievement proof points present")

    all_cats = {cat for r in roles for cat in r.inferred_skills_by_category}
    key_cats = {"leadership_skills", "stakeholder_skills", "strategic_skills", "commercial_skills"}
    cat_coverage = len(key_cats & all_cats)
    if cat_coverage >= 4:
        score = min(score + 10, 100)
        evidence.append("Leadership, stakeholder, strategic and commercial skills all evidenced")
    elif cat_coverage >= 2:
        score = min(score + 5, 100)
        evidence.append(f"{cat_coverage}/4 key skill categories evidenced")

    score = max(10, min(100, score))
    if pivot_delta:
        explanation = (
            "Very strong readiness — target-role vocabulary, transferable skills, trajectory, "
            "and achievement signals align well. Limited gaps stand between this profile and a "
            "credible approach to market."
            if score >= 85 else
            "Strong foundation — vocabulary overlap, trajectory, and skills are well-matched. "
            "Meaningful gaps remain; addressing the priority items will make this profile compelling."
            if score >= 70 else
            "Partial readiness — some key signals are present but several gaps need closing. "
            "Vocabulary, credibility, or achievement signals do not yet fully align with target-role "
            "expectations."
            if score >= 55 else
            "Early-stage readiness — significant repositioning work required across vocabulary, "
            "skills, or experience signals before a credible transition is achievable."
        )
    else:
        explanation = (
            "Strong advancement signals — trajectory, achievements, and skill breadth support a "
            "credible move to the next level."
            if score >= 65 else
            "Advancement readiness is partial — specific gaps need closing before the move is compelling."
            if score >= 45 else
            "Significant development work required before a promotion or transition is credible."
        )
    return HeuristicScore(
        score=score,
        confidence_level=_confidence(score),
        explanation=explanation,
        supporting_evidence=evidence,
    )


def _score_narrative_strength(
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
) -> HeuristicScore:
    evidence: list[str] = []
    score = 40

    # Zone of genius present
    if profile.adaptive.zone_of_genius:
        score += 15
        evidence.append("Zone of genius clearly articulated")

    # Career themes detected
    n_themes = len(profile.functional.core_skills)
    if n_themes >= 6:
        score += 15
        evidence.append(f"{n_themes} core skill signals available as narrative anchors")
    elif n_themes >= 3:
        score += 8

    # Achievements provide proof points
    n_ach = len(profile.functional.notable_achievements)
    if n_ach >= 3:
        score += 15
        evidence.append(f"{n_ach} achievement proof points to anchor narrative")
    elif n_ach >= 1:
        score += 7

    # Evidence snippets from roles add narrative texture
    snippets = sum(len(r.evidence_snippets) for r in roles)
    if snippets >= 5:
        score += 10
        evidence.append(f"{snippets} evidence snippets available from CV")
    elif snippets >= 2:
        score += 5

    score = max(10, min(100, score))
    explanation = (
        "Strong narrative foundation — coherent story with clear proof points and a differentiated angle."
        if score >= 65 else
        "Narrative has the right building blocks but needs sharper framing and crisper proof points."
        if score >= 45 else
        "Narrative is thin — more evidence snippets, achievements, and a clearer zone of genius are needed."
    )
    return HeuristicScore(
        score=score,
        confidence_level=_confidence(score),
        explanation=explanation,
        supporting_evidence=evidence,
    )


def _score_strategic_optionality(
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
    pivot_delta: Optional[PivotDeltaReport],
    trajectory: Optional[CareerTrajectory],
) -> HeuristicScore:
    evidence: list[str] = []
    score = 40

    n_pivots = len(profile.pivot_directions)
    if n_pivots >= 3:
        score += 20
        evidence.append(f"{n_pivots} viable pivot directions identified")
    elif n_pivots >= 1:
        score += 10

    unique_sectors = len({r.sector or r.inferred_industry for r in roles if r.sector or r.inferred_industry})
    if unique_sectors >= 3:
        score += 15
        evidence.append(f"Cross-sector exposure creates {unique_sectors} potential market entry points")
    elif unique_sectors >= 2:
        score += 7

    if trajectory and trajectory.trajectory_type == "strategic_generalist":
        score += 12
        evidence.append("Strategic generalist profile maximises optionality")

    if profile.aspirational.upskilling_willingness:
        score += 8
        evidence.append("Upskilling willingness expands option space over time")

    if pivot_delta and pivot_delta.overall_fit_score >= 0.60:
        score += 5
        evidence.append("Strong fit with stated target role validates primary option")

    n_skill_cats = len({cat for r in roles for cat in r.inferred_skills_by_category})
    if n_skill_cats >= 7:
        score += 10
        evidence.append(f"Skill breadth across {n_skill_cats} categories maximises option space")
    elif n_skill_cats >= 5:
        score += 5
        evidence.append(f"Skills evidenced across {n_skill_cats} categories")

    score = max(10, min(100, score))
    explanation = (
        "High strategic optionality — multiple credible pathways available from this profile."
        if score >= 65 else
        "Moderate optionality — a primary path is clear but alternatives require deliberate effort to open."
        if score >= 45 else
        "Limited optionality — profile depth is in a narrow band. Expanding cross-sector exposure is advisable."
    )
    return HeuristicScore(
        score=score,
        confidence_level=_confidence(score),
        explanation=explanation,
        supporting_evidence=evidence,
    )


def _score_execution_gap(
    profile: CareerDNAProfile,
    pivot_delta: Optional[PivotDeltaReport],
) -> HeuristicScore:
    """
    Measures the gap between stated goals/ambitions and demonstrated execution track record.
    High score = large gap (negative). Low score = ambition well-matched by evidence.
    """
    evidence: list[str] = []
    score = 30  # Start with a low gap (good)

    if pivot_delta:
        gap_severity = sum(g.severity for g in pivot_delta.priority_gaps) / max(len(pivot_delta.priority_gaps), 1)
        score = int(gap_severity * 80)
        n_gaps = len(pivot_delta.priority_gaps)
        if n_gaps >= 3:
            evidence.append(f"{n_gaps} priority gaps relative to stated goal — execution distance is material")
        elif n_gaps >= 1:
            evidence.append(f"{n_gaps} targeted gap(s) to close before stated goal is credible")
        else:
            evidence.append("No material gaps identified relative to stated goal")
    else:
        if profile.functional_strength_score >= 0.70:
            score = 20
            evidence.append("Strong functional execution track record relative to declared ambitions")
        elif profile.functional_strength_score >= 0.50:
            score = 40
            evidence.append("Moderate execution record — some ambition/evidence gap present")
        else:
            score = 60
            evidence.append("Execution signals are below the threshold needed to validate stated ambitions")

    score = max(5, min(95, score))
    explanation = (
        "Significant gap between stated goals and current execution evidence — bridging work required."
        if score >= 65 else
        "Moderate gap — the ambition is credible but specific proof points are missing."
        if score >= 35 else
        "Execution record is well-matched to stated ambitions. Gap is minimal."
    )
    return HeuristicScore(
        score=score,
        confidence_level=_confidence(100 - score),
        explanation=explanation,
        supporting_evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Compound pathway readiness scorer
# ---------------------------------------------------------------------------

def _score_compound_readiness(compound_pathways: List[Any]) -> HeuristicScore:
    """
    Compute an overall Executive Pathway Readiness score from per-pathway results.

    Formula: 70% best-pathway readiness + 30% average of top-two readiness scores.
    This prevents a single strong pathway from fully inflating the score while
    still rewarding having at least one credible option.

    Banding (deliberate — see requirements):
      85+  : very strong across stated pathways
      70–84: strong for at least one, manageable gaps elsewhere
      55–69: credible pathway exists, meaningful gaps remain
      40–54: partial readiness, significant repositioning needed
      <40  : early-stage readiness for stated pathways
    """
    # Sort by readiness_score — accounts for gaps, not just vocabulary overlap.
    # "Strong readiness for at least one pathway (X)" should name the pathway
    # the candidate is most ready for, not just where vocabulary matches best.
    # Section 6 uses fit_score for "Best-fit pathway" (a different dimension),
    # so the two sections may name different pathways when the highest-fit path
    # also has a credibility or skill gap.
    by_readiness = sorted(compound_pathways, key=lambda p: p.readiness_score, reverse=True)
    best = by_readiness[0]
    best_score = best.readiness_score

    if len(by_readiness) >= 2:
        second_score = by_readiness[1].readiness_score
        avg_top_two = (best_score + second_score) / 2
    else:
        avg_top_two = best_score

    overall = max(10, min(100, round(0.7 * best_score + 0.3 * avg_top_two)))

    if overall >= 85:
        explanation = "Very strong readiness across stated executive pathways."
        confidence = "high"
    elif overall >= 70:
        explanation = (
            f"Strong readiness for at least one pathway ({best.pathway_name}), "
            "with manageable gaps across the others."
        )
        confidence = "high"
    elif overall >= 55:
        explanation = (
            f"Credible pathway exists ({best.pathway_name} at {int(best.fit_score * 100)}% fit), "
            "but meaningful positioning gaps remain across the full set of stated targets."
        )
        confidence = "medium"
    elif overall >= 40:
        explanation = (
            "Partial readiness across stated pathways. "
            "Significant repositioning work required before approaching more than one stated target."
        )
        confidence = "medium"
    else:
        explanation = (
            "Early-stage readiness for most stated pathways. "
            "Targeted development needed across vocabulary, skills, and credibility signals."
        )
        confidence = "low"

    evidence = [
        f"Best-fit pathway: {best.pathway_name} ({int(best.fit_score * 100)}% fit, readiness {best.readiness_score}/100)"
    ]
    for pw in by_readiness[1:3]:
        evidence.append(
            f"{pw.pathway_name}: {int(pw.fit_score * 100)}% fit, readiness {pw.readiness_score}/100"
        )

    return HeuristicScore(
        score=overall,
        confidence_level=confidence,
        explanation=explanation,
        supporting_evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_heuristic_scores(
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
    pivot_delta: Optional[PivotDeltaReport],
    trajectory: Optional[CareerTrajectory],
    market_context_notes: Optional[str] = None,
    compound_pathways: Optional[List[Any]] = None,
) -> HeuristicScoreSet:
    # Compound target: override promotion_readiness with pathway-blended score
    if compound_pathways and len(compound_pathways) > 1:
        promotion_readiness = _score_compound_readiness(compound_pathways)
    else:
        promotion_readiness = _score_promotion_readiness(profile, roles, pivot_delta, trajectory)

    return HeuristicScoreSet(
        career_coherence=_score_career_coherence(profile, roles, trajectory),
        transferability=_score_transferability(profile, roles),
        market_alignment=_score_market_alignment(profile, roles, pivot_delta, market_context_notes),
        promotion_readiness=promotion_readiness,
        narrative_strength=_score_narrative_strength(profile, roles),
        strategic_optionality=_score_strategic_optionality(profile, roles, pivot_delta, trajectory),
        execution_gap=_score_execution_gap(profile, pivot_delta),
    )
