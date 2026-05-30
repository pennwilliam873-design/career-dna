"""
Executive positioning service.

Diagnoses a client's market positioning for their stated transition.
Distinct from CV Studio (which analyses what the CV proves/misses).
This service answers: how does this person land in market, what narrative
opens doors, and what risks does the advisor need to manage?

Architecture mirrors cv_intelligence.py:
  Primary path  — Anthropic tool use (forced tool_choice).
                  SDK returns block.input as a Python dict. No JSON parsing.
  Fallback path — sectioned markdown template.
                  Raw text stored on client record; never a hard crash.

If cv_intelligence is available on the client record it is injected as
structured context so the positioning is grounded in already-extracted
evidence rather than re-parsing raw CV text.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from app.models.client import ClientProfile, CVIntelligence, PositioningOutput, PositioningPathway

logger = logging.getLogger(__name__)

_MODEL: str = os.getenv("POSITIONING_MODEL", "claude-haiku-4-5-20251001")

# Truncate raw CV text if no structured intelligence is available.
_CV_MAX_WORDS = 1200


# ── Tool schema ───────────────────────────────────────────────────────────────

_TOOL = {
    "name": "submit_positioning",
    "description": (
        "Submit structured executive positioning assessment. "
        "All string values must be on a single line with no literal newlines. "
        "Keep list items concise — under 20 words each."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "executive_positioning": {
                "type": "string",
                "description": (
                    "2-3 sentences, single line, no newlines. "
                    "How this candidate lands in the market for their stated transition. "
                    "Cite specific role types, sectors, or evidence."
                ),
            },
            "leadership_archetype": {
                "type": "string",
                "description": (
                    "Single concise label. "
                    "e.g. Operational Turnaround Leader / Strategic Growth Architect / "
                    "PE Value Creation Partner / Board-Facing Advisor / Founder-to-Enterprise Operator"
                ),
            },
            "core_strengths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-5 strengths this candidate has that the market values for the target move. "
                    "Grounded in evidence. Under 15 words each."
                ),
            },
            "market_credibility": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-4 specific credibility assets: deal sizes, team scale, brand names, credentials. "
                    "Not generic leadership qualities."
                ),
            },
            "positioning_risks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 specific risks that will create friction with hiring decision-makers.",
            },
            "narrative_to_lead": {
                "type": "string",
                "description": (
                    "1-2 sentences, single line, no newlines. "
                    "The narrative thread that will resonate most for this specific transition."
                ),
            },
            "narrative_to_avoid": {
                "type": "string",
                "description": (
                    "1-2 sentences, single line, no newlines. "
                    "The narrative that will close doors or trigger doubt for this transition."
                ),
            },
            "recommended_pathways": {
                "type": "array",
                "description": "2-4 realistic transition pathways given stated goals and constraints.",
                "items": {
                    "type": "object",
                    "properties": {
                        "pathway": {
                            "type": "string",
                            "description": "Role or pathway name.",
                        },
                        "rationale": {
                            "type": "string",
                            "description": "Why this fits this candidate. Single line, under 30 words.",
                        },
                        "fit_level": {
                            "type": "string",
                            "enum": ["High", "Medium", "Stretch"],
                        },
                        "stretch_risk": {
                            "type": "string",
                            "description": "What gap must close or condition must be true. Single line, under 25 words.",
                        },
                    },
                    "required": ["pathway", "rationale", "fit_level", "stretch_risk"],
                },
            },
            "advisor_only_notes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "2-4 advisor-only observations not for the client: "
                    "blind spots, negotiation context, risks to manage."
                ),
            },
        },
        "required": [
            "executive_positioning", "leadership_archetype", "core_strengths",
            "market_credibility", "positioning_risks", "narrative_to_lead",
            "narrative_to_avoid", "recommended_pathways", "advisor_only_notes",
        ],
    },
}


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class PositioningAnalysisResult:
    positioning: Optional[PositioningOutput] = None
    raw_text: Optional[str] = None
    parse_failed: bool = False


# ── Context builders ──────────────────────────────────────────────────────────

def _cv_context_block(profile: ClientProfile, cv_intel: Optional[CVIntelligence]) -> str:
    """
    Returns the best available CV evidence block for the prompt.
    Prefers structured CV intelligence over raw text — it is more token-efficient
    and already has evidence extracted into usable signal.
    """
    if cv_intel:
        parts = []
        if cv_intel.executive_summary:
            parts.append(f"Executive Summary: {cv_intel.executive_summary}")
        if cv_intel.career_arc:
            parts.append(f"Career Arc: {cv_intel.career_arc}")
        if cv_intel.core_capabilities:
            parts.append("Core Capabilities: " + "; ".join(cv_intel.core_capabilities))
        if cv_intel.signature_achievements:
            parts.append("Signature Achievements:\n" + "\n".join(f"- {a}" for a in cv_intel.signature_achievements))
        scale = cv_intel.leadership_scale
        scale_items = [v for v in [scale.team_size, scale.revenue_or_pnl, scale.geography, scale.stakeholders] if v]
        if scale_items:
            parts.append("Leadership Scale: " + " | ".join(scale_items))
        if cv_intel.sector_experience:
            parts.append("Sectors: " + ", ".join(cv_intel.sector_experience))
        if cv_intel.commercial_strengths:
            parts.append("Commercial Strengths: " + "; ".join(cv_intel.commercial_strengths))
        if cv_intel.evidence_gaps:
            parts.append("Evidence Gaps: " + "; ".join(cv_intel.evidence_gaps))
        if cv_intel.under_positioned_assets:
            parts.append("Under-positioned Assets: " + "; ".join(cv_intel.under_positioned_assets))
        if parts:
            return "[STRUCTURED CV INTELLIGENCE]\n" + "\n".join(parts)

    # Fall back to raw CV text (truncated)
    raw = (profile.cv_text or "").strip()
    if not raw:
        return "[No CV text provided]"
    words = raw.split()
    if len(words) > _CV_MAX_WORDS:
        raw = " ".join(words[:_CV_MAX_WORDS]) + "\n[CV truncated]"
    return "[RAW CV TEXT]\n" + raw


def _profile_block(profile: ClientProfile) -> str:
    fields = {
        "Current role": profile.current_role,
        "Location": profile.location,
        "Target geography": profile.target_geography,
        "Desired next move": profile.desired_next_move,
        "Timeframe": profile.timeframe,
        "Roles wanted": profile.roles_wanted,
        "Roles not wanted": profile.roles_not_wanted,
        "Constraints": profile.constraints,
        "Relationship assets": profile.relationship_assets,
        "Advisor notes": profile.advisor_notes,
    }
    lines = [f"{k}: {v}" for k, v in fields.items() if v and v.strip()]
    return "\n".join(lines) if lines else "No profile context provided."


# ── Tool use path (primary) ───────────────────────────────────────────────────

def _tool_use_prompt(profile: ClientProfile, cv_intel: Optional[CVIntelligence]) -> str:
    return (
        "You are supporting an executive transition advisor. "
        "Diagnose this client's market positioning for their stated transition. "
        "Do not summarise the CV. Focus on how the market will read this candidate: "
        "what narrative opens doors, what creates friction, what pathways are realistic.\n\n"
        f"CLIENT PROFILE:\n{_profile_block(profile)}\n\n"
        f"CV EVIDENCE:\n{_cv_context_block(profile, cv_intel)}\n\n"
        "Use the submit_positioning tool to return your assessment. "
        "Be commercially specific. Cite actual evidence. Keep every string on a single line. "
        "If evidence is insufficient for a field, use an empty string or empty array — do not invent."
    )


def _call_tool_use(
    client,
    profile: ClientProfile,
    cv_intel: Optional[CVIntelligence],
) -> Optional[PositioningOutput]:
    prompt = _tool_use_prompt(profile, cv_intel)

    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "submit_positioning"},
        messages=[{"role": "user", "content": prompt}],
    )

    tool_block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if tool_block is None:
        logger.warning(
            "positioning: tool use response had no tool_use block; stop_reason=%s",
            response.stop_reason,
        )
        return None

    data = tool_block.input  # Python dict — no JSON parsing needed

    def s(k: str) -> str:
        v = data.get(k)
        return str(v).strip() if v and not isinstance(v, list) else ""

    def lst(k: str) -> list:
        v = data.get(k)
        return [str(i).strip() for i in v if i] if isinstance(v, list) else []

    pathways = []
    for pw in data.get("recommended_pathways") or []:
        if isinstance(pw, dict):
            pathways.append(PositioningPathway(
                pathway=str(pw.get("pathway") or "").strip(),
                rationale=str(pw.get("rationale") or "").strip(),
                fit_level=str(pw.get("fit_level") or "").strip(),
                stretch_risk=str(pw.get("stretch_risk") or "").strip(),
            ))

    return PositioningOutput(
        executive_positioning=s("executive_positioning"),
        leadership_archetype=s("leadership_archetype"),
        core_strengths=lst("core_strengths"),
        market_credibility=lst("market_credibility"),
        positioning_risks=lst("positioning_risks"),
        narrative_to_lead=s("narrative_to_lead"),
        narrative_to_avoid=s("narrative_to_avoid"),
        recommended_pathways=pathways,
        advisor_only_notes=lst("advisor_only_notes"),
    )


# ── Markdown fallback path ────────────────────────────────────────────────────

_MARKDOWN_TEMPLATE = """\
## Executive Positioning
[2-3 sentences. How this candidate lands in the market for their stated transition.]

