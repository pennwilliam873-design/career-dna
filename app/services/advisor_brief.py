"""
Advisor Brief service.

Generates a private, advisor-facing pre-session briefing by synthesising
all stored workspace data: profile, CV intelligence, positioning, market
radar digest, and opportunities pipeline.

This brief is NOT client-facing. It is candid, commercially direct, and
may include sensitive observations about blind spots, positioning risks,
and negotiation context that should not appear in the client report.

Architecture mirrors cv_intelligence.py and positioning.py:
  Primary path  — Anthropic tool use (forced tool_choice).
  Fallback path — sectioned markdown template.
  Never a hard crash; raw text stored if structured parse fails.

Model defaults to claude-sonnet-4-6 for better synthesis across many
data sources. Override with ADVISOR_BRIEF_MODEL env var.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from app.models.client import (
    AdvisorBrief,
    ClientRecord,
    PriorityOpportunity,
)

logger = logging.getLogger(__name__)

_MODEL: str = os.getenv("ADVISOR_BRIEF_MODEL", "claude-sonnet-4-6")

_CV_MAX_WORDS  = 500   # raw CV text fallback truncation
_RAW_MAX_WORDS = 300   # other raw fallback truncation


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class AdvisorBriefResult:
    brief: Optional[AdvisorBrief] = None
    raw_text: Optional[str] = None
    parse_failed: bool = False


# ── Context builders ──────────────────────────────────────────────────────────

def _profile_block(record: ClientRecord) -> str:
    p = record.profile
    fields = {
        "Name":              p.name,
        "Current role":      p.current_role,
        "Location":          p.location,
        "Target geography":  p.target_geography,
        "Desired next move": p.desired_next_move,
        "Timeframe":         p.timeframe,
        "Roles wanted":      p.roles_wanted,
        "Roles not wanted":  p.roles_not_wanted,
        "Constraints":       p.constraints,
        "Relationship assets": p.relationship_assets,
        "Advisor notes":     p.advisor_notes,
    }
    lines = [f"{k}: {v}" for k, v in fields.items() if v and v.strip()]
    return "[CLIENT PROFILE]\n" + ("\n".join(lines) if lines else "No profile data provided.")


def _cv_block(record: ClientRecord) -> str:
    cv = record.cv_intelligence
    if cv:
        parts = []
        if cv.executive_summary:
            parts.append(f"Executive Summary: {cv.executive_summary}")
        if cv.career_arc:
            parts.append(f"Career Arc: {cv.career_arc}")
        if cv.signature_achievements:
            parts.append(
                "Signature Achievements:\n"
                + "\n".join(f"  - {a}" for a in cv.signature_achievements)
            )
        if cv.core_capabilities:
            parts.append("Core Capabilities: " + "; ".join(cv.core_capabilities))
        scale = cv.leadership_scale
        scale_items = [
            v for v in [scale.team_size, scale.revenue_or_pnl, scale.geography, scale.stakeholders]
            if v
        ]
        if scale_items:
            parts.append("Leadership Scale: " + " | ".join(scale_items))
        if cv.sector_experience:
            parts.append("Sectors: " + ", ".join(cv.sector_experience))
        if cv.evidence_gaps:
            parts.append("Evidence Gaps: " + "; ".join(cv.evidence_gaps))
        if cv.under_positioned_assets:
            parts.append("Under-positioned Assets: " + "; ".join(cv.under_positioned_assets))
        if cv.advisor_only_notes:
            parts.append(
                "CV Advisor Notes:\n" + "\n".join(f"  - {n}" for n in cv.advisor_only_notes)
            )
        if parts:
            return "[CV INTELLIGENCE]\n" + "\n".join(parts)

    raw = (record.cv_intelligence_raw or "").strip()
    if raw:
        words = raw.split()
        if len(words) > _RAW_MAX_WORDS:
            raw = " ".join(words[:_RAW_MAX_WORDS]) + "\n[truncated]"
        return "[CV ANALYSIS (fallback)]\n" + raw

    cv_text = (record.profile.cv_text or "").strip()
    if cv_text:
        words = cv_text.split()
        if len(words) > _CV_MAX_WORDS:
            cv_text = " ".join(words[:_CV_MAX_WORDS]) + "\n[CV truncated]"
        return "[RAW CV TEXT]\n" + cv_text

    return "[CV]\nNo CV data available."


def _positioning_block(record: ClientRecord) -> str:
    p = record.positioning
    if p:
        parts = []
        if p.executive_positioning:
            parts.append(f"Market Positioning: {p.executive_positioning}")
        if p.leadership_archetype:
            parts.append(f"Archetype: {p.leadership_archetype}")
        if p.narrative_to_lead:
            parts.append(f"Lead With: {p.narrative_to_lead}")
        if p.narrative_to_avoid:
            parts.append(f"Avoid: {p.narrative_to_avoid}")
        if p.positioning_risks:
            parts.append("Positioning Risks: " + "; ".join(p.positioning_risks))
        if p.core_strengths:
            parts.append("Core Strengths: " + "; ".join(p.core_strengths))
        if p.market_credibility:
            parts.append("Market Credibility: " + "; ".join(p.market_credibility))
        if p.recommended_pathways:
            pw_lines = [
                f"  - {pw.pathway} [{pw.fit_level}]: {pw.rationale}"
                for pw in p.recommended_pathways
            ]
            parts.append("Recommended Pathways:\n" + "\n".join(pw_lines))
        if p.advisor_only_notes:
            parts.append(
                "Positioning Advisor Notes:\n"
                + "\n".join(f"  - {n}" for n in p.advisor_only_notes)
            )
        if parts:
            return "[POSITIONING]\n" + "\n".join(parts)

    raw = (record.positioning_raw or "").strip()
    if raw:
        words = raw.split()
        if len(words) > _RAW_MAX_WORDS:
            raw = " ".join(words[:_RAW_MAX_WORDS]) + "\n[truncated]"
        return "[POSITIONING (fallback)]\n" + raw

    return "[POSITIONING]\nNo positioning data available."


def _radar_digest(record: ClientRecord) -> str:
    """Compact digest — top signals, companies, and advisor notes only."""
    radar = record.market_radar
    if not radar:
        raw = (record.market_radar_raw or "").strip()
        if raw:
            words = raw.split()
            if len(words) > 200:
                raw = " ".join(words[:200]) + "\n[truncated]"
            return "[MARKET RADAR (fallback)]\n" + raw
        return "[MARKET RADAR]\nNo market radar data available."

    parts = ["[MARKET RADAR DIGEST]"]

    if radar.market_summary:
        parts.append(f"Summary: {radar.market_summary}")

    # Tiered company map — use new structure if available, fall back to legacy flat list
    if radar.tier1_companies:
        parts.append("Tier 1 Priority Targets:")
        for c in radar.tier1_companies[:8]:
            line = f"  - {c.company}"
            if c.category:
                line += f" ({c.category})"
            if c.signal_or_trigger:
                line += f" — {c.signal_or_trigger}"
            if c.priority:
                line += f" [{c.priority}]"
            if c.confidence:
                line += f" [{c.confidence}]"
            parts.append(line)
            if c.advisor_angle:
                parts.append(f"    Advisor angle: {c.advisor_angle}")
        if radar.tier2_companies:
            t2_sorted = sorted(
                radar.tier2_companies,
                key=lambda c: {"High": 0, "Medium": 1, "Low": 2}.get(c.priority, 1),
            )[:5]
            parts.append("Tier 2 Strongest Picks:")
            for c in t2_sorted:
                line = f"  - {c.company}"
                if c.likely_role_angle:
                    line += f" — {c.likely_role_angle}"
                if c.priority:
                    line += f" [{c.priority}]"
                parts.append(line)
    else:
        # Backward compat: legacy flat target_companies on old records
        companies = [c for c in radar.target_companies if c.company]
        companies_sorted = sorted(
            companies,
            key=lambda c: {"High": 0, "Medium": 1, "Low": 2}.get(c.priority, 1),
        )[:5]
        if companies_sorted:
            parts.append("Target Companies:")
            for c in companies_sorted:
                line = f"  - {c.company}"
                if c.category:
                    line += f" ({c.category})"
                if c.signal_or_trigger:
                    line += f" — {c.signal_or_trigger}"
                if c.priority:
                    line += f" [{c.priority}]"
                parts.append(line)

    # Verified and inferred signals only, up to 5
    signals = [
        s for s in radar.market_signals if s.confidence in ("verified", "inferred")
    ][:5]
    if signals:
        parts.append("Key Market Signals:")
        for s in signals:
            line = f"  - [{s.confidence.upper()}] {s.signal}"
            if s.company:
                line += f" — {s.company}"
            parts.append(line)

    # High/Medium confidence hypotheses, up to 3
    hypotheses = [
        h for h in radar.hidden_market_hypotheses if h.confidence in ("High", "Medium")
    ][:3]
    if hypotheses:
        parts.append("Hidden Market Hypotheses:")
        for h in hypotheses:
            parts.append(f"  - [{h.confidence}] {h.hypothesis}")

    # Radar advisor notes — always include
    if radar.advisor_only_notes:
        parts.append("Radar Advisor Notes:")
        for n in radar.advisor_only_notes:
            parts.append(f"  - {n}")

    # Open research actions
    if radar.next_research_actions:
        parts.append("Open Research Actions:")
        for a in radar.next_research_actions[:5]:
            parts.append(f"  - {a}")

    return "\n".join(parts)


def _opportunities_block(record: ClientRecord) -> str:
    active = [
        o for o in record.opportunities if o.status not in ("Paused", "Rejected")
    ]
    if not active:
        if record.opportunities:
            return "[OPPORTUNITIES]\nAll opportunities are currently paused or rejected."
        return "[OPPORTUNITIES]\nNo opportunities saved yet."

    priority_rank = {"High": 0, "Medium": 1, "Low": 2}
    active_sorted = sorted(active, key=lambda o: priority_rank.get(o.priority, 1))

    lines = ["[OPPORTUNITIES PIPELINE]"]
    for o in active_sorted:
        line = f"  [{o.priority}] {o.title}"
        if o.company:
            line += f" — {o.company}"
        line += f" | {o.status}"
        if o.confidence:
            line += f" | {o.confidence}"
        lines.append(line)
        if o.next_action:
            lines.append(f"    Next action: {o.next_action}")
        if o.advisor_note:
            lines.append(f"    Advisor note: {o.advisor_note}")

    return "\n".join(lines)


def _notes_block(record: ClientRecord) -> str:
    notes   = record.session_notes or []
    actions = record.action_items  or []

    if not notes and not actions:
        return "[NOTES & ACTIONS]\nNo session notes or action items recorded."

    lines = ["[NOTES & ACTIONS]"]

    if notes:
        sorted_notes = sorted(notes, key=lambda n: n.date or "", reverse=True)
        lines.append("\nSession Notes (most recent first, up to 5):")
        for note in sorted_notes[:5]:
            header = f"  [{note.date or 'No date'}]"
            if note.title:
                header += f" {note.title}"
            if note.advisor_only:
                header += " [ADVISOR ONLY]"
            lines.append(header)
            if note.notes:
                text = note.notes.strip()
                if len(text) > 400:
                    text = text[:400] + "…"
                lines.append(f"    {text}")

    if actions:
        open_actions   = [a for a in actions if a.status not in ("Done", "Parked")]
        closed_actions = [a for a in actions if a.status in ("Done", "Parked")]

        if open_actions:
            lines.append("\nOpen Action Items:")
            for a in open_actions:
                line = f"  [{a.owner}] {a.action}"
                if a.due_date:
                    line += f" (due {a.due_date})"
                line += f" — {a.status}"
                lines.append(line)
                if a.related_opportunity:
                    lines.append(f"    Re: {a.related_opportunity}")
                if a.advisor_note:
                    lines.append(f"    Note: {a.advisor_note}")

        if closed_actions:
            lines.append(f"\nCompleted/Parked: {len(closed_actions)} item(s)")
            for a in closed_actions[:3]:
                lines.append(f"  [{a.owner}] {a.action} — {a.status}")

    return "\n".join(lines)


def _contacts_block(record: ClientRecord) -> str:
    contacts = record.target_contacts or []
    active = [c for c in contacts if c.status != "Parked"]
    parked = [c for c in contacts if c.status == "Parked"]

    if not active and not parked:
        return "[TARGET CONTACTS]\nNo target contacts saved yet."

    conf_rank = {"High": 0, "Medium": 1, "Low": 2}
    active_sorted = sorted(active, key=lambda c: conf_rank.get(c.confidence, 1))

    lines = ["[TARGET CONTACTS]"]
    for c in active_sorted[:8]:
        line = f"  [{c.confidence}] {c.name}"
        if c.title:
            line += f" — {c.title}"
        if c.company:
            line += f" @ {c.company}"
        line += f" | {c.status}"
        lines.append(line)
        if c.suggested_angle:
            lines.append(f"    Angle: {c.suggested_angle}")

    if parked:
        lines.append(f"\nParked: {len(parked)} contact(s)")

    return "\n".join(lines)


def _build_context(record: ClientRecord) -> str:
    return "\n\n".join([
        _profile_block(record),
        _cv_block(record),
        _positioning_block(record),
        _radar_digest(record),
        _opportunities_block(record),
        _contacts_block(record),
        _notes_block(record),
    ])


# ── Tool schema ───────────────────────────────────────────────────────────────

_TOOL = {
    "name": "submit_advisor_brief",
    "description": (
        "Submit a structured advisor pre-session brief. "
        "This is a private document for the advisor only — not the client. "
        "All string values must be on a single line with no literal newlines."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "brief_summary": {
                "type": "string",
                "description": (
                    "2-3 sentences. State of play: where this client is in their transition "
                    "and what most needs advisor attention now. Single line, no newlines."
                ),
            },
            "client_situation": {
                "type": "string",
                "description": (
                    "2-3 sentences. Current transition situation: timeline, urgency, "
                    "key constraints, and momentum. Single line, no newlines."
                ),
            },
            "session_focus": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-5 bullets describing what the next advisor-client session should achieve — "
                    "concrete conversation goals, decisions to reach, or items to validate. "
                    "Under 20 words each."
                ),
            },
            "key_positioning_insights": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-5 commercially specific insights about how this client lands in the "
                    "market and what decision-makers will read. Under 25 words each."
                ),
            },
            "priority_opportunities": {
                "type": "array",
                "description": "Top 3-5 opportunities the advisor should focus on this session.",
                "items": {
                    "type": "object",
                    "properties": {
                        "opportunity": {
                            "type": "string",
                            "description": "Opportunity title or company name. Under 15 words.",
                        },
                        "why_it_matters": {
                            "type": "string",
                            "description": "Why this is priority now. Under 25 words.",
                        },
                        "recommended_advisor_action": {
                            "type": "string",
                            "description": "What the advisor should do to advance this. Under 20 words.",
                        },
                        "risk_or_watchout": {
                            "type": "string",
                            "description": "Main friction, gap, or risk to manage. Under 20 words.",
                        },
                    },
                    "required": [
                        "opportunity", "why_it_matters",
                        "recommended_advisor_action", "risk_or_watchout",
                    ],
                },
            },
            "market_signals_to_discuss": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-5 market signals or intelligence points worth raising or acting "
                    "on for this client. Under 25 words each."
                ),
            },
            "questions_to_ask_client": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "4-6 challenging questions to ask the client — pressure-test assumptions, "
                    "surface blockers, sharpen the narrative. Phrased as questions. Under 25 words each."
                ),
            },
            "advisor_challenges": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "2-4 things the advisor should challenge — positioning gaps, beliefs the "
                    "market doesn't share, narrative risks. Framed as statements. Under 25 words each."
                ),
            },
            "recommended_next_actions": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-5 concrete advisor actions after this session: research, intros, "
                    "validation steps. Under 20 words each."
                ),
            },
            "advisor_only_notes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "2-4 sensitive advisor-only observations NOT for the client: blind spots, "
                    "perception risks, negotiation position, timing pressures. Under 25 words each."
                ),
            },
        },
        "required": [
            "brief_summary", "client_situation", "session_focus",
            "key_positioning_insights", "priority_opportunities",
            "market_signals_to_discuss", "questions_to_ask_client",
            "advisor_challenges", "recommended_next_actions", "advisor_only_notes",
        ],
    },
}


# ── Markdown fallback template ────────────────────────────────────────────────

_MARKDOWN_TEMPLATE = """\
## Brief Summary
[2-3 sentences. State of play and what needs advisor attention now.]

