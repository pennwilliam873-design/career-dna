from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field

from app.services.decision_engine import DecisionUpgradePlan
from app.services.narrative_engine import PivotNarrative
from app.services.stakeholder_simulator import StakeholderFeedback
from app.schemas import PivotDeltaReport


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class ExecutiveTransitionReport(BaseModel):
    # Decision block metadata (used by formatter)
    verdict:               str = ""
    target_role:           str = ""
    time_to_upgrade:       str = ""
    stakeholder_type:      str = ""
    blocking_gap_type:     str = ""
    blocking_gap_evidence: List[str] = Field(default_factory=list)
    # Report sections
    executive_summary:    str
    career_positioning:   str
    market_verdict:       str
    critical_gaps:        List[str] = Field(default_factory=list)
    stakeholder_pushback: List[str] = Field(default_factory=list)
    upgrade_strategy:     List[str] = Field(default_factory=list)
    ninety_day_plan:      List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verdict → human language
# ---------------------------------------------------------------------------

_VERDICT_COPY: dict[str, str] = {
    "strong_yes": (
        "You are a strong candidate. "
        "The profile maps closely to what decision-makers are looking for in this role. "
        "Most hiring panels would progress you without significant reservations."
    ),
    "credible": (
        "You are a credible candidate. "
        "Most decision-makers would progress you to the next stage, "
        "subject to the right conversation on a small number of specific gaps."
    ),
    "borderline": (
        "You are not currently a clear hire, but within reach. "
        "The core is transferable — the gaps are specific and closable. "
        "One or two deliberate moves will shift this verdict."
    ),
    "lean_no": (
        "You are not a clear hire at this stage. "
        "The profile has genuine transferable value, but specific gaps are "
        "blocking the transition. A structured 90–180 day programme closes this."
    ),
}


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_executive_summary(
    narrative: PivotNarrative,
    decision_plan: DecisionUpgradePlan,
    stakeholder: StakeholderFeedback,
) -> str:
    # Trim narrative executive_summary to first 3 sentences
    sentences = [s.strip() for s in narrative.executive_summary.split(". ") if s.strip()]
    base = ". ".join(sentences[:3]).rstrip(".")

    verdict_phrase = _VERDICT_COPY.get(stakeholder.verdict, "").split(".")[0]
    time_phrase = decision_plan.time_to_upgrade.split(".")[0]

    return f"{base}. {verdict_phrase}. {time_phrase}."


def _build_market_verdict(
    stakeholder: StakeholderFeedback,
    pivot_delta: PivotDeltaReport,
) -> str:
    copy = _VERDICT_COPY.get(stakeholder.verdict, stakeholder.decision_logic)
    confidence_pct = round(stakeholder.confidence_score * 100)
    fit_pct = round(pivot_delta.overall_fit_score * 100)
    return (
        f"{copy} "
        f"[Assessed by {stakeholder.stakeholder_type}. "
        f"Fit score: {fit_pct}%. Assessor confidence: {confidence_pct}%.]"
    )


def _build_critical_gaps(decision_plan: DecisionUpgradePlan) -> list[str]:
    if not decision_plan.required_shifts:
        return ["No material gaps identified. Focus on narrative sharpness and network activation."]
    lines: list[str] = []
    for shift in decision_plan.required_shifts:
        # Plain English: area label + the delta (what to do about it)
        lines.append(f"{shift.area}: {shift.delta}")
    return lines


def _build_ninety_day_plan(
    narrative: PivotNarrative,
    decision_plan: DecisionUpgradePlan,
) -> list[str]:
    # Prefer narrative execution_plan (already time-stamped) if populated
    if narrative.execution_plan:
        return narrative.execution_plan[:5]

    # Fall back: bucket fastest_path_actions into time windows
    buckets = ["Week 1–2", "Week 3–4", "Month 2", "Month 3", "Ongoing"]
    plan: list[str] = []
    for i, action in enumerate(decision_plan.fastest_path_actions[:5]):
        label = buckets[i] if i < len(buckets) else "Ongoing"
        plan.append(f"{label}: {action.rstrip('.')}.")
    return plan


