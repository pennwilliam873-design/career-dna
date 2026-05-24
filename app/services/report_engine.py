from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field

from app.services.decision_engine import DecisionUpgradePlan
from app.services.narrative_engine import PivotNarrative
from app.services.stakeholder_simulator import StakeholderFeedback
from app.services.skill_taxonomy import CATEGORY_LABELS, CATEGORY_PRIORITY, aggregate_skills
from app.schemas import (
    CareerDNAProfile, CareerTrajectory, ExtractedRole,
    HeuristicScoreSet, PivotDeltaReport, RawInput,
)


# ---------------------------------------------------------------------------
# Output model (unchanged — frontend summary card reads these fields)
# ---------------------------------------------------------------------------

class ExecutiveTransitionReport(BaseModel):
    verdict:               str = ""
    target_role:           str = ""
    time_to_upgrade:       str = ""
    stakeholder_type:      str = ""
    blocking_gap_type:     str = ""
    blocking_gap_evidence: List[str] = Field(default_factory=list)
    executive_summary:    str
    career_positioning:   str
    market_verdict:       str
    critical_gaps:        List[str] = Field(default_factory=list)
    stakeholder_pushback: List[str] = Field(default_factory=list)
    upgrade_strategy:     List[str] = Field(default_factory=list)
    ninety_day_plan:      List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared formatting primitives
# ---------------------------------------------------------------------------

def _heading(title: str) -> str:
    return f"{title}\n{'=' * len(title)}"


def _embolden(text: str) -> str:
    text = re.sub(r'(\d+% fit)', r'**\1**', text)
    text = re.sub(r'(\d+[–\-]\d+ days)', r'**\1**', text)
    text = re.sub(r'(Fit score: \d+%)', r'**\1**', text)
    text = re.sub(r'(Assessor confidence: \d+%)', r'**\1**', text)
    return text


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[^A-Z]{2})\. (?=[A-Z])', text)
    return [p.rstrip('.').strip() for p in parts if p.strip()]


def _prose_block(text: str, embolden: bool = False) -> str:
    if embolden:
        text = _embolden(text)
    sentences = _split_sentences(text)
    if len(sentences) <= 2:
        return ". ".join(sentences) + "."
    mid = len(sentences) // 2
    return ". ".join(sentences[:mid]) + ".\n\n" + ". ".join(sentences[mid:]) + "."


def _bullet_list(items: list[str], labelled: bool = False) -> str:
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
                lines.append(f"  - {sentences[0]}.")
                for s in sentences[1:]:
                    lines.append(f"    {s}.")
        lines.append("")
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Legacy section builders (used by assemble_executive_report)
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


def _build_executive_summary(narrative, decision_plan, stakeholder) -> str:
    sentences = [s.strip() for s in narrative.executive_summary.split(". ") if s.strip()]
    base = ". ".join(sentences[:3]).rstrip(".")
    verdict_phrase = _VERDICT_COPY.get(stakeholder.verdict, "").split(".")[0]
    time_phrase = decision_plan.time_to_upgrade.split(".")[0]
    return f"{base}. {verdict_phrase}. {time_phrase}."


def _build_market_verdict(stakeholder, pivot_delta) -> str:
    copy = _VERDICT_COPY.get(stakeholder.verdict, stakeholder.decision_logic)
    confidence_pct = round(stakeholder.confidence_score * 100)
    fit_pct = round(pivot_delta.overall_fit_score * 100)
    return (
        f"{copy} "
        f"[Assessed by {stakeholder.stakeholder_type}. "
        f"Fit score: {fit_pct}%. Assessor confidence: {confidence_pct}%.]"
    )


def _build_critical_gaps(decision_plan) -> list[str]:
    if not decision_plan.required_shifts:
        return ["No material gaps identified. Focus on narrative sharpness and network activation."]
    return [f"{shift.area}: {shift.delta}" for shift in decision_plan.required_shifts]


def _build_ninety_day_plan(narrative, decision_plan) -> list[str]:
    if narrative.execution_plan:
        return narrative.execution_plan[:5]
    buckets = ["Week 1–2", "Week 3–4", "Month 2", "Month 3", "Ongoing"]
    return [
        f"{buckets[i] if i < len(buckets) else 'Ongoing'}: {action.rstrip('.')}."
        for i, action in enumerate(decision_plan.fastest_path_actions[:5])
    ]


def _decision_content_lines(report: ExecutiveTransitionReport) -> list[str]:
    """Content lines for the decision context block, without the heading."""
    verdict_label = _VERDICT_DISPLAY.get(report.verdict, report.verdict.replace("_", " ").title())
    time_str = report.time_to_upgrade.split(".")[0].rstrip(".") + "."
    lines = [
        f"Verdict:         **{verdict_label}**",
        f"Target Role:     {report.target_role}", "",
        f"Time to Upgrade: {time_str}",
    ]
    if report.verdict == "strong_yes":
        if report.upgrade_strategy:
            raw = _split_sentences(report.upgrade_strategy[0])[0].rstrip(".")
            lines += ["", "Next action:", f"  - {raw.split(' — ')[0].rstrip(',').strip()}."]
        return lines
    if not report.blocking_gap_type:
        blocker = (
            f"Profile has the substance but not yet the language of {report.target_role}. "
            "Operational credibility is present; role-specific positioning is not."
        )
    else:
        evidence_str = ", ".join(report.blocking_gap_evidence) if report.blocking_gap_evidence else "key signals"
        blocker = _BLOCKER_COPY.get(
            report.blocking_gap_type,
            "Not yet demonstrated at the level {role} requires — {evidence} absent from profile.",
        ).format(evidence=evidence_str, role=report.target_role)
    fix_text = "Reposition the profile with target-role language and one new credential."
    if report.upgrade_strategy:
        fix_text = _split_sentences(report.upgrade_strategy[0])[0].rstrip(".").split(" — ")[0].rstrip(",").strip() + "."
    risk_map = _RISK_COPY.get(report.stakeholder_type, {})
    risk_text = risk_map.get(report.blocking_gap_type, _DEFAULT_RISK)
    lines += [
        "", "Blocked by:", f"  - {blocker}",
        "", "Fix:", f"  - {fix_text}",
        "", "Risk:", f"  - {risk_text}",
    ]
    return lines


