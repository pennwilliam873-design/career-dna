from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.schemas import (
    AdaptiveDNA, AspirationalDNA, CareerDNAProfile,
    ExtractedRole, FunctionalDNA, KeyTension, PathwayReadiness, PivotDirection,
    ProcessedProfile, RawInput, RiskFlagDetail, WeightedSignal,
)
from app.services.cv_parser import parse_cv
from app.services.signal_generator import (
    MIN_HIGH_CONFIDENCE_SIGNALS,
    generate_weighted_signals,
    process_raw_inputs,
)
from app.services.scoring import run_scoring_engine
from app.services.pattern_detection import (
    DetectedPattern, PATTERN_ROUTING, run_pattern_pipeline,
)
from app.services.prioritisation import PrioritisedInsightSet, build_prioritised_set
from app.services.narrative import NarrativeReport, assemble_report
from app.services.target_profiles import build_target_profile, parse_compound_target
from app.services.delta_engine import compute_pivot_delta
from app.services.narrative_engine import PivotNarrative, build_pivot_narrative
from app.services.stakeholder_simulator import StakeholderFeedback, simulate_stakeholder_feedback
from app.services.decision_engine import DecisionUpgradePlan, build_decision_upgrade_plan
from app.services.report_engine import (
    ExecutiveTransitionReport,
    assemble_executive_report,
    format_executive_report,
    format_career_dna_report,
)
from app.services.trajectory_engine import build_career_trajectory
from app.services.heuristic_scoring import build_heuristic_scores
from app.services.llm_judgment import build_llm_judgment
from app.schemas import CareerTrajectory, HeuristicScoreSet, LLMReportIntelligence, PathwayReadiness, TargetRoleProfile, PivotDeltaReport
LLMJudgment = LLMReportIntelligence  # keep local alias for any other references

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class PipelineError(Exception):
    def __init__(self, stage: str, message: str, recoverable: bool = False):
        self.stage = stage
        self.message = message
        self.recoverable = recoverable
        super().__init__(f"[{stage}] {message}")


class InputValidationError(PipelineError):
    def __init__(self, message: str):
        super().__init__("validate_input", message, recoverable=False)


class WeakSignalError(PipelineError):
    def __init__(self, message: str):
        super().__init__("generate_weighted_signals", message, recoverable=True)


class ScoringError(PipelineError):
    def __init__(self, message: str):
        super().__init__("run_scoring_engine", message, recoverable=False)


class NarrativeError(PipelineError):
    def __init__(self, message: str):
        super().__init__("run_narrative_engine", message, recoverable=True)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class SignalSummary(BaseModel):
    total_signals: int
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    suppressed_count: int
    weak_signal_warning: bool


class PipelineOutput(BaseModel):
    profile: CareerDNAProfile
    report: Optional[NarrativeReport] = None
    warnings: List[str] = Field(default_factory=list)
    signal_summary: SignalSummary
    target_profile: Optional[TargetRoleProfile] = None
    pivot_delta: Optional[PivotDeltaReport] = None
    pivot_narrative: Optional[PivotNarrative] = None
    stakeholder_feedback: Optional[StakeholderFeedback] = None
    decision_plan: Optional[DecisionUpgradePlan] = None
    executive_report: Optional[ExecutiveTransitionReport] = None
    formatted_report: Optional[str] = None
    # New: enriched intelligence outputs
    heuristic_scores: Optional[Any] = None      # HeuristicScoreSet
    career_trajectory: Optional[Any] = None     # CareerTrajectory
    enriched_roles: Optional[List[Any]] = None  # List[ExtractedRole] (richly parsed)
    compound_pathways: Optional[List[PathwayReadiness]] = None
    llm_judgment: Optional[LLMReportIntelligence] = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_CV_WORD_COUNT    = 80
WEAK_SIGNAL_RATIO    = 0.60   # warn if > 60% of signals are low-confidence


