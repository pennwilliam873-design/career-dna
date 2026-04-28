from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas import (
    AdaptiveDNA, ClassifiedAchievement, ExtractedRole,
    ProcessedProfile, RawInput, SignalTrace, WeightedSignal,
)


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class PatternType(str, Enum):
    # Career themes
    transformation         = "transformation"
    growth_scaling         = "growth_scaling"
    optimisation           = "optimisation"
    innovation             = "innovation"
    stakeholder_influence  = "stakeholder_influence"
    turnaround             = "turnaround"
    team_building          = "team_building"
    commercial_expansion   = "commercial_expansion"
    # Success patterns
    strategic_thinker      = "strategic_thinker"
    executional_driver     = "executional_driver"
    individual_performer   = "individual_performer"
    team_multiplier        = "team_multiplier"
    structured_operator    = "structured_operator"
    ambiguity_navigator    = "ambiguity_navigator"
    # Energy
    energy_aligned         = "energy_aligned"
    energy_divergent       = "energy_divergent"
    # Avoidance
    micromanagement_averse = "micromanagement_averse"
    bureaucracy_averse     = "bureaucracy_averse"
    instability_averse     = "instability_averse"
    collaboration_averse   = "collaboration_averse"
    high_politics_averse   = "high_politics_averse"
    # Trajectory
    trajectory_linear          = "trajectory_linear"
    trajectory_exploratory     = "trajectory_exploratory"
    trajectory_opportunistic   = "trajectory_opportunistic"
    trajectory_plateaued       = "trajectory_plateaued"
    trajectory_accelerating    = "trajectory_accelerating"


class DetectedPattern(BaseModel):
    pattern_type: PatternType
    label: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    weight: float = Field(default=1.0)
    supporting_signals: List[WeightedSignal] = Field(default_factory=list)
    traces: List[SignalTrace] = Field(default_factory=list)
    evidence_summary: str


