from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas import PivotDeltaReport, PivotGap, TargetRoleProfile


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class StakeholderFeedback(BaseModel):
    stakeholder_type: str
    verdict: str = Field(..., description="lean_no | borderline | credible | strong_yes")
    core_concerns: List[str] = Field(default_factory=list)
    pushback_questions: List[str] = Field(default_factory=list)
    decision_logic: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Stakeholder type detection
# ---------------------------------------------------------------------------

_STAKEHOLDER_MAP: list[tuple[str, str]] = [
    ("private equity",    "PE Partner / MD"),
    ("operating partner", "PE Partner / MD"),
    ("venture capital",   "VC General Partner"),
    ("venture",           "VC General Partner"),
    (" vc ",              "VC General Partner"),
    ("chief executive",   "CEO / Executive Chair"),
    ("ceo",               "CEO / Executive Chair"),
    ("chief operating",   "COO / Operating Committee"),
    ("coo",               "COO / Operating Committee"),
    ("general manager",   "MD / General Manager"),
]


def _detect_stakeholder_type(role_name: str) -> str:
    lower = f" {role_name.lower()} "
    for key, label in _STAKEHOLDER_MAP:
        if key in lower:
            return label
    return "Executive Hiring Committee"


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def _verdict(fit_score: float) -> str:
    if fit_score >= 0.75:
        return "strong_yes"
    if fit_score >= 0.60:
        return "credible"
    if fit_score >= 0.40:
        return "borderline"
    return "lean_no"


# ---------------------------------------------------------------------------
# Gap → objection sentences (role-aware)
# ---------------------------------------------------------------------------

_OBJECTIONS: dict[str, dict[str, str]] = {
    "PE Partner / MD": {
        "skill_gap": (
            "The operational toolkit is incomplete. Value creation at portfolio level requires "
            "more than efficiency — EBITDA bridge work, operating model design, and management "
            "team assessment need to be visible."
        ),
        "credibility_gap": (
            "I don't see the PE context here. Working adjacent to PE isn't the same as operating "
            "inside a backed business. The credibility markers we look for — EBITDA ownership, "
            "100-day delivery, IC-level reporting — are absent."
        ),
        "leadership_gap": (
            "Portfolio company work requires authority without line power. I need someone who has "
            "operated at board level, replaced management if needed, and held a CEO accountable. "
            "That track record isn't here."
        ),
        "commercial_gap": (
            "Commercial signal is thin. Operating Partners in our portfolio get pulled into "
            "commercial decisions — pricing, customer economics, revenue growth. "
            "The profile reads as cost-focused, not growth-focused."
        ),
        "narrative_gap": (
            "They're not speaking PE language. That matters because they'll be in rooms with "
            "GPs, lenders, and management teams who are. The vocabulary gap signals a steep "
            "learning curve in the wrong direction."
        ),
    },
    "VC General Partner": {
        "skill_gap": (
            "Deal sourcing, thesis-building, and portfolio governance are distinct skills — "
            "not derivable from operational experience. I need evidence of investing judgement, "
            "not just operating capability."
        ),
        "credibility_gap": (
            "No investing track record. No angel deals, no advisory equity, no co-investments. "
            "Operators make great VC partners only when they've crossed that threshold themselves."
        ),
        "leadership_gap": (
            "Sitting on a founder's board while holding them accountable is a specific skill. "
            "Where has this person done that? Corporate leadership isn't the same."
        ),
        "commercial_gap": (
            "VC commercial thinking is unit-economics-first. CAC, LTV, payback period, "
            "net revenue retention. The profile shows P&L experience but not startup commercial "
            "architecture."
        ),
        "narrative_gap": (
            "The language is enterprise, not venture. Our founders need to see someone who "
            "thinks like them — risk appetite, outlier framing, conviction under uncertainty. "
            "That's missing."
        ),
    },
    "CEO / Executive Chair": {
        "skill_gap": (
            "The CEO brief is 60% external — board, investors, major customers, M&A. "
            "The operational depth is clear but the enterprise-ownership signals are not."
        ),
        "credibility_gap": (
            "I need to see full P&L ownership at group level, not BU level. "
            "Board governance, fundraising, and capital allocation decisions need to be visible."
        ),
        "leadership_gap": (
            "Leading a C-suite is different from leading a function. The ability to set culture, "
            "manage lateral tension, and be the final decision authority — has that been tested?"
        ),
        "commercial_gap": (
            "Commercial strategy at CEO level means owning the revenue thesis. "
            "Not supporting sales — setting direction. That signal isn't here."
        ),
        "narrative_gap": (
            "The CV reads as an operator, not a CEO. The framing, the language, the evidence "
            "hierarchy — all of it needs repositioning before it lands with a board."
        ),
    },
    "COO / Operating Committee": {
        "skill_gap": (
            "COO scope demands cross-functional authority — finance, ops, tech, people. "
            "The profile shows functional depth but not breadth of ownership."
        ),
        "credibility_gap": (
            "Where has this person owned a full operating model? Delivering within one "
            "isn't the same as designing and running one."
        ),
        "leadership_gap": (
            "COO means being the CEO's operational alter ego. That requires political acuity, "
            "ability to hold the exec team accountable, and standing in front of the board. "
            "Evidence of that is thin."
        ),
        "commercial_gap": (
            "COOs who succeed own the commercial operating rhythm — pipeline, conversion, "
            "retention. The profile is efficiency-heavy without commercial integration."
        ),
        "narrative_gap": (
            "The framing doesn't signal COO readiness. The language of operating model, "
            "scalability, and organisational cadence isn't coming through clearly."
        ),
    },
    "MD / General Manager": {
        "skill_gap": (
            "GM scope means owning the business — P&L, customers, and people simultaneously. "
            "The profile shows functional expertise but not full business ownership."
        ),
        "credibility_gap": (
            "I need to see revenue accountability, not just cost accountability. "
            "Where have they owned the top line?"
        ),
        "leadership_gap": (
            "Managing a function and managing a business are different jobs. "
            "Has this person navigated the political complexity of a GM role?"
        ),
        "commercial_gap": (
            "Commercial instinct needs to come through more clearly. "
            "GMs live and die on revenue performance, not efficiency."
        ),
        "narrative_gap": (
            "The pitch doesn't read as a general manager. It reads as a senior functional leader "
            "who is ready to make that step. That gap needs to close before this lands."
        ),
    },
}