# ---------------------------------------------------------------------------
# Stage 1 — Input validation
# ---------------------------------------------------------------------------

def validate_input(raw: RawInput) -> None:
    word_count = len(raw.cv_text.split())
    if word_count < MIN_CV_WORD_COUNT:
        raise InputValidationError(
            f"CV is too short ({word_count} words). "
            f"Minimum required: {MIN_CV_WORD_COUNT} words."
        )
    # All other fields are now optional — emit warnings but do not block


# ---------------------------------------------------------------------------
# Stage 5 — Scoring engine wrapper
# ---------------------------------------------------------------------------

def run_scoring_engine_stage(
    processed: ProcessedProfile,
    raw: RawInput,
) -> Tuple[FunctionalDNA, AdaptiveDNA, AspirationalDNA, List[KeyTension], List[PivotDirection]]:
    try:
        return run_scoring_engine(processed, raw)
    except NotImplementedError:
        raise   # propagate — caller will handle per-function stubs
    except Exception as exc:
        raise ScoringError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Stage 6 — Assemble pre-pattern CareerDNAProfile
# ---------------------------------------------------------------------------

def assemble_career_dna_profile(
    functional: FunctionalDNA,
    adaptive: AdaptiveDNA,
    aspirational: AspirationalDNA,
    tensions: List[KeyTension],
    pivots: List[PivotDirection],
) -> CareerDNAProfile:
    return CareerDNAProfile(
        functional=functional,
        adaptive=adaptive,
        aspirational=aspirational,
        key_tensions=tensions,
        pivot_directions=pivots,
        risk_flags=[],
        functional_strength_score=functional.strength_score.score,
        adaptive_alignment_score=adaptive.alignment_score.score,
        aspirational_clarity_score=aspirational.clarity_score.score,
    )


# ---------------------------------------------------------------------------
# Stage 7 — Pattern engine wrapper
# ---------------------------------------------------------------------------

def run_pattern_engine_stage(
    processed: ProcessedProfile,
    raw: RawInput,
    adaptive: AdaptiveDNA,
    functional: FunctionalDNA,
) -> List[DetectedPattern]:
    patterns = run_pattern_pipeline(
        processed=processed,
        zone_of_genius=adaptive.zone_of_genius,
        never_again_text=raw.never_again,
        conflict_marker_text=raw.conflict_marker,
    )

    # Inject career themes back into processed
    processed.career_themes = [
        WeightedSignal(
            value=p.label,
            confidence_score=p.confidence_score,
            weight=p.weight,
            source="cv",
            traces=p.traces,
        )
        for p in patterns
        if PATTERN_ROUTING.get(p.pattern_type) == "career_themes"
    ]

    # Inject trajectory label into FunctionalDNA
    trajectory = next(
        (p for p in patterns if p.pattern_type.value.startswith("trajectory_")),
        None,
    )
    functional.career_trajectory = trajectory.label if trajectory else "undetermined"

    return patterns


# ---------------------------------------------------------------------------
# Stage 8 — Prioritisation wrapper
# ---------------------------------------------------------------------------

def run_prioritisation_engine_stage(
    profile: CareerDNAProfile,
    patterns: List[DetectedPattern],
) -> PrioritisedInsightSet:
    try:
        return build_prioritised_set(profile, patterns)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise PipelineError("run_prioritisation_engine", str(exc)) from exc


# ---------------------------------------------------------------------------
# Stage 9 — Narrative wrapper
# ---------------------------------------------------------------------------

def run_narrative_engine_stage(
    profile: CareerDNAProfile,
    patterns: List[DetectedPattern],
    prioritised: PrioritisedInsightSet,
) -> Optional[NarrativeReport]:
    try:
        return assemble_report(profile, patterns, prioritised)
    except NotImplementedError:
        raise
    except NarrativeError:
        raise
    except Exception as exc:
        raise NarrativeError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Stage 10 — Output assembly
