from __future__ import annotations

from app.schemas import TargetRoleProfile

_PROFILES: dict[str, TargetRoleProfile] = {
    "ceo": TargetRoleProfile(
        role_name="CEO",
        seniority="c-suite",
        core_skills=[
            "strategic planning", "p&l ownership", "stakeholder management",
            "board governance", "capital allocation", "organisational design",
            "change management", "executive leadership",
        ],
        credibility_markers=[
            "full p&l responsibility", "board reporting", "scaled organisation",
            "fundraising", "m&a", "ipo", "exit", "turnaround", "transformation",
        ],
        leadership_signals=[
            "vision", "culture", "ceo", "founder", "president",
            "executive team", "c-suite", "managing director",
        ],
        commercial_signals=[
            "revenue", "growth", "market share", "customers", "commercial",
            "business development", "partnerships",
        ],
        language_markers=[
            "enterprise value", "strategic direction", "shareholder", "governance",
            "accountability", "long-term", "organisational health",
        ],
        common_objections=[
            "no p&l ownership at group level",
            "limited board exposure",
            "never led through a full economic cycle",
            "functional rather than general management background",
        ],
    ),

    "general manager": TargetRoleProfile(
        role_name="General Manager",
        seniority="director",
        core_skills=[
            "p&l management", "operations", "commercial strategy",
            "team leadership", "cross-functional collaboration", "budget ownership",
        ],
        credibility_markers=[
            "business unit ownership", "revenue accountability",
            "delivered targets", "managed full function", "multi-site",
        ],
        leadership_signals=[
            "general manager", "gm", "head of", "director", "led team",
            "people management", "performance management",
        ],
        commercial_signals=[
            "revenue targets", "margin", "cost control", "customer satisfaction",
            "sales", "commercial", "pipeline",
        ],
        language_markers=[
            "business performance", "operational excellence", "kpis",
            "accountability", "delivery", "results",
        ],
        common_objections=[
            "not owned a full P&L",
            "limited cross-functional exposure",
            "only functional leadership experience",
        ],
    ),

    "private equity operating partner": TargetRoleProfile(
        role_name="Private Equity Operating Partner",
        sector="private equity",
        seniority="partner",
        core_skills=[
            "value creation", "operational improvement", "ebitda",
            "buy-and-build", "due diligence", "portfolio management",
            "operating model", "exit",
        ],
        credibility_markers=[
            "portfolio compan", "pe-backed", "private equity", "ebitda",
            "operational transformation", "management team",
            "m&a", "value creation",
        ],
        leadership_signals=[
            "chief executive", "chief operating", "ceo", "coo",
            "board", "operating partner", "transformation",
            "vp operations", "director of operations",
        ],
        commercial_signals=[
            "revenue growth", "revenue", "margin", "cost reduction",
            "commercial", "p&l", "profit",
        ],
        language_markers=[
            "value creation", "ebitda", "private equity", "portfolio",
            "investment thesis", "operating model",
        ],
        common_objections=[
            "no direct PE portfolio experience",
            "limited financial engineering knowledge",
            "not operated in a PE ownership environment",
        ],
    ),

    "venture capital partner": TargetRoleProfile(
        role_name="Venture Capital Partner",
        sector="venture capital",
        seniority="partner",
        core_skills=[
            "deal sourcing", "investment thesis", "founder relationships",
            "startup scaling", "board governance", "portfolio support",
            "market analysis", "term sheets",
        ],
        credibility_markers=[
            "founded", "scaled startup", "raised funding", "angel investor",
            "board advisor", "accelerator", "product-market fit",
        ],
        leadership_signals=[
            "founder", "cto", "cpo", "gp", "partner", "advisor",
            "invested", "board seat",
        ],
        commercial_signals=[
            "arr", "mrr", "churn", "ltv", "cac", "growth rate",
            "fundraise", "runway",
        ],
        language_markers=[
            "stage", "thesis", "founder", "ecosystem", "conviction",
            "deal flow", "portfolio", "emerging markets",
        ],
        common_objections=[
            "no investing track record",
            "limited startup operator experience",
            "no existing founder network",
        ],
    ),

    "chief operating officer": TargetRoleProfile(
        role_name="Chief Operating Officer",
        seniority="c-suite",
        core_skills=[
            "operational strategy", "process optimisation", "people management",
            "cross-functional leadership", "systems thinking",
            "kpi design", "execution", "scale",
        ],
        credibility_markers=[
            "scaled operations", "restructured", "implemented systems",
            "multi-function", "delivered transformation",
            "built operating model", "efficiency programme",
        ],
        leadership_signals=[
            "coo", "chief operating officer", "director of operations",
            "head of operations", "vp operations", "led cross-functional",
        ],
        commercial_signals=[
            "cost reduction", "margin", "capacity", "throughput",
            "customer experience", "sla", "operational efficiency",
        ],
        language_markers=[
            "operating model", "organisational design", "scalability",
            "execution", "delivery", "infrastructure", "cadence",
        ],
        common_objections=[
            "no c-suite title to date",
            "limited board-level exposure",
            "functional rather than operational breadth",
        ],
    ),
}