## Client Situation
[2-3 sentences. Where the client is in their transition, timeline, key constraints.]

## Session Focus
- [concrete goal or decision for this advisor-client session]
- [goal]
- [goal]

## Key Positioning Insights
- [commercially specific positioning insight]
- [insight]
- [insight]

## Priority Opportunities
### [Opportunity / Company Name]
Why it matters: [1-2 sentences]
Advisor action: [specific next step for the advisor]
Risk / watch out: [main friction or gap to manage]

### [Opportunity / Company Name]
Why it matters: [1-2 sentences]
Advisor action: [specific next step]
Risk / watch out: [main friction or gap]

## Market Signals to Discuss
- [market signal or intelligence point worth raising]
- [signal]

## Questions to Ask the Client
- [challenging question to pressure-test an assumption]
- [question]
- [question]

## Advisor Challenges
- [belief or positioning the advisor should challenge]
- [challenge]

## Recommended Next Actions
- [specific advisor action after this session]
- [action]

## Advisor Notes (Not for Client)
- [sensitive observation: blind spot, perception risk, negotiation context]
- [advisor-only note]"""


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(context: str) -> str:
    return (
        "You are an executive transition advisor preparing for a client session. "
        "This brief is for YOUR EYES ONLY — it is not shown to the client.\n\n"
        "Generate a candid, commercially direct pre-session briefing from the workspace "
        "data below. Your goal: walk into the session prepared to challenge assumptions, "
        "advance the best opportunities, and add genuine value — not merely review what "
        "the client already knows.\n\n"
        "TONE RULES — strictly observed:\n"
        "• Be candid and advisor-facing, but avoid unsupported certainty\n"
        "• Distinguish between known facts (evidenced in the data), advisor inference "
        "(reasonable read-across), and questions to validate (uncertain context)\n"
        "• Do NOT write absolute claims unless directly supported by the workspace data — "
        "use calibrated language: 'may question', 'could read as', 'risk that', "
        "'should be validated'\n"
        "• Where a claim depends on uncertain context, phrase it as a validation point: "
        "'Clarify whether…', 'Test whether…', 'Validate if…'\n"
        "• Sensitive observations about blind spots, perception risks, and what the market "
        "probably doesn't believe are appropriate — but state the basis for each\n"
        "• Do not soften for client consumption — this is advisor intelligence\n"
        "• Do not invent information not present in the workspace data\n"
        "• Every string must be on a single line with no literal newlines\n\n"
        f"WORKSPACE DATA:\n{context}\n\n"
        "Use the submit_advisor_brief tool to return the brief."
    )


# ── Tool use path (primary) ───────────────────────────────────────────────────

def _call_tool_use(anthropic_client, prompt: str) -> Optional[AdvisorBrief]:
    response = anthropic_client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "submit_advisor_brief"},
        messages=[{"role": "user", "content": prompt}],
    )

    tool_block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if tool_block is None:
        logger.warning(
            "advisor_brief: no tool_use block in response; stop_reason=%s",
            response.stop_reason,
        )
        return None

    data = tool_block.input  # Python dict — no JSON parsing needed

    def s(k: str) -> str:
        v = data.get(k)
        return str(v).strip() if v and not isinstance(v, (list, dict)) else ""

    def lst(k: str) -> List[str]:
        v = data.get(k)
        return [str(i).strip() for i in v if i] if isinstance(v, list) else []

    priority_opps = []
    for item in (data.get("priority_opportunities") or []):
        if isinstance(item, dict):
            priority_opps.append(PriorityOpportunity(
                opportunity=str(item.get("opportunity") or "").strip(),
                why_it_matters=str(item.get("why_it_matters") or "").strip(),
                recommended_advisor_action=str(item.get("recommended_advisor_action") or "").strip(),
                risk_or_watchout=str(item.get("risk_or_watchout") or "").strip(),
            ))

    return AdvisorBrief(
        brief_summary=s("brief_summary"),
        client_situation=s("client_situation"),
        session_focus=lst("session_focus"),
        key_positioning_insights=lst("key_positioning_insights"),
        priority_opportunities=priority_opps,
        market_signals_to_discuss=lst("market_signals_to_discuss"),
        questions_to_ask_client=lst("questions_to_ask_client"),
        advisor_challenges=lst("advisor_challenges"),
        recommended_next_actions=lst("recommended_next_actions"),
        advisor_only_notes=lst("advisor_only_notes"),
    )


# ── Markdown fallback path ────────────────────────────────────────────────────

def _call_markdown_fallback(anthropic_client, context: str) -> str:
    prompt = (
        "You are an executive transition advisor preparing for a client session. "
        "This brief is for your eyes only — not shown to the client.\n\n"
        "Generate a candid, commercially direct pre-session briefing. "
        "Be direct and advisor-facing, but distinguish between known facts, "
        "advisor inference, and items to validate. Use calibrated language — "
        "'may question', 'could read as', 'risk that', 'Clarify whether…' — "
        "rather than absolute claims without evidence.\n\n"
        f"WORKSPACE DATA:\n{context}\n\n"
        f"Complete this template exactly. Do not add extra sections.\n\n{_MARKDOWN_TEMPLATE}"
    )

    response = anthropic_client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── Public entry point ────────────────────────────────────────────────────────

def generate_advisor_brief(record: ClientRecord) -> AdvisorBriefResult:
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed — add it to requirements.txt") from exc

    has_analysis = any([
        record.cv_intelligence,
        record.cv_intelligence_raw,
        record.positioning,
        record.positioning_raw,
        record.market_radar,
        record.market_radar_raw,
        record.opportunities,
    ])
    has_cv_text = bool((record.profile.cv_text or "").strip())
    if not has_analysis and not has_cv_text:
        raise ValueError(
            "Not enough workspace data to generate a brief. "
            "Run CV Studio, Positioning, or Market Radar first, "
            "or paste a CV in the Profile tab."
        )

    anthropic_client = anthropic.Anthropic()
    context = _build_context(record)
    prompt = _build_prompt(context)

    # ── Primary: tool use ────────────────────────────────────────────────────
    try:
        brief = _call_tool_use(anthropic_client, prompt)
        if brief is not None:
            logger.info("advisor_brief: tool use succeeded")
            return AdvisorBriefResult(brief=brief, parse_failed=False)
        logger.warning("advisor_brief: tool use returned no block, falling back to markdown")
    except Exception as exc:
        logger.warning("advisor_brief: tool use failed (%s), falling back to markdown", exc)

    # ── Fallback: structured markdown ────────────────────────────────────────
    try:
        raw_text = _call_markdown_fallback(anthropic_client, context)
        logger.info("advisor_brief: markdown fallback succeeded (%d chars)", len(raw_text))
        return AdvisorBriefResult(raw_text=raw_text, parse_failed=True)
    except Exception as exc:
        logger.error("advisor_brief: markdown fallback also failed: %s", exc)
        raise RuntimeError(
            f"Advisor Brief generation failed on both paths. Last error: {exc}"
        ) from exc