# ---------------------------------------------------------------------------

def build_signal_summary(
    processed: ProcessedProfile,
    suppressed_count: int,
) -> SignalSummary:
    all_signals: List[WeightedSignal] = (
        processed.skills_inferred
        + processed.personality_traits
        + processed.motivators
        + processed.stress_behaviours
        + processed.avoidance_patterns
        + processed.transferable_skills
    )
    total  = len(all_signals)
    high   = sum(1 for s in all_signals if s.confidence_score >= 0.75)
    medium = sum(1 for s in all_signals if 0.50 <= s.confidence_score < 0.75)
    low    = sum(1 for s in all_signals if s.confidence_score < 0.50)
    weak   = (low / total > WEAK_SIGNAL_RATIO) if total > 0 else True

    return SignalSummary(
        total_signals=total,
        high_confidence_count=high,
        medium_confidence_count=medium,
        low_confidence_count=low,
        suppressed_count=suppressed_count,
        weak_signal_warning=weak,
    )


def build_pipeline_output(
    profile: CareerDNAProfile,
    report: Optional[NarrativeReport],
    processed: ProcessedProfile,
    suppressed_count: int,
    warnings: List[str],
    target_profile: Optional[TargetRoleProfile] = None,
    pivot_delta: Optional[PivotDeltaReport] = None,
    pivot_narrative: Optional[PivotNarrative] = None,
    stakeholder_feedback: Optional[StakeholderFeedback] = None,
    decision_plan: Optional[DecisionUpgradePlan] = None,
    executive_report: Optional[ExecutiveTransitionReport] = None,
    formatted_report: Optional[str] = None,
    heuristic_scores: Optional[Any] = None,
    career_trajectory: Optional[Any] = None,
    enriched_roles: Optional[List[Any]] = None,
    compound_pathways: Optional[List[PathwayReadiness]] = None,
    llm_judgment: Optional[LLMReportIntelligence] = None,
) -> PipelineOutput:
    summary = build_signal_summary(processed, suppressed_count)

    if summary.weak_signal_warning:
        msg = (
            "Signal quality is below the recommended threshold. "
            "Report conclusions should be treated as indicative. "
            "Consider enriching the CV or questionnaire responses."
        )
        if msg not in warnings:
            warnings.append(msg)

    if report is None:
        warnings.append(
            "Narrative report could not be generated. "
            "The structured profile is available in the 'profile' field."
        )

    return PipelineOutput(
        profile=profile,
        report=report,
        warnings=warnings,
        signal_summary=summary,
        target_profile=target_profile,
        pivot_delta=pivot_delta,
        pivot_narrative=pivot_narrative,
        stakeholder_feedback=stakeholder_feedback,
        decision_plan=decision_plan,
        executive_report=executive_report,
        formatted_report=formatted_report,
        heuristic_scores=heuristic_scores,
        career_trajectory=career_trajectory,
        enriched_roles=enriched_roles,
        compound_pathways=compound_pathways,
        llm_judgment=llm_judgment,
    )


# ---------------------------------------------------------------------------
# Serialisation helpers (called by API layer)
# ---------------------------------------------------------------------------

def serialise_output(output: PipelineOutput) -> Dict[str, Any]:
    return output.model_dump(mode="json")


def serialise_pipeline_error(error: PipelineError) -> Dict[str, Any]:
    return {
        "error": True,
        "stage": error.stage,
        "message": error.message,
        "recoverable": error.recoverable,
    }


# ---------------------------------------------------------------------------
# Compound target pathway helpers
# ---------------------------------------------------------------------------

