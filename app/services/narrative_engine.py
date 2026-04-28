from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas import PivotDeltaReport, PivotGap, TargetRoleProfile


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class PivotNarrative(BaseModel):
    executive_summary:     str
    positioning_statement: str
    critical_gaps:         List[str] = Field(default_factory=list)
    execution_plan:        List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fit_label(score: float) -> str:
    if score >= 0.70:
        return "strong"
    if score >= 0.50:
        return "credible"
    if score >= 0.35:
        return "partial"
    return "early-stage"


def _fit_sentence(score: float, role: str) -> str:
    pct = round(score * 100)
    label = _fit_label(score)
    if label == "strong":
        return (
            f"At {pct}% fit, this profile presents a strong operational case for {role}. "
            "The signal density is high and the trajectory is directionally aligned."
        )
    if label == "credible":
        return (
            f"At {pct}% fit, there is a credible but incomplete case for {role}. "
            "The transferable core is genuine; the gaps are specific and addressable."
        )
    if label == "partial":
        return (
            f"At {pct}% fit, the profile shows partial transferability to {role}. "
            "There is a real foundation here, but the repositioning work is non-trivial."
        )
    return (
        f"At {pct}% fit, this is an early-stage case for {role}. "
        "The profile needs targeted development before the transition is credible."
    )


def _matches_thesis(matches: list[str]) -> str:
    """Weave the top matched signals into a single investment-case sentence."""
    if not matches:
        return ""
    top = matches[:4]
    if len(top) == 1:
        return f"The strongest signal is {top[0]}."
    joined = ", ".join(top[:-1]) + f" and {top[-1]}"
    return f"The transferable core centres on {joined}."


def _gap_rewrite(gap: PivotGap, role: str) -> str:
    """Rewrite a PivotGap as a clean, specific executive statement."""
    severity_word = "critical" if gap.severity >= 0.70 else "notable" if gap.severity >= 0.45 else "minor"

    rewrites: dict[str, str] = {
        "skill_gap": (
            f"Core skill coverage is {severity_word}. "
            + (f"Key absences: {', '.join(gap.evidence[:3])}." if gap.evidence else "")
            + f" {gap.recommended_action}"
        ),
        "credibility_gap": (
            f"Credibility markers expected for {role} are {severity_word}ly thin. "
            + (f"Missing signals: {', '.join(gap.evidence[:3])}." if gap.evidence else "")
            + f" {gap.recommended_action}"
        ),
        "leadership_gap": (
            f"Leadership narrative needs elevation for {role}. "
            + (f"Absent signals: {', '.join(gap.evidence[:3])}." if gap.evidence else "")
            + f" {gap.recommended_action}"
        ),
        "commercial_gap": (
            f"Commercial signal is {severity_word}ly weak relative to {role} expectations. "
            + (f"Missing: {', '.join(gap.evidence[:3])}." if gap.evidence else "")
            + f" {gap.recommended_action}"
        ),
        "narrative_gap": (
            f"The profile does not yet speak the language of {role}. "
            + (f"Vocabulary gaps: {', '.join(gap.evidence[:3])}." if gap.evidence else "")
            + f" {gap.recommended_action}"
        ),
    }
    return rewrites.get(gap.gap_type, gap.implication)


def _plan_item(action: str, index: int) -> str:
    """Prefix a 90-day action with a structured time-horizon label."""
    labels = ["Immediate (0–30 days)", "Near-term (30–60 days)", "60–90 days", "90 days+", "Ongoing"]
    label = labels[index] if index < len(labels) else "Ongoing"
    # Strip the action of generic preamble if present
    stripped = action.strip().rstrip(".")
    return f"{label}: {stripped}."


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_executive_summary(
    delta: PivotDeltaReport,
    target: TargetRoleProfile,
) -> str:
    lines: list[str] = []

    lines.append(_fit_sentence(delta.overall_fit_score, target.role_name))

    thesis = _matches_thesis(delta.strongest_matches)
    if thesis:
        lines.append(thesis)

    # One sentence on the biggest gap only
    if delta.priority_gaps:
        top = delta.priority_gaps[0]
        severity_word = "critical" if top.severity >= 0.70 else "material" if top.severity >= 0.45 else "manageable"
        lines.append(
            f"The {severity_word} gap is {top.label.lower().replace(' gap', '')}: "
            f"{top.implication.split('.')[0].strip()}."
        )

    # Trajectory read
    label = _fit_label(delta.overall_fit_score)
    if label in ("strong", "credible"):
        lines.append(
            "The operational track record is real. "
            "The primary work is repositioning and language — not rebuilding the substance."
        )
    else:
        lines.append(
            "The substance exists, but the narrative distance to this role is significant. "
            "Targeted experience-building is required before the transition is compelling."
        )

    return " ".join(lines)


