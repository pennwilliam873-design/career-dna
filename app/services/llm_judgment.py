"""
LLM Report Intelligence Layer (Stage 12b).

Sits after deterministic heuristic scoring (Stage 12) and before report
formatting (Stage 13). The LLM receives a structured evidence package and
returns advisory prose that personalises the premium report sections.

Scoring remains fully deterministic. The LLM may recommend a score
adjustment but that is a secondary output; the primary outputs are the
advisory text fields that replace generic templates in S1, S6–S11.

Config (env vars):
    LLM_JUDGMENT_MAX_ADJUSTMENT  int   hard ceiling on score adjustment (default 10)
    LLM_JUDGMENT_MODEL           str   Anthropic model ID (default claude-haiku-4-5)
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, List, Literal, Optional, Tuple

from app.schemas import (
    CareerDNAProfile, CareerTrajectory, ExtractedRole,
    HeuristicScoreSet, LLMReportIntelligence, PathwayReadiness,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LLM_JUDGMENT_MAX_ADJUSTMENT: int = int(os.getenv("LLM_JUDGMENT_MAX_ADJUSTMENT", "10"))
_LLM_MODEL: str = os.getenv("LLM_JUDGMENT_MODEL", "claude-haiku-4-5-20251001")

# ---------------------------------------------------------------------------
# Executive title / seniority patterns
# ---------------------------------------------------------------------------

_EXEC_TITLE_RE = re.compile(
    r"\b(ceo|chief executive|chief exec|managing director|executive vice president"
    r"|evp|president|partner|founder|chairman|chair(?:man|woman|person)?"
    r"|ned|non.executive|chief operating|chief financial|coo|cfo|principal)\b",
    re.I,
)

_EXEC_SENIORITY_TOKENS = {"c-suite", "executive", "partner", "director", "vp", "principal"}

_SCALE_PATTERNS: dict[str, re.Pattern | None] = {
    "pl_ownership": re.compile(
        r"\bp&l\b|profit.and.loss|revenue.accountability|budget.responsib|"
        r"financial.account|p&l.account",
        re.I,
    ),
    "regional_remit": re.compile(
        r"\bregional\b|\bapac\b|asia.pacific|\bglobal\b|international|"
        r"multi.country|multi-country|country.head|geography",
        re.I,
    ),
    "team_leadership": re.compile(
        r"\bstaff\b|team.of\s+\d|direct.reports|headcount|people.management"
        r"|\d+\s+staff|\d+\s+people|\d+\s+employees|built.the.team|led.a.team",
        re.I,
    ),
    "board_advisory": re.compile(
        r"\bboard\b|\badvisory\b|\bned\b|non.executive|governance|"
        r"board.member|directorship|audit.committee|aicd",
        re.I,
    ),
    "transformation": re.compile(
        r"\btransformation\b|restructur|business.transformation|change.programme",
        re.I,
    ),
    "multi_exec_roles": None,
}


# ---------------------------------------------------------------------------
# Senior-executive detection
# ---------------------------------------------------------------------------

def _has_executive_title(roles: List[ExtractedRole]) -> bool:
    for role in roles:
        title_text = " ".join(filter(None, [
            role.title or "", role.raw_title or "", role.organisation or "",
        ])).lower()
        seniority_text = " ".join(filter(None, [
            role.seniority or "", role.inferred_seniority or "",
        ])).lower()
        if _EXEC_TITLE_RE.search(title_text):
            return True
        if any(tok in seniority_text for tok in _EXEC_SENIORITY_TOKENS):
            return True
    corpus = " ".join(
        s
        for role in roles
        for s in (
            role.evidence_snippets
            + role.achievement_signals
            + role.leadership_signals
            + role.commercial_signals
            + role.core_responsibilities
        )
    ).lower()
    return bool(_EXEC_TITLE_RE.search(corpus))


def _count_scale_signals(roles: List[ExtractedRole], cv_text: str = "") -> int:
    corpus = " ".join(
        s
        for role in roles
        for s in (
            [role.organisation or ""]
            + role.evidence_snippets
            + role.achievement_signals
            + role.leadership_signals
            + role.commercial_signals
            + role.core_responsibilities
        )
    ).lower()
    if cv_text:
        corpus += " " + cv_text.lower()

    detected: set[str] = set()
    for name, pattern in _SCALE_PATTERNS.items():
        if name == "multi_exec_roles":
            if sum(1 for r in roles if _has_executive_title([r])) >= 2:
                detected.add(name)
        elif pattern and pattern.search(corpus):
            detected.add(name)
    return len(detected)


# ---------------------------------------------------------------------------
# Dynamic cap determination
# ---------------------------------------------------------------------------

def _determine_cap(
    roles: List[ExtractedRole],
    pipeline_warnings: List[str],
    signal_summary: Optional[Any],
    cv_text: str = "",
) -> Tuple[int, str, str]:
    has_parser_warning = any(
        "parser" in w.lower() or "extraction" in w.lower() for w in pipeline_warnings
    )
    has_weak_signals = bool(
        signal_summary and getattr(signal_summary, "weak_signal_warning", False)
    )
    has_too_few_roles = len(roles) < 2

    if has_parser_warning or (has_weak_signals and has_too_few_roles):
        cap = min(5, LLM_JUDGMENT_MAX_ADJUSTMENT)
        return cap, "weak evidence or parser warnings — conservative cap applied", "weak_evidence"

    has_exec = _has_executive_title(roles)
    scale_count = _count_scale_signals(roles, cv_text=cv_text)
    is_senior_exec = (has_exec and scale_count >= 2) or (scale_count >= 3)

    if is_senior_exec:
        cap = min(15, LLM_JUDGMENT_MAX_ADJUSTMENT)
        return cap, "senior executive profile with strong structured evidence", "senior_executive"

    cap = min(10, LLM_JUDGMENT_MAX_ADJUSTMENT)
    return cap, "standard adjustment cap", "default"


# ---------------------------------------------------------------------------
# CV text extraction helpers
# ---------------------------------------------------------------------------

_TITLE_LINE_RE = re.compile(
    r"^[ \t]*(.{0,100}(?:ceo|chief executive|managing director|executive vice president"
    r"|evp|president|partner|founder|chairman|chairwoman|non.executive director"
    r"|ned|chief operating|chief financial|coo|cfo|group ceo"
    r"|regional president|general manager|vice president).{0,80})[ \t]*$",
    re.I | re.MULTILINE,
)

_CREDENTIAL_LINE_RE = re.compile(
    r"(?i)aicd|australian institute of company directors|non.executive director"
    r"|board member|board director|advisory board|audit committee"
    r"|remuneration committee|company director|directorship"
    r"|non-executive|board chair|committee member|governance",
)

_GEOGRAPHY_TOKENS = [
    "apac", "asia pacific", "asia-pacific", "southeast asia", "singapore",
    "australia", "new zealand", "hong kong", "china", "japan", "india",
    "indonesia", "thailand", "malaysia", "global", "international", "emea",
]

_NAMED_VENTURE_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+"
    r"(?:Venture|Initiative|Program|Project|Partnership|Launch|Platform)\b"
)

_PIPE_LEADER_RE = re.compile(r"^(.+?)\s*\|", re.MULTILINE)

# Contact / personal-header lines must never be treated as organisation names.
# Matches: email addresses, phone numbers, URLs, contact labels, and location/metadata
# labels such as "based: Sydney", "location: Melbourne", "address: ...", etc.
_CONTACT_ORG_RE = re.compile(
    r"""
    (?:
        [a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}   # email
        | (?:phone|tel|mobile|cell|fax|email|e-mail
           |linkedin|github|twitter|skype|contact)\s*:        # contact labels
        | \+\d[\d\s\-().]{5,}                                 # international phone
        | https?://                                            # URL
        | www\.[a-zA-Z0-9]                                    # www
        | linkedin\.com                                        # LinkedIn
        | github\.com                                          # GitHub
        | (?:based(?:\s+in)?|location|address|city|suburb     # location/metadata labels
           |residence|nationality|languages?|available
           |availability|notice|clearance|visa
           |right\s+to\s+work|work\s+rights)\s*:
    )
    """,
    re.I | re.VERBOSE,
)


def _extract_candidate_titles(cv_text: str) -> List[str]:
    found: List[str] = []
    for m in _TITLE_LINE_RE.finditer(cv_text):
        line = m.group(1).strip()
        if len(line) <= 120 and line not in found:
            found.append(line)
    return found[:8]


def _extract_credentials_and_board(cv_text: str) -> List[str]:
    found: List[str] = []
    for line in cv_text.splitlines():
        if _CREDENTIAL_LINE_RE.search(line) and line.strip():
            clean = line.strip()
            if clean not in found:
                found.append(clean)
    return found[:10]


def _extract_named_entities(cv_text: str) -> dict:
    text_lower = cv_text.lower()
    geographies = [g for g in _GEOGRAPHY_TOKENS if g.lower() in text_lower]
    ventures: List[str] = []
    for m in _NAMED_VENTURE_RE.finditer(cv_text):
        v = m.group(0).strip()
        if v not in ventures:
            ventures.append(v)
    org_candidates: List[str] = []
    for m in _PIPE_LEADER_RE.finditer(cv_text):
        candidate = m.group(1).strip()
        if _CONTACT_ORG_RE.search(candidate):
            continue  # skip emails, phones, URLs masquerading as org names
        if 2 <= len(candidate.split()) <= 6 and not re.match(r"^\d", candidate):
            if candidate not in org_candidates:
                org_candidates.append(candidate)
    return {
        "geographies": geographies[:8],
        "named_ventures_initiatives": ventures[:5],
        "organisation_candidates": org_candidates[:8],
    }


# ---------------------------------------------------------------------------
# Evidence package builder
# ---------------------------------------------------------------------------

def _build_evidence_package(
    roles: List[ExtractedRole],
    trajectory: Optional[CareerTrajectory],
    compound_pathways: Optional[List[Any]],
    heuristic_scores: Optional[HeuristicScoreSet],
    cv_text: str = "",
    market_context_notes: Optional[str] = None,
) -> dict:
    role_summaries = []
    for r in roles:
        # Sanitise: if the parser assigned a contact line (email/phone/URL) as an
        # organisation, replace it before it enters the LLM evidence package.
        raw_org = r.organisation or ""
        safe_org = "Unknown Organisation" if _CONTACT_ORG_RE.search(raw_org) else raw_org

        title_has_exec = bool(_EXEC_TITLE_RE.search(r.title or ""))
        org_has_exec = bool(_EXEC_TITLE_RE.search(safe_org))
        has_pipe_in_title = "|" in (r.title or "")
        org_is_unknown = safe_org == "Unknown Organisation"
        has_inversion = (
            has_pipe_in_title
            or org_is_unknown
            or (org_has_exec and not title_has_exec)
        )
        if has_inversion:
            title_display = safe_org if org_has_exec else "unknown (parser mis-assignment)"
            org_candidate = r.title
        else:
            title_display = r.title
            org_candidate = None

        entry: dict = {
            "title": title_display,
            "organisation": safe_org,
            "years": f"{r.start_year or '?'}–{r.end_year or 'present'}",
            "seniority": r.seniority or r.inferred_seniority,
            "duration_months": r.duration_months,
            "evidence_snippets": r.evidence_snippets[:4],
            "achievement_signals": r.achievement_signals[:4],
            "leadership_signals": r.leadership_signals[:4],
            "commercial_signals": r.commercial_signals[:4],
            "strategic_signals": r.strategic_signals[:3],
        }
        if org_candidate:
            entry["organisation_candidate"] = org_candidate
        role_summaries.append(entry)

    pathway_summaries = []
    if compound_pathways:
        for pw in compound_pathways:
            pathway_summaries.append({
                "pathway": pw.pathway_name,
                "fit_score": f"{int(pw.fit_score * 100)}%",
                "readiness_score": pw.readiness_score,
                "readiness_band": pw.readiness_band,
                "key_strengths": pw.key_strengths[:4],
                "key_gaps": pw.key_gaps[:3],
            })

    baseline: dict = {}
    if heuristic_scores:
        baseline = {
            "career_coherence": heuristic_scores.career_coherence.score,
            "transferability": heuristic_scores.transferability.score,
            "market_alignment": heuristic_scores.market_alignment.score,
            "promotion_readiness": heuristic_scores.promotion_readiness.score,
            "narrative_strength": heuristic_scores.narrative_strength.score,
            "execution_gap": heuristic_scores.execution_gap.score,
        }

    return {
        "candidate_title_summary": _extract_candidate_titles(cv_text) if cv_text else [],
        "credentials_and_board_evidence": _extract_credentials_and_board(cv_text) if cv_text else [],
        "named_entity_evidence": _extract_named_entities(cv_text) if cv_text else {},
        "roles": role_summaries,
        "trajectory": {
            "type": trajectory.trajectory_type if trajectory else "unknown",
            "confidence": (
                f"{int(trajectory.confidence_score * 100)}%" if trajectory else "unknown"
            ),
            "supporting_evidence": (trajectory.supporting_evidence[:3] if trajectory else []),
        },
        "target_pathways": pathway_summaries,
        "baseline_scores": baseline,
        "market_context_notes": market_context_notes,
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(evidence_package: dict, target_role: Optional[str]) -> str:
    evidence_json = json.dumps(evidence_package, indent=2)
    return f"""You are a senior executive career advisor authoring a premium Career DNA intelligence report.