# ---------------------------------------------------------------------------
# Text formatter — private helpers
# ---------------------------------------------------------------------------

def _heading(title: str) -> str:
    return f"{title}\n{'=' * len(title)}"


def _embolden(text: str) -> str:
    """Wrap key metrics in ** for markdown-aware renderers."""
    # Fit score percentage, e.g. "48% fit"
    text = re.sub(r'(\d+% fit)', r'**\1**', text)
    # Day ranges, e.g. "90–120 days" or "30-60 days"
    text = re.sub(r'(\d+[–\-]\d+ days)', r'**\1**', text)
    # Bracketed stats line from market_verdict
    text = re.sub(r'(Fit score: \d+%)', r'**\1**', text)
    text = re.sub(r'(Assessor confidence: \d+%)', r'**\1**', text)
    return text


def _split_sentences(text: str) -> list[str]:
    """Split text into individual sentences at '. [Capital]' boundaries."""
    parts = re.split(r'(?<=[^A-Z]{2})\. (?=[A-Z])', text)
    return [p.rstrip('.').strip() for p in parts if p.strip()]


def _prose_block(text: str, embolden: bool = False) -> str:
    """Format a prose paragraph: short sentences get a line break between them."""
    if embolden:
        text = _embolden(text)
    sentences = _split_sentences(text)
    if len(sentences) <= 2:
        return ". ".join(sentences) + "."
    # Three or more sentences: group into two short paragraphs
    mid = len(sentences) // 2
    para_1 = ". ".join(sentences[:mid]) + "."
    para_2 = ". ".join(sentences[mid:]) + "."
    return f"{para_1}\n\n{para_2}"


def _bullet_list(items: list[str], labelled: bool = False) -> str:
    """
    Render a bullet list.
    labelled=True: expect items in "Label: description" form — bold the label,
                   then emit each sentence of the description on its own indented line.
    """
    lines: list[str] = []
    for item in items:
        if labelled and ": " in item:
            label, body = item.split(": ", 1)
            lines.append(f"  - **{label}**")
            for sentence in _split_sentences(body):
                lines.append(f"    {sentence}.")
        else:
            sentences = _split_sentences(item)
            if len(sentences) == 1:
                lines.append(f"  - {item}")
            else:
                # First sentence as bullet, remainder indented
                lines.append(f"  - {sentences[0]}.")
                for s in sentences[1:]:
                    lines.append(f"    {s}.")
        lines.append("")  # blank line between bullets
    return "\n".join(lines).rstrip()


_VERDICT_DISPLAY: dict[str, str] = {
    "strong_yes": "Strong",
    "credible":   "Credible",
    "borderline": "Borderline",
    "lean_no":    "No-Fit",
}


_BLOCKER_COPY: dict[str, str] = {
    "skill_gap":        "Missing required skills — {evidence} unproven at the depth this role demands.",
    "credibility_gap":  "No credible proof of {evidence}. Does not pattern-match for {role} at this level.",
    "leadership_gap":   "Leadership scope undemonstrated — {evidence} not yet visible in record.",
    "commercial_gap":   "No evidence of commercial ownership — {evidence} absent from profile.",
    "narrative_gap":    "Not yet speaking {role} language — {evidence} missing. Reads as operator, not principal.",
}