_DEFAULT_OBJECTIONS: dict[str, str] = {
    "skill_gap":        "Core skill coverage doesn't fully meet the brief.",
    "credibility_gap":  "Credibility markers expected at this level are not clearly visible.",
    "leadership_gap":   "Leadership track record at the required scope is not yet established.",
    "commercial_gap":   "Commercial ownership signals are weaker than the role demands.",
    "narrative_gap":    "The profile language doesn't yet match the target role vocabulary.",
}


def _get_objection(gap: PivotGap, stakeholder: str) -> str:
    role_map = _OBJECTIONS.get(stakeholder, {})
    return role_map.get(gap.gap_type, _DEFAULT_OBJECTIONS.get(gap.gap_type, gap.implication))


# ---------------------------------------------------------------------------
# Gap → pushback questions (role-aware, evidence-referenced)
# ---------------------------------------------------------------------------

_PUSHBACK_QUESTIONS: dict[str, dict[str, list[str]]] = {
    "PE Partner / MD": {
        "skill_gap": [
            "Walk me through your EBITDA bridge work on a specific business. "
            "What was the starting point, what levers did you pull, and what was the verified outcome?",
            "You've driven operational efficiency — but what percentage of that translated "
            "directly to EBITDA? How do you prove that?",
            "Have you ever designed a full operating model for a PE-backed business from scratch? "
            "What did that process look like?",
        ],
        "credibility_gap": [
            "Which PE firm have you worked most closely alongside? "
            "What did you contribute to their investment thesis, not just the operations?",
            "Have you ever presented a 100-day plan to an investment committee? "
            "What was the GP's biggest concern and how did you handle it?",
            "If I called the GP on your last deal, what would they say about your value-add "
            "beyond the operational work?",
        ],
        "leadership_gap": [
            "Have you ever replaced a portfolio company CEO? "
            "Walk me through the process — how did you diagnose the problem, make the call, "
            "and manage the transition?",
            "A portfolio MD is telling you the operating plan is unrealistic. "
            "You disagree. How do you handle that conversation without losing the relationship?",
            "How do you build authority in a business you don't own and don't run day-to-day?",
        ],
        "commercial_gap": [
            "Where have you owned revenue? Not influenced it, not supported it — owned it. "
            "Give me a specific example with numbers.",
            "Commercial decisions in portfolio companies — pricing, channel, customer mix — "
            "where have you had a seat at that table and what was your contribution?",
            "Your profile is strong on cost. PE also cares about growth. "
            "What's your track record on the growth side of value creation?",
        ],
        "narrative_gap": [
            "You're describing your work as an efficiency drive. "
            "I would describe it as a value creation programme. "
            "Why does that language distinction matter, and does it come naturally to you?",
            "If you were writing the investment committee memo on yourself as an Operating Partner, "
            "what would the value creation thesis say?",
        ],
    },
    "VC General Partner": {
        "skill_gap": [
            "What's your investment thesis in the sector you'd focus on? "
            "I need a specific, contrarian view — not a framework.",
            "Walk me through a company you would have backed two years ago that has since "
            "proved or disproved your thesis.",
            "How do you think about valuation at pre-revenue stage? "
            "What multiples do you anchor to and why?",
        ],
        "credibility_gap": [
            "Have you made any personal investments in startups? If not, why not? "
            "If yes, what was the outcome and what did you learn?",
            "Why should a Series A founder take a board seat from you over a partner "
            "with a ten-year investing track record?",
            "What's your deal flow? Be specific — how many companies have you evaluated "
            "in the last 12 months, through what channels?",
        ],
        "leadership_gap": [
            "A founder you've backed is underperforming against plan. The team is loyal to them. "
            "What do you do and what's your timeline?",
            "How do you hold a founder accountable without destroying the relationship? "
            "Give me a real example — not a hypothetical.",
        ],
        "commercial_gap": [
            "Walk me through how you'd evaluate unit economics on a B2B SaaS business "
            "at 2M ARR. What numbers matter most and why?",
            "What's a healthy CAC payback period at Series A? "
            "How does that change by sector?",
        ],
        "narrative_gap": [
            "You're describing outcomes in corporate language — efficiency, process, delivery. "
            "We think in outlier outcomes, distribution of returns, and narrative risk. "
            "How do you make that mental shift?",
            "Why VC? And specifically, why now — what's the window you think you're seeing "
            "that an existing GP doesn't?",
        ],
    },
    "CEO / Executive Chair": {
        "skill_gap": [
            "Walk me through a board meeting where the board pushed back hard on your direction. "
            "What was the dynamic and how did you handle it?",
            "Where have you owned a full P&L at group level — not BU, not function? "
            "What was the scope and what were the outcomes?",
            "What's the biggest capital allocation decision you've made independently? "
            "Not recommended to a board — made.",
        ],
        "credibility_gap": [
            "Have you run a fundraise — equity or debt? "
            "Walk me through your role in that process end-to-end.",
            "What governance experience do you have? "
            "Board composition, audit, remuneration — where have you sat at that table?",
        ],
        "leadership_gap": [
            "Your C-suite disagrees with your strategic direction. Two of them are threatening "
            "to leave. How do you handle that?",
            "How do you decide when to override your CFO on a financial decision?",
        ],
        "commercial_gap": [
            "What's your revenue thesis for a business like ours? "
            "Don't give me operational levers — give me the commercial architecture.",
            "Where have you directly influenced a major commercial relationship — "
            "not delegated it, personally owned it?",
        ],
        "narrative_gap": [
            "Your CV reads as COO-level. What's the specific moment where you transitioned "
            "from functional leader to enterprise leader? "
            "What changed in how you operated?",
        ],
    },
    "COO / Operating Committee": {
        "skill_gap": [
            "What functions have you actually owned? Not partnered with — owned, with "
            "budget authority and accountability for outcomes.",
            "Walk me through how you designed and implemented an operating model "
            "for a scaling business. What broke, and what did you do about it?",
        ],
        "credibility_gap": [
            "Where have you owned a business unit or function from setup through to scale? "
            "What were the key inflection points?",
            "Have you ever restructured an organisation? "
            "Walk me through the process, the politics, and the outcome.",
        ],
        "leadership_gap": [
            "How do you manage lateral accountability — people who don't report to you "
            "but whose outcomes you own?",
            "Describe a time you had to hold a peer accountable for performance. "
            "How did that conversation go?",
        ],
        "commercial_gap": [
            "COO at our level means owning the commercial operating rhythm alongside the CEO. "
            "Where have you sat in that seat — pipeline reviews, pricing decisions, "
            "renewal strategy?",
        ],
        "narrative_gap": [
            "How would you describe your operating philosophy in three sentences? "
            "I want to hear the language you use, not a job description.",
        ],
    },
    "MD / General Manager": {
        "skill_gap": [
            "Walk me through a period where you owned a full P&L — revenue and cost. "
            "What were the biggest decisions you made independently?",
            "Where have you managed a customer-facing function? "
            "Not supported it — owned the relationship and the revenue.",
        ],
        "credibility_gap": [
            "Have you ever been the accountable leader for missing a revenue target? "
            "What happened and what did you do?",
            "What's the largest team you've directly managed? "
            "What was the culture like when you inherited it and what did you change?",
        ],
        "leadership_gap": [
            "How do you manage someone who is technically better than you at their job?",
            "Describe a situation where you had to make an unpopular decision quickly. "
            "How did you bring the team with you?",
        ],
        "commercial_gap": [
            "GMs live on revenue performance. Where have you owned a sales or commercial target? "
            "What's the number and how did you get there?",
        ],
        "narrative_gap": [
            "Your background reads as operational. GMs need to be commercial first. "
            "How do you make that transition in how you present yourself?",
        ],
    },
}

