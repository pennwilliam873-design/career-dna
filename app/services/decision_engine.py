from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from app.schemas import PivotDeltaReport, PivotGap
from app.services.stakeholder_simulator import StakeholderFeedback


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class RequiredShift(BaseModel):
    area: str
    current_state: str
    required_state: str
    delta: str


class DecisionUpgradePlan(BaseModel):
    current_verdict: str
    target_verdict: str
    blocking_factors: List[str] = Field(default_factory=list)
    required_shifts: List[RequiredShift] = Field(default_factory=list)
    fastest_path_actions: List[str] = Field(default_factory=list)
    time_to_upgrade: str


# ---------------------------------------------------------------------------
# Verdict progression
# ---------------------------------------------------------------------------

_NEXT_VERDICT = {
    "lean_no":    "borderline",
    "borderline": "credible",
    "credible":   "strong_yes",
    "strong_yes": "strong_yes",
}


# ---------------------------------------------------------------------------
# Gap → RequiredShift (evidence-referenced, role-aware)
# ---------------------------------------------------------------------------

_AREA_LABELS = {
    "skill_gap":        "Core Skills",
    "credibility_gap":  "Credibility",
    "leadership_gap":   "Leadership Scope",
    "commercial_gap":   "Commercial Ownership",
    "narrative_gap":    "Narrative & Language",
}


def _build_required_shift(gap: PivotGap, stakeholder: str, target_role: str) -> RequiredShift:
    area = _AREA_LABELS.get(gap.gap_type, gap.label)
    missing = gap.evidence[:3]
    missing_str = ", ".join(missing) if missing else "key markers"
    match_pct = round((1.0 - gap.severity) * 100)

    if gap.gap_type == "skill_gap":
        current = (
            f"Covers {match_pct}% of required core skills. "
            f"Missing evidence of: {missing_str}."
        )
        required = (
            f"Demonstrable experience in {missing_str} in a context "
            f"directly comparable to {target_role}."
        )
        delta = (
            "Source 2–3 specific examples from existing work that can be reframed "
            f"to show {missing_str}. If none exist, take on a project, interim role, "
            "or advisory engagement that generates the evidence within 90 days."
        )

    elif gap.gap_type == "credibility_gap":
        current = (
            f"Credibility markers are {match_pct}% of what {stakeholder} expects. "
            f"Pattern-matched signals absent: {missing_str}."
        )
        required = (
            f"Visible proof of at least 2 of: {missing_str}. "
            "Can come from a role title, a documented outcome, a reference, "
            "or a network introduction from inside the target world."
        )
        delta = (
            "Identify one person currently in the target role who can validate the fit "
            "and provide an internal reference. Simultaneously, take on an advisory or "
            f"interim position that generates at least one of the missing credentials: {missing_str}."
        )

    elif gap.gap_type == "leadership_gap":
        current = (
            f"Leadership narrative covers {match_pct}% of the scope {stakeholder} requires. "
            f"Missing signals: {missing_str}."
        )
        required = (
            f"Evidence of operating at {target_role} authority level: "
            "board exposure, enterprise decision ownership, or equivalent scope. "
            f"Specifically: {missing_str}."
        )
        delta = (
            "Apply for a NED, advisory board, or operating partner role within the next 60 days. "
            "One well-chosen board seat creates more signal than three years of functional leadership. "
            "Target organisations where you already have a warm contact."
        )

    elif gap.gap_type == "commercial_gap":
        current = (
            f"Commercial signal covers {match_pct}% of what {stakeholder} expects to see. "
            f"Missing: {missing_str}. Profile reads as cost and ops focused, not commercially led."
        )
        required = (
            "Quantified commercial ownership — revenue influenced, deals led, pricing decisions made — "
            f"visible in CV and interview narrative. {missing_str} must have evidence."
        )
        delta = (
            "Audit existing achievements for commercial impact that has gone unquantified. "
            "Rewrite those bullets with revenue and margin numbers. "
            "Then target a role or project that adds direct commercial accountability "
            "— even a small P&L or a customer-facing leadership position changes the story."
        )

    elif gap.gap_type == "narrative_gap":
        current = (
            f"Profile language is {match_pct}% aligned with {target_role} vocabulary. "
            f"Missing terminology: {missing_str}. "
            "Reads as a strong operator who hasn't crossed into the target frame yet."
        )
        required = (
            f"{target_role} language used naturally throughout CV summary, LinkedIn headline, "
            f"and verbal positioning. {missing_str} should appear as first-language, not translation."
        )
        delta = (
            "Conduct 5 information interviews with people currently in the target role. "
            f"Rewrite CV executive summary and LinkedIn using the vocabulary of {target_role}. "
            "Get the positioning reviewed by one person inside the target world before using it."
        )

    else:
        current = gap.implication
        required = gap.recommended_action
        delta = gap.recommended_action

    return RequiredShift(area=area, current_state=current, required_state=required, delta=delta)


# ---------------------------------------------------------------------------
# Fastest-path actions (per gap type, highest-leverage first)
# ---------------------------------------------------------------------------