# Routing: PatternType → CareerDNAProfile destination field
PATTERN_ROUTING: dict[PatternType, str] = {
    PatternType.transformation:          "career_themes",
    PatternType.growth_scaling:          "career_themes",
    PatternType.optimisation:            "career_themes",
    PatternType.innovation:              "career_themes",
    PatternType.stakeholder_influence:   "career_themes",
    PatternType.turnaround:              "career_themes",
    PatternType.team_building:           "career_themes",
    PatternType.commercial_expansion:    "career_themes",
    PatternType.strategic_thinker:       "functional",
    PatternType.executional_driver:      "functional",
    PatternType.individual_performer:    "functional",
    PatternType.team_multiplier:         "functional",
    PatternType.structured_operator:     "functional",
    PatternType.ambiguity_navigator:     "functional",
    PatternType.energy_aligned:          "adaptive",
    PatternType.energy_divergent:        "adaptive",
    PatternType.micromanagement_averse:  "adaptive",
    PatternType.bureaucracy_averse:      "adaptive",
    PatternType.instability_averse:      "adaptive",
    PatternType.collaboration_averse:    "adaptive",
    PatternType.high_politics_averse:    "adaptive",
    PatternType.trajectory_linear:           "functional",
    PatternType.trajectory_exploratory:      "functional",
    PatternType.trajectory_opportunistic:    "functional",
    PatternType.trajectory_plateaued:        "functional",
    PatternType.trajectory_accelerating:     "functional",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pattern_pipeline(
    processed: ProcessedProfile,
    zone_of_genius: Optional[WeightedSignal],
    never_again_text: str,
    conflict_marker_text: str,
) -> List[DetectedPattern]:
    """
    Run all pattern detectors and return the unified, deduplicated pattern list.
    Each detector is independently stubbed — implement them individually.
    """
    patterns: List[DetectedPattern] = []

    patterns += _detect_career_themes(processed)
    patterns += _detect_success_patterns(processed.achievements_classified)
    patterns += _detect_energy_alignment(zone_of_genius, processed.achievements_classified, processed.roles)
    patterns += _detect_avoidance_patterns(never_again_text, conflict_marker_text, processed.roles)
    patterns.append(_classify_trajectory(processed.roles))

    return _dedup(patterns)


# ---------------------------------------------------------------------------
# Theme taxonomy — keywords are matched as case-insensitive substrings
# ---------------------------------------------------------------------------

THEME_TAXONOMY: dict[PatternType, list[str]] = {
    PatternType.transformation: [
        "transform", "restructur", "overhaul", "redesign", "revamp",
        "change management", "transition",
    ],
    PatternType.growth_scaling: [
        "scale", "growth", "expand", "expansion", "revenue growth",
        "headcount", "market share", "double", "triple",
    ],
    PatternType.optimisation: [
        "optimis", "optimiz", "efficien", "streamline", "reduce cost",
        "automat", "process improvement", "lean",
    ],
    PatternType.innovation: [
        "innovat", "launch", "pioneer", "prototype", "patent",
        "new product", "new feature", "r&d", "research and development",
    ],
    PatternType.stakeholder_influence: [
        "stakeholder", "board", "executive", "c-suite",
        "influenc", "negotiat", "align", "partner",
    ],
    PatternType.turnaround: [
        "turnaround", "rescue", "recover", "underperform", "failing",
        "loss-making", "distressed", "crisis",
    ],
    PatternType.team_building: [
        "hire", "recruit", "build team", "culture", "onboard", "mentor",
        "coach", "talent pipeline", "people manager",
    ],
    PatternType.commercial_expansion: [
        "commercial", "sales", "customer acquisition", "client",
        "business development", "new business", "pipeline", "upsell",
    ],
}


# ---------------------------------------------------------------------------
# Individual detectors (stubbed — implement per pattern_engine.py design)
# ---------------------------------------------------------------------------

def _detect_career_themes(processed: ProcessedProfile) -> List[DetectedPattern]:
    # Build corpus: (text, InputSource) from achievements and role titles
    corpus: list[tuple[str, str]] = []
    for ach in processed.achievements_classified:
        corpus.append((ach.raw_text, "achievement"))
        if ach.impact_summary:
            corpus.append((ach.impact_summary, "achievement"))
    for role in processed.roles:
        if role.title:
            corpus.append((role.title, "cv"))

    patterns: list[DetectedPattern] = []

    for theme, keywords in THEME_TAXONOMY.items():
        hit_texts: list[str] = []
        traces: list[SignalTrace] = []

        for text, source in corpus:
            lower = text.lower()
            for kw in keywords:
                if kw in lower:
                    hit_texts.append(text)
                    traces.append(SignalTrace(source=source, excerpt=text[:120]))  # type: ignore[arg-type]
                    break  # one hit per text fragment

        if len(hit_texts) < 2:
            continue

        confidence = round(min(0.50 + 0.08 * len(hit_texts), 0.95), 3)
        label = theme.value.replace("_", " ").title()
        summary_excerpts = "; ".join(hit_texts[:2])[:120]
        patterns.append(DetectedPattern(
            pattern_type=theme,
            label=label,
            confidence_score=confidence,
            weight=1.0,
            traces=traces[:5],
            evidence_summary=f"{len(hit_texts)} signal(s) matched: {summary_excerpts}",
        ))

    return patterns


SUCCESS_PATTERN_TAXONOMY: dict[PatternType, list[str]] = {
    PatternType.strategic_thinker: [
        "strateg", "vision", "roadmap", "long-term", "framework",
        "direction", "prioriti", "c-suite", "board",
    ],
    PatternType.executional_driver: [
        "deliver", "launch", "implement", "execute", "ship", "deploy",
        "on time", "on budget", "complet", "achiev",
    ],
    PatternType.individual_performer: [
        "independently", "solo", "own initiative", "sole",
        "single-handedly", "personally", "self-direct",
    ],
    PatternType.team_multiplier: [
        "team", "lead", "manag", "coach", "mentor", "develop people",
        "hire", "recruit", "staff", "people",
    ],
    PatternType.structured_operator: [
        "process", "system", "procedure", "standard", "compli",
        "audit", "governance", "policy", "protocol", "framework",
    ],
    PatternType.ambiguity_navigator: [
        "ambig", "uncertain", "pioneer", "greenfield", "from scratch",
        "undefin", "startup", "0 to 1", "new market", "first",
    ],
}


def _detect_success_patterns(
    achievements: List[ClassifiedAchievement],
) -> List[DetectedPattern]:
    if not achievements:
        return []

    total_weight = sum(a.weight for a in achievements)

    # axis_score[axis] = sum of weights of achievements that voted for it
    axis_scores: dict[PatternType, float] = {pt: 0.0 for pt in SUCCESS_PATTERN_TAXONOMY}
    axis_traces: dict[PatternType, list[SignalTrace]] = {pt: [] for pt in SUCCESS_PATTERN_TAXONOMY}

    for ach in achievements:
        text = (ach.raw_text + " " + (ach.impact_summary or "")).lower()
        for axis, keywords in SUCCESS_PATTERN_TAXONOMY.items():
            for kw in keywords:
                if kw in text:
                    axis_scores[axis] += ach.weight
                    axis_traces[axis].append(
                        SignalTrace(source="achievement", excerpt=ach.raw_text[:120])
                    )
                    break  # one vote per achievement per axis

    patterns: list[DetectedPattern] = []
    for axis, score in axis_scores.items():
        confidence = round(score / total_weight, 3) if total_weight > 0 else 0.0
        if confidence < 0.60:
            continue
        label = axis.value.replace("_", " ").title()
        patterns.append(DetectedPattern(
            pattern_type=axis,
            label=label,
            confidence_score=min(confidence, 0.95),
            weight=1.0,
            traces=axis_traces[axis][:5],
            evidence_summary=(
                f"{confidence:.0%} of achievement weight signals {label.lower()} "
                f"({score:.1f}/{total_weight:.1f} weighted votes)."
            ),
        ))

    return patterns


ENERGY_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "people_leadership": [
        "lead", "coach", "mentor", "develop", "people", "team",
        "culture", "talent", "inspire", "hire",
    ],
    "commercial": [
        "sales", "revenue", "commercial", "business development",
        "customer", "client", "deal", "market",
    ],
    "technical": [
        "engineer", "build", "code", "software", "architect",
        "system", "technical", "infrastructure",
    ],
    "creative": [
        "design", "creat", "brand", "content", "storytell",
        "narrative", "visual", "campaign",
    ],
    "analytical": [
        "data", "analys", "insight", "research", "model",
        "metric", "measure", "forecast",
    ],
    "operational": [
        "operation", "process", "efficien", "optimis", "optimiz",
        "logistic", "supply chain", "workflow",
    ],
    "strategic": [
        "strateg", "vision", "roadmap", "transform", "consult",
        "advis", "framework", "long-term",
    ],
}