## Leadership Archetype
[Single label, e.g. Operational Turnaround Leader]

## Core Strengths
- [strength grounded in evidence]
- [strength grounded in evidence]
- [strength grounded in evidence]

## Market Credibility
- [specific credibility asset: deal size, brand, credential]
- [specific credibility asset]
- [specific credibility asset]

## Positioning Risks
- [specific friction point for hiring decision-makers]
- [specific friction point]

## Lead With
[1-2 sentences: the narrative that opens doors for this transition]

## Avoid
[1-2 sentences: the narrative that closes doors]

## Recommended Pathways
### [Pathway Name] | [High / Medium / Stretch]
Why it fits: [1-2 sentences citing evidence]
Stretch risk: [what gap must close]

### [Pathway Name] | [High / Medium / Stretch]
Why it fits: [1-2 sentences]
Stretch risk: [what gap must close]

## Advisor Notes (not for client)
- [advisor-only observation: blind spot, negotiation context, perception risk]
- [advisor-only observation]"""


def _call_markdown_fallback(
    client,
    profile: ClientProfile,
    cv_intel: Optional[CVIntelligence],
) -> str:
    prompt = (
        "You are supporting an executive transition advisor. "
        "Diagnose this client's market positioning for their stated transition. "
        "Do not summarise the CV. Focus on market strategy: narrative, pathways, risks.\n\n"
        f"CLIENT PROFILE:\n{_profile_block(profile)}\n\n"
        f"CV EVIDENCE:\n{_cv_context_block(profile, cv_intel)}\n\n"
        f"Complete this template exactly. Do not add extra sections.\n\n{_MARKDOWN_TEMPLATE}"
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── Public entry point ────────────────────────────────────────────────────────

def generate_positioning(
    profile: ClientProfile,
    cv_intelligence: Optional[CVIntelligence] = None,
) -> PositioningAnalysisResult:
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed — add it to requirements.txt") from exc

    if not profile.cv_text and not profile.desired_next_move and not profile.current_role:
        raise ValueError(
            "Insufficient profile data. Provide at least a CV, current role, or desired next move."
        )

    client = anthropic.Anthropic()

    # ── Primary: tool use ────────────────────────────────────────────────────
    try:
        positioning = _call_tool_use(client, profile, cv_intelligence)
        if positioning is not None:
            logger.info("positioning: tool use succeeded")
            return PositioningAnalysisResult(positioning=positioning, parse_failed=False)
        logger.warning("positioning: tool use returned no block, falling back to markdown")
    except Exception as exc:
        logger.warning("positioning: tool use failed (%s), falling back to markdown", exc)

    # ── Fallback: structured markdown ────────────────────────────────────────
    try:
        raw_text = _call_markdown_fallback(client, profile, cv_intelligence)
        logger.info("positioning: markdown fallback succeeded (%d chars)", len(raw_text))
        return PositioningAnalysisResult(raw_text=raw_text, parse_failed=True)
    except Exception as exc:
        logger.error("positioning: markdown fallback also failed: %s", exc)
        raise RuntimeError(
            f"Positioning generation failed on both paths. Last error: {exc}"
        ) from exc