_RISK_COPY: dict[str, dict[str, str]] = {
    "PE Partner / MD": {
        "skill_gap":        "Will fail operating partner technical screen — missing toolkit raises LP-level doubts.",
        "credibility_gap":  "Will be filtered at sourcing stage — no PE context means no shortlist.",
        "leadership_gap":   "Will lose every finalist comparison to candidates with board or operating partner experience.",
        "commercial_gap":   "Will be screened out at partner interview — commercial gap is disqualifying in most PE processes.",
        "narrative_gap":    "Will be read as an operator, not a principal — language gap kills first-impression scoring.",
    },
    "VC General Partner": {
        "skill_gap":        "Will not be taken seriously by founders — no investing track record is a structural barrier.",
        "credibility_gap":  "Will lose every final-round comparison to candidates with even one deal on record.",
        "leadership_gap":   "Will fail portfolio board responsibilities — founding-stage accountability gap is disqualifying.",
        "commercial_gap":   "Will fail unit-economics screens — a standard VC partner interview filter.",
        "narrative_gap":    "Will read as a corporate hire — founders will not engage.",
    },
    "CEO / Executive Chair": {
        "skill_gap":        "Will face board veto — no enterprise ownership signals is disqualifying at CEO level.",
        "credibility_gap":  "Will be outcompeted by candidates with clear board and full-P&L history.",
        "leadership_gap":   "Will fail the executive authority test — decision-making scope is in question.",
        "commercial_gap":   "Will fail the commercial strategy question — standard disqualifier for external CEO hires.",
        "narrative_gap":    "Will be perceived as COO-level — board will not back the transition without reframing.",
    },
    "COO / Operating Committee": {
        "skill_gap":        "Will be outcompeted by candidates with broader functional ownership.",
        "credibility_gap":  "Will fail the operating model depth test — standard COO appointment screen.",
        "leadership_gap":   "Will be passed over for candidates with proven cross-functional authority.",
        "commercial_gap":   "Will lose to candidates who can speak commercial rhythm alongside operations.",
        "narrative_gap":    "Will be read as a functional head, not an operating principal.",
    },
    "MD / General Manager": {
        "skill_gap":        "Will be outcompeted by candidates with demonstrated full-P&L ownership.",
        "credibility_gap":  "Will fail the business ownership test — revenue accountability gap is disqualifying.",
        "leadership_gap":   "Will be passed over for candidates who have led through ambiguity at GM level.",
        "commercial_gap":   "Will lose to candidates who lead with revenue performance, not operational efficiency.",
        "narrative_gap":    "Will be read as a strong operator who is not ready to own the business.",
    },
}
_DEFAULT_RISK = "Will be deprioritised in favour of candidates with stronger matching signals."


