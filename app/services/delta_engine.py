from __future__ import annotations

from typing import List

from app.schemas import CareerDNAProfile, PivotDeltaReport, PivotGap, TargetRoleProfile, WeightedSignal

# ---------------------------------------------------------------------------
# Synonym expansion table
# Each key is a target-role phrase (lowercase); values are alternative signals
# in a typical CV that carry the same meaning.
# ---------------------------------------------------------------------------
_SYNONYMS: dict[str, list[str]] = {
    # Operational
    "operational improvement": [
        "process optimisation", "operational efficiency", "workflow redesign",
        "transformation", "restructuring", "efficiency", "optimisation",
        "operating costs", "streamlin", "process improvement",
    ],
    "ebitda growth": [
        "operating profit", "margin improvement", "profitability", "cost reduction",
        "efficiency", "ebitda", "earnings growth", "operating cost",
    ],
    "ebitda": [
        "operating profit", "margin", "profitability", "cost reduction",
        "operating costs", "earnings", "cost savings", "efficiency",
    ],
    "ebitda bridge": [
        "cost reduction", "margin improvement", "profitability", "efficiency programme",
        "operating costs",
    ],
    "value creation": [
        "transformation", "performance improvement", "cost reduction", "scaling",
        "revenue growth", "efficiency programme", "value deliver", "optimisation",
    ],
    "buy-and-build": ["acquisition", "m&a", "bolt-on", "mergers", "inorganic"],
    "due diligence": ["business review", "assessment", "commercial analysis", "evaluation"],
    "portfolio management": [
        "programme management", "managing multiple", "cross-functional", "projects",
        "project portfolio",
    ],
    "100-day planning": [
        "transformation", "change programme", "onboarding", "100 day",
        "planning", "implementation plan",
    ],
    "100-day plan": [
        "transformation plan", "change programme", "100 day", "implementation plan",
        "transition plan",
    ],
    "exit preparation": ["exit", "disposal", "sale preparation", "ipo", "transaction"],
    "operating model": [
        "operations", "operational", "organisation design", "business model",
        "operating structure", "delivery model",
    ],
    # PE credibility
    "backed business": ["private equity", "pe-backed", "investor-backed", "backed"],
    "portfolio company": ["portfolio", "managed business", "operating company"],
    "pe-backed": ["private equity", "pe ", "investor-backed", "backed"],
    "operational transformation": [
        "operational", "transformation", "restructuring", "change management",
        "operating model", "process transformation",
    ],
    "management team assessment": [
        "team leadership", "talent", "executive team", "people management",
        "leadership team", "team assessment",
    ],
    "bolt-on acquisition": ["acquisition", "m&a", "deal", "bolt-on"],
    "multiple expansion": ["margin", "profitability", "valuation", "growth", "expansion"],
    "investment thesis": ["strategy", "strategic", "investment", "thesis", "rationale"],
    "lbo": ["leveraged", "buyout", "private equity", "pe"],
    # Leadership
    "board member": [
        "board", "stakeholder", "governance", "non-executive", "director",
        "board reporting",
    ],
    "board reporting": ["board", "stakeholder", "governance", "exec reporting"],
    "operating partner": ["operations lead", "transformation lead", "operating"],
    "transformation lead": [
        "transformation", "led transformation", "change lead",
        "change management", "drove transformation",
    ],
    "interim": ["interim", "contract", "acting"],
    # Commercial
    "revenue growth": ["revenue", "growth", "scaling", "commercial", "top-line"],
    "margin expansion": ["margin", "profitability", "cost reduction", "efficiency"],
    "cost reduction": [
        "reduced costs", "operating costs", "cost saving", "efficiency",
        "optimisation", "savings", "reduced operating",
    ],
    "commercial excellence": ["commercial", "sales", "revenue", "customer", "go-to-market"],
    "customer retention": ["customer", "client", "retention", "satisfaction", "churn"],
    "pricing": ["price", "pricing strategy", "monetisation", "revenue model"],
    # Leadership / general
    "stakeholder management": [
        "stakeholder", "stakeholder alignment", "executive engagement",
        "board engagement", "influencing",
    ],
    "cross-functional": ["cross-functional", "cross functional", "matrix", "multi-functional"],
    "organisational design": [
        "organisational", "org design", "restructur", "team design",
        "operating model",
    ],
    "p&l ownership": [
        "p&l", "profit and loss", "budget", "revenue accountability",
        "financial ownership", "business unit",
    ],
    "p&l management": [
        "p&l", "profit and loss", "budget", "revenue accountability",
        "cost management",
    ],
    "capital allocation": ["capital", "investment", "budget allocation", "resource allocation"],
    "fundraising": ["fundraise", "capital raise", "series", "investment round", "raise"],
    # CEO-specific
    "board governance": ["board", "governance", "board reporting", "exec", "compliance"],
    "executive leadership": [
        "executive", "leadership", "c-suite", "senior leadership", "exec team",
        "leadership team",
    ],
    "full p&l responsibility": [
        "p&l", "business unit", "revenue accountability", "budget", "full ownership",
    ],
    "scaled organisation": ["scaled", "scaling", "growth", "headcount", "expanded"],
    # VC-specific
    "deal sourcing": ["deal", "sourcing", "pipeline", "origination", "network"],
    "founder relationships": ["founder", "startup", "entrepreneur", "relationship"],
    "startup scaling": ["startup", "scaling", "growth", "early stage", "series"],
    "term sheets": ["term sheet", "investment", "deal terms", "negotiation"],
    "arr": ["arr", "recurring revenue", "mrr", "subscription"],
    "mrr": ["mrr", "monthly revenue", "recurring", "arr"],
    "churn": ["churn", "retention", "attrition", "customer loss"],
    "ltv": ["ltv", "lifetime value", "customer value"],
    "cac": ["cac", "customer acquisition", "acquisition cost"],
}


