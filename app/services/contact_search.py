"""
Contact search service.

Finds plausible real people to contact at target companies using
web search (Tavily) + Claude Haiku extraction.

Rules enforced at every level:
- Only include people EXPLICITLY named in search result snippets.
- Never fabricate names, titles, or LinkedIn URLs.
- LinkedIn URLs included only when directly found in search results.
- Confidence labels reflect evidence quality honestly.
- If search results are weak, return fewer contacts rather than guess.

If Tavily is not configured, searches still run using Claude's
training knowledge but all results are marked confidence=Low and
clearly labelled as not web-verified.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

_MODEL = os.getenv("MARKET_RADAR_MODEL", "claude-haiku-4-5-20251001")
_TAVILY_URL = "https://api.tavily.com/search"
_SNIPPET_MAX_WORDS = 80
_MAX_QUERIES = 5
_RESULTS_PER_QUERY = 3


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class SuggestedContact:
    name: str = ""
    title: str = ""
    company: str = ""
    linkedin_url: str = ""
    source_url: str = ""
    why_relevant: str = ""
    suggested_angle: str = ""
    confidence: str = "Low"


@dataclass
class ContactSearchResult:
    contacts: List[SuggestedContact] = field(default_factory=list)
    search_mode: str = "none"   # "web" | "knowledge" | "none"
    message: str = ""


# ── Tool schema ───────────────────────────────────────────────────────────────

_TOOL = {
    "name": "submit_contact_suggestions",
    "description": (
        "Submit 3-10 suggested people to contact at the target company. "
        "Only include people explicitly mentioned in the sources provided. "
        "Never invent names, titles, or URLs."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "contacts": {
                "type": "array",
                "description": "3-10 suggested contacts. Only include people explicitly named in sources.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Full name exactly as found in sources. Never invent names.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Job title as found in sources. Leave empty if not clear.",
                        },
                        "company": {"type": "string"},
                        "linkedin_url": {
                            "type": "string",
                            "description": (
                                "Full LinkedIn profile URL only if explicitly present in a source URL. "
                                "Empty string if not found. Never construct or guess LinkedIn URLs."
                            ),
                        },
                        "source_url": {
                            "type": "string",
                            "description": "URL of the source where this person was mentioned.",
                        },
                        "why_relevant": {
                            "type": "string",
                            "description": "Why this person is a useful contact. Under 20 words.",
                        },
                        "suggested_angle": {
                            "type": "string",
                            "description": "How to approach or frame contact. Under 20 words.",
                        },
                        "confidence": {
                            "type": "string",
                            "enum": ["High", "Medium", "Low"],
                            "description": (
                                "High: name + title + LinkedIn URL all confirmed from sources. "
                                "Medium: name + title confirmed, URL missing. "
                                "Low: mentioned but details incomplete or uncertain."
                            ),
                        },
                    },
                    "required": [
                        "name", "title", "company", "linkedin_url", "source_url",
                        "why_relevant", "suggested_angle", "confidence",
                    ],
                },
            }
        },
        "required": ["contacts"],
    },
}


# ── Query builder ─────────────────────────────────────────────────────────────

def _build_queries(company: str, role_context: str, search_focus: str) -> List[str]:
    queries = [
        f'site:linkedin.com/in "{company}" CEO OR COO OR CFO OR CTO',
        f'"{company}" chief executive OR chief operating OR chief technology 2024 2025',
        f'"{company}" leadership team executive directors',
    ]
    if role_context:
        queries.append(f'site:linkedin.com/in "{company}" "{role_context}"')
    if search_focus:
        queries.append(f'"{company}" {search_focus} executive contact')
    return queries[:_MAX_QUERIES]


# ── Tavily search ─────────────────────────────────────────────────────────────

def _tavily_search(query: str, api_key: str) -> List[dict]:
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
                "url": r.get("url", ""),
                "snippet": snippet,
            })
        return out
    except Exception as exc:
        logger.warning("contact search: tavily query failed %r: %s", query, exc)
        return []


def _format_sources(results: List[dict]) -> str:
    if not results:
        return "[No web search results available — use only general knowledge about the company.]"
    lines = []
    for i, r in enumerate(results, 1):
        line = f"[S{i}]"
        if r.get("title"):
            line += f" {r['title']}"
        if r.get("url"):
            line += f"\n     {r['url']}"
        if r.get("snippet"):
            line += f"\n     {r['snippet']}"
        lines.append(line)
    return "\n".join(lines)


# ── Claude extraction ─────────────────────────────────────────────────────────

def _extract_contacts(
    anthropic_client,
    company: str,
    role_context: str,
    search_focus: str,
    sources_block: str,
    web_available: bool,
) -> List[SuggestedContact]:
    if web_available:
        fabrication_rule = (
            "CRITICAL: Only include people EXPLICITLY NAMED in the sources below. "
            "Do NOT invent names. Do NOT construct LinkedIn URLs — only include a "
            "linkedin_url if the exact URL appears in the sources."
        )
        confidence_note = "Confidence must reflect actual source evidence."
    else:
        fabrication_rule = (
            "No live web search was available. Use only well-established public knowledge "
            "about typical leadership at this company. Set confidence=Low for all contacts. "
            "Do NOT invent LinkedIn URLs — set linkedin_url to empty string for all contacts."
        )
        confidence_note = "All contacts must have confidence=Low since no live sources are available."

    focus_line = ""
    if role_context:
        focus_line = f"ROLE CONTEXT: Focus on people relevant to a client seeking a {role_context} role.\n"
    if search_focus:
        focus_line += f"SEARCH FOCUS: {search_focus}\n"

    prompt = (
        f"You are supporting an executive transition advisor identifying people to contact "
        f"at a specific company.\n\n"
        f"COMPANY: {company}\n"
        f"{focus_line}\n"
        f"{fabrication_rule}\n"
        f"{confidence_note}\n\n"
        f"SOURCES:\n{sources_block}\n\n"
        f"Use the submit_contact_suggestions tool. Return 3-8 contacts. "
        f"Return fewer if the sources are weak — do not pad with invented names."
    )

    try:
        response = anthropic_client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "submit_contact_suggestions"},
            messages=[{"role": "user", "content": prompt}],
        )
        block = next(
            (b for b in response.content if getattr(b, "type", None) == "tool_use"),
            None,
        )
        if not block:
            return []

        contacts = []
        for item in (block.input.get("contacts") or []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            contacts.append(SuggestedContact(
                name=name,
                title=str(item.get("title") or "").strip(),
                company=str(item.get("company") or company).strip(),
                linkedin_url=str(item.get("linkedin_url") or "").strip(),
                source_url=str(item.get("source_url") or "").strip(),
                why_relevant=str(item.get("why_relevant") or "").strip(),
                suggested_angle=str(item.get("suggested_angle") or "").strip(),
                confidence=str(item.get("confidence") or "Low").strip(),
            ))
        return contacts
    except Exception as exc:
        logger.error("contact search: extraction failed: %s", exc)
        return []


# ── Public entry point ────────────────────────────────────────────────────────

def search_contacts(
    company: str,
    role_context: str = "",
    search_focus: str = "",
) -> ContactSearchResult:
    if not company.strip():
        return ContactSearchResult(message="Company name is required.")

    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed") from exc

    anthropic_client = anthropic.Anthropic()
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()

    if tavily_key:
        queries = _build_queries(company, role_context, search_focus)
        all_results: List[dict] = []
        seen_urls: set = set()
        for q in queries:
            for r in _tavily_search(q, tavily_key):
                url = r.get("url", "")
                if url and url in seen_urls:
                    continue
                all_results.append(r)
                if url:
                    seen_urls.add(url)
        sources_block = _format_sources(all_results[:15])
        web_available = True
        mode = "web"
        logger.info("contact_search: web mode %d results for %r", len(all_results), company)
    else:
        sources_block = _format_sources([])
        web_available = False
        mode = "knowledge"
        logger.info("contact_search: knowledge mode (no Tavily) for %r", company)

    contacts = _extract_contacts(
        anthropic_client, company, role_context, search_focus,
        sources_block, web_available,
    )

    message = "" if web_available else (
        "Web search not configured — contacts based on general knowledge only. "
        "Confidence is Low for all results. Verify before contacting."
    )

    logger.info("contact_search: returned %d contacts mode=%s", len(contacts), mode)
    return ContactSearchResult(contacts=contacts, search_mode=mode, message=message)