def _decision_block(report: ExecutiveTransitionReport) -> str:
    return "\n".join([_heading("DECISION"), ""] + _decision_content_lines(report))


# ---------------------------------------------------------------------------
# Legacy public entry points (unchanged — used for executive_report field)
# ---------------------------------------------------------------------------

def format_executive_report(report: ExecutiveTransitionReport) -> str:
    SEP = "\n\n\n"
    sections: list[str] = [
        _decision_block(report),
        "\n".join([_heading("EXECUTIVE SUMMARY"), "", _prose_block(report.executive_summary, embolden=True)]),
        "\n".join([_heading("CAREER POSITIONING"), "", _prose_block(report.career_positioning)]),
        "\n".join([_heading("MARKET VERDICT"), "", _embolden(report.market_verdict)]),
        "\n".join([_heading("CRITICAL GAPS"), "", _bullet_list(report.critical_gaps, labelled=True)]),
        *(["\n".join([_heading("WHAT THE HIRING PANEL WILL ASK"), "", _bullet_list(report.stakeholder_pushback)])]
          if report.stakeholder_pushback else []),
        "\n".join([_heading("UPGRADE STRATEGY"), "", _bullet_list(report.upgrade_strategy)]),
        "\n".join([_heading("90-DAY PLAN"), "", _bullet_list(report.ninety_day_plan)]),
    ]
    return SEP.join(sections)


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
        executive_summary=_build_executive_summary(pivot_narrative, decision_plan, stakeholder_feedback),
        career_positioning=pivot_narrative.positioning_statement,
        market_verdict=_build_market_verdict(stakeholder_feedback, pivot_delta),
        critical_gaps=_build_critical_gaps(decision_plan),
        stakeholder_pushback=stakeholder_feedback.pushback_questions[:5],
        upgrade_strategy=decision_plan.fastest_path_actions[:5],
        ninety_day_plan=_build_ninety_day_plan(pivot_narrative, decision_plan),
    )


# ===========================================================================
# 12-SECTION CAREER DNA REPORT
# ===========================================================================

# ---------------------------------------------------------------------------
# Trajectory → inferred next-step options
# ---------------------------------------------------------------------------

_TRAJECTORY_OPTIONS: dict[str, list[str]] = {
    "linear_specialist": [
        "Domain Authority / Principal Consultant: Leverage specialist depth as an independent advisor or practice lead.",
        "Senior Leadership within Domain: Move into VP or Director-level roles within your area of specialisation.",
        "Advisory or Board Role: Position specialist expertise at board or advisory level to expand scope without leaving the domain.",
    ],
    "strategic_generalist": [
        "Chief Operating Officer: Broad cross-functional range maps directly to COO-level accountability.",
        "General Manager / Country Manager: P&L unit ownership is the natural next move for a strategic generalist.",
        "VP Strategy or Corporate Development: Formalise the generalist positioning into an enterprise strategy brief.",
    ],
    "operator_to_strategist": [
        "Chief Operating Officer: The operator-to-strategist arc terminates naturally at COO.",
        "PE / Infrastructure Operating Partner: Operating expertise combined with strategic framing is the profile PE firms recruit.",
        "General Manager or MD: Business unit ownership bridges operational track record with strategic scope.",
    ],
    "technical_to_commercial": [
        "Chief Product Officer: Technical-to-commercial arc with product as the bridge role.",
        "Commercial Director / VP Commercial: Lead revenue with technical credibility as the differentiator.",
        "General Manager in a Technology Business: Technical fluency plus commercial ownership.",
    ],
    "builder_profile": [
        "Founder or Co-Founder: The data supports it — the default next step for builders is to build.",
        "Chief Product Officer or CTO: Building track record maps directly to product or technical leadership.",
        "Venture Partner or Operating Partner: Investors value operators who can identify and support other builders.",
    ],
    "corporate_climber": [
        "Next Level Up within Current Organisation: Progression is clear — the move is upward, not lateral.",
        "Equivalent Level at a Larger or More Prestigious Organisation: Leverage institutional brand to reset the ceiling.",
        "Lateral Move to a Higher-Growth Organisation: Trade institutional prestige for equity and growth exposure.",
    ],
    "pivot_candidate": [
        "Commit to a Primary Vertical: Multiple pivots signal optionality — the work now is to pick one and go deep.",
        "Portfolio Career or Multi-Sector Advisory: Lean into breadth deliberately as a consultant across verticals.",
        "Intentional Industry Transition: Use the pivot pattern to enter a new sector at a higher entry point.",
    ],
    "early_formation": [
        "Deepen Skills in Current Domain: Too early to pivot — accumulate credibility before seeking a step change.",
        "Stretch Assignment or Secondment: Expand scope within the current context before moving on.",
        "Structured Development Programme: MBA, professional qualification, or accelerated leadership path.",
    ],
    "underleveraged_talent": [
        "Reframe and Re-enter at a Higher Seniority: Strong capability signals support a move upward — the gap is positioning, not substance.",
        "Move to a Smaller or Higher-Stakes Environment: Escape institutional ceilings by entering a context that rewards output.",
        "Advisory or Consulting: Monetise accumulated expertise outside the organisational structure.",
    ],
    "unclear": [
        "Target Role Clarification: Provide a specific target role for a grounded directional analysis.",
        "Structured Career Conversation: The available data does not yet support a definitive directional recommendation.",
    ],
}

