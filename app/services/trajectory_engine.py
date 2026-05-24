from __future__ import annotations

from typing import List, Optional

from app.schemas import CareerTrajectory, ExtractedRole

# ---------------------------------------------------------------------------
# Trajectory type definitions
# ---------------------------------------------------------------------------

TRAJECTORY_TYPES = {
    "linear_specialist":       "Career has deepened in a single domain with consistent upward progression.",
    "strategic_generalist":    "Career spans multiple functions, with breadth used as the differentiator.",
    "operator_to_strategist":  "Career began in execution/operations and has progressively moved toward strategy and leadership.",
    "technical_to_commercial": "Career originated in technical or engineering roles and has transitioned toward commercial or business roles.",
    "builder_profile":         "Career shows a pattern of building: teams, products, companies, or capabilities from scratch.",
    "corporate_climber":       "Career follows a clear institutional ladder within large organisations.",
    "pivot_candidate":         "Career contains one or more significant industry or function changes.",
    "early_formation":         "Career is at an early stage with fewer than 5 years of experience.",
    "underleveraged_talent":   "Career shows strong capability signals that have not been matched by seniority or scope progression.",
    "unclear":                 "Career pattern does not fit a single clear type given available data.",
}

_BUILDER_KEYWORDS = {"founded", "co-founded", "built", "launched", "created", "established", "started"}
# Weaker builder verbs only count when paired with "from scratch" or founding context
_BUILDER_WEAK = {"built", "created", "established", "started"}
_BUILDER_STRONG = {"founded", "co-founded", "launched"}
_STRATEGY_KEYWORDS = {"strategy", "strategic", "advisory", "consulting", "transformation"}
_TECHNICAL_KEYWORDS = {"engineer", "developer", "architect", "data", "software", "technical", "technology"}
_COMMERCIAL_KEYWORDS = {"commercial", "sales", "revenue", "business development", "p&l", "general manager"}


def _total_years(roles: List[ExtractedRole]) -> float:
    if not roles:
        return 0.0
    years = [r.start_year for r in roles if r.start_year]
    if not years:
        return 0.0
    earliest = min(years)
    latest = max((r.end_year or 2025 for r in roles if r.end_year or r.start_year), default=2025)
    return max(0.0, latest - earliest)


def _seniority_levels(roles: List[ExtractedRole]) -> list[str]:
    return [r.inferred_seniority or r.seniority or "" for r in roles if r.inferred_seniority or r.seniority]


def _functions(roles: List[ExtractedRole]) -> list[str]:
    return [r.inferred_function for r in roles if r.inferred_function]


def _has_keywords(roles: List[ExtractedRole], keywords: set[str]) -> bool:
    corpus = " ".join(
        f"{r.title} {r.inferred_function or ''} {' '.join(r.core_responsibilities)}"
        for r in roles
    ).lower()
    return any(kw in corpus for kw in keywords)


def _is_builder_profile(roles: List[ExtractedRole]) -> bool:
    """
    Builder profile requires a strong signal, not just common verbs like 'built'.
    Rules (any one is sufficient):
      1. Role title contains 'founder' or 'co-founder'
      2. Strong builder keyword (founded, co-founded, launched) appears anywhere
      3. Weak builder verb + 'from scratch' in the same responsibility corpus
    """
    titles_lower = " ".join(r.title.lower() for r in roles)
    if "founder" in titles_lower or "co-founder" in titles_lower:
        return True

    responsibilities = " ".join(
        " ".join(r.core_responsibilities) for r in roles
    ).lower()

    if any(kw in responsibilities for kw in _BUILDER_STRONG):
        return True

    if any(kw in responsibilities for kw in _BUILDER_WEAK) and "from scratch" in responsibilities:
        return True

    return False


def _unique_functions(roles: List[ExtractedRole]) -> int:
    return len(set(f for f in _functions(roles) if f))