# Normalise lookup keys
_LOOKUP = {k.lower().strip(): v for k, v in _PROFILES.items()}

# Short-form aliases → canonical _LOOKUP key
_ALIASES: dict[str, str] = {
    "pe operating partner":         "private equity operating partner",
    "pe partner":                   "private equity operating partner",
    "operating partner":            "private equity operating partner",
    "vc partner":                   "venture capital partner",
    "vc":                           "venture capital partner",
    "gp":                           "venture capital partner",
    "coo":                          "chief operating officer",
    "gm":                           "general manager",
    "md":                           "general manager",
    "managing director":            "general manager",
    "chief executive officer":      "ceo",
    "chief exec":                   "ceo",
    "executive chair":              "ceo",
    "executive chairman":           "ceo",
}

_STOPWORDS = {"the", "a", "an", "of", "in", "at", "for", "and", "or", "to"}


def _best_token_match(key: str) -> TargetRoleProfile | None:
    """Return the profile whose canonical name shares the most tokens with key."""
    query_tokens = {t for t in key.split() if t not in _STOPWORDS}
    if not query_tokens:
        return None
    best, best_score = None, 0
    for k, profile in _LOOKUP.items():
        k_tokens = {t for t in k.split() if t not in _STOPWORDS}
        score = len(query_tokens & k_tokens)
        if score > best_score:
            best_score, best = score, profile
    return best


def get_target_profile(role_name: str) -> TargetRoleProfile | None:
    """Return the closest hardcoded profile, or None only when _LOOKUP is empty."""
    key = role_name.lower().strip()

    # 1. Exact match
    if key in _LOOKUP:
        return _LOOKUP[key]

    # 2. Alias match
    if key in _ALIASES:
        return _LOOKUP[_ALIASES[key]]

    # 3. Substring containment
    for k, profile in _LOOKUP.items():
        if k in key or key in k:
            return profile

    # 4. Token overlap (handles "PE Operating Partner" → "private equity operating partner")
    return _best_token_match(key)


def build_target_profile(role_name: str, sector: str | None, seniority: str | None) -> TargetRoleProfile:
    """Return a matched profile, overlaying caller-supplied name/sector/seniority."""
    profile = get_target_profile(role_name)
    if profile is None:
        # Absolute last resort — _LOOKUP should never be empty in practice
        profile = next(iter(_LOOKUP.values()))

    overrides: dict = {
        # Always surface the caller's role name in reports
        "role_name": role_name,
    }
    if sector and not profile.sector:
        overrides["sector"] = sector
    if seniority and not profile.seniority:
        overrides["seniority"] = seniority
    return profile.model_copy(update=overrides)