_TRAJECTORY_ACTIONS: dict[str, list[str]] = {
    "linear_specialist": [
        "0–30 days: Audit current skill depth against the market rate for your specialist area — identify where you over-index and where demand is growing.",
        "30–60 days: Identify 3 senior roles one level above your current position and map the experience gap precisely.",
        "60–90 days: Build or update a credentials portfolio — case studies, publications, or talks that demonstrate domain authority.",
        "Ongoing: Seek at least one cross-functional project or advisory role to build breadth alongside depth.",
    ],
    "operator_to_strategist": [
        "0–30 days: Reframe your CV to lead with strategic outcomes, not operational inputs — every role should answer 'so what?' not just 'I did'.",
        "30–60 days: Identify 2 senior strategic or leadership roles and run a gap analysis against your current profile.",
        "60–90 days: Take on a board advisory or NED role — even unpaid — to add governance credibility to your record.",
        "Ongoing: Build a network in the sector you are moving toward — attend relevant conferences and reach out to 3 senior practitioners per month.",
    ],
    "strategic_generalist": [
        "0–30 days: Define your primary positioning anchor — one specific thing you are better at than anyone else.",
        "30–60 days: Target COO or GM roles and prepare a clear narrative on why breadth is a strategic asset, not a liability.",
        "60–90 days: Build 3 proof-point case studies across different functions that demonstrate strategic ownership, not just contribution.",
        "Ongoing: Develop a visible point of view on a specific market or operational challenge — write, speak, or advise.",
    ],
    "builder_profile": [
        "0–30 days: Document what you have built with precision — team size, revenue, products, systems — and the specific conditions that made it possible.",
        "30–60 days: Identify whether you want to build again (founder) or support others building (operating partner, CPO, CTO).",
        "60–90 days: Make 2 angel investments or take 2 advisory positions to extend your builder network.",
        "Ongoing: Stay connected to the early-stage ecosystem — founders need operators, and operators need founders.",
    ],
    "corporate_climber": [
        "0–30 days: Identify what you need for the next promotion and have a direct conversation with your sponsor.",
        "30–60 days: Secure a stretch project with visible cross-functional impact and board-level exposure.",
        "60–90 days: Build external optionality — update your market profile and have 2 exploratory conversations with search firms.",
        "Ongoing: Develop a mentor relationship with someone 2 levels above you who can advocate internally.",
    ],
    "pivot_candidate": [
        "0–30 days: Pick one destination sector or role and stress-test it — speak to 5 people who have made the same transition.",
        "30–60 days: Build a bridge narrative that reframes your career history as relevant preparation for the target, not a departure from it.",
        "60–90 days: Take on a project, advisory role, or qualification that adds one concrete credibility signal in the new direction.",
        "Ongoing: Narrow your focus — multiple pivots in a short period signals indecision rather than optionality.",
    ],
    "early_formation": [
        "0–30 days: Identify the 3 skills most valued at the next level in your target area — assess your current coverage honestly.",
        "30–60 days: Seek a stretch assignment or secondment that gives exposure to work one level above your current scope.",
        "60–90 days: Build a learning plan — formal or informal — that closes at least one identified skill gap.",
        "Ongoing: Find one mentor who is 5–10 years ahead on the path you want to take.",
    ],
    "underleveraged_talent": [
        "0–30 days: Conduct a positioning audit — document the gap between what you have done and how you have presented it.",
        "30–60 days: Rewrite your career narrative to surface impact and scope, not just activity.",
        "60–90 days: Target 3 roles that match your actual capability level, not your current title.",
        "Ongoing: Build external visibility — the market cannot reward what it cannot see.",
    ],
    "technical_to_commercial": [
        "0–30 days: Identify the commercial or product leadership role you are targeting and map the specific gap.",
        "30–60 days: Seek a project or temporary assignment with P&L, revenue, or customer accountability.",
        "60–90 days: Build a narrative that positions technical depth as a commercial advantage, not a separate track.",
        "Ongoing: Develop commercial fluency — read, study, and speak to commercial leaders in your target domain.",
    ],
}
_DEFAULT_ACTIONS = [
    "0–30 days: Clarify your specific target role and run a gap analysis against your current profile.",
    "30–60 days: Identify 3 people currently in your target role and arrange exploratory conversations.",
    "60–90 days: Take one concrete action that closes the most visible gap.",
    "Ongoing: Build a network in your target context — warm relationships shorten search timelines significantly.",
]

_STEPPING_STONE_MAP: dict[str, str] = {
    "skill_gap":        "Targeted upskilling or a qualification that directly closes the missing technical or functional gap.",
    "credibility_gap":  "Interim, fractional, or advisory role that creates a concrete proof-point in the target context.",
    "leadership_gap":   "NED, board advisor, or cross-functional leadership role that elevates the seniority and scope signal.",
    "commercial_gap":   "P&L ownership role — even at smaller scale — to establish a commercial track record.",
    "narrative_gap":    "Consulting or advisory engagement in the target sector to build language and pattern-recognition credibility.",
}

_READINESS_COPY: dict[str, str] = {
    "strong_yes": "Ready now — profile already maps to the target role requirements.",
    "credible":   "Credible — one focused programme closes the remaining gap.",
    "borderline": "Not ready yet — a 90–180 day structured programme is required.",
    "lean_no":    "Significant development needed — a 6–18 month programme to close key gaps.",
}

_FRICTION_LABEL = [
    (0.30, "Low"),
    (0.55, "Moderate"),
    (1.00, "High"),
]


def _friction_label(fit_score: float) -> str:
    friction = 1.0 - fit_score
    for threshold, label in _FRICTION_LABEL:
        if friction <= threshold:
            return label
    return "High"


# ---------------------------------------------------------------------------
# Section 1 — Executive Career Thesis (no target) / DECISION (with target)
# ---------------------------------------------------------------------------

