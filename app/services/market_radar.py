"""
Market Radar service — section pipeline architecture.

Three modes:
  full         — TAVILY_API_KEY set: generates queries, runs searches, builds
                 stable source map (S1…SN), generates each section separately.
  manual       — No Tavily key, advisor-provided research text supplied.
  profile_only — Neither. Sections generated from client context only.

Each of the 8 sections is generated as a separate focused tool-use call with
its own small schema. Sections are validated individually; each retries once
before being marked incomplete. A failing section never aborts other sections.
Source IDs (S1, S2…) returned by Claude are resolved to RadarSource objects
in the backend before assembly — the frontend is unchanged.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import httpx

from app.models.client import (
    ClientProfile,
    CVIntelligence,
    HiddenMarketHypothesis,
    MarketRadarOutput,
    MarketRadarPathway,
    MarketRadarSignal,
    PositioningOutput,
    RadarSource,
    RelationshipStrategy,
    TargetCompany,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_MODEL: str = os.getenv("MARKET_RADAR_MODEL", "claude-haiku-4-5-20251001")
_TAVILY_URL = "https://api.tavily.com/search"
_SNIPPET_MAX_WORDS = 150       # stored in DB / returned with search results
_PROMPT_SNIPPET_WORDS = 50     # compact version injected into section prompts
_MAX_QUERIES = 8
_RESULTS_PER_QUERY = 3

# Minimum item counts for a section to be considered complete
_COMPLETENESS_MIN: Dict[str, int] = {
    "priority_pathways":        3,
    "target_companies":         5,
    "market_signals":           5,
    "hidden_market_hypotheses": 3,
    "relationship_strategy":    3,
    "next_research_actions":    3,
    "advisor_only_notes":       3,
}

# Max output tokens per section (tight budgets prevent partial generation)
_SECTION_MAX_TOKENS: Dict[str, int] = {
    "market_summary":            256,
    "priority_pathways":        1024,
    "target_companies":         2048,
    "market_signals":           2048,
    "hidden_market_hypotheses": 1024,
    "relationship_strategy":    1024,
    "next_research_actions":     512,
    "advisor_only_notes":        512,
}

_PIPELINE_SECTIONS = [
    "market_summary",
    "priority_pathways",
    "target_companies",
    "market_signals",
    "hidden_market_hypotheses",
    "relationship_strategy",
    "next_research_actions",
    "advisor_only_notes",
]

# Sections that carry item-level source attribution
_SOURCED_SECTIONS = {"target_companies", "market_signals", "hidden_market_hypotheses"}


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class MarketRadarResult:
    radar: Optional[MarketRadarOutput] = None
    raw_text: Optional[str] = None      # kept for API compat; always None in pipeline
    parse_failed: bool = False           # always False in pipeline
    mode: str = "profile_only"
    is_complete: bool = True
    missing_sections: List[str] = field(default_factory=list)


# ── Section tool schemas ──────────────────────────────────────────────────────

_SECTION_TOOLS: Dict[str, dict] = {
    "market_summary": {
        "name": "submit_market_summary",
        "description": "Submit the Market Summary. Single string, no newlines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market_summary": {
                    "type": "string",
                    "description": (
                        "2-3 sentences on the overall market opportunity landscape "
                        "for this client's transition. Single line, no literal newlines."
                    ),
                }
            },
            "required": ["market_summary"],
        },
    },
    "priority_pathways": {
        "name": "submit_priority_pathways",
        "description": "Submit 3-5 priority transition pathways.",
        "input_schema": {
            "type": "object",
            "properties": {
                "priority_pathways": {
                    "type": "array",
                    "description": "3-5 priority transition pathways.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pathway": {"type": "string"},
                            "why_relevant": {"type": "string", "description": "Under 25 words."},
                            "market_pull": {"type": "string", "description": "Under 20 words."},
                            "fit_level": {"type": "string", "enum": ["High", "Medium", "Stretch"]},
                            "watchouts": {"type": "string", "description": "Under 20 words."},
                        },
                        "required": ["pathway", "why_relevant", "market_pull", "fit_level", "watchouts"],
                    },
                }
            },
            "required": ["priority_pathways"],
        },
    },
    "target_companies": {
        "name": "submit_target_companies",
        "description": "Submit 5-8 target companies with source IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_companies": {
                    "type": "array",
                    "description": "5-8 specific companies worth monitoring or approaching.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "company": {"type": "string"},
                            "category": {
                                "type": "string",
                                "description": "e.g. PE portfolio, listed, private, scale-up, NED target",
                            },
                            "why_relevant": {"type": "string", "description": "Under 20 words."},
                            "signal_or_trigger": {"type": "string", "description": "Under 20 words."},
                            "entry_route": {"type": "string", "description": "Under 20 words."},
                            "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                            "sources": {
                                "type": "array",
                                "description": (
                                    "Source IDs from the SOURCES block that directly mention "
                                    "or support this company (e.g. ['S1','S3']). "
                                    "Empty array if none apply."
                                ),
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "company", "category", "why_relevant", "signal_or_trigger",
                            "entry_route", "priority", "sources",
                        ],
                    },
                }
            },
            "required": ["target_companies"],
        },
    },
    "market_signals": {
        "name": "submit_market_signals",
        "description": "Submit 5-8 market signals with confidence labels and source IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "market_signals": {
                    "type": "array",
                    "description": "5-8 market signals relevant to this client's transition.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "signal": {"type": "string", "description": "Under 20 words."},
                            "signal_type": {
                                "type": "string",
                                "enum": [
                                    "role", "leadership_change", "acquisition", "restructure",
                                    "expansion", "funding", "recently_filled",
                                    "hidden_market_hypothesis",
                                ],
                            },
                            "company": {
                                "type": "string",
                                "description": "Company or entity. Empty string if none.",
                            },
                            "evidence_or_rationale": {"type": "string", "description": "Under 25 words."},
                            "confidence": {"type": "string", "enum": ["verified", "inferred", "hypothesis"]},
                            "recommended_action": {"type": "string", "description": "Under 20 words."},
                            "sources": {
                                "type": "array",
                                "description": (
                                    "Source IDs supporting this signal. "
                                    "At least one required if confidence='verified'. "
                                    "Must be empty if confidence='hypothesis'."
                                ),
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "signal", "signal_type", "company", "evidence_or_rationale",
                            "confidence", "recommended_action", "sources",
                        ],
                    },
                }
            },
            "required": ["market_signals"],
        },
    },
    "hidden_market_hypotheses": {
        "name": "submit_hidden_market_hypotheses",
        "description": "Submit 3-5 hidden market opportunity hypotheses with source IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hidden_market_hypotheses": {
                    "type": "array",
                    "description": "3-5 hidden-market opportunities not visible on job boards.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "hypothesis": {"type": "string", "description": "Under 25 words."},
                            "trigger": {"type": "string", "description": "Under 20 words."},
                            "why_client_fits": {"type": "string", "description": "Under 20 words."},
                            "what_to_validate": {"type": "string", "description": "Under 20 words."},
                            "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
                            "sources": {
                                "type": "array",
                                "description": (
                                    "Source IDs that triggered this hypothesis. "
                                    "Empty array for purely advisory hypotheses."
                                ),
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "hypothesis", "trigger", "why_client_fits", "what_to_validate",
                            "confidence", "sources",
                        ],
                    },
                }
            },
            "required": ["hidden_market_hypotheses"],
        },
    },
    "relationship_strategy": {
        "name": "submit_relationship_strategy",
        "description": "Submit 3-5 relationship-led entry strategies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "relationship_strategy": {
                    "type": "array",
                    "description": "3-5 relationship-led market entry strategies.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "Person, firm, or network to activate.",
                            },
                            "relationship_angle": {"type": "string", "description": "Under 20 words."},
                            "suggested_conversation": {"type": "string", "description": "Under 25 words."},
                        },
                        "required": ["target", "relationship_angle", "suggested_conversation"],
                    },
                }
            },
            "required": ["relationship_strategy"],
        },
    },
    "next_research_actions": {
        "name": "submit_next_research_actions",
        "description": "Submit 3-5 specific next research or outreach actions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "next_research_actions": {
                    "type": "array",
                    "description": "3-5 concrete next steps for the advisor. Each under 20 words.",
                    "items": {"type": "string"},
                }
            },
            "required": ["next_research_actions"],
        },
    },
    "advisor_only_notes": {
        "name": "submit_advisor_only_notes",
        "description": "Submit 3-5 advisor-only observations not for the client.",
        "input_schema": {
            "type": "object",
            "properties": {
                "advisor_only_notes": {
                    "type": "array",
                    "description": (
                        "3-5 observations for the advisor only: blind spots, perception risks, "
                        "negotiation context. Each under 20 words."
                    ),
                    "items": {"type": "string"},
                }
            },
            "required": ["advisor_only_notes"],
        },
    },
}


# ── Section-specific task instructions ───────────────────────────────────────

_SECTION_INSTRUCTIONS: Dict[str, str] = {
    "market_summary": (
        "Write market_summary: 2-3 sentences capturing the overall market opportunity "
        "landscape for this client's transition right now. Be commercially specific. "
        "Single non-empty string."
    ),
    "priority_pathways": (
        "Generate priority_pathways: the 3-5 transition pathways the market currently "
        "supports most strongly for this client. Each needs: pathway name, why_relevant "
        "(market evidence, ≤25 words), market_pull (forces making this timely, ≤20 words), "
        "fit_level (High/Medium/Stretch), watchouts (≤20 words). Minimum 3 items."
    ),
    "target_companies": (
        "Generate target_companies: 5-8 specific named companies worth monitoring or "
        "approaching for this client. Each needs: company name, category (PE portfolio / "
        "listed / private / scale-up / NED target), why_relevant (≤20 words), "
        "signal_or_trigger (≤20 words), entry_route (≤20 words), priority (High/Medium/Low), "
        "sources (source IDs from SOURCES that directly mention this company — empty array "
        "if none). Name real companies. Minimum 5 items."
    ),
    "market_signals": (
        "Generate market_signals: 5-8 specific market signals relevant to this client's "
        "transition. Each needs: signal (≤20 words), signal_type, company (empty string if "
        "none), evidence_or_rationale (≤25 words), confidence (verified/inferred/hypothesis), "
        "recommended_action (≤20 words), sources (source IDs — required if verified, empty if "
        "hypothesis). Mix verified signals from research with inferred/hypothesis signals from "
        "profile context. Minimum 5 items."
    ),
    "hidden_market_hypotheses": (
        "Generate hidden_market_hypotheses: 3-5 hidden-market opportunities not visible on "
        "job boards. Each needs: hypothesis (≤25 words), trigger (event creating the "
        "opportunity, ≤20 words), why_client_fits (≤20 words), what_to_validate (how to test "
        "it, ≤20 words), confidence (High/Medium/Low), sources (source IDs that triggered this "
        "hypothesis — empty array for purely advisory hypotheses). Minimum 3 items."
    ),
    "relationship_strategy": (
        "Generate relationship_strategy: 3-5 specific relationship-led entry strategies. "
        "Each is a concrete person, firm, or network to activate — not generic advice. "
        "Each needs: target, relationship_angle (basis for approach, ≤20 words), "
        "suggested_conversation (opening theme, ≤25 words). Minimum 3 items."
    ),
    "next_research_actions": (
        "Generate next_research_actions: 3-5 specific, concrete next steps for the advisor "
        "to validate or pursue this market intelligence. Name companies, people, or data "
        "sources where possible. Each action under 20 words. Minimum 3 items."
    ),
    "advisor_only_notes": (
        "Generate advisor_only_notes: 3-5 observations strictly for the advisor's eyes only "
        "— not for the client. Cover perception risks, blind spots, negotiation context, or "
        "sensitivities. Each under 20 words. Minimum 3 items."
    ),
}


# ── Source map helpers ────────────────────────────────────────────────────────

def _build_source_map(
    search_results: list,
    manual_research: Optional[str],
) -> Tuple[Dict[str, dict], str]:
    """
    Assigns stable S1…SN IDs to deduplicated search results.
    Returns (source_map, manual_block).
    source_map: {"S1": {title, url, snippet, query}, ...}
    manual_block: advisor-provided research text or "".
    """
    source_map: Dict[str, dict] = {}
    seen_urls: set = set()

    for r in search_results:
        url = r.get("url", "")
        if url and url in seen_urls:
            continue
        sid = f"S{len(source_map) + 1}"
        source_map[sid] = {
            "title":   r.get("title", ""),
            "url":     url,
            "snippet": r.get("snippet", ""),
            "query":   r.get("query", ""),
        }
        if url:
            seen_urls.add(url)

    manual_block = (manual_research or "").strip()
    return source_map, manual_block


def _format_sources_block(source_map: Dict[str, dict], manual_block: str) -> str:
    """
    Compact text block injected into every section prompt.
    Uses _PROMPT_SNIPPET_WORDS (50-word) truncation, not the full stored snippet.
    """
    parts: List[str] = []

    for sid, src in source_map.items():
        snippet = src.get("snippet", "")
        words = snippet.split()
        if len(words) > _PROMPT_SNIPPET_WORDS:
            snippet = " ".join(words[:_PROMPT_SNIPPET_WORDS]) + "…"
        line = f"[{sid}]"
        if src.get("title"):
            line += f" {src['title']}"
        if src.get("url"):
            line += f"\n     {src['url']}"
        if snippet:
            line += f"\n     {snippet}"
        parts.append(line)

    if manual_block:
        if parts:
            parts.append("")
        parts.append("[ADVISOR-PROVIDED RESEARCH]")
        parts.append(manual_block)

    if not parts:
        return (
            "[No external research — generate all items from client profile and "
            "positioning context only. All market_signal confidence values must be 'hypothesis'.]"
        )

    return "\n".join(parts)


def _resolve_source_ids(ids: list, source_map: Dict[str, dict]) -> List[RadarSource]:
    """Convert source ID strings ['S1','S3'] → [RadarSource(…), RadarSource(…)]."""
    result: List[RadarSource] = []
    for sid in (ids or []):
        # Normalise: strip whitespace, uppercase, keep only alphanumerics
        sid_norm = re.sub(r"[^A-Z0-9]", "", str(sid).strip().upper())
        if sid_norm and sid_norm in source_map:
            src = source_map[sid_norm]
            result.append(RadarSource(
                title=src.get("title", ""),
                url=src.get("url", ""),
                snippet=src.get("snippet", ""),
            ))
    return result


# ── Context builders ──────────────────────────────────────────────────────────

def _profile_block(profile: ClientProfile) -> str:
    fields = {
        "Current role":      profile.current_role,
        "Location":          profile.location,
        "Target geography":  profile.target_geography,
        "Desired next move": profile.desired_next_move,
        "Timeframe":         profile.timeframe,
        "Roles wanted":      profile.roles_wanted,
        "Roles not wanted":  profile.roles_not_wanted,
        "Constraints":       profile.constraints,
        "Relationship assets": profile.relationship_assets,
        "Advisor notes":     profile.advisor_notes,
    }
    lines = [f"{k}: {v}" for k, v in fields.items() if v and v.strip()]
    return "\n".join(lines) if lines else "No profile context provided."


def _cv_context_block(
    profile: ClientProfile,
    cv_intel: Optional[CVIntelligence],
    cv_intel_raw: Optional[str],
) -> str:
    if cv_intel:
        parts = []
        if cv_intel.executive_summary:
            parts.append(f"Executive Summary: {cv_intel.executive_summary}")
        if cv_intel.career_arc:
            parts.append(f"Career Arc: {cv_intel.career_arc}")
        if cv_intel.core_capabilities:
            parts.append("Core Capabilities: " + "; ".join(cv_intel.core_capabilities))
        if cv_intel.signature_achievements:
            parts.append(
                "Signature Achievements:\n"
                + "\n".join(f"- {a}" for a in cv_intel.signature_achievements)
            )
        scale = cv_intel.leadership_scale
        scale_items = [
            v for v in [scale.team_size, scale.revenue_or_pnl, scale.geography, scale.stakeholders]
            if v
        ]
        if scale_items:
            parts.append("Leadership Scale: " + " | ".join(scale_items))
        if cv_intel.sector_experience:
            parts.append("Sectors: " + ", ".join(cv_intel.sector_experience))
        if cv_intel.commercial_strengths:
            parts.append("Commercial Strengths: " + "; ".join(cv_intel.commercial_strengths))
        if cv_intel.evidence_gaps:
            parts.append("Evidence Gaps: " + "; ".join(cv_intel.evidence_gaps))
        if parts:
            return "[STRUCTURED CV INTELLIGENCE]\n" + "\n".join(parts)

    if cv_intel_raw:
        words = cv_intel_raw.split()
        if len(words) > 400:
            cv_intel_raw = " ".join(words[:400]) + "\n[truncated]"
        return "[CV ANALYSIS (fallback text)]\n" + cv_intel_raw

    raw = (profile.cv_text or "").strip()
    if not raw:
        return "[No CV provided]"
    words = raw.split()
    if len(words) > 600:
        raw = " ".join(words[:600]) + "\n[CV truncated]"
    return "[RAW CV TEXT]\n" + raw


def _positioning_context_block(
    positioning: Optional[PositioningOutput],
    positioning_raw: Optional[str],
) -> str:
    if positioning:
        parts = []
        if positioning.executive_positioning:
            parts.append(f"Executive Positioning: {positioning.executive_positioning}")
        if positioning.leadership_archetype:
            parts.append(f"Leadership Archetype: {positioning.leadership_archetype}")
        if positioning.narrative_to_lead:
            parts.append(f"Lead With: {positioning.narrative_to_lead}")
        if positioning.positioning_risks:
            parts.append("Positioning Risks: " + "; ".join(positioning.positioning_risks))
        if positioning.recommended_pathways:
            pw_lines = [
                f"  - {p.pathway} [{p.fit_level}]: {p.rationale}"
                for p in positioning.recommended_pathways
            ]
            parts.append("Recommended Pathways:\n" + "\n".join(pw_lines))
        if parts:
            return "[POSITIONING ASSESSMENT]\n" + "\n".join(parts)

    if positioning_raw:
        words = positioning_raw.split()
        if len(words) > 300:
            positioning_raw = " ".join(words[:300]) + "\n[truncated]"
        return "[POSITIONING ASSESSMENT (fallback text)]\n" + positioning_raw

    return "[No positioning assessment available]"


def _build_context_block(profile: ClientProfile, cv_block: str, pos_block: str) -> str:
    """Shared context header, computed once and reused across all section calls."""
    return (
        f"CLIENT PROFILE:\n{_profile_block(profile)}\n\n"
        f"CV EVIDENCE:\n{cv_block}\n\n"
        f"POSITIONING:\n{pos_block}"
    )


# ── Tavily search ─────────────────────────────────────────────────────────────

def _tavily_search(query: str, api_key: str) -> list:
    try:
        resp = httpx.post(
            _TAVILY_URL,
            json={
                "api_key": api_key,
                "query": query,
                "max_results": _RESULTS_PER_QUERY,
                "search_depth": "advanced",
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        out = []
        for r in resp.json().get("results", []):
            snippet = r.get("content", "")
            words = snippet.split()
            if len(words) > _SNIPPET_MAX_WORDS:
                snippet = " ".join(words[:_SNIPPET_MAX_WORDS]) + "…"
            out.append({
                "title": r.get("title", ""),
                "url":   r.get("url", ""),
                "snippet": snippet,
                "query": query,
            })
        return out
    except Exception as exc:
        logger.warning("tavily search failed for %r: %s", query, exc)
        return []


# ── Query generation ──────────────────────────────────────────────────────────

def _static_fallback_queries(
    profile: ClientProfile,
    cv_intel: Optional[CVIntelligence],
    positioning: Optional[PositioningOutput],
) -> List[str]:
    geo = profile.target_geography or ""
    role = profile.desired_next_move or profile.current_role or "executive"
    sector = ""
    if cv_intel and cv_intel.sector_experience:
        sector = cv_intel.sector_experience[0]

    queries = []
    if sector:
        queries.append(f"{sector} CEO OR CFO OR COO appointment {geo} 2025")
        queries.append(f"PE portfolio {sector} transformation executive hire 2025")
        queries.append(f"{sector} acquisition OR restructure OR merger {geo} 2025")
    queries.append(f"{role} executive search {geo} 2025")
    queries.append(f"interim OR fractional {sector or 'executive'} leadership {geo}")
    queries.append(f"{sector or 'executive'} board NED appointment {geo} 2025")
    queries.append(f"{sector or 'business'} expansion {geo} leadership hire 2025")
    queries.append(f"{sector or 'corporate'} leadership change {geo} 2025")
    return queries[:_MAX_QUERIES]


def _generate_queries(
    profile: ClientProfile,
    cv_intel: Optional[CVIntelligence],
    positioning: Optional[PositioningOutput],
    anthropic_client,
) -> List[str]:
    ctx: List[str] = []
    if profile.current_role:
        ctx.append(f"Current role: {profile.current_role}")
    if profile.desired_next_move:
        ctx.append(f"Desired move: {profile.desired_next_move}")
    if profile.target_geography:
        ctx.append(f"Target geography: {profile.target_geography}")
    if profile.roles_wanted:
        ctx.append(f"Roles wanted: {profile.roles_wanted}")
    if cv_intel and cv_intel.sector_experience:
        ctx.append("Sectors: " + ", ".join(cv_intel.sector_experience[:4]))
    if cv_intel and cv_intel.core_capabilities:
        ctx.append("Key capabilities: " + "; ".join(cv_intel.core_capabilities[:3]))
    if positioning and positioning.leadership_archetype:
        ctx.append(f"Leadership archetype: {positioning.leadership_archetype}")
    if positioning and positioning.recommended_pathways:
        names = [p.pathway for p in positioning.recommended_pathways[:3] if p.pathway]
        if names:
            ctx.append("Top pathways: " + ", ".join(names))

    prompt = (
        "Generate 8 targeted web search queries for executive market intelligence. "
        "Find: leadership appointments, executive hirings, company restructures, "
        "PE/acquisition activity, expansion signals, and hidden-market opportunities.\n\n"
        "CLIENT CONTEXT:\n" + "\n".join(ctx) + "\n\n"
        "Categories to cover:\n"
        "1. Executive appointments in target sector + geography (2024-2025)\n"
        "2. PE portfolio company transformation leadership in target sector\n"
        "3. Acquisitions, restructures, or leadership changes in target sector\n"
        "4. Interim or fractional executive roles in target sector\n"
        "5. Expansion signals in target sector/geography\n"
        "6. Board or NED appointments relevant to this profile\n"
        "7. Hidden-market opportunities in target sector\n"
        "8. Specific company names from the client's background with recent changes\n\n"
        'Return ONLY a JSON array of 8 query strings. No explanation, no markdown.\n'
        'Example: ["query one", "query two"]'
    )

    try:
        response = anthropic_client.messages.create(
            model=_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        queries = json.loads(text)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            logger.info("market_radar: generated %d queries via Haiku", len(queries))
            return queries[:_MAX_QUERIES]
    except Exception as exc:
        logger.warning("market_radar: query generation failed (%s), using static fallback", exc)

    return _static_fallback_queries(profile, cv_intel, positioning)


# ── Sanitiser ─────────────────────────────────────────────────────────────────
# Strips any leaked "Result N" or "[S1]"-style refs from advisory text fields.

_RE_PAREN        = re.compile(r'\s*\(\s*(?:search\s+)?[Rr]esults?\s+[\d\s,–\-]+\)', re.I)
_RE_BRACKET      = re.compile(r'\s*\[\s*(?:search\s+)?[Rr]esults?\s+[\d\s,–\-]+\]', re.I)
_RE_INLINE       = re.compile(
    r'\b(?:search\s+)?[Rr]esults?\s+\d+(?:\s*[–\-]\s*\d+)?(?:\s*,\s*\d+(?:\s*[–\-]\s*\d+)?)*',
    re.I,
)
_RE_SOURCE_ID    = re.compile(r'\s*\[\s*S\d+\s*\]', re.I)   # strips leaked [S1] refs
_RE_SPACES       = re.compile(r'  +')
_RE_ORPHAN_COMMA = re.compile(r'\s*,\s*,|\s*,\s*$|^\s*,\s*')


def _clean(text: str) -> str:
    if not text:
        return text
    text = _RE_PAREN.sub('', text)
    text = _RE_BRACKET.sub('', text)
    text = _RE_INLINE.sub('', text)
    text = _RE_SOURCE_ID.sub('', text)
    text = _RE_SPACES.sub(' ', text)
    text = _RE_ORPHAN_COMMA.sub('', text)
    return text.strip()


def _sanitise_radar(radar: MarketRadarOutput) -> MarketRadarOutput:
    def cl(lst: list) -> list:
        return [_clean(s) for s in lst]

    radar.market_summary = _clean(radar.market_summary)

    for pw in radar.priority_pathways:
        pw.why_relevant = _clean(pw.why_relevant)
        pw.market_pull  = _clean(pw.market_pull)
        pw.watchouts    = _clean(pw.watchouts)

    for co in radar.target_companies:
        co.why_relevant      = _clean(co.why_relevant)
        co.signal_or_trigger = _clean(co.signal_or_trigger)
        co.entry_route       = _clean(co.entry_route)

    for sig in radar.market_signals:
        sig.signal                = _clean(sig.signal)
        sig.evidence_or_rationale = _clean(sig.evidence_or_rationale)
        sig.recommended_action    = _clean(sig.recommended_action)

    for hyp in radar.hidden_market_hypotheses:
        hyp.hypothesis       = _clean(hyp.hypothesis)
        hyp.trigger          = _clean(hyp.trigger)
        hyp.why_client_fits  = _clean(hyp.why_client_fits)
        hyp.what_to_validate = _clean(hyp.what_to_validate)

    for rel in radar.relationship_strategy:
        rel.relationship_angle     = _clean(rel.relationship_angle)
        rel.suggested_conversation = _clean(rel.suggested_conversation)

    radar.advisor_only_notes    = cl(radar.advisor_only_notes)
    radar.next_research_actions = cl(radar.next_research_actions)

    return radar


# ── Section generation ────────────────────────────────────────────────────────

_SOURCE_ATTRIBUTION_RULES = (
    "\n\nSOURCE ATTRIBUTION RULES:\n"
    "• In the sources field, list ONLY source ID strings from the SOURCES block "
    "(e.g. [\"S1\", \"S3\"])\n"
    "• Do NOT copy titles, URLs, or any text from sources into text fields\n"
    "• Do NOT write source IDs or any index reference inside any text field\n"
    "• confidence 'verified' → sources must contain at least one ID\n"
    "• confidence 'inferred' → include the triggering source ID if available\n"
    "• confidence 'hypothesis' → sources must be empty []"
)

_CLEAN_LANGUAGE_RULES = (
    "\n\nCLEAN LANGUAGE RULES:\n"
    "• All advisory prose must read as clean business intelligence\n"
    "• Never write source IDs, result numbers, or any internal index inside a text field\n"
    "• Single line per string field — no literal newlines inside a string value"
)


def _build_section_prompt(
    section: str,
    ctx_block: str,
    sources_block: str,
    mode: str,
    retry_note: Optional[str] = None,
) -> str:
    mode_note = {
        "full": (
            "Research results are from live web searches. "
            "Apply confidence labels strictly: only 'verified' when a source explicitly "
            "states the fact."
        ),
        "manual": (
            "Research is advisor-provided context. Apply confidence labels based on how "
            "explicitly the research supports each claim."
        ),
        "profile_only": (
            "No external research is available. All market_signal confidence values must "
            "be 'hypothesis'. Provide your best advisory reasoning from the client context."
        ),
    }[mode]

    attribution = _SOURCE_ATTRIBUTION_RULES if section in _SOURCED_SECTIONS else ""
    tool_name = _SECTION_TOOLS[section]["name"]

    prompt = (
        "You are supporting an executive transition advisor with targeted market intelligence.\n\n"
        f"TASK: {_SECTION_INSTRUCTIONS[section]}\n\n"
        f"MODE: {mode_note}"
        f"{attribution}"
        f"{_CLEAN_LANGUAGE_RULES}\n\n"
        f"CONTEXT:\n{ctx_block}\n\n"
        f"SOURCES:\n{sources_block}\n\n"
        f"Use the {tool_name} tool to return your result."
    )

    if retry_note:
        prompt += f"\n\nRETRY INSTRUCTION: {retry_note}"

    return prompt


def _call_section(
    anthropic_client,
    section: str,
    prompt: str,
    max_tokens: int,
) -> Optional[dict]:
    """Call the forced-tool-use endpoint for one section. Returns raw dict or None."""
    tool = _SECTION_TOOLS[section]
    response = anthropic_client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    tool_block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if tool_block is None:
        logger.warning(
            "market_radar: section=%s no tool_use block stop_reason=%s",
            section, response.stop_reason,
        )
        return None
    return tool_block.input  # Python dict — no JSON parsing needed


def _parse_section_result(
    section: str,
    data: Optional[dict],
    source_map: Dict[str, dict],
):
    """
    Parse raw tool dict for one section.
    Resolves source ID strings to RadarSource objects for sourced sections.
    Returns str for market_summary; List[Pydantic model] for list sections.
    """
    if data is None:
        return "" if section == "market_summary" else []

    def fstr(item: dict, key: str) -> str:
        return _clean(str(item.get(key) or "").strip())

    def resolve(ids) -> List[RadarSource]:
        return _resolve_source_ids(ids if isinstance(ids, list) else [], source_map)

    if section == "market_summary":
        v = data.get("market_summary")
        return _clean(str(v).strip()) if v and not isinstance(v, (list, dict)) else ""

    if section == "priority_pathways":
        out = []
        for item in (data.get("priority_pathways") or []):
            if isinstance(item, dict):
                out.append(MarketRadarPathway(
                    pathway=str(item.get("pathway") or "").strip(),
                    why_relevant=fstr(item, "why_relevant"),
                    market_pull=fstr(item, "market_pull"),
                    fit_level=str(item.get("fit_level") or "").strip(),
                    watchouts=fstr(item, "watchouts"),
                ))
        return out

    if section == "target_companies":
        out = []
        for item in (data.get("target_companies") or []):
            if isinstance(item, dict):
                out.append(TargetCompany(
                    company=str(item.get("company") or "").strip(),
                    category=str(item.get("category") or "").strip(),
                    why_relevant=fstr(item, "why_relevant"),
                    signal_or_trigger=fstr(item, "signal_or_trigger"),
                    entry_route=fstr(item, "entry_route"),
                    priority=str(item.get("priority") or "").strip(),
                    sources=resolve(item.get("sources")),
                ))
        return out

    if section == "market_signals":
        out = []
        for item in (data.get("market_signals") or []):
            if isinstance(item, dict):
                out.append(MarketRadarSignal(
                    signal=fstr(item, "signal"),
                    signal_type=str(item.get("signal_type") or "").strip(),
                    company=str(item.get("company") or "").strip(),
                    evidence_or_rationale=fstr(item, "evidence_or_rationale"),
                    confidence=str(item.get("confidence") or "").strip(),
                    recommended_action=fstr(item, "recommended_action"),
                    sources=resolve(item.get("sources")),
                ))
        return out

    if section == "hidden_market_hypotheses":
        out = []
        for item in (data.get("hidden_market_hypotheses") or []):
            if isinstance(item, dict):
                out.append(HiddenMarketHypothesis(
                    hypothesis=fstr(item, "hypothesis"),
                    trigger=fstr(item, "trigger"),
                    why_client_fits=fstr(item, "why_client_fits"),
                    what_to_validate=fstr(item, "what_to_validate"),
                    confidence=str(item.get("confidence") or "").strip(),
                    sources=resolve(item.get("sources")),
                ))
        return out

    if section == "relationship_strategy":
        out = []
        for item in (data.get("relationship_strategy") or []):
            if isinstance(item, dict):
                out.append(RelationshipStrategy(
                    target=str(item.get("target") or "").strip(),
                    relationship_angle=fstr(item, "relationship_angle"),
                    suggested_conversation=fstr(item, "suggested_conversation"),
                ))
        return out

    if section == "next_research_actions":
        return [_clean(str(i).strip()) for i in (data.get("next_research_actions") or []) if i]

    if section == "advisor_only_notes":
        return [_clean(str(i).strip()) for i in (data.get("advisor_only_notes") or []) if i]

    logger.warning("market_radar: unknown section %r in _parse_section_result", section)
    return []


def _validate_section(section: str, result) -> bool:
    """True if the section result meets its minimum threshold."""
    if section == "market_summary":
        return bool(result and str(result).strip())
    minimum = _COMPLETENESS_MIN.get(section, 1)
    return isinstance(result, list) and len(result) >= minimum


def _generate_section(
    anthropic_client,
    section: str,
    ctx_block: str,
    sources_block: str,
    source_map: Dict[str, dict],
    mode: str,
) -> Tuple:
    """
    Generate one section end-to-end. Returns (result, is_complete).
    Validates result; retries once if below minimum. Never raises.
    """
    max_tokens = _SECTION_MAX_TOKENS[section]
    empty: object = "" if section == "market_summary" else []

    # ── Attempt 1 ────────────────────────────────────────────────────────────
    result = empty
    try:
        prompt = _build_section_prompt(section, ctx_block, sources_block, mode)
        data = _call_section(anthropic_client, section, prompt, max_tokens)
        result = _parse_section_result(section, data, source_map)
    except Exception as exc:
        logger.warning("market_radar: section=%s attempt-1 error: %s", section, exc)

    if _validate_section(section, result):
        count = len(result) if isinstance(result, list) else 1
        logger.info("market_radar: section=%s ok count=%d", section, count)
        return result, True

    # ── Retry ─────────────────────────────────────────────────────────────────
    first_count = len(result) if isinstance(result, list) else (1 if result else 0)
    minimum = _COMPLETENESS_MIN.get(section, 1) if section != "market_summary" else 1
    retry_note = (
        f"The previous attempt returned {first_count} item(s); "
        f"the minimum required is {minimum}. "
        "You MUST return at least that many items. "
        "Use reasoned inference or hypothesis labels where direct evidence is limited."
    )
    logger.warning(
        "market_radar: section=%s incomplete got=%d need=%d — retrying",
        section, first_count, minimum,
    )

    result2 = empty
    try:
        prompt2 = _build_section_prompt(
            section, ctx_block, sources_block, mode, retry_note=retry_note
        )
        data2 = _call_section(anthropic_client, section, prompt2, max_tokens)
        result2 = _parse_section_result(section, data2, source_map)
    except Exception as exc:
        logger.warning("market_radar: section=%s retry error: %s", section, exc)

    if _validate_section(section, result2):
        count = len(result2) if isinstance(result2, list) else 1
        logger.info("market_radar: section=%s retry ok count=%d", section, count)
        return result2, True

    # Both attempts insufficient — keep whichever produced more content
    second_count = len(result2) if isinstance(result2, list) else (1 if result2 else 0)
    best = result2 if second_count > first_count else result
    logger.error(
        "market_radar: section=%s failed after retry best=%d need=%d",
        section, max(first_count, second_count), minimum,
    )
    return best, False


# ── Public entry point ────────────────────────────────────────────────────────

def run_market_radar(
    profile: ClientProfile,
    cv_intelligence: Optional[CVIntelligence] = None,
    cv_intelligence_raw: Optional[str] = None,
    positioning: Optional[PositioningOutput] = None,
    positioning_raw: Optional[str] = None,
    manual_research: Optional[str] = None,
) -> MarketRadarResult:
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed — add it to requirements.txt") from exc

    if not profile.cv_text and not profile.desired_next_move and not profile.current_role:
        raise ValueError(
            "Insufficient profile data. Provide at least a CV, current role, or desired next move."
        )

    anthropic_client = anthropic.Anthropic()
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()

    # ── Mode detection and search ─────────────────────────────────────────────
    search_results: list = []

    if tavily_key:
        mode = "full"
        queries = _generate_queries(profile, cv_intelligence, positioning, anthropic_client)
        for query in queries:
            search_results.extend(_tavily_search(query, tavily_key))
        logger.info(
            "market_radar: full mode %d queries %d results",
            len(queries), len(search_results),
        )
    elif manual_research and manual_research.strip():
        mode = "manual"
        logger.info("market_radar: manual mode %d chars", len(manual_research))
    else:
        mode = "profile_only"
        logger.info("market_radar: profile-only mode")

    # ── Build source map and shared context ───────────────────────────────────
    source_map, manual_block = _build_source_map(search_results, manual_research)
    sources_block = _format_sources_block(source_map, manual_block)
    logger.info("market_radar: source map %d entries", len(source_map))

    cv_block  = _cv_context_block(profile, cv_intelligence, cv_intelligence_raw)
    pos_block = _positioning_context_block(positioning, positioning_raw)
    ctx_block = _build_context_block(profile, cv_block, pos_block)

    # ── Section pipeline ──────────────────────────────────────────────────────
    section_results: Dict[str, object] = {}
    incomplete_sections: List[str] = []

    for section in _PIPELINE_SECTIONS:
        result, ok = _generate_section(
            anthropic_client, section, ctx_block, sources_block, source_map, mode
        )
        section_results[section] = result
        if not ok:
            incomplete_sections.append(section)

    # ── Assemble ──────────────────────────────────────────────────────────────
    source_urls = list(dict.fromkeys(
        src["url"] for src in source_map.values() if src.get("url")
    ))

    radar = MarketRadarOutput(
        market_summary=section_results.get("market_summary", ""),
        priority_pathways=section_results.get("priority_pathways", []),
        target_companies=section_results.get("target_companies", []),
        market_signals=section_results.get("market_signals", []),
        hidden_market_hypotheses=section_results.get("hidden_market_hypotheses", []),
        relationship_strategy=section_results.get("relationship_strategy", []),
        next_research_actions=section_results.get("next_research_actions", []),
        advisor_only_notes=section_results.get("advisor_only_notes", []),
        source_urls=source_urls,
    )

    radar = _sanitise_radar(radar)

    is_complete = len(incomplete_sections) == 0
    logger.info(
        "market_radar: pipeline done mode=%s complete=%s incomplete=%s",
        mode, is_complete, incomplete_sections or "none",
    )

    return MarketRadarResult(
        radar=radar,
        parse_failed=False,
        mode=mode,
        is_complete=is_complete,
        missing_sections=incomplete_sections,
    )