_DEFAULT_QUESTIONS: dict[str, str] = {
    "skill_gap":        "Your skill profile doesn't fully cover the brief. What would you do about that in the first 90 days?",
    "credibility_gap":  "What's the single strongest piece of evidence you'd point to for your credibility in this role?",
    "leadership_gap":   "Describe your leadership at the level this role requires. What's the most stretching thing you've done?",
    "commercial_gap":   "Where have you owned a commercial outcome, not just influenced one?",
    "narrative_gap":    "Your CV doesn't yet read as a [role] candidate. What's your explanation for that?",
}


def _get_questions(gap: PivotGap, stakeholder: str, max_q: int = 2) -> list[str]:
    role_qs = _PUSHBACK_QUESTIONS.get(stakeholder, {})
    questions = role_qs.get(gap.gap_type, [])
    if not questions:
        questions = [_DEFAULT_QUESTIONS.get(gap.gap_type, "Tell me more about your experience in this area.")]
    return questions[:max_q]


# ---------------------------------------------------------------------------
# Decision logic text
# ---------------------------------------------------------------------------

def _build_decision_logic(
    verdict: str,
    fit_score: float,
    stakeholder: str,
    gaps: list[PivotGap],
    matches: list[str],
    objections: list[str],
) -> str:
    pct = round(fit_score * 100)
    top_match = matches[0] if matches else "operational track record"
    top_gap = gaps[0].label.lower().replace(" gap", "") if gaps else None

    if verdict == "strong_yes":
        return (
            f"At {pct}% fit, this is a strong candidate. The {top_match} signal is compelling "
            f"and the profile covers the core brief. I would move to the next stage "
            f"with specific questions around {top_gap if top_gap else 'depth of experience'}."
        )
    if verdict == "credible":
        return (
            f"Credible case at {pct}% fit. The {top_match} is real and the trajectory makes sense. "
            f"The {top_gap} concern is manageable if they can address it in interview. "
            f"I'd progress with a case study or panel to pressure-test the gaps."
        )
    if verdict == "borderline":
        return (
            f"Borderline at {pct}% fit. The transferable core is there — {top_match} is genuine. "
            f"But the {top_gap} gap creates real doubt. I'd want to see one more data point "
            f"— an advisory role, a reference from someone in the target world, or a "
            f"specific example that closes the credibility question — before committing."
        )
    # lean_no
    return (
        f"At {pct}% fit, this is a lean no from me at this stage. "
        f"The {top_gap} gap is the blocking issue — not the person, the evidence. "
        f"I'd keep the relationship warm and revisit in 12–18 months if they can "
        f"build the missing signals. Refer to a headhunter who places stretch candidates."
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def simulate_stakeholder_feedback(
    pivot_delta: PivotDeltaReport,
    target_profile: TargetRoleProfile,
) -> StakeholderFeedback:
    stakeholder = _detect_stakeholder_type(target_profile.role_name)
    verdict = _verdict(pivot_delta.overall_fit_score)

    # Core concerns: top 3 gaps → objection sentences, supplemented by common_objections
    top_gaps = pivot_delta.priority_gaps[:3]
    core_concerns: list[str] = [_get_objection(g, stakeholder) for g in top_gaps]
    if not core_concerns and target_profile.common_objections:
        core_concerns = target_profile.common_objections[:3]

    # Pushback questions: 2 questions per gap, up to 5 total
    pushback_questions: list[str] = []
    for gap in top_gaps:
        pushback_questions.extend(_get_questions(gap, stakeholder, max_q=2))
        if len(pushback_questions) >= 5:
            break
    pushback_questions = pushback_questions[:5]

    # Fallback: use common_objections as questions if no gaps
    if not pushback_questions and target_profile.common_objections:
        pushback_questions = [
            f"You'll hear this objection: '{obj}' — how do you respond?"
            for obj in target_profile.common_objections[:3]
        ]

    decision_logic = _build_decision_logic(
        verdict=verdict,
        fit_score=pivot_delta.overall_fit_score,
        stakeholder=stakeholder,
        gaps=top_gaps,
        matches=pivot_delta.strongest_matches,
        objections=core_concerns,
    )

    # Confidence: how certain the simulator is in this verdict
    # High confidence at the extremes, lower at borderline
    distance_from_boundary = min(
        abs(pivot_delta.overall_fit_score - 0.40),
        abs(pivot_delta.overall_fit_score - 0.60),
        abs(pivot_delta.overall_fit_score - 0.75),
    )
    confidence = round(min(0.55 + distance_from_boundary * 2.0, 0.92), 3)

    return StakeholderFeedback(
        stakeholder_type=stakeholder,
        verdict=verdict,
        core_concerns=core_concerns,
        pushback_questions=pushback_questions,
        decision_logic=decision_logic,
        confidence_score=confidence,
    )