def _s1_thesis_or_decision(
    executive_report: Optional[ExecutiveTransitionReport],
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
    trajectory: Optional[CareerTrajectory],
    input_data: RawInput,
    llm_intel: Optional[object] = None,
) -> str:
    lines = [_heading("EXECUTIVE CAREER THESIS"), ""]

    # LLM-authored thesis — replaces template when available
    if llm_intel and getattr(llm_intel, "executive_thesis", None):
        lines.append(llm_intel.executive_thesis)
        lines.append("")
        if trajectory:
            traj_label = trajectory.trajectory_type.replace("_", " ").title()
            lines.append(f"Career trajectory:  **{traj_label}** ({int(trajectory.confidence_score * 100)}% confidence)")
    else:
        # Deterministic fallback
        traj_label = trajectory.trajectory_type.replace("_", " ").title() if trajectory else "Professional"
        traj_conf = f" ({int(trajectory.confidence_score * 100)}% confidence)" if trajectory else ""
        lines.append(f"Career trajectory:  **{traj_label}**{traj_conf}")
        lines.append("")

        fs_pct = int(profile.functional_strength_score * 100)
        lines.append(f"Functional strength: **{fs_pct}%**")
        lines.append("")

        top_skills = [s.value for s in profile.functional.core_skills[:5]]
        if top_skills:
            lines.append(f"Core signals:  {', '.join(top_skills)}.")
            lines.append("")

        zog = profile.adaptive.zone_of_genius
        if zog and zog.value:
            lines.append(f"Zone of Genius: {zog.value[:180]}")
            lines.append("")

        if trajectory:
            lines.append(trajectory.explanation)
            lines.append("")

        sectors = sorted(
            {r.sector or r.inferred_industry for r in roles if r.sector or r.inferred_industry}
        )
        if sectors:
            lines.append(f"Sector exposure: {', '.join(sectors[:4])}.")

    # With a target role: append a PATHWAY DECISION CONTEXT block after the thesis.
    # Use a single blank line separator — two blanks (\n\n\n) would split the section.
    if executive_report:
        lines += ["", _heading("PATHWAY DECISION CONTEXT"), ""]
        lines += _decision_content_lines(executive_report)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 2 — Career DNA Snapshot (heuristic scores)
# ---------------------------------------------------------------------------

_SCORE_LABELS = [
    ("career_coherence",     "Career Coherence"),
    ("transferability",      "Transferability"),
    ("market_alignment",     "Market Alignment"),
    ("promotion_readiness",  "Promotion Readiness"),   # label overridden below when target supplied
    ("narrative_strength",   "Narrative Strength"),
    ("strategic_optionality","Strategic Options"),
    ("execution_gap",        "Execution Gap"),
]

_EXEC_GAP_NOTE = (
    "A lower Execution Gap score is better — it means stated ambitions are well-matched by evidence."
)

_COMPOUND_SEP = re.compile(r"\s*/\s*|\s*,\s*|\s+or\s+", re.I)


def _s2_dna_snapshot(
    heuristic_scores: Optional[HeuristicScoreSet],
    input_data: Optional[RawInput] = None,
    llm_judgment: Optional[object] = None,
) -> str:
    lines = [_heading("CAREER DNA SNAPSHOT"), ""]
    if not heuristic_scores:
        lines.append("Scoring could not be completed for this profile.")
        return "\n".join(lines)

    target = input_data.target_role if input_data else None
    is_compound = bool(target and len(_COMPOUND_SEP.split(target)) > 1)

    for attr, label in _SCORE_LABELS:
        if attr == "promotion_readiness":
            if is_compound:
                label = "Executive Pathway Readiness"
            elif target:
                label = "Target Role Readiness"
        hs = getattr(heuristic_scores, attr)
        padded = (label + ":").ljust(27)

        # Use LLM-adjusted score for readiness when an adjustment was applied
        if attr == "promotion_readiness" and llm_judgment:
            score = llm_judgment.final_adjusted_score
            explanation = hs.explanation
            adj = llm_judgment.score_adjustment
            tag = f" *(+{adj} advisory)" if adj > 0 else (
                f" *({adj} advisory)" if adj < 0 else ""
            )
            lines.append(f"{padded} **{score}/100** — {explanation}{tag}")
        else:
            lines.append(f"{padded} **{hs.score}/100** — {hs.explanation}")

    lines.append("")
    lines.append(_EXEC_GAP_NOTE)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 3 — Role-by-Role Intelligence Map
# ---------------------------------------------------------------------------

def _role_signals(role: ExtractedRole) -> list[str]:
    subs = []
    # Use taxonomy-inferred skills when available
    if role.inferred_skills_by_category:
        for cat in CATEGORY_PRIORITY:
            skills = role.inferred_skills_by_category.get(cat, [])
            if not skills:
                continue
            label = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
            skill_strs = []
            for skill in skills[:2]:
                ev = role.skill_evidence.get(skill, "")
                if ev:
                    ev_short = ev[:55] + ("…" if len(ev) > 55 else "")
                    skill_strs.append(f"{skill} — {ev_short}")
                else:
                    skill_strs.append(skill)
            padded = (label + ":").ljust(15)
            subs.append(f"    {padded} {'; '.join(skill_strs)}")
            if len(subs) >= 4:
                break
    else:
        # Fallback: raw keyword signals
        if role.commercial_signals:
            subs.append(f"    Commercial:     {'; '.join(role.commercial_signals[:2])}")
        if role.leadership_signals:
            subs.append(f"    Leadership:     {'; '.join(role.leadership_signals[:2])}")
        if role.strategic_signals:
            subs.append(f"    Strategic:      {'; '.join(role.strategic_signals[:2])}")
        if role.technical_signals:
            subs.append(f"    Technical:      {'; '.join(role.technical_signals[:2])}")
    if role.evidence_snippets:
        subs.append(f"    Evidence:       {role.evidence_snippets[0]}")
    return subs