Your task: using ONLY the structured evidence provided below, generate personalised advisory
content for the report. Your writing should be specific, commercially grounded, and read as
if written about this person — not assembled from generic career templates.

STRUCTURED EVIDENCE (the only facts you may reason from):
{evidence_json}

TARGET ROLE / PATHWAYS: {target_role or "Not specified"}

STRICT RULES:
- You may ONLY use facts, roles, organisations, figures, credentials, and skills
  explicitly present in the structured evidence above.
- Do NOT invent or infer any company name, revenue figure, title, date, credential,
  market claim, or skill not present in the data.
- Every substantive claim must be traceable to a specific evidence field.
- If evidence is insufficient for a specific section, return null for that field.
- Write as a senior advisor: direct, evidence-grounded, commercially specific.
  Avoid generic advice that could apply to any executive.
- action_plan_items must reference specific gaps or evidence from the data, not generic templates.

RESPOND IN JSON with exactly these fields (null where evidence is insufficient):
{{
  "executive_thesis": "<3-4 sentence career narrative synthesising this candidate's
    distinctive positioning, scale evidence, and career arc. Cite specific roles,
    organisations, and evidence. Not generic — if you cannot be specific, return null.>",
  "pathway_judgment": "<2-3 sentence comparative assessment of the target pathways,
    explaining relative positioning and what differentiates the strongest from the rest.
    Cite specific strengths and gaps from the evidence.>",
  "strongest_pathway": "<pathway name from target_pathways, or null>",
  "weakest_pathway": "<pathway name from target_pathways, or null>",
  "transferable_advantage": "<2 sentences on what makes this candidate distinctively
    valuable — cite specific evidence, not generic leadership qualities.>",
  "positioning_risks": "<2 sentences on the specific positioning risks or blind spots
    visible in the evidence — what is missing, ambiguous, or likely to raise objections.>",
  "strategic_options": [
    "<Role Title: 1-sentence rationale citing this person's specific evidence>",
    "<Role Title: 1-sentence rationale>",
    "<Role Title: 1-sentence rationale>"
  ],
  "recommended_pathway": "<pathway name from target_pathways, or closest match>",
  "recommended_pathway_rationale": "<2-3 sentences: why this pathway for this person,
    what specific evidence makes it viable, and what 1-2 concrete actions close the gap.>",
  "action_plan_items": [
    "0-30 days: <specific action referencing actual gaps or evidence from the data>",
    "30-60 days: <specific action>",
    "60-90 days: <specific action>",
    "90 days+: <specific action>",
    "Ongoing: <specific action>"
  ],
  "score_verdict": "fair" | "too_conservative" | "too_generous",
  "score_adjustment": <integer -15 to +15. Positive = baseline underweights executive depth.
    Negative = baseline too generous. Zero = baseline is fair.>,
  "evidence_used": ["<3-5 specific evidence items from the package that informed the assessment>"],
  "confidence_level": "high" | "medium" | "low",
  "warnings": ["<any warnings about evidence quality, gaps, or limitations>"]
}}