def _domain_scores(text: str) -> dict[str, int]:
    lower = text.lower()
    return {
        domain: sum(1 for kw in keywords if kw in lower)
        for domain, keywords in ENERGY_DOMAIN_KEYWORDS.items()
    }


def _detect_energy_alignment(
    zone_of_genius: Optional[WeightedSignal],
    achievements: List[ClassifiedAchievement],
    roles: List[ExtractedRole],
) -> List[DetectedPattern]:
    if not zone_of_genius:
        return []

    # Score ZoG text
    zog_scores = _domain_scores(zone_of_genius.value)
    zog_total  = sum(zog_scores.values())
    if zog_total == 0:
        return []

    # Score career corpus: achievements + role titles
    career_text = " ".join(
        [a.raw_text + " " + (a.impact_summary or "") for a in achievements]
        + [r.title for r in roles if r.title]
    )
    career_scores = _domain_scores(career_text)
    career_total  = sum(career_scores.values())
    if career_total == 0:
        return []

    zog_top, zog_top_score       = max(zog_scores.items(),    key=lambda x: x[1])
    career_top, career_top_score = max(career_scores.items(), key=lambda x: x[1])

    zog_conf    = zog_top_score    / zog_total
    career_conf = career_top_score / career_total
    confidence  = round((zog_conf + career_conf) / 2, 3)

    aligned = zog_top == career_top
    pattern_type = PatternType.energy_aligned if aligned else PatternType.energy_divergent

    traces = [
        SignalTrace(source="zone_of_genius", excerpt=zone_of_genius.value[:120]),
    ]
    if achievements:
        traces.append(SignalTrace(source="achievement", excerpt=achievements[0].raw_text[:120]))
    if roles:
        traces.append(SignalTrace(source="cv", excerpt=roles[0].title[:80]))

    if aligned:
        summary = (
            f"Zone of Genius ({zog_top}) aligns with career history ({career_top}). "
            f"Energy is coherently directed."
        )
    else:
        summary = (
            f"Zone of Genius points to {zog_top} but career history centres on {career_top}. "
            f"Possible energy-role mismatch."
        )

    return [DetectedPattern(
        pattern_type=pattern_type,
        label=pattern_type.value.replace("_", " ").title(),
        confidence_score=min(max(confidence, 0.50), 0.95),
        weight=1.2,
        traces=traces,
        evidence_summary=summary,
    )]