def _signal_values(signals: List[WeightedSignal]) -> list[str]:
    return [s.value.lower() for s in signals]


def _term_matched(term: str, exact_corpus: str, synonym_corpus: str) -> bool:
    """
    Return True if:
    - term appears literally anywhere in exact_corpus (full CV text), OR
    - any synonym of term appears in synonym_corpus (structured signal values only).
    Keeping synonym matching restricted to structured signals prevents common
    narrative words (e.g. "efficiency") from over-matching PE-specific terms.
    """
    t = term.lower()
    if t in exact_corpus:
        return True
    return any(syn in synonym_corpus for syn in _SYNONYMS.get(t, []))


def _match_rate(
    exact_corpus: str,
    synonym_corpus: str,
    targets: list[str],
) -> tuple[float, list[str]]:
    """Return (match_rate 0–1, list of matched target terms)."""
    if not targets:
        return 1.0, []
    matched = [t for t in targets if _term_matched(t, exact_corpus, synonym_corpus)]
    return len(matched) / len(targets), matched


def _missing_terms(targets: list[str], exact_corpus: str, synonym_corpus: str) -> list[str]:
    """Return target terms that matched neither literally nor via synonym."""
    return [t for t in targets if not _term_matched(t, exact_corpus, synonym_corpus)]


def _build_corpus(profile: CareerDNAProfile) -> str:
    parts: list[str] = []
    for s in profile.functional.core_skills:
        parts.append(s.value)
    for s in profile.functional.domain_expertise:
        parts.append(s.value)
    if profile.functional.leadership_style:
        parts.append(profile.functional.leadership_style.value)
    for a in profile.functional.notable_achievements:
        parts.append(a.raw_text)
        if a.impact_summary:
            parts.append(a.impact_summary)
    for s in profile.adaptive.personality_traits:
        parts.append(s.value)
    for s in profile.adaptive.motivators:
        parts.append(s.value)
    if profile.adaptive.zone_of_genius:
        parts.append(profile.adaptive.zone_of_genius.value)
    for s in profile.aspirational.industry_interests:
        parts.append(s.value)
    for s in profile.aspirational.career_goals:
        parts.append(s.value)
    if profile.functional.career_trajectory:
        parts.append(profile.functional.career_trajectory)
    return " ".join(parts).lower()