_FAST_ACTIONS: dict[str, list[str]] = {
    "skill_gap": [
        "Audit your last 5 years of work for undocumented examples of the missing skills — "
        "reframe and add them to the CV before anything else.",
        "Accept one advisory engagement in the target sector within 30 days, "
        "even if unpaid, to create a current-tense proof point.",
        "Commission a skills gap assessment from a specialist recruiter in the target area "
        "to confirm which gaps are real versus perception.",
    ],
    "credibility_gap": [
        "Identify your single strongest connection to someone inside the target world "
        "and ask them for a warm introduction to one hiring decision-maker this week.",
        "Take on a board advisory role, NED position, or operating role in a business "
        "that overlaps with the target credential — one role changes the whole profile.",
        "Build a reference pre-emptively: brief two people who can speak to your work "
        "in the target context so they're ready when called.",
    ],
    "leadership_gap": [
        "Apply for one NED or advisory board role in the next 30 days — "
        "target businesses where you have an existing warm relationship.",
        "Request that your current or most recent employer document your leadership scope "
        "formally (committee membership, strategy involvement, board reporting) "
        "so it's visible in a reference.",
        "Identify the specific leadership moment your profile is missing and manufacture it: "
        "lead a task force, take on an interim role, or chair an industry body.",
    ],
    "commercial_gap": [
        "Quantify the commercial impact of your three biggest past initiatives — "
        "revenue influenced, cost of inaction avoided, customer outcomes. "
        "Rewrite those three bullets before anything else.",
        "Take on a commercial responsibility in your current role — "
        "own a customer relationship, a pricing decision, or a revenue target — "
        "even temporarily, to close the gap with a current-tense example.",
        "Lead one external-facing commercial conversation: a partnership negotiation, "
        "a major customer review, or a commercial strategy presentation to a board.",
    ],
    "narrative_gap": [
        "Rewrite your CV executive summary (top 5 lines) using the exact vocabulary "
        "of the target role. Test it on one person in that world before publishing.",
        "Update your LinkedIn headline and About section to lead with target-role language. "
        "This changes first impressions in under an hour.",
        "Do 5 information interviews with people in the target role — not to network, "
        "but to absorb the language and then embed it in your own positioning.",
    ],
}

_DEFAULT_FAST_ACTIONS = [
    "Map your strongest 3 experiences directly to the role requirements and document the match.",
    "Identify the single most credible person in your network who is already doing this role "
    "and request a 30-minute conversation.",
    "Brief your three best professional references on the target role so they can speak to the fit "
    "when called.",
]


def _select_fast_actions(gaps: list[PivotGap]) -> list[str]:
    seen: set[str] = set()
    actions: list[str] = []
    for gap in gaps[:3]:
        for action in _FAST_ACTIONS.get(gap.gap_type, []):
            if action not in seen:
                seen.add(action)
                actions.append(action)
            if len(actions) >= 5:
                return actions
    if not actions:
        return _DEFAULT_FAST_ACTIONS[:3]
    return actions


# ---------------------------------------------------------------------------
# Time estimate
# ---------------------------------------------------------------------------

def _estimate_time(gaps: list[PivotGap], verdict: str) -> str:
    if verdict == "strong_yes":
        return "You are already at target. Focus on interview preparation and network activation."
    if verdict == "credible":
        return "30–60 days. The primary work is narrative refinement, not experience-building."

    if not gaps:
        return "30–60 days with focused repositioning work."

    max_severity = max(g.severity for g in gaps)
    high_severity_count = sum(1 for g in gaps if g.severity >= 0.70)

    if high_severity_count >= 2:
        return (
            "120–180 days. Multiple high-severity gaps require real experience-building, "
            "not just narrative work. The fastest path is one high-signal advisory or interim role."
        )
    if max_severity >= 0.70:
        return (
            "90–120 days. One high-severity gap is blocking the transition. "
            "A single well-chosen role or credential closes this faster than incremental progress."
        )
    return (
        "60–90 days. The gaps are addressable through targeted reframing and "
        "one or two deliberate positioning moves."
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_decision_upgrade_plan(
    pivot_delta: PivotDeltaReport,
    stakeholder_feedback: StakeholderFeedback,
) -> DecisionUpgradePlan:
    current_verdict = stakeholder_feedback.verdict
    target_verdict  = _NEXT_VERDICT[current_verdict]

    # Blocking factors: top 3 concerns from the stakeholder simulation
    blocking_factors = stakeholder_feedback.core_concerns[:3]

    # Required shifts: top 3 gaps by severity
    top_gaps = sorted(pivot_delta.priority_gaps, key=lambda g: g.severity, reverse=True)[:3]
    required_shifts = [
        _build_required_shift(g, stakeholder_feedback.stakeholder_type, pivot_delta.target_role)
        for g in top_gaps
    ]

    fastest_path_actions = _select_fast_actions(top_gaps)
    time_to_upgrade = _estimate_time(top_gaps, current_verdict)

    return DecisionUpgradePlan(
        current_verdict=current_verdict,
        target_verdict=target_verdict,
        blocking_factors=blocking_factors,
        required_shifts=required_shifts,
        fastest_path_actions=fastest_path_actions,
        time_to_upgrade=time_to_upgrade,
    )