AVOIDANCE_TAXONOMY: dict[PatternType, dict] = {
    PatternType.micromanagement_averse: {
        "label": "Micromanagement Averse",
        "keywords": [
            "micromanag", "lack of autonomy", "no autonomy", "over-manag",
            "overmanag", "no trust", "closely monitor",
        ],
    },
    PatternType.high_politics_averse: {
        "label": "High Politics Averse",
        "keywords": [
            "politic", "toxic culture", "blame culture", "backstab",
            "infighting", "hidden agenda",
        ],
    },
    PatternType.bureaucracy_averse: {
        "label": "Bureaucracy Averse",
        "keywords": [
            "bureaucra", "red tape", "slow decision", "slow to decide",
            "endless approval", "excessive process",
        ],
    },
    PatternType.instability_averse: {
        "label": "Instability Averse",
        "keywords": [
            "instabilit", "unstable", "unclear leadership", "no direction",
            "constant reorgani", "no clear", "unclear direction",
        ],
    },
    PatternType.collaboration_averse: {
        "label": "Poor Communication Averse",
        "keywords": [
            "poor communication", "bad communication", "no communication",
            "siloed", "no collaboration", "lack of communication",
        ],
    },
}


def _detect_avoidance_patterns(
    never_again_text: str,
    conflict_marker_text: str,
    roles: List[ExtractedRole],
) -> List[DetectedPattern]:
    corpus = (never_again_text + " " + conflict_marker_text).lower()

    never_lower   = never_again_text.lower()
    conflict_lower = conflict_marker_text.lower()

    patterns: list[DetectedPattern] = []

    for pattern_type, meta in AVOIDANCE_TAXONOMY.items():
        hits = sum(1 for kw in meta["keywords"] if kw in corpus)
        if hits < 1:
            continue

        traces: list[SignalTrace] = []
        if any(kw in never_lower for kw in meta["keywords"]):
            traces.append(SignalTrace(source="never_again", excerpt=never_again_text[:120]))  # type: ignore[arg-type]
        if any(kw in conflict_lower for kw in meta["keywords"]):
            traces.append(SignalTrace(source="conflict_marker", excerpt=conflict_marker_text[:120]))  # type: ignore[arg-type]

        confidence = round(min(0.6 + 0.1 * hits, 0.95), 3)
        patterns.append(DetectedPattern(
            pattern_type=pattern_type,
            label=meta["label"],
            confidence_score=confidence,
            weight=1.0,
            traces=traces[:2],
            evidence_summary=f"{hits} keyword hit(s) across never-again and conflict inputs.",
        ))

    return patterns


_SENIORITY_LEVELS: list[tuple[int, list[str]]] = [
    (8, ["ceo", "founder", "president", "managing director"]),
    (7, ["cto", "cfo", "coo", "cmo", "chief", "svp", "evp"]),
    (6, ["vp", "vice president"]),
    (5, ["director", "head of", "head,"]),
    (4, ["manager", "staff engineer"]),
    (3, ["senior", "lead", "principal"]),
    (2, ["specialist", "consultant"]),
    (1, ["junior", "associate", "analyst", "graduate", "intern"]),
]