def _pathway_interpretation(pathway_name: str, fit_score: float, band: str, key_gaps: List[str]) -> str:
    if band == "strong":
        return (
            f"Very strong match — {pathway_name} is a primary target. "
            "Profile demonstrates the required vocabulary, credibility, and track record."
        )
    elif band == "credible":
        if key_gaps:
            return (
                f"Credible pathway — core signals are present. "
                f"Closing the {key_gaps[0].lower()} will make this approach compelling."
            )
        return f"Credible pathway — signals align well. Sharpen the narrative to make the case explicit."
    elif band == "partial":
        if key_gaps:
            return (
                f"Partial readiness — the foundation is there but {key_gaps[0].lower()} "
                "requires targeted development before approaching the market."
            )
        return "Partial readiness — experience is relevant but framing and vocabulary development needed."
    else:
        return (
            f"Early-stage readiness — significant repositioning required "
            f"before a credible approach to {pathway_name} opportunities."
        )


def _make_pathway_readiness(
    pathway_name: str,
    profile: "CareerDNAProfile",
    raw_cv_text: str,
    target_sector: Optional[str],
    target_seniority: Optional[str],
) -> Optional[PathwayReadiness]:
    """Compute PathwayReadiness for a single parsed pathway name."""
    try:
        tp = build_target_profile(pathway_name, target_sector, target_seniority)
        pd = compute_pivot_delta(profile, tp, raw_cv_text=raw_cv_text)
        n_gaps = len(pd.priority_gaps)

        base = int(pd.overall_fit_score * 100)
        penalty = min(n_gaps * 8, 25)
        readiness_score = max(10, min(100, base - penalty))

        if pd.overall_fit_score >= 0.65 and n_gaps == 0:
            band = "strong"
        elif pd.overall_fit_score >= 0.50 or (pd.overall_fit_score >= 0.35 and n_gaps <= 1):
            band = "credible"
        elif pd.overall_fit_score >= 0.28:
            band = "partial"
        else:
            band = "early-stage"

        key_gaps = [g.label for g in pd.priority_gaps[:3]]
        interpretation = _pathway_interpretation(pathway_name, pd.overall_fit_score, band, key_gaps)

        return PathwayReadiness(
            pathway_name=pathway_name,
            matched_profile_name=tp.role_name,
            fit_score=round(pd.overall_fit_score, 3),
            readiness_score=readiness_score,
            readiness_band=band,
            key_strengths=pd.strongest_matches[:4],
            key_gaps=key_gaps,
            interpretation=interpretation,
            pivot_delta=pd,
        )
    except Exception as exc:
        logger.warning("pathway analysis failed for %s: %s", pathway_name, exc)
        return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def generate_career_dna_report(input_data: RawInput) -> PipelineOutput:
    """
    Single entry point for the full Career DNA pipeline.

    Non-recoverable failures (InputValidationError, ScoringError) propagate
    to the caller. Recoverable failures (WeakSignalError, NarrativeError)
    are caught, logged, and surfaced as warnings in PipelineOutput.
    """
    warnings: List[str] = []
    suppressed_count: int = 0

    # Stage 1 — Validate
    validate_input(input_data)

    # Stage 2 — Parse CV
    roles, raw_skills, raw_responsibilities = parse_cv(input_data.cv_text)
    logger.info("parse_cv: extracted %d roles, %d skills", len(roles), len(raw_skills))

    # Stage 3 — Build initial ProcessedProfile
    processed = process_raw_inputs(input_data, roles, raw_skills, raw_responsibilities)

    # Stage 4 — Enrich with weighted signals
    try:
        processed = generate_weighted_signals(processed, input_data)
    except WeakSignalError as exc:
        logger.warning("WeakSignalError: %s", exc.message)
        warnings.append(exc.message)
        # Continue with whatever signals exist.

    # Stage 5 — Score strands, build DNA, detect tensions, score pivots
    functional, adaptive, aspirational, tensions, pivots = run_scoring_engine_stage(
        processed, input_data
    )

    # Stage 6 — Assemble pre-pattern profile
    profile = assemble_career_dna_profile(
        functional, adaptive, aspirational, tensions, pivots
    )

    # Stage 7 — Pattern detection
    patterns = run_pattern_engine_stage(processed, input_data, adaptive, functional)
    logger.info("pattern_engine: detected %d patterns", len(patterns))

    # Refresh profile with mutated trajectory + career themes
    profile.functional = functional

    # Stage 8 — Prioritise insights
    prioritised = run_prioritisation_engine_stage(profile, patterns)
    suppressed_count = sum(
        1 for rp in prioritised.ranked_patterns
        if rp.tier.value == "suppressed"
    )

    # Stage 9 — Narrative assembly
    report: Optional[NarrativeReport] = None
    try:
        report = run_narrative_engine_stage(profile, patterns, prioritised)
    except NarrativeError as exc:
        logger.error("NarrativeError: %s\n%s", exc.message, traceback.format_exc())
        warnings.append(exc.message)
    except NotImplementedError as exc:
        logger.warning("Narrative engine not yet implemented: %s", exc)
        warnings.append("Narrative report is not yet available (engine pending implementation).")

    # Stage 10 — Career trajectory (uses enriched roles from cv_parser)
    career_trajectory_obj: Optional[CareerTrajectory] = None
    try:
        career_trajectory_obj = build_career_trajectory(roles)
        logger.info("trajectory_engine: type=%s confidence=%.2f",
                    career_trajectory_obj.trajectory_type,
                    career_trajectory_obj.confidence_score)
    except Exception as exc:
        logger.warning("trajectory_engine failed: %s", exc)
        warnings.append(f"Career trajectory analysis could not be completed: {exc}")

    # Stage 11 — Transition analysis stack (optional, only when target_role supplied)
    target_profile_obj: Optional[TargetRoleProfile] = None
    pivot_delta_obj: Optional[PivotDeltaReport] = None
    pivot_narrative_obj: Optional[PivotNarrative] = None
    stakeholder_feedback_obj: Optional[StakeholderFeedback] = None
    decision_plan_obj: Optional[DecisionUpgradePlan] = None
    executive_report_obj: Optional[ExecutiveTransitionReport] = None
    compound_pathway_results: Optional[List[PathwayReadiness]] = None

    if input_data.target_role:
        try:
            parsed_pathways = parse_compound_target(input_data.target_role)
            is_compound = len(parsed_pathways) > 1

            if is_compound:
                # Evaluate each pathway; use best-fit for single-pathway downstream steps
                pathway_results: List[PathwayReadiness] = []
                for pathway_name in parsed_pathways:
                    pr = _make_pathway_readiness(
                        pathway_name, profile, input_data.cv_text,
                        input_data.target_sector, input_data.target_seniority,
                    )
                    if pr:
                        pathway_results.append(pr)

                if pathway_results:
                    pathway_results.sort(key=lambda p: p.readiness_score, reverse=True)
                    compound_pathway_results = pathway_results
                    best = pathway_results[0]
                    target_profile_obj = build_target_profile(
                        best.pathway_name,
                        input_data.target_sector,
                        input_data.target_seniority,
                    )
                    pivot_delta_obj = best.pivot_delta
                    logger.info(
                        "compound_target: %d pathways parsed, best=%s fit=%.2f",
                        len(pathway_results), best.pathway_name, best.fit_score,
                    )
            else:
                target_profile_obj = build_target_profile(
                    input_data.target_role,
                    input_data.target_sector,
                    input_data.target_seniority,
                )
                pivot_delta_obj = compute_pivot_delta(
                    profile, target_profile_obj, raw_cv_text=input_data.cv_text
                )

            # Run remaining transition analysis on the selected pivot_delta / target_profile
            if pivot_delta_obj and target_profile_obj:
                pivot_narrative_obj = build_pivot_narrative(pivot_delta_obj, target_profile_obj)
                stakeholder_feedback_obj = simulate_stakeholder_feedback(pivot_delta_obj, target_profile_obj)
                decision_plan_obj = build_decision_upgrade_plan(pivot_delta_obj, stakeholder_feedback_obj)
                executive_report_obj = assemble_executive_report(
                    pivot_delta_obj, pivot_narrative_obj,
                    stakeholder_feedback_obj, decision_plan_obj,
                )
                logger.info(
                    "transition_analysis: target=%s verdict=%s fit=%.2f upgrade_to=%s",
                    input_data.target_role,
                    stakeholder_feedback_obj.verdict,
                    pivot_delta_obj.overall_fit_score,
                    decision_plan_obj.target_verdict,
                )

        except Exception as exc:
            logger.warning("transition analysis failed: %s", exc)
            warnings.append(f"Transition analysis could not be completed: {exc}")

    # Stage 12 — Heuristic scoring
    heuristic_scores_obj = None
    try:
        heuristic_scores_obj = build_heuristic_scores(
            profile=profile,
            roles=roles,
            pivot_delta=pivot_delta_obj,
            trajectory=career_trajectory_obj,
            market_context_notes=input_data.market_context_notes,
            compound_pathways=compound_pathway_results,
        )
    except Exception as exc:
        logger.warning("heuristic_scoring failed: %s", exc)
        warnings.append(f"Heuristic scoring could not be completed: {exc}")

    # Stage 12b — LLM executive judgment (optional, Concierge tier only)
    llm_judgment_obj: Optional[LLMReportIntelligence] = None
    if input_data.llm_judgment_enabled:
        try:
            llm_judgment_obj = build_llm_judgment(
                roles=roles,
                profile=profile,
                trajectory=career_trajectory_obj,
                heuristic_scores=heuristic_scores_obj,
                compound_pathways=compound_pathway_results,
                signal_summary=build_signal_summary(processed, suppressed_count),
                pipeline_warnings=warnings,
                target_role=input_data.target_role,
                cv_text=input_data.cv_text,
                market_context_notes=input_data.market_context_notes,
            )
            if llm_judgment_obj:
                logger.info(
                    "llm_report_intel: verdict=%s adj=%+d tier=%s confidence=%s",
                    llm_judgment_obj.score_verdict,
                    llm_judgment_obj.score_adjustment,
                    llm_judgment_obj.profile_tier,
                    llm_judgment_obj.confidence_level,
                )
        except Exception as exc:
            logger.warning("llm_report_intel stage failed: %s", exc)
            warnings.append(f"Report intelligence layer could not be completed: {exc}")

    # Stage 13 — Format 12-section Career DNA report (always generated)
    formatted_report_str: Optional[str] = None
    try:
        formatted_report_str = format_career_dna_report(
            input_data=input_data,
            profile=profile,
            roles=roles,
            career_trajectory=career_trajectory_obj,
            heuristic_scores=heuristic_scores_obj,
            pivot_delta=pivot_delta_obj,
            pivot_narrative=pivot_narrative_obj,
            stakeholder_feedback=stakeholder_feedback_obj,
            decision_plan=decision_plan_obj,
            executive_report=executive_report_obj,
            compound_pathways=compound_pathway_results,
            llm_judgment=llm_judgment_obj,
        )
    except Exception as exc:
        logger.warning("format_career_dna_report failed: %s", exc)
        warnings.append(f"Report formatting could not be completed: {exc}")

    # Stage 14 — Assemble output
    return build_pipeline_output(
        profile, report, processed, suppressed_count, warnings,
        target_profile=target_profile_obj,
        pivot_delta=pivot_delta_obj,
        pivot_narrative=pivot_narrative_obj,
        stakeholder_feedback=stakeholder_feedback_obj,
        decision_plan=decision_plan_obj,
        executive_report=executive_report_obj,
        formatted_report=formatted_report_str,
        heuristic_scores=heuristic_scores_obj,
        career_trajectory=career_trajectory_obj,
        enriched_roles=roles,
        compound_pathways=compound_pathway_results,
        llm_judgment=llm_judgment_obj,
    )