def _build_positioning_statement(
    delta: PivotDeltaReport,
    target: TargetRoleProfile,
) -> str:
    role = target.role_name
    matches = delta.strongest_matches[:4]
    fit_label = _fit_label(delta.overall_fit_score)

    # Opening: frame as an investment case
    if fit_label in ("strong", "credible"):
        opening = (
            f"This candidate is an operator with a proven track record in "
            f"{', '.join(matches[:2]) if matches else 'core operational delivery'}. "
            f"The case for {role} rests on depth of execution, not breadth of title."
        )
    else:
        opening = (
            f"The candidate brings genuine operational depth — "
            f"{', '.join(matches[:2]) if matches else 'core delivery capability'} — "
            f"but has not yet operated in the context that {role} demands."
        )

    # Middle: translate into role-specific language
    role_lower = role.lower()
    if "private equity" in role_lower or "operating partner" in role_lower:
        translation = (
            "In PE terms: this is a value-creation operator who has driven EBITDA improvement "
            "from within a business, not as an investor directing from outside. "
            "That insider credibility is an asset in portfolio company work."
        )
    elif "venture" in role_lower or "vc" in role_lower:
        translation = (
            "The operator-to-investor thesis is well-worn but works when the track record is specific. "
            "This candidate's strength is product-market credibility with founders — "
            "the fund sourcing and portfolio construction muscle needs to be built."
        )
    elif "ceo" in role_lower:
        translation = (
            "The move to CEO is fundamentally a shift from functional depth to enterprise ownership. "
            "The commercial and governance signals in this profile need amplification "
            "before the full CEO brief is natural territory."
        )
    elif "coo" in role_lower or "chief operating" in role_lower:
        translation = (
            "COO is the natural next step for an operator at this level. "
            "The question hiring committees ask is not whether they can run operations "
            "— it's whether they can own the agenda alongside a CEO."
        )
    else:
        translation = (
            f"The translation to {role} is a narrative exercise as much as an experience one. "
            "The underlying competence is present; the framing needs to match the brief."
        )

    # Closing: investor-case framing
    if matches:
        closing = (
            f"Position this candidate as: {matches[0]} with {matches[1] if len(matches) > 1 else 'execution depth'}. "
            "That framing holds under interview scrutiny."
        )
    else:
        closing = f"The positioning anchor for {role} should be operational credibility under ambiguity."

    return f"{opening} {translation} {closing}"


def _build_critical_gaps(
    delta: PivotDeltaReport,
    target: TargetRoleProfile,
) -> list[str]:
    top_gaps = delta.priority_gaps[:3]
    if not top_gaps:
        return ["No material gaps identified. Focus on narrative sharpness and network activation."]
    return [_gap_rewrite(g, target.role_name) for g in top_gaps]


def _build_execution_plan(
    delta: PivotDeltaReport,
    target: TargetRoleProfile,
) -> list[str]:
    actions = list(delta.ninety_day_actions)

    # Inject a role-specific high-value action if no board/network action present
    joined = " ".join(actions).lower()
    role_lower = target.role_name.lower()

    if "board" not in joined and "network" not in joined:
        if "private equity" in role_lower or "operating partner" in role_lower:
            actions.append(
                "Secure one advisory or interim operating role in a PE-backed business "
                "to establish direct portfolio company credibility."
            )
        elif "venture" in role_lower or "vc" in role_lower:
            actions.append(
                "Take two angel investments or advisory positions in early-stage companies "
                "to begin building a visible investing track record."
            )
        elif "ceo" in role_lower:
            actions.append(
                "Join a board as NED or advisor to develop governance experience "
                "and demonstrate enterprise-level thinking."
            )

    return [_plan_item(a, i) for i, a in enumerate(actions[:5])]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_pivot_narrative(
    pivot_delta: PivotDeltaReport,
    target_profile: TargetRoleProfile,
) -> PivotNarrative:
    return PivotNarrative(
        executive_summary=_build_executive_summary(pivot_delta, target_profile),
        positioning_statement=_build_positioning_statement(pivot_delta, target_profile),
        critical_gaps=_build_critical_gaps(pivot_delta, target_profile),
        execution_plan=_build_execution_plan(pivot_delta, target_profile),
    )
