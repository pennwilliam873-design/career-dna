"""
Rule-based skill taxonomy and inference module.

Infers skills from role text (titles, responsibilities, achievements) without
relying on capitalised noun phrases. Each skill has named trigger phrases;
matches produce an evidence snippet taken from the source text.

No hallucination: a skill is only emitted if a trigger phrase is literally
present in the input text.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas import ExtractedRole

# ---------------------------------------------------------------------------
# Taxonomy: (skill_label, [trigger_phrases ordered longest → shortest])
# ---------------------------------------------------------------------------
# Triggers are checked case-insensitively.
# Short triggers (< 5 chars) require word boundaries to avoid false positives
# (e.g. "p&l" in "p&l ownership", not inside "compliance").
# ---------------------------------------------------------------------------

_PATTERNS: dict[str, list[tuple[str, list[str]]]] = {
    "leadership_skills": [
        ("Team Leadership",           ["led a team of", "managed a team of", "team of ",
                                       "direct reports", "headcount of", "oversaw a team",
                                       "led the team", "people manager"]),
        ("People Development",        ["talent development", "performance management",
                                       "grew the team", "hired and developed", "coaching and",
                                       "mentoring", "coached"]),
        ("Executive Presence",        ["presented to the board", "presented to exco",
                                       "board risk committee", "presented to c-suite",
                                       "exco presentation", "executive briefing",
                                       "presented to senior", "board update", "exco"]),
        ("Organisational Leadership", ["led the organisation", "led the function",
                                       "divisional leadership", "business unit leadership",
                                       "organisational leadership"]),
    ],

    "commercial_skills": [
        ("P&L Management",            ["full p&l", "p&l ownership", "revenue accountability",
                                       "p&l responsibility", "business unit p&l", "p&l"]),
        ("Budget Management",         ["combined budget", "total budget", "annual budget",
                                       "budget of ", "budget management", "budget owner",
                                       "financial responsibility", "capex", "opex", "budget"]),
        ("Cost Reduction",            ["cost reduction", "cost saving", "cost optimisation",
                                       "reduced operating cost", "operating cost reduction",
                                       "savings of ", "cost down", "reduced costs"]),
        ("Revenue Growth",            ["revenue growth", "grew revenue", "revenue increase",
                                       "top-line growth", "revenue target", "commercial growth"]),
        ("Commercial Negotiation",    ["contract negotiation", "commercial negotiation",
                                       "negotiated commercial", "vendor negotiation",
                                       "negotiated contracts", "negotiated terms"]),
        ("Vendor Management",         ["vendor consolidation", "supplier management",
                                       "vendor management", "supplier negotiation",
                                       "contract renewal", "third-party management",
                                       "vendor contracts"]),
        ("Business Development",      ["business development", "new business pipeline",
                                       "client acquisition", "market development",
                                       "won new business"]),
    ],

    "strategic_skills": [
        ("Strategic Planning",        ["strategy development", "strategic planning",
                                       "corporate strategy", "strategic direction",
                                       "developed the strategy", "strategy engagements",
                                       "strategy work"]),
        ("Operating Model Design",    ["target operating model", "operating model design",
                                       "organisational design", "org design",
                                       "operating model", "designed the operating"]),
        ("Market Analysis",           ["competitive analysis", "market intelligence",
                                       "market research", "market sizing", "market analysis",
                                       "competitive landscape"]),
        ("Business Case Development", ["developed a business case", "investment case",
                                       "cost-benefit analysis", "roi analysis",
                                       "business case"]),
        ("Growth Strategy",           ["expansion strategy", "market entry strategy",
                                       "growth strategy", "scaling strategy",
                                       "market entry"]),
        ("Corporate Development",     ["post-merger integration", "due diligence",
                                       "acquisition integration", "m&a integration",
                                       "m&a"]),
    ],

    "operational_skills": [
        ("Process Improvement",       ["process redesign", "process optimisation",
                                       "workflow redesign", "process improvement",
                                       "six sigma", "lean methodology", "streamlined"]),
        ("Programme Delivery",        ["programme management", "project governance",
                                       "programme governance", "delivery management",
                                       "project delivery"]),
        ("Implementation Management", ["deployed across", "rolled out across",
                                       "implementation plan", "go-live", "cutover",
                                       "implementation"]),
        ("Operational Excellence",    ["operational excellence", "operational improvement",
                                       "operational efficiency", "operational performance"]),
        ("Logistics & Scheduling",    ["coordinated logistics", "capacity planning",
                                       "resource scheduling", "scheduling", "logistics"]),
    ],

    "technical_skills": [
        ("Salesforce / CRM",          ["salesforce", "crm platform", "crm migration",
                                       "crm system", "customer relationship management system"]),
        ("ERP Systems",               ["erp implementation", "sap implementation",
                                       "oracle erp", "netsuite", "microsoft dynamics", "erp"]),
        ("Data & Analytics Platforms",["power bi", "tableau", "data platform",
                                       "analytics platform", "data warehouse",
                                       "data analytics", "dashboard"]),
        ("Technology Infrastructure", ["technology infrastructure", "digital infrastructure",
                                       "system implementation", "digital platform",
                                       "infrastructure projects"]),
        ("Automation",                ["workflow automation", "process automation",
                                       "robotic process", "rpa", "automated processes",
                                       "automation"]),
        ("AI / Machine Learning",     ["artificial intelligence", "machine learning",
                                       "generative ai", "predictive analytics",
                                       "large language model", "llm"]),
        ("Python / SQL",              ["python", "sql", "data engineering",
                                       "software development", "scripting"]),
    ],

    "analytical_skills": [
        ("Financial Modelling",       ["financial modelling", "three-statement model",
                                       "financial model", "dcf", "lbo model",
                                       "financial analysis", "valuation model"]),
        ("Market Sizing",             ["addressable market", "market opportunity",
                                       "market sizing", "tam", "sam"]),
        ("Scenario & Sensitivity",    ["sensitivity analysis", "scenario planning",
                                       "what-if analysis", "scenario modelling",
                                       "scenario analysis"]),
        ("Performance Measurement",   ["tracking dashboard", "performance measurement",
                                       "kpi framework", "balanced scorecard",
                                       "reporting framework", "kpi"]),
        ("Operational Diagnostics",   ["operational diagnostic", "diagnostic analysis",
                                       "root cause", "diagnostic tool",
                                       "operational analysis"]),
    ],

    "communication_skills": [
        ("Board & ExCo Reporting",    ["board risk committee", "board reporting",
                                       "exco reporting", "board presentation",
                                       "presented to the board", "presented to exco",
                                       "programme updates to exco", "board update"]),
        ("Executive Storytelling",    ["executive narrative", "executive communication",
                                       "written for c-suite", "strategic narrative",
                                       "executive presentation"]),
        ("Stakeholder Reporting",     ["stakeholder reporting", "programme update",
                                       "status report", "quarterly report",
                                       "management reporting", "progress report"]),
    ],

    "stakeholder_skills": [
        ("Stakeholder Management",    ["stakeholder management", "stakeholder engagement",
                                       "managing stakeholders", "stakeholder alignment",
                                       "key stakeholders", "stakeholder"]),
        ("Executive Engagement",      ["executive engagement", "c-suite engagement",
                                       "engagement with the board", "board engagement",
                                       "senior leadership team", "executive committee"]),
        ("Cross-Functional Collaboration", ["cross-functional teams", "across business units",
                                            "across departments", "matrix environment",
                                            "multi-disciplinary teams", "cross-functional"]),
        ("Client Relationship Management", ["account management", "client management",
                                            "client relationships", "client-facing",
                                            "customer management"]),
    ],

    "transformation_skills": [
        ("Business Transformation",   ["transformation programme", "business transformation",
                                       "enterprise transformation", "transformation across",
                                       "transformation of", "transforming"]),
        ("Change Management",         ["change management programme", "change management",
                                       "change programme", "change initiative",
                                       "managing change", "change agenda"]),
        ("Digital Transformation",    ["digital transformation", "digitalisation",
                                       "digitisation", "digital change programme"]),
        ("Agile Delivery",            ["agile delivery methodology", "agile framework",
                                       "agile methodology", "scrum", "kanban",
                                       "agile delivery", "agile"]),
        ("PMO / Programme Office",    ["programme management office", "programme office",
                                       "pmo lead", "pmo"]),
    ],

    "entrepreneurial_or_builder_skills": [
        ("Greenfield Building",       ["built from scratch", "from zero", "greenfield",
                                       "zero to one", "first of its kind"]),
        ("Startup Building",          ["co-founded", "founded", "early-stage startup",
                                       "startup environment", "venture"]),
        ("Product Development",       ["go-to-market launch", "product development",
                                       "product launch", "mvp", "prototype"]),
        ("Scaling Organisations",     ["scaled the organisation", "scaled from",
                                       "scale-up environment", "growth from"]),
        ("Innovation",                ["innovation programme", "pioneered", "novel approach",
                                       "first of its kind", "innovation"]),
    ],

    "risk_and_governance_skills": [
        ("Risk Framework Design",     ["enterprise risk framework", "risk framework design",
                                       "risk management framework", "risk framework",
                                       "enterprise risk"]),
        ("Risk Management",           ["risk management programme", "risk management",
                                       "risk assessment", "risk mitigation",
                                       "risk appetite"]),
        ("Governance Reporting",      ["audit committee", "risk committee reporting",
                                       "board governance", "governance reporting",
                                       "governance framework", "governance"]),
        ("Regulatory Compliance",     ["regulatory requirements", "regulatory framework",
                                       "compliance programme", "gdpr", "sox", "aml",
                                       "regulatory", "compliance"]),
        ("Internal Controls",         ["internal controls", "control framework",
                                       "sox controls", "internal audit"]),
    ],
}

# Human-readable category labels
CATEGORY_LABELS: dict[str, str] = {
    "leadership_skills":               "Leadership",
    "commercial_skills":               "Commercial",
    "strategic_skills":                "Strategic",
    "operational_skills":              "Operational",
    "technical_skills":                "Technical",
    "analytical_skills":               "Analytical",
    "communication_skills":            "Communication",
    "stakeholder_skills":              "Stakeholder",
    "transformation_skills":           "Transformation",
    "entrepreneurial_or_builder_skills": "Entrepreneurial",
    "risk_and_governance_skills":      "Risk & Governance",
}

# Display priority for report sections (most reader-relevant first)
CATEGORY_PRIORITY: list[str] = [
    "leadership_skills",
    "transformation_skills",
    "commercial_skills",
    "strategic_skills",
    "stakeholder_skills",
    "operational_skills",
    "risk_and_governance_skills",
    "analytical_skills",
    "technical_skills",
    "communication_skills",
    "entrepreneurial_or_builder_skills",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _word_match(trigger: str, text_lower: str) -> bool:
    """
    For short triggers (< 5 chars) require word boundaries so 'p&l' doesn't
    match inside 'compliance', etc.
    For longer triggers, a substring match is sufficient.
    """
    if len(trigger) >= 5:
        return trigger in text_lower

    idx = text_lower.find(trigger)
    while idx >= 0:
        before_ok = idx == 0 or not text_lower[idx - 1].isalnum()
        end = idx + len(trigger)
        after_ok = end >= len(text_lower) or not text_lower[end].isalnum()
        if before_ok and after_ok:
            return True
        idx = text_lower.find(trigger, idx + 1)
    return False


_BULLET_PREFIX = re.compile(r"^[\s\-•*▪◦]+")


def _evidence_for(text: str, trigger: str) -> str:
    """Return the line/sentence containing the trigger, cleaned and capped at 90 chars."""
    lower = text.lower()
    idx = lower.find(trigger.lower())
    if idx < 0:
        return ""
    line_start = text.rfind("\n", 0, idx)
    line_start = line_start + 1 if line_start >= 0 else 0
    line_end = text.find("\n", idx)
    line_end = line_end if line_end >= 0 else len(text)
    line = _BULLET_PREFIX.sub("", text[line_start:line_end]).strip()
    return line[:90] + ("…" if len(line) > 90 else "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def infer_skills_from_text(
    text: str,
) -> tuple[dict[str, list[str]], list[str], dict[str, str]]:
    """
    Infer skills from a block of text using the taxonomy.

    Returns:
        skills_by_category  — {category_key: [skill_labels]}
        top_skills          — ordered flat list (up to 12, priority-ranked)
        evidence            — {skill_label: evidence_phrase}
    """
    if not text.strip():
        return {}, [], {}

    text_lower = text.lower()
    skills_by_category: dict[str, list[str]] = {}
    evidence: dict[str, str] = {}

    for category, patterns in _PATTERNS.items():
        matched: list[str] = []
        for skill_label, triggers in patterns:
            for trigger in triggers:
                if _word_match(trigger, text_lower):
                    if skill_label not in matched:
                        matched.append(skill_label)
                    if skill_label not in evidence:
                        ev = _evidence_for(text, trigger)
                        if ev:
                            evidence[skill_label] = ev
                    break  # first matching trigger per skill is enough
        if matched:
            skills_by_category[category] = matched

    # Build top_skills list ordered by category priority, ≤3 per category, ≤12 total
    top: list[str] = []
    for cat in CATEGORY_PRIORITY:
        if len(top) >= 12:
            break
        for skill in skills_by_category.get(cat, [])[:3]:
            if skill not in top:
                top.append(skill)
                if len(top) >= 12:
                    break

    return skills_by_category, top, evidence


def enrich_role_skills(role: ExtractedRole) -> ExtractedRole:
    """
    Populate inferred_skills_by_category, top_inferred_skills, skill_evidence
    on an ExtractedRole. Returns a model_copy with those fields set.
    """
    # Build the text corpus from all available role text
    parts: list[str] = [
        role.title or "",
        role.inferred_function or "",
        role.inferred_industry or "",
    ]
    parts.extend(role.core_responsibilities)
    parts.extend(role.achievement_signals)
    parts.extend(role.leadership_signals)
    parts.extend(role.commercial_signals)
    parts.extend(role.strategic_signals)
    parts.extend(role.technical_signals)
    parts.extend(role.entrepreneurial_or_building_signals)
    parts.extend(role.evidence_snippets)

    text = "\n".join(p for p in parts if p)

    skills_by_cat, top_skills, ev = infer_skills_from_text(text)

    return role.model_copy(update={
        "inferred_skills_by_category": skills_by_cat,
        "top_inferred_skills":         top_skills,
        "skill_evidence":              ev,
    })


def aggregate_skills(
    roles: list[ExtractedRole],
) -> tuple[dict[str, list[str]], list[str], dict[str, str]]:
    """
    Merge skill data across all roles.
    Returns (skills_by_category, top_skills, evidence) for the whole profile.
    """
    merged_by_cat: dict[str, set[str]] = {}
    merged_evidence: dict[str, str] = {}

    for role in roles:
        for cat, skills in role.inferred_skills_by_category.items():
            merged_by_cat.setdefault(cat, set()).update(skills)
        for skill, ev in role.skill_evidence.items():
            if skill not in merged_evidence:
                merged_evidence[skill] = ev

    skills_by_cat = {k: sorted(v) for k, v in merged_by_cat.items()}

    top: list[str] = []
    for cat in CATEGORY_PRIORITY:
        if len(top) >= 15:
            break
        for skill in skills_by_cat.get(cat, [])[:4]:
            if skill not in top:
                top.append(skill)

    return skills_by_cat, top, merged_evidence
