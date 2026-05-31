"""
CV Intelligence service.

Primary path  — Anthropic tool use with forced tool_choice.
  The SDK returns block.input as a Python dict validated against the schema.
  No JSON string parsing. No escaping issues. No truncation surprises.

Fallback path — sectioned markdown.
  If the tool-use call fails for any reason (network, SDK version, unexpected
  stop reason), a second call asks for structured markdown sections instead.
  The raw markdown is returned and stored on the client record so the advisor
  sees useful output rather than a hard error.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from app.models.client import ClientProfile, CVIntelligence, LeadershipScale

logger = logging.getLogger(__name__)

_MODEL: str = os.getenv("CV_INTELLIGENCE_MODEL", "claude-haiku-4-5-20251001")


# ── Anthropic error classifier ────────────────────────────────────────────────

def _classify_anthropic_error(exc: Exception) -> str:
    """
    Map Anthropic SDK exception types to user-facing error strings.
    Never includes the API key or any secret material.
    """
    try:
        import anthropic as _ant  # noqa: PLC0415
        if isinstance(exc, _ant.AuthenticationError):
            return (
                "Anthropic authentication failed — ANTHROPIC_API_KEY on Railway "
                "is missing or invalid"
            )
        if isinstance(exc, _ant.RateLimitError):
            return "Anthropic rate limit or credit limit reached"
        if isinstance(exc, _ant.APIConnectionError):
            return "Anthropic API connection failed from Railway (network or DNS)"
        if isinstance(exc, _ant.APITimeoutError):
            return "Anthropic API request timed out from Railway"
        if isinstance(exc, _ant.APIStatusError):
            return f"Anthropic API returned HTTP {exc.status_code}"
    except ImportError:
        pass
    return f"{type(exc).__name__}: {exc}"

# Truncate very long CVs before they inflate the response.
_CV_MAX_WORDS = 1200


# ── Tool schema ───────────────────────────────────────────────────────────────

_TOOL = {
    "name": "submit_cv_intelligence",
    "description": (
        "Submit structured CV intelligence extracted from an executive's CV. "
        "All string values must be on a single line with no literal newlines. "
        "Keep list items concise — under 20 words each."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "executive_summary": {
                "type": "string",
                "description": (
                    "2 sentences, single line, no newlines, under 60 words. "
                    "Cite specific organisations, deal sizes, or sector patterns."
                ),
            },
            "career_arc": {
                "type": "string",
                "description": (
                    "1 sentence, single line, no newlines, under 25 words. "
                    "Describe the trajectory pattern (e.g. ascending operator, advisory drift, builder-then-operator)."
                ),
            },
            "core_capabilities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4–6 specific functional capabilities evidenced in the CV. Not 'leadership' — specific skills like 'PE-backed M&A execution'.",
            },
            "signature_achievements": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3–5 achievements with scale/figure, each under 25 words. Only include directly evidenced achievements.",
            },
            "leadership_scale": {
                "type": "object",
                "description": "Largest scales evidenced in the CV. Use empty string if not evidenced.",
                "properties": {
                    "team_size":      {"type": "string", "description": "Largest team size evidenced with context."},
                    "revenue_or_pnl": {"type": "string", "description": "Largest revenue or P&L figure evidenced."},
                    "geography":      {"type": "string", "description": "Geographic scope evidenced."},
                    "stakeholders":   {"type": "string", "description": "Highest stakeholder level evidenced."},
                },
                "required": ["team_size", "revenue_or_pnl", "geography", "stakeholders"],
            },
            "sector_experience": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Sectors with demonstrable evidenced experience.",
            },
            "role_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2–4 observable patterns across the career arc, each under 20 words.",
            },
            "commercial_strengths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific commercial skills evidenced: deals, revenue, clients, pricing. Empty list if not evidenced.",
            },
            "transformation_strengths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific transformation skills evidenced: restructuring, OpEx, change. Empty list if not evidenced.",
            },
            "evidence_gaps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Capabilities claimed or implied but NOT evidenced with specific examples or figures.",
            },
            "under_positioned_assets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Genuine strengths present in the evidence but poorly emphasised in the current CV.",
            },
            "cv_improvement_recommendations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific actionable CV fixes — structure, language, missing evidence, emphasis.",
            },
            "advisor_only_notes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Advisor-only observations not for the client: pattern concerns, narrative inconsistencies, perception risks.",
            },
        },
        "required": [
            "executive_summary", "career_arc", "core_capabilities",
            "signature_achievements", "leadership_scale", "sector_experience",
            "role_patterns", "commercial_strengths", "transformation_strengths",
            "evidence_gaps", "under_positioned_assets",
            "cv_improvement_recommendations", "advisor_only_notes",
        ],
    },
}


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class CVAnalysisResult:
    intelligence: Optional[CVIntelligence] = None
    raw_text: Optional[str] = None          # set when tool use fails
    parse_failed: bool = False


# ── CV truncation ─────────────────────────────────────────────────────────────

def _truncate_cv(text: str) -> str:
    words = text.split()
    if len(words) <= _CV_MAX_WORDS:
        return text
    logger.info("cv_intelligence: CV truncated from %d to %d words", len(words), _CV_MAX_WORDS)
    return " ".join(words[:_CV_MAX_WORDS]) + "\n[CV truncated for analysis]"


# ── Tool use path (primary) ───────────────────────────────────────────────────

def _tool_use_prompt(cv_text: str, desired_next_move: str) -> str:
    return (
        f"You are an analyst for an executive transition advisor.\n\n"
        f"CLIENT'S DESIRED NEXT MOVE: {desired_next_move}\n\n"
        f"CV:\n{cv_text}\n\n"
        f"Use the submit_cv_intelligence tool to return your analysis. "
        f"Be commercially specific. Cite figures and organisations from the CV. "
        f"Do not invent evidence. Keep every string on a single line."
    )


def _call_tool_use(client, cv_text: str, desired_next_move: str) -> Optional[CVIntelligence]:
    prompt = _tool_use_prompt(cv_text, desired_next_move)

    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "submit_cv_intelligence"},
        messages=[{"role": "user", "content": prompt}],
    )

    # Locate the tool_use block
    tool_block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if tool_block is None:
        logger.warning("cv_intelligence: tool use response contained no tool_use block; stop_reason=%s", response.stop_reason)
        return None

    data = tool_block.input  # already a Python dict — no JSON parsing needed

    scale = data.get("leadership_scale") or {}
    leadership_scale = LeadershipScale(
        team_size=scale.get("team_size") or "",
        revenue_or_pnl=scale.get("revenue_or_pnl") or "",
        geography=scale.get("geography") or "",
        stakeholders=scale.get("stakeholders") or "",
    )

    def s(k: str) -> str:
        v = data.get(k)
        return str(v).strip() if v and not isinstance(v, list) else ""

    def lst(k: str) -> list:
        v = data.get(k)
        return [str(i).strip() for i in v if i] if isinstance(v, list) else []

    return CVIntelligence(
        executive_summary=s("executive_summary"),
        career_arc=s("career_arc"),
        core_capabilities=lst("core_capabilities"),
        signature_achievements=lst("signature_achievements"),
        leadership_scale=leadership_scale,
        sector_experience=lst("sector_experience"),
        role_patterns=lst("role_patterns"),
        commercial_strengths=lst("commercial_strengths"),
        transformation_strengths=lst("transformation_strengths"),
        evidence_gaps=lst("evidence_gaps"),
        under_positioned_assets=lst("under_positioned_assets"),
        cv_improvement_recommendations=lst("cv_improvement_recommendations"),
        advisor_only_notes=lst("advisor_only_notes"),
    )


# ── Markdown fallback path ────────────────────────────────────────────────────

_MARKDOWN_TEMPLATE = """\
## Executive Summary
[2 sentences. Cite specific organisations, figures, sector patterns.]