Return ONLY valid JSON. No preamble, no text outside the JSON object."""


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_llm(prompt: str) -> str:
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed") from exc

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=_LLM_MODEL,
        max_tokens=2048,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Hallucination check
# ---------------------------------------------------------------------------

_COMMON_REASONING_WORDS = {
    "should", "could", "would", "their", "which", "about", "being", "having",
    "years", "roles", "level", "score", "shows", "strong", "senior", "career",
    "executive", "profile", "evidence", "baseline", "pathway", "signal",
    "candidate", "assessment", "demonstrates", "indicates", "suggests",
    "depth", "scope", "scale", "across", "three", "multiple", "significant",
    "structured", "keyword", "matching", "misses", "under", "over",
    "provides", "offers", "requires", "within", "before", "after", "first",
    "second", "third", "primary", "secondary", "further", "approach",
    "market", "boards", "board", "group", "commercial", "business",
    "leadership", "management", "experience", "opportunity", "position",
    "specifically", "particular", "direct", "directly", "combined",
    "combined", "including", "especially", "however", "although",
}


def _hallucination_check(
    generated_texts: List[str],
    evidence_package: dict,
) -> Literal["low", "medium", "high"]:
    permitted_text = json.dumps(evidence_package).lower()
    all_text = " ".join(t for t in generated_texts if t)
    words = {
        w.lower().strip(".,;:()'\"–-")
        for w in all_text.split()
        if len(w) > 4
    }
    suspicious = {
        w for w in words
        if w not in _COMMON_REASONING_WORDS and w not in permitted_text
    }
    if len(suspicious) > 10:
        return "high"
    if len(suspicious) > 5:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# LLM output sanitization — strip prompt boilerplate echoed back by the model
# ---------------------------------------------------------------------------

# Phrases from the prompt that the model should never echo into advisory prose.
_SANITISE_PATTERNS: list[re.Pattern] = [
    re.compile(r"structured evidence\s*(?:\([^)]*\))?\s*[:.]?\s*", re.I),
    re.compile(r"strict rules\s*[:.]?\s*", re.I),
    re.compile(r"respond in json\s*[:.]?\s*", re.I),
]


def _sanitise_llm_text(text: Optional[str]) -> Optional[str]:
    """Remove prompt section labels and boilerplate that the LLM echoed back."""
    if not text:
        return text
    result = text
    for pat in _SANITISE_PATTERNS:
        result = pat.sub("", result)
    result = result.strip()
    return result if result else None


# ---------------------------------------------------------------------------
# Parser / validator
# ---------------------------------------------------------------------------

def _parse_and_validate(
    raw_response: str,
    cap: int,
    cap_reason: str,
    profile_tier: str,
    baseline_score: int,
    evidence_package: dict,
) -> LLMReportIntelligence:
    try:
        data = json.loads(raw_response.strip())
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError("LLM response contained no valid JSON")

    # Extract and sanitize all advisory prose fields
    executive_thesis          = _sanitise_llm_text(data.get("executive_thesis") or None)
    pathway_judgment          = _sanitise_llm_text(data.get("pathway_judgment") or None)
    transferable_advantage    = _sanitise_llm_text(data.get("transferable_advantage") or None)
    positioning_risks         = _sanitise_llm_text(data.get("positioning_risks") or None)
    market_context_implications = _sanitise_llm_text(data.get("market_context_implications") or None)
    recommended_pathway       = data.get("recommended_pathway") or None
    recommended_pathway_rationale = _sanitise_llm_text(data.get("recommended_pathway_rationale") or None)

    strategic_options_raw = data.get("strategic_options")
    strategic_options = (
        [t for s in strategic_options_raw if (t := _sanitise_llm_text(str(s)))]
        if strategic_options_raw else None
    ) or None

    action_plan_raw = data.get("action_plan_items")
    action_plan_items = (
        [t for s in action_plan_raw if (t := _sanitise_llm_text(str(s)))]
        if action_plan_raw else None
    ) or None
    strongest_pathway = data.get("strongest_pathway") or None
    weakest_pathway = data.get("weakest_pathway") or None
    score_verdict = str(data.get("score_verdict", "fair"))
    score_adjustment_raw = int(data.get("score_adjustment", 0))
    evidence_used = list(data.get("evidence_used", []))[:6]
    confidence_level = str(data.get("confidence_level", "medium"))
    warnings = list(data.get("warnings", []))

    # Hallucination check across all generated text
    all_texts = [
        executive_thesis or "",
        pathway_judgment or "",
        transferable_advantage or "",
        positioning_risks or "",
        " ".join(strategic_options or []),
        recommended_pathway_rationale or "",
        " ".join(action_plan_items or []),
    ]
    hallucination_risk = _hallucination_check(all_texts, evidence_package)

    # If hallucination risk is high, clear narrative fields — keep scores
    if hallucination_risk == "high":
        executive_thesis = None
        pathway_judgment = None
        transferable_advantage = None
        positioning_risks = None
        strategic_options = None
        recommended_pathway_rationale = None
        action_plan_items = None
        warnings.append("hallucination risk detected — advisory prose cleared, deterministic fallback used")
        score_adjustment_raw = 0

    # Clamp score adjustment to cap
    score_adjustment = max(-cap, min(cap, score_adjustment_raw))
    final_adjusted_score = max(0, min(100, baseline_score + score_adjustment))

    return LLMReportIntelligence(
        executive_thesis=executive_thesis,
        pathway_judgment=pathway_judgment,
        transferable_advantage=transferable_advantage,
        positioning_risks=positioning_risks,
        market_context_implications=market_context_implications,
        strategic_options=strategic_options,
        recommended_pathway=recommended_pathway,
        recommended_pathway_rationale=recommended_pathway_rationale,
        action_plan_items=action_plan_items,
        strongest_pathway=strongest_pathway,
        weakest_pathway=weakest_pathway,
        score_adjustment=score_adjustment,
        score_verdict=score_verdict,
        baseline_score=baseline_score,
        final_adjusted_score=final_adjusted_score,
        evidence_used=evidence_used,
        confidence_level=confidence_level,  # type: ignore[arg-type]
        hallucination_risk=hallucination_risk,
        profile_tier=profile_tier,  # type: ignore[arg-type]
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Mock intelligence (dev / demo when no API key available)
# ---------------------------------------------------------------------------

def _build_mock_intelligence(
    evidence_package: dict,
    baseline_score: int,
    cap: int,
    cap_reason: str,
    profile_tier: str,
) -> LLMReportIntelligence:
    pathways = evidence_package.get("target_pathways", [])
    titles = evidence_package.get("candidate_title_summary", [])
    credentials = evidence_package.get("credentials_and_board_evidence", [])
    entities = evidence_package.get("named_entity_evidence", {})
    roles = evidence_package.get("roles", [])

    strongest = pathways[0]["pathway"] if pathways else None
    weakest = pathways[-1]["pathway"] if len(pathways) > 1 else None

    orgs = [r.get("organisation", "") for r in roles[:4] if r.get("organisation")]
    role_titles = [r.get("title", "") for r in roles[:4] if r.get("title")]
    geos = entities.get("geographies", [])
    aicd_present = any("aicd" in c.lower() for c in credentials)

    if profile_tier == "senior_executive":
        score_adj = min(cap, 5) if baseline_score < 55 else min(cap, 3)
        verdict = "too_conservative"

        # Executive thesis — uses specific orgs and geos from evidence
        geo_phrase = f"across {' and '.join(geos[:2])}" if geos else "across multiple geographies"
        org_phrase = f" at {' and '.join(orgs[:2])}" if orgs else ""

        executive_thesis = (
            f"This is a senior executive profile characterised by sustained P&L ownership at scale, "
            f"progressive increases in enterprise scope, and multi-geography commercial leadership "
            f"{geo_phrase}. "
            f"Consecutive executive appointments{org_phrase} demonstrate a deliberate career arc from "
            f"operational leadership through regional and group-level accountability, with commercial "
            f"transformation and governance exposure layered across each stage. "
            f"The combination of executive title continuity, scale evidence, and "
            f"{'formal governance qualification' if aicd_present else 'board engagement'} "
            f"positions this profile at the credible end of senior executive and board-facing opportunity."
        )

        # Pathway judgment
        if len(pathways) >= 2:
            p0, p1 = pathways[0]["pathway"], pathways[1]["pathway"]
            p0_gaps = pathways[0].get("key_gaps", [])
            p1_gaps = pathways[1].get("key_gaps", [])
            gap0_str = f" — the primary gap is {p0_gaps[0].lower()}" if p0_gaps else ""
            gap1_str = f", requiring {p1_gaps[0].lower()} to close before market approach" if p1_gaps else ""
            pathway_judgment = (
                f"{p0} is the strongest near-term positioning given the profile's P&L depth and "
                f"executive track record{gap0_str}. "
                f"{p1} is a credible secondary target{gap1_str}, and the underlying capability "
                f"is present — the gap is framing and evidence presentation rather than substance."
            )
        elif pathways:
            pw = pathways[0]
            gap_str = f"; the primary gap is {pw['key_gaps'][0].lower()}" if pw.get("key_gaps") else ""
            pathway_judgment = (
                f"{pw['pathway']} is well-supported by the evidence, with core executive signals "
                f"present{gap_str}. "
                f"The profile demonstrates the required seniority and scope — the priority is "
                f"sharpening the written narrative to make commercial impact immediately visible."
            )
        else:
            pathway_judgment = (
                "The available evidence supports a senior executive positioning across multiple "
                "opportunity types. Provide specific target pathways for a comparative assessment."
            )

        # Transferable advantage
        geo_adv = f"across {' and '.join(geos[:3])}" if len(geos) >= 2 else "across multiple markets"
        transferable_advantage = (
            f"The combination of large-scale P&L ownership and multi-geography executive leadership "
            f"{geo_adv} is genuinely scarce — most executives carry depth in one dimension or breadth "
            f"in the other, not both at the same scale. "
            f"This profile's commercial transformation track record, delivered at enterprise scale "
            f"across successive roles, is the differentiating signal in any senior executive or "
            f"board-facing process."
        )

        # Positioning risks
        positioning_risks = (
            f"The primary positioning risk is CV language that underplays commercial impact: "
            f"the evidence contains strong P&L and transformation signals, but these "
            f"may not be sufficiently explicit and quantified in the written profile — search firms "
            f"and boards scan for revenue figures, growth rates, and market-position outcomes. "
            f"{'The secondary risk is the gap between board-adjacent engagement (advisory, AICD) and a formal listed-board directorship appointment, which limits NED credibility until a seat is secured.' if aicd_present else 'The secondary risk is limited visible board-level engagement — adding a formal governance credential or advisory appointment would strengthen the NED and board-facing positioning.'}"
        )

        # Strategic options — cite evidence
        geo0 = geos[0].upper() if geos else "APAC"
        org0 = orgs[0] if orgs else "a major organisation"
        options = [
            f"Group CEO of a Listed Business: The P&L scale, digital transformation track record "
            f"and executive leadership at {org0} create a directly competitive profile for listed "
            f"group CEO appointments, particularly in sectors where transformation is the brief.",

            f"Senior Regional President / CEO (Global MNC): The multi-country P&L and regional "
            f"leadership track record — evidenced {geo_phrase} — positions this profile strongly "
            f"for equivalent or larger regional CEO roles at global organisations where {geo0} "
            f"market depth is required.",

            f"Non-Executive Director (Board Appointment): "
            f"{'The AICD qualification and board engagement' if aicd_present else 'Board reporting experience and executive governance exposure'} "
            f"support a credible first NED appointment, particularly on boards seeking "
            f"operating-executive depth and sector transformation experience.",
        ]

        # Recommended pathway and rationale
        rec_pathway = pathways[0]["pathway"] if pathways else "Senior Executive"
        rec_strengths = pathways[0].get("key_strengths", []) if pathways else []
        strength_str = (
            f"with {', '.join(rec_strengths[:2])} as the core differentiating signals"
            if rec_strengths else "with P&L scale and executive scope as the core signals"
        )
        rec_rationale = (
            f"{rec_pathway} is the strongest current market positioning for this profile, "
            f"{strength_str}. "
            f"The evidence demonstrates the scale, scope, and seniority signals that search firms "
            f"and boards require at this level — the gap is narrative and vocabulary presentation, "
            f"not executive substance. "
            f"The priority before market approach is ensuring the CV explicitly quantifies commercial "
            f"outcomes within the first three lines of each role description."
        )

        # Action plan
        plan = [
            "0–30 days: Rewrite the CV executive summary and the top two role descriptions to "
            "lead with quantified commercial outcomes — P&L scale, revenue growth figures, "
            "transformation results, team size at peak. Boards and search firms read the first "
            "page only; every line should carry specific evidence.",

            "30–60 days: Brief 2–3 executive search firms at the appropriate seniority level. "
            "These conversations directly shape how boards are briefed. Arrive with a one-page "
            "positioning document — not a CV — that names the type of opportunity you are "
            "targeting and the two or three distinctive signals you bring.",

            "60–90 days: Identify 3–5 boards where your sector expertise and executive experience "
            "are genuinely scarce. Approach through warm introductions from existing networks or "
            "through the search firms already briefed — cold applications are rarely effective "
            "at this level.",

            f"90 days+: {'Convert the AICD qualification into a formal board engagement — listed, private, or NFP — to build a direct directorship track record before approaching listed NED roles.' if aicd_present else 'Pursue a formal governance credential (AICD or equivalent) alongside a first board engagement to build the directorship track record required for listed NED appointments.'}",

            "Ongoing: Build market visibility through one published piece or senior forum appearance "
            "per quarter in the target sector. Inbound CEO and board interest is strongly "
            "correlated with visible thought leadership — it shortens search timelines significantly.",
        ]

    else:
        # Default / weak-evidence tier
        score_adj = 0
        verdict = "fair"
        executive_thesis = None
        pathway_judgment = (
            "The available evidence supports the baseline assessment. "
            "Enriching the CV and questionnaire responses will enable a more specific advisory assessment."
        )
        transferable_advantage = None
        positioning_risks = None
        options = None
        rec_pathway = pathways[0]["pathway"] if pathways else None
        rec_rationale = None
        plan = None

    applied = max(-cap, min(cap, score_adj))
    final = max(0, min(100, baseline_score + applied))

    return LLMReportIntelligence(
        executive_thesis=executive_thesis,
        pathway_judgment=pathway_judgment,
        transferable_advantage=transferable_advantage,
        positioning_risks=positioning_risks,
        market_context_implications=None,
        strategic_options=options,
        recommended_pathway=rec_pathway,
        recommended_pathway_rationale=rec_rationale,
        action_plan_items=plan,
        strongest_pathway=strongest,
        weakest_pathway=weakest,
        score_adjustment=applied,
        score_verdict=verdict,
        baseline_score=baseline_score,
        final_adjusted_score=final,
        evidence_used=[
            f"Roles: {', '.join(role_titles[:3])}" if role_titles else "structured role data",
            f"Organisations: {', '.join(orgs[:2])}" if orgs else "structured organisation data",
            f"Geographies: {', '.join(geos[:3])}" if geos else "geographic signals",
            f"Credentials: {credentials[0]}" if credentials else "board/governance signals",
        ],
        confidence_level="high" if profile_tier == "senior_executive" else "medium",
        hallucination_risk="low",
        profile_tier=profile_tier,  # type: ignore[arg-type]
        warnings=[],
    )


# ---------------------------------------------------------------------------
# Public entry point (function name unchanged — pipeline calls this)
# ---------------------------------------------------------------------------

def build_llm_judgment(
    roles: List[ExtractedRole],
    profile: CareerDNAProfile,
    trajectory: Optional[CareerTrajectory],
    heuristic_scores: Optional[HeuristicScoreSet],
    compound_pathways: Optional[List[Any]],
    signal_summary: Optional[Any],
    pipeline_warnings: List[str],
    target_role: Optional[str] = None,
    cv_text: str = "",
    market_context_notes: Optional[str] = None,
) -> Optional[LLMReportIntelligence]:
    """
    Stage 12b entry point. Returns None on any failure so Stage 13 falls back
    to raw heuristic scores and template content without surfacing errors.
    """
    try:
        if not heuristic_scores:
            return None

        baseline_score = heuristic_scores.promotion_readiness.score
        cap, cap_reason, profile_tier = _determine_cap(
            roles, pipeline_warnings, signal_summary, cv_text=cv_text
        )
        evidence_package = _build_evidence_package(
            roles, trajectory, compound_pathways, heuristic_scores,
            cv_text=cv_text, market_context_notes=market_context_notes,
        )

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key:
            try:
                prompt = _build_prompt(evidence_package, target_role)
                raw_response = _call_llm(prompt)
                return _parse_and_validate(
                    raw_response, cap, cap_reason, profile_tier,
                    baseline_score, evidence_package,
                )
            except Exception as exc:
                logger.warning("LLM call failed, using mock intelligence: %s", exc)

        logger.info(
            "llm_report_intel: using mock (api_key_present=%s, profile_tier=%s)",
            bool(api_key), profile_tier,
        )
        return _build_mock_intelligence(
            evidence_package, baseline_score, cap, cap_reason, profile_tier
        )

    except Exception as exc:
        logger.warning("build_llm_judgment failed entirely: %s", exc)
        return None