def _decision_block(report: ExecutiveTransitionReport) -> str:
    verdict_label = _VERDICT_DISPLAY.get(report.verdict, report.verdict.replace("_", " ").title())
    time_str = report.time_to_upgrade.split(".")[0].rstrip(".") + "."

    lines = [
        _heading("DECISION"),
        "",
        f"Verdict:         **{verdict_label}**",
        f"Target Role:     {report.target_role}",
        "",
        f"Time to Upgrade: {time_str}",
    ]

    # strong_yes — no blocker/fix/risk block; profile is ready
    if report.verdict == "strong_yes":
        if report.upgrade_strategy:
            raw = _split_sentences(report.upgrade_strategy[0])[0].rstrip(".")
            next_action = raw.split(" — ")[0].rstrip(",").strip() + "."
            lines += ["", "Next action:", f"  - {next_action}"]
        return "\n".join(lines)

    # blocked verdict — show blocker, fix, risk
    if not report.blocking_gap_type:
        # No single blocking gap: the profile is close but lacks PE-specific framing
        blocker = (
            f"Profile has the substance but not yet the language of {report.target_role}. "
            "Operational credibility is present; PE-specific positioning is not."
        )
    else:
        evidence_str = ", ".join(report.blocking_gap_evidence) if report.blocking_gap_evidence else "key signals"
        blocker_template = _BLOCKER_COPY.get(
            report.blocking_gap_type,
            "Not yet demonstrated at the level {role} requires — {evidence} absent from profile.",
        )
        blocker = blocker_template.format(evidence=evidence_str, role=report.target_role)

    fix_text = "Reposition the profile with target-role language and one new credential."
    if report.upgrade_strategy:
        raw = _split_sentences(report.upgrade_strategy[0])[0].rstrip(".")
        fix_text = raw.split(" — ")[0].rstrip(",").strip() + "."

    risk_map = _RISK_COPY.get(report.stakeholder_type, {})
    risk_text = risk_map.get(report.blocking_gap_type, _DEFAULT_RISK)

    lines += [
        "",
        "Blocked by:",
        f"  - {blocker}",
        "",
        "Fix:",
        f"  - {fix_text}",
        "",
        "Risk:",
        f"  - {risk_text}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Text formatter — public
# ---------------------------------------------------------------------------

def format_executive_report(report: ExecutiveTransitionReport) -> str:
    SEP = "\n\n\n"

    sections: list[str] = [
        # ── Decision block ─────────────────────────────────────────────────
        _decision_block(report),

        # ── Executive Summary ──────────────────────────────────────────────
        "\n".join([
            _heading("EXECUTIVE SUMMARY"),
            "",
            _prose_block(report.executive_summary, embolden=True),
        ]),

        # ── Career Positioning ─────────────────────────────────────────────
        "\n".join([
            _heading("CAREER POSITIONING"),
            "",
            _prose_block(report.career_positioning),
        ]),

        # ── Market Verdict ─────────────────────────────────────────────────
        "\n".join([
            _heading("MARKET VERDICT"),
            "",
            _embolden(report.market_verdict),
        ]),

        # ── Critical Gaps ──────────────────────────────────────────────────
        "\n".join([
            _heading("CRITICAL GAPS"),
            "",
            _bullet_list(report.critical_gaps, labelled=True),
        ]),

        # ── What the Hiring Panel Will Ask (omit if empty) ─────────────────
        *(["\n".join([
            _heading("WHAT THE HIRING PANEL WILL ASK"),
            "",
            _bullet_list(report.stakeholder_pushback),
        ])] if report.stakeholder_pushback else []),

        # ── Upgrade Strategy ───────────────────────────────────────────────
        "\n".join([
            _heading("UPGRADE STRATEGY"),
            "",
            _bullet_list(report.upgrade_strategy),
        ]),

        # ── 90-Day Plan ────────────────────────────────────────────────────
        "\n".join([
            _heading("90-DAY PLAN"),
            "",
            _bullet_list(report.ninety_day_plan),
        ]),
    ]

    return SEP.join(sections)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def assemble_executive_report(
    pivot_delta: PivotDeltaReport,
    pivot_narrative: PivotNarrative,
    stakeholder_feedback: StakeholderFeedback,
    decision_plan: DecisionUpgradePlan,
) -> ExecutiveTransitionReport:
    top_gap = pivot_delta.priority_gaps[0] if pivot_delta.priority_gaps else None
    return ExecutiveTransitionReport(
        verdict=stakeholder_feedback.verdict,
        target_role=pivot_delta.target_role,
        time_to_upgrade=decision_plan.time_to_upgrade,
        stakeholder_type=stakeholder_feedback.stakeholder_type,
        blocking_gap_type=top_gap.gap_type if top_gap else "",
        blocking_gap_evidence=top_gap.evidence[:3] if top_gap else [],
        executive_summary=_build_executive_summary(
            pivot_narrative, decision_plan, stakeholder_feedback
        ),
        career_positioning=pivot_narrative.positioning_statement,
        market_verdict=_build_market_verdict(stakeholder_feedback, pivot_delta),
        critical_gaps=_build_critical_gaps(decision_plan),
        stakeholder_pushback=stakeholder_feedback.pushback_questions[:5],
        upgrade_strategy=decision_plan.fastest_path_actions[:5],
        ninety_day_plan=_build_ninety_day_plan(pivot_narrative, decision_plan),
    )