def compute_pivot_delta(
    profile: CareerDNAProfile,
    target: TargetRoleProfile,
    raw_cv_text: str = "",
) -> PivotDeltaReport:
    # exact_corpus: structured signals + raw CV text for literal term matching
    exact_corpus = _build_corpus(profile)
    if raw_cv_text:
        exact_corpus = exact_corpus + " " + raw_cv_text.lower()

    skill_values  = _signal_values(profile.functional.core_skills)
    domain_values = _signal_values(profile.functional.domain_expertise)
    leadership_values = (
        _signal_values(profile.adaptive.personality_traits)
        + _signal_values(profile.adaptive.motivators)
        + ([profile.adaptive.zone_of_genius.value.lower()] if profile.adaptive.zone_of_genius else [])
        + ([profile.functional.leadership_style.value.lower()] if profile.functional.leadership_style else [])
    )

    # synonym_corpus: only structured WeightedSignal values — prevents common
    # narrative words from triggering over-broad synonym matches.
    synonym_corpus = " ".join(skill_values + domain_values + leadership_values)

    # --- Match rates (two-tier: literal on full corpus, synonyms on structured signals) ---
    skill_rate, skill_matches = _match_rate(exact_corpus, synonym_corpus, target.core_skills)
    cred_rate,  cred_matches  = _match_rate(exact_corpus, synonym_corpus, target.credibility_markers)
    lead_rate,  lead_matches  = _match_rate(exact_corpus, synonym_corpus, target.leadership_signals)
    comm_rate,  comm_matches  = _match_rate(exact_corpus, synonym_corpus, target.commercial_signals)
    lang_rate,  lang_matches  = _match_rate(exact_corpus, synonym_corpus, target.language_markers)

    # --- Overall fit score (weighted) ---
    overall_fit = round(
        skill_rate * 0.30
        + cred_rate  * 0.25
        + lead_rate  * 0.25
        + comm_rate  * 0.20,
        3,
    )

    # --- Strongest matches (deduplicated, target-language labels) ---
    strongest_matches = list(dict.fromkeys(
        skill_matches[:3] + cred_matches[:2] + lead_matches[:2] + comm_matches[:2]
    ))[:8]

    # --- Gap detection (uses synonym-aware missing check) ---
    gaps: list[PivotGap] = []

    if skill_rate < 0.50:
        missing = _missing_terms(target.core_skills, exact_corpus, synonym_corpus)[:4]
        gaps.append(PivotGap(
            gap_type="skill_gap",
            label="Core Skill Gap",
            severity=round(1.0 - skill_rate, 2),
            evidence=missing,
            implication=(
                f"Profile demonstrates {skill_rate:.0%} of required core skills for {target.role_name}. "
                "Missing skills may raise recruiter or interview-panel concerns."
            ),
            recommended_action=(
                "Build evidence of missing skills through project work, advisory roles, "
                "or targeted upskilling before repositioning."
            ),
        ))

    if cred_rate < 0.40:
        missing = _missing_terms(target.credibility_markers, exact_corpus, synonym_corpus)[:4]
        gaps.append(PivotGap(
            gap_type="credibility_gap",
            label="Credibility Marker Gap",
            severity=round(1.0 - cred_rate, 2),
            evidence=missing,
            implication=(
                f"Fewer than {cred_rate:.0%} of expected credibility signals are visible in the profile. "
                "Hiring panels may question fitness for the level."
            ),
            recommended_action=(
                "Identify 2–3 past achievements that can be reframed using target-role language. "
                "Add board/advisory experience where possible."
            ),
        ))

    if lead_rate < 0.40:
        missing = _missing_terms(target.leadership_signals, exact_corpus, synonym_corpus)[:4]
        gaps.append(PivotGap(
            gap_type="leadership_gap",
            label="Leadership Signal Gap",
            severity=round(1.0 - lead_rate, 2),
            evidence=missing,
            implication=(
                "Leadership narrative does not yet align with expectations for "
                f"{target.role_name}. Decision-makers may perceive a leadership ceiling."
            ),
            recommended_action=(
                "Anchor the CV and interview narrative around scale, culture, and team impact. "
                "Seek a board seat, NED role, or senior advisory position."
            ),
        ))

    if comm_rate < 0.40:
        missing = _missing_terms(target.commercial_signals, exact_corpus, synonym_corpus)[:4]
        gaps.append(PivotGap(
            gap_type="commercial_gap",
            label="Commercial Signal Gap",
            severity=round(1.0 - comm_rate, 2),
            evidence=missing,
            implication=(
                "Commercial language and revenue-ownership signals are weak relative to "
                f"{target.role_name} expectations."
            ),
            recommended_action=(
                "Quantify commercial impact of past roles (revenue influenced, deals closed, "
                "margin improvement) and surface it earlier in the CV."
            ),
        ))

    if lang_rate < 0.30:
        missing = _missing_terms(target.language_markers, exact_corpus, synonym_corpus)[:4]
        gaps.append(PivotGap(
            gap_type="narrative_gap",
            label="Narrative Language Gap",
            severity=round(1.0 - lang_rate, 2),
            evidence=missing,
            implication=(
                f"The profile does not yet use the language of {target.role_name}. "
                "Even strong profiles lose out when the vocabulary doesn't pattern-match."
            ),
            recommended_action=(
                "Rewrite the CV summary and LinkedIn headline to mirror the language "
                f"used in {target.role_name} job descriptions and the profile taxonomy."
            ),
        ))

    gaps.sort(key=lambda g: g.severity, reverse=True)

    # --- Narrative repositioning ---
    narrative: list[str] = []
    if strongest_matches:
        narrative.append(
            f"Lead with proven strengths: {', '.join(strongest_matches[:3])}."
        )
    if gaps:
        top_gap = gaps[0]
        narrative.append(
            f"Address the '{top_gap.label}' head-on: {top_gap.recommended_action}"
        )
    if target.common_objections:
        narrative.append(
            f"Pre-empt the most common objection: '{target.common_objections[0]}'"
        )
    narrative.append(
        f"Reframe your trajectory as deliberate preparation for {target.role_name}."
    )

    # --- 90-day actions ---
    actions: list[str] = []
    for gap in gaps[:3]:
        actions.append(gap.recommended_action)
    if not actions:
        actions.append(
            f"Your profile is already well-positioned for {target.role_name}. "
            "Focus on deepening relationships in target organisations."
        )
    if target.common_objections:
        actions.append(
            f"Prepare a concise rebuttal to: '{target.common_objections[0]}'"
        )

    return PivotDeltaReport(
        target_role=target.role_name,
        overall_fit_score=overall_fit,
        strongest_matches=strongest_matches,
        priority_gaps=gaps,
        narrative_repositioning=narrative,
        ninety_day_actions=actions[:5],
    )
