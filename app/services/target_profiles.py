from __future__ import annotations

import re

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

    "head of strategy": TargetRoleProfile(
        role_name="Head of Strategy",
        seniority="director",
        core_skills=[
            "strategic planning", "business strategy", "stakeholder management",
            "cross-functional leadership", "transformation", "change management",
            "market analysis", "organisational design",
        ],
        credibility_markers=[
            "strategy", "strategic", "transformation", "board", "advisory",
            "corporate strategy", "market entry", "growth strategy",
            "business case", "strategic initiatives", "executive committee",
        ],
        leadership_signals=[
            "head of strategy", "strategy director", "director", "strategy team",
            "strategic leadership", "strategic planning", "strategy function",
            "executive committee", "exco", "board reporting", "transformation",
        ],
        commercial_signals=[
            "revenue", "growth", "market", "commercial", "p&l",
            "business performance", "value creation", "investment",
            "budget", "cost", "margin", "financial",
        ],
        language_markers=[
            "strategic direction", "business strategy", "market intelligence",
            "competitive positioning", "strategic priorities", "roadmap",
            "long-term", "strategic options", "scenario planning", "horizon",
        ],
        common_objections=[
            "no p&l ownership at director level",
            "limited pure strategy role experience",
            "operational background may overshadow strategic positioning",
            "mckinsey exit before manager level",
        ],
    ),

    "head of transformation": TargetRoleProfile(
        role_name="Head of Transformation",
        seniority="director",
        core_skills=[
            "transformation", "change management", "programme management",
            "stakeholder management", "cross-functional leadership",
            "operating model design", "organisational design", "delivery",
        ],
        credibility_markers=[
            "transformation", "change programme", "operating model",
            "restructuring", "business transformation", "programme delivery",
            "executive sponsorship", "board reporting",
        ],
        leadership_signals=[
            "head of transformation", "transformation director", "change director",
            "programme director", "director", "cross-functional", "transformation lead",
        ],
        commercial_signals=[
            "cost reduction", "efficiency", "savings", "margin", "budget",
            "benefits realisation", "business case", "roi", "p&l",
        ],
        language_markers=[
            "transformation", "operating model", "future state", "change management",
            "benefits", "delivery", "programme", "roadmap", "execution",
        ],
        common_objections=[
            "too focused on delivery rather than design",
            "limited C-suite sponsorship experience",
            "no full P&L ownership",
        ],
    ),

    "group ceo": TargetRoleProfile(
        role_name="Group CEO",
        seniority="c-suite",
        core_skills=[
            "p&l", "transformation", "commercial", "revenue",
            "board", "executive team", "managing director",
            "market entry", "partnerships", "regional expansion", "licensing",
        ],
        credibility_markers=[
            "regional p&l", "full p&l", "managing director", "chief executive",
            "scaled organisation", "board reporting", "business transformation",
            "commercial growth", "revenue growth", "regional leadership",
            "executive vice president", "ceo", "transformation",
        ],
        leadership_signals=[
            "ceo", "managing director", "executive vice president", "evp",
            "regional president", "executive team", "c-suite", "board",
            "chief executive", "group leader",
        ],
        commercial_signals=[
            "revenue", "growth", "market expansion", "commercial", "partnerships",
            "business development", "p&l", "profit", "market share",
            "licensing", "distribution",
        ],
        language_markers=[
            "regional expansion", "group strategy", "strategic direction", "governance",
            "organisational leadership", "market leadership", "accountability",
            "commercial strategy", "long-term value",
        ],
        common_objections=[
            "regional rather than group/enterprise scope",
            "media-sector experience may limit perceived versatility",
            "limited board-level governance exposure",
            "no public company CEO track record",
        ],
    ),

    "regional president": TargetRoleProfile(
        role_name="Regional President",
        seniority="c-suite",
        core_skills=[
            "regional p&l", "managing director", "market entry",
            "commercial", "revenue", "regional expansion",
            "content monetisation", "distribution", "executive vice president",
            "apac", "transformation",
        ],
        credibility_markers=[
            "regional p&l", "regional team", "apac", "asia pacific",
            "managing director", "regional head", "evp", "revenue growth",
            "multi-country", "seven offices", "regional offices",
        ],
        leadership_signals=[
            "managing director", "regional head", "evp", "executive vice president",
            "regional president", "country manager", "led regional team", "180 staff",
            "regional team", "chief executive", "ceo",
        ],
        commercial_signals=[
            "revenue growth", "market share", "commercial", "partnerships",
            "business development", "distribution", "licensing", "market expansion",
            "tripled revenue", "grew revenue",
        ],
        language_markers=[
            "regional strategy", "market leadership", "apac", "growth strategy",
            "commercial excellence", "regional expansion", "go-to-market",
            "regional p&l", "business growth",
        ],
        common_objections=[
            "regional rather than global scope",
            "media-specific experience may limit sector transfer",
            "no full P&L autonomy at group level",
        ],
    ),

    "non-executive director": TargetRoleProfile(
        role_name="Non-Executive Director",
        seniority="executive",
        core_skills=[
            "governance",
            "board",
            "p&l",
            "aicd",
            "accountability",
            "executive",
            "industry",
            "transformation",
        ],
        credibility_markers=[
            # Formal appointment — only candidates who have held a formal NED seat match these
            "non-executive director of",
            "appointed director",
            "independent director",
            "company directorship",
            "board appointment",
            "public company board",
            "private company board",
            # Governance qualification (AICD + committee experience)
            "aicd",
            "australian institute of company directors",
            "audit committee",
            "remuneration committee",
            # Supporting board engagement evidence (advisory/reporting counts but is not sufficient alone)
            "board member",
            "board reporting",
            "governance",
            "ned",
        ],
        leadership_signals=[
            "board", "governance", "executive committee", "managing director",
            "ceo", "chief executive", "listed board", "chairman",
            "board reporting", "board risk committee",
        ],
        commercial_signals=[
            "revenue", "commercial", "p&l", "financial oversight",
            "governance", "board",
        ],
        language_markers=[
            "governance", "board oversight", "fiduciary", "accountability",
            "strategic challenge", "risk appetite", "stewardship",
            "long-term value", "shareholder interests", "board engagement",
        ],
        common_objections=[
            "no listed company board experience",
            "limited audit or remuneration committee exposure",
            "executive rather than governance mindset",
            "no formal director qualifications (e.g. AICD)",
        ],
    ),

    "strategic advisory": TargetRoleProfile(
        role_name="Strategic Advisory Portfolio",
        seniority="executive",
        core_skills=[
            "advisory",              # was "trusted advisor" — literal in most advisory CVs
            "commercial partnerships", # kept — literal match common
            "growth strategy",       # kept — literal match common
            "market entry",          # kept — literal match common
            "sector expertise",      # kept — synonymed to industry/domain
            "board communication",   # kept — synonymed to board/stakeholder
            "client development",    # kept — synonymed to commercial/partnerships
            "content monetisation",  # kept — synonymed to content/licensing
        ],
        credibility_markers=[
            "advisory", "board advisor", "strategic advisor", "founded",
            "commercial growth", "transformation", "partnerships",
            "commercial strategy", "media expertise", "regional leadership",
        ],
        leadership_signals=[
            "managing director", "ceo", "evp", "executive", "advisor",
            "board", "founder", "transformation", "chief executive",
        ],
        commercial_signals=[
            "commercial", "revenue", "growth", "business development",
            "partnerships", "client", "market", "licensing", "distribution",
        ],
        language_markers=[
            "advisory", "strategic advisory", "trusted advisor", "sector insight",
            "commercial judgment", "pattern recognition", "board-level",
            "portfolio", "advisory board", "media strategy",
        ],
        common_objections=[
            "advisory income may be unpredictable",
            "no established advisory client base",
            "advisory positioning requires strong personal brand",
            "competition from established advisory firms",
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
    # PE / VC
    "pe operating partner":         "private equity operating partner",
    "pe partner":                   "private equity operating partner",
    "operating partner":            "private equity operating partner",
    "vc partner":                   "venture capital partner",
    "vc":                           "venture capital partner",
    "gp":                           "venture capital partner",
    # C-suite
    "coo":                          "chief operating officer",
    "chief executive officer":      "ceo",
    "chief exec":                   "ceo",
    "executive chair":              "ceo",
    "executive chairman":           "ceo",
    # GM / MD
    "gm":                           "general manager",
    "md":                           "general manager",
    "managing director":            "general manager",
    # Group CEO / Regional President
    "group chief executive":        "group ceo",
    "group chief executive officer": "group ceo",
    "regional ceo":                 "group ceo",
    "president":                    "regional president",
    "regional md":                  "regional president",
    "apac president":               "regional president",
    "apac md":                      "regional president",
    "apac managing director":       "regional president",
    # NED / Board
    "ned":                          "non-executive director",
    "non executive director":       "non-executive director",
    "board director":               "non-executive director",
    "independent director":         "non-executive director",
    "board member":                 "non-executive director",
    # Advisory / Portfolio
    "advisory portfolio":           "strategic advisory",
    "portfolio career":             "strategic advisory",
    "strategic advisor":            "strategic advisory",
    "advisory career":              "strategic advisory",
    "fractional executive":         "strategic advisory",
    # Strategy
    "strategy director":            "head of strategy",
    "director of strategy":         "head of strategy",
    "chief strategy officer":       "head of strategy",
    "cso":                          "head of strategy",
    "vp strategy":                  "head of strategy",
    "head of corporate strategy":   "head of strategy",
    "head of strategy & planning":  "head of strategy",
    # Transformation
    "transformation director":      "head of transformation",
    "change director":              "head of transformation",
    "programme director":           "head of transformation",
    "head of change":               "head of transformation",
}

_STOPWORDS = {"the", "a", "an", "of", "in", "at", "for", "and", "or", "to"}

_COMPOUND_SPLIT = re.compile(r"\s*/\s*|\s*,\s*|\s+or\s+", re.I)


def parse_compound_target(target_role: str) -> list[str]:
    """
    Split a compound target string into individual pathway names.

    Examples:
        "Group CEO / Regional President / NED"  → ["Group CEO", "Regional President", "NED"]
        "CEO, COO, or GM"                       → ["CEO", "COO", "GM"]
    """
    parts = _COMPOUND_SPLIT.split(target_role)
    return [p.strip() for p in parts if p.strip()]


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

    # 3. Substring containment — prefer longest match to avoid short keys absorbing specific ones
    best_sub, best_len = None, 0
    for k, profile in _LOOKUP.items():
        if (k in key or key in k) and len(k) > best_len:
            best_len, best_sub = len(k), profile
    if best_sub:
        return best_sub

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