## Career Arc
[1 sentence. Describe the trajectory pattern.]

## Signature Achievements
- [achievement with scale/outcome]
- [achievement with scale/outcome]
- [achievement with scale/outcome]

## Core Capabilities
- [specific capability]
- [specific capability]
- [specific capability]
- [specific capability]

## Leadership Scale
- Team size: [largest team evidenced, or "Not evidenced"]
- Revenue / P&L: [largest figure evidenced, or "Not evidenced"]
- Geography: [scope evidenced, or "Not evidenced"]
- Stakeholders: [highest level evidenced, or "Not evidenced"]

## Sector Experience
- [sector]
- [sector]

## Commercial Strengths
- [specific commercial skill]

## Transformation Strengths
- [specific transformation skill]

## Evidence Gaps
- [gap]
- [gap]

## Under-positioned Assets
- [asset]
- [asset]

## CV Improvement Recommendations
- [specific actionable recommendation]
- [specific actionable recommendation]

## Advisor Notes (not for client)
- [advisor-only observation]"""


def _call_markdown_fallback(client, cv_text: str, desired_next_move: str) -> str:
    prompt = (
        f"You are an analyst for an executive transition advisor. "
        f"Analyse this executive CV and complete the template below. "
        f"Be commercially specific. Cite figures and organisations from the CV. "
        f"Do not add extra sections. Do not invent evidence.\n\n"
        f"CLIENT'S DESIRED NEXT MOVE: {desired_next_move}\n\n"
        f"CV:\n{cv_text}\n\n"
        f"Complete this template exactly:\n\n{_MARKDOWN_TEMPLATE}"
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── Public entry point ────────────────────────────────────────────────────────

def analyse_cv(profile: ClientProfile) -> CVAnalysisResult:
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed — add it to requirements.txt") from exc

    # ── Preflight: API key presence and basic shape ──────────────────────────
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set — add it to Railway environment variables"
        )
    if api_key.startswith("sk-ant-"):
        logger.info("cv_intelligence: ANTHROPIC_API_KEY present, prefix ok (sk-ant-...)")
    else:
        logger.warning(
            "cv_intelligence: ANTHROPIC_API_KEY is set but does not start with 'sk-ant-' "
            "(len=%d) — key may be invalid or copied incorrectly",
            len(api_key),
        )

    if not profile.cv_text or not profile.cv_text.strip():
        raise ValueError("No CV text found. Save CV text in the Profile tab first.")

    if len(profile.cv_text.split()) < 50:
        raise ValueError(
            "CV text is too short to analyse. Paste the full CV in the Profile tab."
        )

    cv_text = _truncate_cv(profile.cv_text.strip())
    desired_next_move = profile.desired_next_move.strip() or "Not specified"
    client = anthropic.Anthropic(
        timeout=anthropic.Timeout(connect=30.0, read=600.0, write=600.0, pool=600.0)
    )

    # ── Primary: tool use, one retry on transient network errors ─────────────
    _TRANSIENT = (anthropic.APIConnectionError, anthropic.APITimeoutError)

    for attempt in range(1, 3):
        try:
            intelligence = _call_tool_use(client, cv_text, desired_next_move)
            if intelligence is not None:
                logger.info("cv_intelligence: tool use succeeded (attempt %d)", attempt)
                return CVAnalysisResult(intelligence=intelligence, parse_failed=False)
            # Response arrived but contained no tool_use block — not a transient issue
            logger.warning(
                "cv_intelligence: tool use returned no block (attempt %d); falling back to markdown",
                attempt,
            )
            break
        except _TRANSIENT as exc:
            if attempt == 1:
                logger.warning(
                    "cv_intelligence: transient error attempt %d [%s: %s] — retrying",
                    attempt, type(exc).__name__, exc,
                )
                continue
            logger.warning(
                "cv_intelligence: transient error attempt %d [%s: %s] — falling back to markdown",
                attempt, type(exc).__name__, exc,
            )
        except Exception as exc:
            # Auth failures, rate limits, bad requests — do not retry
            logger.warning(
                "cv_intelligence: non-transient error attempt %d [%s: %s] — falling back to markdown",
                attempt, type(exc).__name__, exc,
            )
            break

    # ── Fallback: structured markdown ────────────────────────────────────────
    try:
        raw_text = _call_markdown_fallback(client, cv_text, desired_next_move)
        logger.info("cv_intelligence: markdown fallback succeeded (%d chars)", len(raw_text))
        return CVAnalysisResult(raw_text=raw_text, parse_failed=True)
    except Exception as exc:
        user_msg = _classify_anthropic_error(exc)
        logger.error(
            "cv_intelligence: markdown fallback also failed [%s: %s]",
            type(exc).__name__, exc,
        )
        raise RuntimeError(user_msg) from exc