def _s3_role_map(roles: List[ExtractedRole]) -> str:
    if not roles:
        return "\n".join([_heading("ROLE-BY-ROLE INTELLIGENCE MAP"), "", "No role history extracted."])

    lines = [_heading("ROLE-BY-ROLE INTELLIGENCE MAP"), ""]
    for role in roles:
        # Header line
        years = ""
        if role.start_year:
            end = role.end_year or "present"
            dur = f"  [{role.inferred_duration}]" if role.inferred_duration else ""
            years = f" | {role.start_year}–{end}{dur}"

        fn   = role.inferred_function.replace("_", " ").title() if role.inferred_function else None
        snr  = role.inferred_seniority.replace("_", " ").title() if role.inferred_seniority else role.seniority
        rt   = role.role_type.replace("_", " ").title() if role.role_type else None

        meta_parts = [p for p in [fn, snr, rt] if p]
        meta = "  |  ".join(meta_parts) if meta_parts else None

        lines.append(f"  - **{role.title}** — {role.organisation}{years}")
        if meta:
            lines.append(f"    {meta}")

        for sig in _role_signals(role):
            lines.append(sig)
        lines.append("")

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Section 4 — Career Trajectory Pattern
# ---------------------------------------------------------------------------

def _s4_trajectory(trajectory: Optional[CareerTrajectory]) -> str:
    lines = [_heading("CAREER TRAJECTORY PATTERN"), ""]
    if not trajectory:
        lines.append("Trajectory analysis was not available for this profile.")
        return "\n".join(lines)

    label = trajectory.trajectory_type.replace("_", " ").title()
    conf  = int(trajectory.confidence_score * 100)
    lines += [
        f"Type:        **{label}**",
        f"Confidence:  {conf}%",
        "",
        trajectory.explanation,
    ]
    if trajectory.supporting_evidence:
        lines += ["", "Supporting evidence:"]
        for ev in trajectory.supporting_evidence:
            lines.append(f"  - {ev}")
    if trajectory.risks_or_limitations:
        lines += ["", "Limitations:"]
        for r in trajectory.risks_or_limitations[:3]:
            lines.append(f"  - {r}")
    if trajectory.secondary_trajectory:
        sec = trajectory.secondary_trajectory
        sec_label = sec.trajectory_type.replace("_", " ").title()
        lines += ["", f"Secondary pattern:  {sec_label} — {sec.explanation}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 5 — External Market Context
# ---------------------------------------------------------------------------

def _s5_market_context(input_data: RawInput) -> str:
    lines = [_heading("EXTERNAL MARKET CONTEXT"), ""]
    if input_data.market_context_notes:
        lines.append("The following market context was provided for this report.")
        lines.append("Evidence type: market context (manually provided).")
        lines.append("")
        # Surface the notes directly, wrapped at sentence level
        notes = input_data.market_context_notes.strip()
        for sentence in _split_sentences(notes):
            lines.append(f"  - {sentence}.")
    else:
        lines += [
            "No external market data was provided for this report.",
            "",
            "  - Market alignment has been assessed from profile signals alone.",
            "  - Salary benchmarks, job posting trends, and macroeconomic factors have not been incorporated.",
            "  - For a fully grounded assessment, paste current market research into the market_context_notes field.",
        ]
    if input_data.location:
        lines += ["", f"Geography:  {input_data.location}"]
    if input_data.timeframe:
        lines += ["", f"Timeframe:  {input_data.timeframe}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 6 — Target Role / Promotion Delta (or Inferred Pathways)
# ---------------------------------------------------------------------------

_BAND_LABELS: dict[str, str] = {
    "strong":       "Strong — ready to approach the market",
    "credible":     "Credible — one focused programme closes the gap",
    "partial":      "Partial — development needed before market approach",
    "early-stage":  "Early-stage — significant repositioning required",
}


def _s6_compound_pathways(
    compound_pathways: list,
    input_data: RawInput,
    llm_judgment: Optional[object] = None,
) -> str:
    lines = [
        _heading("TARGET ROLE / PROMOTION DELTA"), "",
        "Because the stated objective contains multiple possible executive pathways, Career DNA has",
        "assessed each pathway separately rather than treating it as a single role.",
        "",
    ]

    for pw in compound_pathways:  # already sorted best→worst
        fit_pct = int(pw.fit_score * 100)
        band_label = _BAND_LABELS.get(pw.readiness_band, pw.readiness_band.title())
        lines += [
            f"**{pw.pathway_name.upper()}**",
            f"Fit score:    **{fit_pct}%**",
            f"Readiness:    {band_label}",
        ]
        if pw.key_strengths:
            lines.append(f"Strengths:    {', '.join(pw.key_strengths[:4])}")
        if pw.key_gaps:
            lines.append(f"Gaps:         {', '.join(pw.key_gaps[:2])}")
        lines.append(f"Assessment:   {pw.interpretation}")
        lines.append("")

    # Overall summary — ordered by readiness_score (same as pipeline sort)
    best = compound_pathways[0]
    worst = compound_pathways[-1]
    lines += [
        "OVERALL READINESS",
        "─" * 40,
        f"Most ready pathway:  {best.pathway_name} (readiness {best.readiness_score}/100, {best.readiness_band})",
    ]
    if len(compound_pathways) >= 2:
        second = compound_pathways[1]
        lines.append(f"Second pathway:      {second.pathway_name} (readiness {second.readiness_score}/100, {second.readiness_band})")
    if len(compound_pathways) >= 3:
        rs = worst.readiness_score
        if rs < 45:
            furthest_label = "significant development required"
        elif rs < 55:
            furthest_label = "most development required"
        elif rs < 70:
            furthest_label = "most positioning work required"
        else:
            furthest_label = "comparable pathway — minor differentiation required"
        lines.append(f"Furthest pathway:    {worst.pathway_name} (readiness {worst.readiness_score}/100) — {furthest_label}")

    # LLM pathway intelligence — replaces old score-adjustment block
    if llm_judgment and getattr(llm_judgment, "pathway_judgment", None):
        lines += [
            "",
            "PATHWAY INTELLIGENCE",
            "─" * 40,
            llm_judgment.pathway_judgment,
        ]

    if input_data.career_concerns:
        lines += ["", "Career concerns raised:"]
        for concern in input_data.career_concerns[:2]:
            lines.append(f"  - {concern}")

    return "\n".join(lines)


def _s6_target_delta(
    pivot_delta: Optional[PivotDeltaReport],
    decision_plan: Optional[DecisionUpgradePlan],
    stakeholder_feedback: Optional[StakeholderFeedback],
    input_data: RawInput,
    profile: CareerDNAProfile,
    trajectory: Optional[CareerTrajectory],
    compound_pathways: Optional[list] = None,
    llm_judgment: Optional[object] = None,
) -> str:
    # Compound pathway view takes priority when multiple pathways were assessed
    if compound_pathways and len(compound_pathways) > 1:
        return _s6_compound_pathways(compound_pathways, input_data, llm_judgment)

    if not pivot_delta or not stakeholder_feedback:
        return _s6_inferred_pathways(profile, trajectory, input_data)

    role = pivot_delta.target_role
    fit_pct = int(pivot_delta.overall_fit_score * 100)
    friction = _friction_label(pivot_delta.overall_fit_score)
    readiness = _READINESS_COPY.get(stakeholder_feedback.verdict, "Assessment not available.")
    verdict_label = _VERDICT_DISPLAY.get(stakeholder_feedback.verdict, stakeholder_feedback.verdict)

    lines = [_heading("TARGET ROLE / PROMOTION DELTA"), "",
             f"Target role:          {role}",
             f"Fit score:            **{fit_pct}%**",
             f"Hiring verdict:       **{verdict_label}**",
             f"Friction:             {friction}",
             f"Readiness:            {readiness}",
             ""]

    # Transferable strengths
    if pivot_delta.strongest_matches:
        lines += ["Transferable strengths:"]
        for m in pivot_delta.strongest_matches[:4]:
            lines.append(f"  - {m}")
        lines.append("")

    # Priority gaps
    if pivot_delta.priority_gaps:
        lines += ["Priority gaps:"]
        for gap in pivot_delta.priority_gaps[:4]:
            sev = "Critical" if gap.severity >= 0.7 else "Notable" if gap.severity >= 0.45 else "Minor"
            lines.append(f"  - **{gap.label}** [{sev}]: {gap.implication}")
        lines.append("")

    # Narrative bridge
    if pivot_delta.narrative_repositioning:
        lines += ["Narrative bridge:"]
        for line in pivot_delta.narrative_repositioning[:2]:
            lines.append(f"  - {line}")
        lines.append("")

    # Stepping stone roles
    if pivot_delta.priority_gaps:
        lines += ["Stepping-stone roles:"]
        seen: set[str] = set()
        for gap in pivot_delta.priority_gaps[:3]:
            ss = _STEPPING_STONE_MAP.get(gap.gap_type)
            if ss and ss not in seen:
                lines.append(f"  - {ss}")
                seen.add(ss)

    return "\n".join(lines)


def _s6_inferred_pathways(
    profile: CareerDNAProfile,
    trajectory: Optional[CareerTrajectory],
    input_data: RawInput,
) -> str:
    lines = [
        _heading("STRATEGIC PATHWAYS (INFERRED)"), "",
        "No explicit target role was provided.",
        "The following pathways are inferred from your career profile and trajectory.",
        "They are indicative, not assessed — provide a target role for a grounded transition analysis.",
        "",
    ]
    traj_type = trajectory.trajectory_type if trajectory else "unclear"
    options = _TRAJECTORY_OPTIONS.get(traj_type, _TRAJECTORY_OPTIONS["unclear"])

    # Supplement with pivot_directions from profile
    pd_options = [
        f"{pd.title}: {pd.rationale}" if pd.rationale else pd.title
        for pd in profile.pivot_directions[:2]
        if pd.title.strip()
    ]
    combined = (pd_options + options)[:3]

    for opt in combined:
        lines.append(f"  - {opt}")

    if input_data.career_concerns:
        lines += ["", "Career concerns raised:"]
        for concern in input_data.career_concerns[:3]:
            lines.append(f"  - {concern}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 7 — Transferable Advantage
# ---------------------------------------------------------------------------

def _s7_transferable_advantage(
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
    llm_intel: Optional[object] = None,
) -> str:
    lines = [_heading("TRANSFERABLE ADVANTAGE"), ""]

    # LLM synthesis statement — distinctive positioning in prose
    if llm_intel and getattr(llm_intel, "transferable_advantage", None):
        lines.append("Career positioning:")
        lines.append(f"  {llm_intel.transferable_advantage}")
        lines.append("")

    # Taxonomy-inferred skill profile (aggregated across all roles)
    if any(r.inferred_skills_by_category for r in roles):
        merged_by_cat, top_skills_taxonomy, merged_evidence = aggregate_skills(roles)
        if merged_by_cat:
            lines.append("Skill profile (inferred from CV evidence):")
            for cat in CATEGORY_PRIORITY:
                skills = merged_by_cat.get(cat, [])
                if not skills:
                    continue
                label = CATEGORY_LABELS.get(cat, cat)
                skill_parts = []
                for skill in skills[:3]:
                    ev = merged_evidence.get(skill, "")
                    if ev:
                        ev_short = ev[:60] + ("…" if len(ev) > 60 else "")
                        skill_parts.append(f"{skill} — \"{ev_short}\"")
                    else:
                        skill_parts.append(skill)
                lines.append(f"  - **{label}**: {', '.join(skill_parts)}")
            lines.append("")

    # Core skills (LLM-inferred from questionnaire + CV)
    core_skills = profile.functional.core_skills[:6]
    if core_skills:
        lines.append("Core skills (inferred):")
        for s in core_skills:
            conf = f"{int(s.confidence_score * 100)}%"
            lines.append(f"  - {s.value}  [{conf} confidence]")
        lines.append("")

    # Domain expertise
    domains = profile.functional.domain_expertise[:4]
    if domains:
        lines.append("Domain expertise:")
        for d in domains:
            lines.append(f"  - {d.value}")
        lines.append("")

    # Achievement proof points
    achs = profile.functional.notable_achievements[:3]
    if achs:
        lines.append("Achievement proof points:")
        for a in achs:
            lines.append(f"  - {a.impact_summary or a.raw_text[:120]}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 8 — Career Risks and Blind Spots
# ---------------------------------------------------------------------------

def _s8_risks(
    profile: CareerDNAProfile,
    trajectory: Optional[CareerTrajectory],
    llm_intel: Optional[object] = None,
) -> str:
    lines = [_heading("CAREER RISKS AND BLIND SPOTS"), ""]
    items: list[str] = []

    # LLM positioning risks — specific to this profile and target context
    if llm_intel and getattr(llm_intel, "positioning_risks", None):
        items.append(llm_intel.positioning_risks)

    # Deterministic risks — key tensions and trajectory limitations
    for t in profile.key_tensions[:2]:
        items.append(f"{t.label}: {t.implication}")

    if trajectory and trajectory.risks_or_limitations:
        for r in trajectory.risks_or_limitations[:2]:
            items.append(r)

    for rf in profile.risk_flags[:2]:
        items.append(rf.explanation)

    if not items:
        items.append("No significant career risks identified from available data.")

    lines.append(_bullet_list(items))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 9 — Strategic Career Options
# ---------------------------------------------------------------------------

def _s9_strategic_options(
    profile: CareerDNAProfile,
    pivot_delta: Optional[PivotDeltaReport],
    decision_plan: Optional[DecisionUpgradePlan],
    input_data: RawInput,
    trajectory: Optional[CareerTrajectory],
    llm_intel: Optional[object] = None,
) -> str:
    lines = [_heading("STRATEGIC CAREER OPTIONS"), ""]

    # LLM-generated options — specific to this person's evidence and context
    if llm_intel and getattr(llm_intel, "strategic_options", None):
        lines.append(_bullet_list(llm_intel.strategic_options[:4], labelled=True))
        return "\n".join(lines)

    # Deterministic fallback
    traj_type = trajectory.trajectory_type if trajectory else "unclear"
    options = []
    for pd in profile.pivot_directions[:3]:
        if pd.title.strip():
            fit_str = f"  [Fit: {int(pd.fit_score * 100)}%]" if pd.fit_score else ""
            options.append(f"{pd.title}{fit_str}: {pd.rationale or 'Based on transferable skills.'}")

    traj_opts = _TRAJECTORY_OPTIONS.get(traj_type, [])
    for opt in traj_opts:
        if len(options) >= 4:
            break
        if input_data.target_role and input_data.target_role.lower() in opt.lower():
            continue
        options.append(opt)

    if not options:
        options = [
            "Provide a target role for a targeted options analysis.",
            "Supply industry_curiosity or transition_goal to generate sector-specific options.",
        ]

    lines.append(_bullet_list(options[:4], labelled=True))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 10 — Recommended Pathway
# ---------------------------------------------------------------------------

def _s10_recommended_pathway(
    profile: CareerDNAProfile,
    pivot_delta: Optional[PivotDeltaReport],
    stakeholder_feedback: Optional[StakeholderFeedback],
    decision_plan: Optional[DecisionUpgradePlan],
    trajectory: Optional[CareerTrajectory],
    input_data: RawInput,
    llm_intel: Optional[object] = None,
) -> str:
    lines = [_heading("RECOMMENDED PATHWAY"), ""]

    # LLM-authored rationale — specific, evidence-grounded recommendation
    if llm_intel and getattr(llm_intel, "recommended_pathway_rationale", None):
        rec = (
            getattr(llm_intel, "recommended_pathway", None)
            or (pivot_delta.target_role if pivot_delta else None)
            or (input_data.target_role or "")
        )
        lines.append(f"Primary recommendation: pursue {rec}." if rec else "")
        lines.append("")
        lines.append(llm_intel.recommended_pathway_rationale)
        return "\n".join(lines)

    # Deterministic fallback
    if pivot_delta and decision_plan and stakeholder_feedback:
        role = pivot_delta.target_role
        verdict = stakeholder_feedback.verdict
        lines += [f"Primary recommendation: pursue {role}.", ""]
        if verdict == "strong_yes":
            lines.append("The profile is ready. Activate your network and begin approaching the market now.")
        elif verdict == "credible":
            lines.append(
                "The profile is credible. Close the one or two specific gaps identified, then approach the market."
            )
        else:
            lines.append(
                "The profile is not yet ready for the primary target. "
                "Complete the stepping-stone sequence first, then re-evaluate."
            )
        lines.append("")
        if decision_plan.fastest_path_actions:
            lines.append("Fastest path:")
            lines.append(f"  - {decision_plan.fastest_path_actions[0]}")
    else:
        traj_type = trajectory.trajectory_type if trajectory else "unclear"
        traj_opts = _TRAJECTORY_OPTIONS.get(traj_type, [])
        primary = traj_opts[0] if traj_opts else None
        if primary and ": " in primary:
            title, rationale = primary.split(": ", 1)
            lines += [f"Primary recommendation: {title}.", "", rationale, ""]
        elif primary:
            lines += [primary, ""]
        top_skills = [s.value for s in profile.functional.core_skills[:3]]
        if top_skills:
            lines.append(f"This recommendation is grounded in your strongest signals: {', '.join(top_skills)}.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 11 — 30/60/90-Day Action Plan
# ---------------------------------------------------------------------------

def _s11_action_plan(
    decision_plan: Optional[DecisionUpgradePlan],
    pivot_narrative: Optional[PivotNarrative],
    profile: CareerDNAProfile,
    trajectory: Optional[CareerTrajectory],
    input_data: RawInput,
    llm_intel: Optional[object] = None,
) -> str:
    lines = [_heading("30/60/90-DAY ACTION PLAN"), ""]

    # LLM-generated plan — personalised to this profile's specific gaps and context
    if llm_intel and getattr(llm_intel, "action_plan_items", None):
        lines.append(_bullet_list(llm_intel.action_plan_items[:5]))
        return "\n".join(lines)

    # Deterministic fallback — decision_plan then trajectory lookup
    if decision_plan:
        if pivot_narrative and pivot_narrative.execution_plan:
            items = pivot_narrative.execution_plan[:5]
        else:
            buckets = ["0–30 days", "30–60 days", "60–90 days", "90 days+", "Ongoing"]
            items = [
                f"{buckets[i] if i < len(buckets) else 'Ongoing'}: {action.rstrip('.')}."
                for i, action in enumerate(decision_plan.fastest_path_actions[:5])
            ]
        lines.append(_bullet_list(items))
        return "\n".join(lines)

    traj_type = trajectory.trajectory_type if trajectory else "unclear"
    actions = _TRAJECTORY_ACTIONS.get(traj_type, _DEFAULT_ACTIONS)

    if input_data.career_concerns:
        concern = input_data.career_concerns[0]
        actions = list(actions) + [f"Ongoing: Address stated concern — {concern}."]

    lines.append(_bullet_list(actions[:5]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 12 — Evidence Appendix
# ---------------------------------------------------------------------------

def _s12_evidence_appendix(
    roles: List[ExtractedRole],
    input_data: RawInput,
    profile: CareerDNAProfile,
) -> str:
    lines = [_heading("EVIDENCE APPENDIX"), ""]

    # CV evidence
    total_signals = (
        len(profile.functional.core_skills)
        + len(profile.functional.domain_expertise)
        + len(profile.functional.notable_achievements)
    )
    evidence_snippets = sum(len(r.evidence_snippets) for r in roles)
    lines += [
        f"CV evidence:              {len(roles)} roles parsed, {total_signals} signals extracted, {evidence_snippets} quantified evidence snippets.",
    ]

    # Questionnaire evidence
    q_fields = [
        ("zone_of_genius",   input_data.zone_of_genius),
        ("conflict_marker",  input_data.conflict_marker),
        ("never_again",      input_data.never_again),
    ]
    q_provided = sum(1 for _, v in q_fields if v and v.strip())
    q_extra = len(input_data.questionnaire_answers or {})
    if q_provided > 0 or q_extra > 0:
        lines.append(f"Questionnaire evidence:   {q_provided} core fields + {q_extra} additional answers provided.")
    else:
        lines.append("Questionnaire evidence:   Not provided — report is based on CV signals only.")

    # Inferred evidence
    inferred_count = len(profile.functional.core_skills) + len(profile.adaptive.personality_traits)
    lines.append(f"Inferred evidence:        {inferred_count} signals inferred from CV and questionnaire data.")

    # Market context
    if input_data.market_context_notes:
        word_count = len(input_data.market_context_notes.split())
        lines.append(f"Market context evidence:  Provided ({word_count} words). Incorporated into market alignment assessment.")
    else:
        lines.append("Market context evidence:  Not provided. Market alignment estimated from profile signals only.")

    # Target role context
    if input_data.target_role:
        lines.append(f"Target role context:      User-specified — {input_data.target_role}.")
    else:
        lines.append("Target role context:      Not specified — pathways are inferred, not assessed against a stated goal.")

    # Evidence quality note
    lines += [
        "",
        "Evidence quality note: Where evidence is weak or inferred, this report has stated that explicitly rather than overclaiming.",
        "Inferred signals are labelled. CV evidence is extracted directly from provided text.",
    ]

    return "\n".join(lines)


# ===========================================================================
# Public entry point — 12-section report
# ===========================================================================

def format_career_dna_report(
    input_data: RawInput,
    profile: CareerDNAProfile,
    roles: List[ExtractedRole],
    career_trajectory: Optional[CareerTrajectory],
    heuristic_scores: Optional[HeuristicScoreSet],
    pivot_delta: Optional[PivotDeltaReport] = None,
    pivot_narrative: Optional[PivotNarrative] = None,
    stakeholder_feedback: Optional[StakeholderFeedback] = None,
    decision_plan: Optional[DecisionUpgradePlan] = None,
    executive_report: Optional[ExecutiveTransitionReport] = None,
    compound_pathways: Optional[list] = None,
    llm_judgment: Optional[object] = None,
) -> str:
    SEP = "\n\n\n"
    li = llm_judgment  # shorthand — all updated sections accept llm_intel kwarg
    sections = [
        _s1_thesis_or_decision(executive_report, profile, roles, career_trajectory, input_data, llm_intel=li),
        _s2_dna_snapshot(heuristic_scores, input_data, li),
        _s3_role_map(roles),
        _s4_trajectory(career_trajectory),
        _s5_market_context(input_data),
        _s6_target_delta(pivot_delta, decision_plan, stakeholder_feedback, input_data, profile, career_trajectory, compound_pathways, li),
        _s7_transferable_advantage(profile, roles, llm_intel=li),
        _s8_risks(profile, career_trajectory, llm_intel=li),
        _s9_strategic_options(profile, pivot_delta, decision_plan, input_data, career_trajectory, llm_intel=li),
        _s10_recommended_pathway(profile, pivot_delta, stakeholder_feedback, decision_plan, career_trajectory, input_data, llm_intel=li),
        _s11_action_plan(decision_plan, pivot_narrative, profile, career_trajectory, input_data, llm_intel=li),
        _s12_evidence_appendix(roles, input_data, profile),
    ]
    return SEP.join(s for s in sections if s)
