from __future__ import annotations

import re
from typing import Optional

# Short abbreviations that must match as complete tokens (not substrings of other words)
_EXACT_TOKEN_KEYWORDS: frozenset[str] = frozenset({
    "ceo", "cto", "cfo", "coo", "cpo", "cmo", "cdo", "ciso",
    "vp", "gp", "md", "svp", "evp",
})

# ---------------------------------------------------------------------------
# Seniority classification
# Rules ordered most-specific → least-specific
# ---------------------------------------------------------------------------

_SENIORITY_RULES: list[tuple[list[str], str]] = [
    (["intern", "placement", "work experience"],                    "early_career"),
    (["graduate", "junior", "associate analyst"],                   "junior"),
    (["analyst", "consultant", "associate", "coordinator"],         "junior_mid"),
    (["senior analyst", "senior consultant", "senior associate"],   "mid"),
    (["manager", "head of", "lead "],                               "mid_senior"),
    (["senior manager", "principal", "engagement manager"],         "senior"),
    (["director", "vice president", "vp "],                         "senior_leadership"),
    (["partner", "managing director", "md ", "managing partner"],   "executive"),
    (["chief ", "ceo", "cto", "cfo", "coo", "cpo", "cmo", "ciso"], "c_suite"),
    (["founder", "co-founder", "cofounder"],                        "founder"),
]

# ---------------------------------------------------------------------------
# Function classification
# ---------------------------------------------------------------------------

_FUNCTION_RULES: list[tuple[list[str], str]] = [
    (["strategy", "corporate development", "strategic planning"],           "strategy"),
    (["investment banking", "capital markets", "mergers", "m&a", "ecm", "dcm"], "investment_banking"),
    (["private equity", "buyout", "pe ", "venture capital", "vc "],         "investment_management"),
    (["consulting", "advisory", "management consulting"],                   "consulting"),
    (["operations", "operational", "supply chain", "logistics", "process"], "operations"),
    (["product", "product manager", "product management", "pm "],          "product"),
    (["engineering", "software", "developer", "architect", "devops"],      "engineering"),
    (["data", "analytics", "data science", "machine learning", "ai "],     "data_analytics"),
    (["sales", "commercial", "business development", "bd "],               "sales_commercial"),
    (["marketing", "brand", "growth", "demand generation"],                "marketing"),
    (["finance", "financial planning", "fp&a", "treasury", "controller"],  "finance"),
    (["legal", "counsel", "compliance", "regulatory", "risk"],             "legal_risk"),
    (["hr", "human resources", "people", "talent", "recruiting"],          "people"),
    (["general manager", "gm ", "country manager", "managing director"],   "general_management"),
    (["chief executive", "ceo"],                                            "executive_leadership"),
]

# ---------------------------------------------------------------------------
# Role type classification
# ---------------------------------------------------------------------------

_ROLE_TYPE_RULES: list[tuple[list[str], str]] = [
    (["founder", "co-founder", "cofounder"],                                "founder_operator"),
    (["interim", "fractional", "contract"],                                 "interim_contract"),
    (["advisor", "adviser", "board", "non-exec", "ned "],                  "advisory_board"),
    (["intern", "placement", "work experience", "graduate programme"],     "early_career_programme"),
    (["partner", "managing partner", "general partner", "gp "],            "partnership_principal"),
    (["chief ", "ceo", "cto", "cfo", "coo"],                               "c_suite_executive"),
    (["managing director", "md "],                                          "executive_director"),
    (["director"],                                                          "senior_director"),
    (["vice president", "vp "],                                             "vice_president"),
    (["manager", "head of"],                                                "functional_manager"),
    (["analyst", "associate"],                                              "analyst_associate"),
    (["consultant"],                                                        "consultant"),
    (["engineer", "developer"],                                             "individual_contributor"),
]


def _match_rules(title: str, rules: list[tuple[list[str], str]]) -> Optional[str]:
    lower = title.lower()
    # Tokenise once for exact-token lookups
    tokens = set(re.split(r'[^a-z0-9]+', lower)) - {''}
    for keywords, label in rules:
        for kw in keywords:
            kw_clean = kw.strip()
            # Use token-based matching when:
            #   (a) the keyword ends with a space (original boundary-guard convention), OR
            #   (b) the stripped keyword is in the explicit exact-token set
            # This prevents short abbreviations like "coo" matching inside "coordinator",
            # while preserving the original trailing-space intent for "pe ", "vc ", etc.
            if kw.endswith(' ') or kw_clean in _EXACT_TOKEN_KEYWORDS:
                if kw_clean in tokens:
                    return label
            elif kw_clean in lower:
                return label
    return None


def classify_title(title: str) -> dict:
    """
    Returns inferred_seniority, inferred_function, role_type for a job title.
    All values may be None if no rule matches.
    """
    return {
        "inferred_seniority": _match_rules(title, _SENIORITY_RULES),
        "inferred_function":  _match_rules(title, _FUNCTION_RULES),
        "role_type":          _match_rules(title, _ROLE_TYPE_RULES),
    }
