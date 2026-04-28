from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.schemas import (
    AdaptiveDNA, AspirationalDNA, CareerDNAProfile,
    ExtractedRole, FunctionalDNA, KeyTension, PivotDirection,
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
from app.services.target_profiles import build_target_profile
from app.services.delta_engine import compute_pivot_delta
from app.services.narrative_engine import PivotNarrative, build_pivot_narrative
from app.services.stakeholder_simulator import StakeholderFeedback, simulate_stakeholder_feedback
from app.services.decision_engine import DecisionUpgradePlan, build_decision_upgrade_plan
from app.services.report_engine import ExecutiveTransitionReport, assemble_executive_report, format_executive_report
from app.schemas import TargetRoleProfile, PivotDeltaReport

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

    if not raw.zone_of_genius.strip():
        raise InputValidationError("zone_of_genius must not be empty.")

    if not raw.never_again.strip():
        raise InputValidationError("never_again must not be empty.")

    if not raw.top_achievements:
        raise InputValidationError("At least one achievement is required.")

    for i, ach in enumerate(raw.top_achievements):
        if not ach.strip():
            raise InputValidationError(f"Achievement at index {i} is empty.")


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

    # Stage 10 — Transition analysis stack (optional, only when target_role supplied)
    target_profile_obj: Optional[TargetRoleProfile] = None
    pivot_delta_obj: Optional[PivotDeltaReport] = None
    pivot_narrative_obj: Optional[PivotNarrative] = None
    stakeholder_feedback_obj: Optional[StakeholderFeedback] = None
    decision_plan_obj: Optional[DecisionUpgradePlan] = None
    executive_report_obj: Optional[ExecutiveTransitionReport] = None
    formatted_report_str: Optional[str] = None
    if input_data.target_role:
        try:
            target_profile_obj = build_target_profile(
                input_data.target_role,
                input_data.target_sector,
                input_data.target_seniority,
            )
            pivot_delta_obj = compute_pivot_delta(profile, target_profile_obj, raw_cv_text=input_data.cv_text)
            pivot_narrative_obj = build_pivot_narrative(pivot_delta_obj, target_profile_obj)
            stakeholder_feedback_obj = simulate_stakeholder_feedback(pivot_delta_obj, target_profile_obj)
            decision_plan_obj = build_decision_upgrade_plan(pivot_delta_obj, stakeholder_feedback_obj)
            executive_report_obj = assemble_executive_report(
                pivot_delta_obj, pivot_narrative_obj,
                stakeholder_feedback_obj, decision_plan_obj,
            )
            formatted_report_str = format_executive_report(executive_report_obj)
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

    # Stage 11 — Assemble output
    return build_pipeline_output(
        profile, report, processed, suppressed_count, warnings,
        target_profile=target_profile_obj,
        pivot_delta=pivot_delta_obj,
        pivot_narrative=pivot_narrative_obj,
        stakeholder_feedback=stakeholder_feedback_obj,
        decision_plan=decision_plan_obj,
        executive_report=executive_report_obj,
        formatted_report=formatted_report_str,
    )