def _unique_sectors(roles: List[ExtractedRole]) -> int:
    sectors = [r.sector or r.inferred_industry for r in roles if r.sector or r.inferred_industry]
    return len(set(sectors))


def _is_progressing(roles: List[ExtractedRole]) -> bool:
    """True if seniority is broadly increasing over time.
    Sorts by start_year ascending so the comparison is earliest→latest,
    regardless of the order roles appear in the CV text.
    """
    _ORDER = {
        "early_career": 0, "junior": 1, "junior_mid": 2, "mid": 3,
        "mid_senior": 4, "senior": 5, "senior_leadership": 6,
        "executive": 7, "c_suite": 8, "founder": 9,
    }
    # Sort chronologically (earliest first) so levels[-1] = most recent role
    sorted_roles = sorted(roles, key=lambda r: r.start_year or 0)
    levels = [_ORDER.get(s, -1) for s in _seniority_levels(sorted_roles) if s]
    if len(levels) < 2:
        return True
    return levels[-1] >= levels[0]


def _classify_primary(roles: List[ExtractedRole], total_years: float) -> tuple[str, float, list[str]]:
    evidence: list[str] = []

    if total_years < 4:
        return "early_formation", 0.85, ["Fewer than 4 years of career history"]

    funcs = _functions(roles)
    unique_f = _unique_functions(roles)
    unique_s = _unique_sectors(roles)
    progressing = _is_progressing(roles)

    # Builder profile — requires founder title, 'launched/founded', or 'built X from scratch'
    if _is_builder_profile(roles):
        evidence.append("Founding, building, or launching signals detected across roles")
        return "builder_profile", 0.80, evidence

    # Technical → commercial transition
    titles_lower = [r.title.lower() for r in roles]
    early_technical = any(
        any(kw in t for kw in _TECHNICAL_KEYWORDS) for t in titles_lower[:max(1, len(titles_lower)//2)]
    )
    late_commercial = any(
        any(kw in t for kw in _COMMERCIAL_KEYWORDS) for t in titles_lower[len(titles_lower)//2:]
    )
    if early_technical and late_commercial:
        evidence.append("Early-career technical roles transitioning to commercial or leadership roles")
        return "technical_to_commercial", 0.75, evidence

    # Operator → strategist
    early_operational = any("operat" in (r.inferred_function or "").lower() for r in roles[:max(1, len(roles)//2)])
    late_strategic = any("strateg" in (r.inferred_function or "").lower() for r in roles[len(roles)//2:])
    if early_operational and late_strategic:
        evidence.append("Operational foundation with progressive move into strategy and leadership")
        return "operator_to_strategist", 0.75, evidence

    # Pivot candidate — many function changes
    if unique_f >= 3 and unique_s >= 3:
        evidence.append(f"{unique_f} distinct functions across {unique_s} sectors")
        return "pivot_candidate", 0.70, evidence

    # Strategic generalist — broad but not pivoting
    if unique_f >= 2 and unique_s >= 2 and progressing:
        evidence.append(f"Breadth across {unique_f} functions and {unique_s} sectors with upward progression")
        return "strategic_generalist", 0.68, evidence

    # Corporate climber — same sector, progressing seniority
    if unique_s <= 1 and progressing and len(roles) >= 3:
        evidence.append("Consistent sector focus with clear seniority progression within large organisations")
        return "corporate_climber", 0.72, evidence

    # Linear specialist — single function, progressing
    if unique_f <= 1 and progressing:
        fn = funcs[0] if funcs else "a single domain"
        evidence.append(f"Deep specialisation within {fn} with consistent upward progression")
        return "linear_specialist", 0.70, evidence

    # Underleveraged — high signal density, low seniority progression
    if not progressing and total_years > 8:
        evidence.append("Strong CV signal density with limited seniority progression relative to experience")
        return "underleveraged_talent", 0.55, evidence

    return "unclear", 0.40, ["Insufficient role history clarity to assign a primary trajectory"]


def _classify_secondary(
    roles: List[ExtractedRole],
    primary: str,
) -> Optional[CareerTrajectory]:
    """Return a secondary trajectory only when a meaningful secondary pattern exists."""
    funcs = _functions(roles)
    unique_f = _unique_functions(roles)
    progressing = _is_progressing(roles)

    # Operator_to_strategist as secondary for strategic_generalist
    if primary == "strategic_generalist" and any("operat" in f for f in funcs):
        return CareerTrajectory(
            trajectory_type="operator_to_strategist",
            confidence_score=0.50,
            explanation="Operational depth co-exists with broad generalist range.",
            supporting_evidence=["Operational function signals visible alongside cross-functional roles"],
            risks_or_limitations=["May be perceived as too broad without a clear anchor"],
        )

    # Corporate_climber as secondary for linear_specialist
    if primary == "linear_specialist" and progressing and len(roles) >= 3:
        return CareerTrajectory(
            trajectory_type="corporate_climber",
            confidence_score=0.45,
            explanation="Specialisation has followed an institutional progression pathway.",
            supporting_evidence=["Seniority gains within a consistent domain"],
            risks_or_limitations=["Institutional progression may not signal entrepreneurial readiness"],
        )

    return None


def _risks(trajectory_type: str, roles: List[ExtractedRole]) -> list[str]:
    risk_map: dict[str, list[str]] = {
        "linear_specialist": [
            "Depth may limit perceived versatility for senior generalist or leadership roles",
            "Single-domain exposure creates sector-concentration risk",
        ],
        "strategic_generalist": [
            "Breadth without a clear specialisation anchor can undermine credibility in specialist hiring processes",
            "May be perceived as lacking depth in any single area",
        ],
        "operator_to_strategist": [
            "Strategic credentials may lack the seniority markers expected by top-tier hiring panels",
            "Operational background may overshadow strategic positioning in early screening",
        ],
        "technical_to_commercial": [
            "Commercial track record may still be shallow relative to career stage",
            "Technical background may create a ceiling perception in purely commercial roles",
        ],
        "builder_profile": [
            "Building experience is valued differently across corporate vs. investor contexts",
            "Entrepreneurial history may raise questions about ability to operate within structure",
        ],
        "corporate_climber": [
            "Limited exposure to ambiguity or early-stage environments",
            "Institutional progression may not translate to portfolio-company or entrepreneurial contexts",
        ],
        "pivot_candidate": [
            "Multiple transitions may raise questions about focus and commitment",
            "Gap in deep domain credibility across any single vertical",
        ],
        "early_formation": [
            "Insufficient experience base to generate high-confidence assessments",
            "Trajectory is still forming — early signals may not reflect longer-term direction",
        ],
        "underleveraged_talent": [
            "Risk of being trapped in execution roles without a clear promotion trigger",
            "Narrative may not match actual capability — credentialing and positioning work needed",
        ],
        "unclear": [
            "Insufficient data to assess trajectory reliably",
            "Report conclusions should be treated as indicative",
        ],
    }
    return risk_map.get(trajectory_type, [])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_career_trajectory(roles: List[ExtractedRole]) -> CareerTrajectory:
    if not roles:
        return CareerTrajectory(
            trajectory_type="unclear",
            confidence_score=0.20,
            explanation="No role history available to analyse.",
            supporting_evidence=[],
            risks_or_limitations=["Report requires CV content to produce trajectory analysis"],
        )

    total_years = _total_years(roles)
    primary_type, confidence, evidence = _classify_primary(roles, total_years)
    secondary = _classify_secondary(roles, primary_type)

    return CareerTrajectory(
        trajectory_type=primary_type,
        confidence_score=round(confidence, 2),
        explanation=TRAJECTORY_TYPES[primary_type],
        supporting_evidence=evidence,
        risks_or_limitations=_risks(primary_type, roles),
        secondary_trajectory=secondary,
    )