def _seniority_rank(role: ExtractedRole) -> int:
    text = ((role.seniority or "") + " " + (role.title or "")).lower()
    for rank, keywords in _SENIORITY_LEVELS:
        if any(kw in text for kw in keywords):
            return rank
    return 2  # default mid-level


def _classify_trajectory(roles: List[ExtractedRole]) -> DetectedPattern:
    if not roles:
        return DetectedPattern(
            pattern_type=PatternType.trajectory_linear,
            label="Linear",
            confidence_score=0.50,
            weight=1.0,
            traces=[],
            evidence_summary="No role data available to classify trajectory.",
        )

    sorted_roles = sorted(roles, key=lambda r: r.start_year or 0)

    def _tenure(r: ExtractedRole) -> int:
        if r.duration_months:
            return r.duration_months
        if r.start_year and r.end_year:
            return (r.end_year - r.start_year) * 12
        return 24

    tenures = [_tenure(r) for r in sorted_roles]
    avg_tenure = sum(tenures) / len(tenures)
    ranks = [_seniority_rank(r) for r in sorted_roles]
    sectors = {r.sector.lower() for r in sorted_roles if r.sector}
    n = len(sorted_roles)

    traces: list[SignalTrace] = [
        SignalTrace(source="cv", excerpt=sorted_roles[-1].title[:80])
    ]

    # Accelerating: seniority rank has grown from earliest to most recent role
    if n >= 2 and ranks[-1] > ranks[0]:
        delta = ranks[-1] - ranks[0]
        return DetectedPattern(
            pattern_type=PatternType.trajectory_accelerating,
            label="Accelerating",
            confidence_score=round(min(0.65 + 0.05 * delta, 0.85), 3),
            weight=1.0,
            traces=traces,
            evidence_summary=(
                f"Seniority progressed from rank {ranks[0]} to {ranks[-1]} across {n} roles."
            ),
        )

    # Exploratory: broad sector spread or very short average tenure
    if len(sectors) >= 3 or (n >= 3 and avg_tenure < 18):
        return DetectedPattern(
            pattern_type=PatternType.trajectory_exploratory,
            label="Exploratory",
            confidence_score=round(min(0.65 + 0.02 * len(sectors), 0.80), 3),
            weight=1.0,
            traces=traces,
            evidence_summary=(
                f"{len(sectors)} distinct sector(s), avg tenure {avg_tenure:.0f} months."
            ),
        )

    # Opportunistic: frequent moves without seniority growth
    if n >= 3 and avg_tenure < 24 and ranks[-1] <= ranks[0]:
        return DetectedPattern(
            pattern_type=PatternType.trajectory_opportunistic,
            label="Opportunistic",
            confidence_score=0.68,
            weight=1.0,
            traces=traces,
            evidence_summary=(
                f"Frequent moves (avg {avg_tenure:.0f} months) without clear seniority progression."
            ),
        )

    # Plateaued: long tenure with flat seniority
    if avg_tenure >= 48 and len(set(ranks)) <= 2:
        return DetectedPattern(
            pattern_type=PatternType.trajectory_plateaued,
            label="Plateaued",
            confidence_score=0.70,
            weight=1.0,
            traces=traces,
            evidence_summary=(
                f"Long average tenure ({avg_tenure:.0f} months) with stable seniority level."
            ),
        )

    # Default: linear
    return DetectedPattern(
        pattern_type=PatternType.trajectory_linear,
        label="Linear",
        confidence_score=0.65,
        weight=1.0,
        traces=traces,
        evidence_summary=(
            f"{n} role(s) with steady progression and avg tenure {avg_tenure:.0f} months."
        ),
    )


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _dedup(patterns: List[DetectedPattern]) -> List[DetectedPattern]:
    seen: dict[PatternType, DetectedPattern] = {}
    for p in patterns:
        if p.pattern_type not in seen or p.confidence_score > seen[p.pattern_type].confidence_score:
            seen[p.pattern_type] = p
    return sorted(seen.values(), key=lambda p: p.confidence_score, reverse=True)
