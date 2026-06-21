"""
Hidden Market Map — extract from conversation notes.

Lets an advisor paste rough notes from a client conversation and get back
reviewable Hidden Market Map suggestions (people, relationship paths, asks,
missing information, follow-up questions). Nothing is saved automatically —
this module only produces suggestions; app/main.py's existing target-contact
endpoints handle persistence when the advisor explicitly adds one.

Architecture mirrors app/services/contact_search.py: tool-use only (no
markdown fallback — a list of suggestion cards has no sensible prose
fallback), never a hard crash on a model that returns nothing useful,
empty list on failure rather than guessing.

Context blocks are reused directly from app/services/advisor_brief.py
(profile, positioning, market radar digest, opportunities, existing
contacts) rather than re-implemented, since the advisor brief already
has well-tested formatting for the same client data.

Model defaults to claude-sonnet-4-6 — this task requires careful
instruction-following on the trust/safety rules (no hallucinated public
facts, evidence vs inference) as much as it requires extraction quality.
Override with NOTES_EXTRACTION_MODEL env var.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import List

from app.models.client import ClientRecord
from app.services.advisor_brief import (
    _profile_block,
    _positioning_block,
    _radar_digest,
    _opportunities_block,
)

logger = logging.getLogger(__name__)

_MODEL: str = os.getenv("NOTES_EXTRACTION_MODEL", "claude-sonnet-4-6")


# ── Result types ────────────────────────────────────────────────────────────

@dataclass
class SuggestedNetworkContact:
    name: str = ""
    current_title: str = ""
    company: str = ""
    network_source: str = "Unknown"
    relationship_owner: str = "Unknown"
    relationship_to_client: str = ""
    relationship_to_advisor: str = ""
    relationship_strength: str = "Unknown"
    role_in_search: str = "Unknown"
    target_company: str = ""
    target_sector: str = ""
    bridge_to: str = ""
    warm_path_status: str = "Unknown"
    ask_type: str = "Unknown"
    suggested_approach: str = ""
    opportunity_path_hypothesis: str = ""
    next_action: str = ""
    next_action_owner: str = "Advisor"
    status: str = "To assess"
    advisor_only: bool = True
    client_shareable: bool = False
    approved_for_outreach: bool = False
    include_in_advisor_brief: bool = False
    include_in_weekly_plan: bool = False
    missing_information: List[str] = field(default_factory=list)
    follow_up_questions: List[str] = field(default_factory=list)
    confidence: str = "Low"
    evidence_from_notes: str = ""


@dataclass
class NotesExtractionResult:
    suggested_contacts: List[SuggestedNetworkContact] = field(default_factory=list)
    network_insights: List[str] = field(default_factory=list)
    recommended_follow_up_questions: List[str] = field(default_factory=list)


# ── Context: existing contacts (full list, for duplicate avoidance) ────────

def _existing_contacts_block(record: ClientRecord) -> str:
    contacts = [c for c in (record.target_contacts or []) if c.name]
    if not contacts:
        return "[EXISTING HIDDEN MARKET MAP CONTACTS]\nNone mapped yet."
    lines = ["[EXISTING HIDDEN MARKET MAP CONTACTS — do not suggest a duplicate of these]"]
    for c in contacts:
        line = f"  - {c.name}"
        if c.company:
            line += f" ({c.company})"
        if c.network_source and c.network_source != "Unknown":
            line += f" [{c.network_source}]"
        lines.append(line)
    return "\n".join(lines)


def _build_context(record: ClientRecord) -> str:
    return "\n\n".join([
        _profile_block(record),
        _positioning_block(record),
        _radar_digest(record),
        _opportunities_block(record),
        _existing_contacts_block(record),
    ])


# ── Tool schema ───────────────────────────────────────────────────────────────

_CONTACT_PROPERTIES = {
    "name": {
        "type": "string",
        "description": "Person's name exactly as mentioned in the notes. Never invent a name.",
    },
    "current_title": {
        "type": "string",
        "description": "Current title/role if mentioned. Leave empty if not stated — do not guess.",
    },
    "company": {
        "type": "string",
        "description": "Company if mentioned. Leave empty if not stated — do not guess.",
    },
    "network_source": {
        "type": "string",
        "enum": ["Client Network", "Advisor Network", "ViaNova Suggestion", "Unknown"],
        "description": "Whose relationship this is, based on the notes (usually Client Network for people the client mentions knowing).",
    },
    "relationship_owner": {
        "type": "string",
        "enum": ["Client", "Advisor", "Both", "Third-party", "Unknown"],
    },
    "relationship_to_client": {
        "type": "string",
        "description": "Short description of the relationship to the client, e.g. 'Former colleague at Lendlease'. Empty if not relationship_owner Client/Both.",
    },
    "relationship_to_advisor": {
        "type": "string",
        "description": "Short description of the relationship to the advisor. Empty if not relationship_owner Advisor/Both.",
    },
    "relationship_strength": {
        "type": "string",
        "enum": ["Strong", "Medium", "Weak", "Dormant", "Unknown"],
        "description": "E.g. Dormant for a contact not spoken to in years but described as a good relationship.",
    },
    "role_in_search": {
        "type": "string",
        "enum": [
            "Decision-maker", "Introducer", "Bridge contact", "Market intelligence",
            "Search consultant", "Board/investor connector", "Potential sponsor",
            "Former colleague", "Peer", "Other", "Unknown",
        ],
    },
    "target_company": {"type": "string", "description": "Company this contact could unlock, if inferable. Empty if unclear."},
    "target_sector": {"type": "string"},
    "bridge_to": {
        "type": "string",
        "description": "Who, which company, or which sector this person may bridge to — e.g. 'Qantas transformation network'.",
    },
    "warm_path_status": {
        "type": "string",
        "enum": ["Warm path known", "Possible warm path", "Warm path needed", "Cold only", "Unknown"],
    },
    "ask_type": {
        "type": "string",
        "enum": [
            "Market intelligence", "Introduction", "Reconnect", "Search mandate",
            "Company insight", "Role discussion", "Direct opportunity", "Referral", "Other", "Unknown",
        ],
    },
    "suggested_approach": {
        "type": "string",
        "description": "An executive-level outreach angle that does not sound desperate. Under 25 words.",
    },
    "opportunity_path_hypothesis": {
        "type": "string",
        "description": "E.g. 'Client -> Sarah -> Qantas transformation network'.",
    },
    "next_action": {"type": "string", "description": "Concrete next step for the advisor or client. Under 20 words."},
    "next_action_owner": {"type": "string", "enum": ["Advisor", "Client", "Both"]},
    "status": {
        "type": "string",
        "enum": [
            "To assess", "Warm path needed", "Ready for outreach", "Contacted",
            "Meeting booked", "Active conversation", "Parked", "Not relevant",
        ],
    },
    "advisor_only": {"type": "boolean", "description": "Always true for a fresh suggestion."},
    "client_shareable": {"type": "boolean", "description": "Always false for a fresh suggestion."},
    "approved_for_outreach": {"type": "boolean", "description": "Always false for a fresh suggestion."},
    "include_in_advisor_brief": {"type": "boolean", "description": "Always false for a fresh suggestion."},
    "include_in_weekly_plan": {"type": "boolean", "description": "Always false for a fresh suggestion."},
    "missing_information": {
        "type": "array",
        "items": {"type": "string"},
        "description": "What needs confirming before this contact is reliable, e.g. 'Full name and current role need confirmation'.",
    },
    "follow_up_questions": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Questions the advisor should ask the client about this specific contact.",
    },
    "confidence": {
        "type": "string",
        "enum": ["Low", "Medium", "High"],
        "description": "Confidence in this suggestion based on how explicit the notes were. Most note-derived contacts should be Low or Medium.",
    },
    "evidence_from_notes": {
        "type": "string",
        "description": "The specific phrase(s) from the notes this suggestion is based on — evidence, not inference.",
    },
}

_TOOL = {
    "name": "submit_network_extraction",
    "description": (
        "Submit Hidden Market Map suggestions extracted from rough advisor/client "
        "conversation notes. Only suggest people actually mentioned in the notes. "
        "Never claim to have verified a current role or company — that information "
        "comes only from what the notes say, unless it already exists in the "
        "client's workspace data provided as context."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "suggested_contacts": {
                "type": "array",
                "description": "One entry per person mentioned in the notes who could plausibly be part of the hidden market map. Do not pad — return fewer if the notes only mention one or two people.",
                "items": {
                    "type": "object",
                    "properties": _CONTACT_PROPERTIES,
                    "required": list(_CONTACT_PROPERTIES.keys()),
                },
            },
            "network_insights": {
                "type": "array",
                "items": {"type": "string"},
                "description": "1-3 short observations about the overall network/path strategy suggested by these notes. Under 25 words each.",
            },
            "recommended_follow_up_questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "1-4 follow-up questions the advisor should ask the client in the next session, beyond the per-contact ones.",
            },
        },
        "required": ["suggested_contacts", "network_insights", "recommended_follow_up_questions"],
    },
}


# ── Prompt ────────────────────────────────────────────────────────────────────

def _build_prompt(context: str, notes: str) -> str:
    return (
        "You are an expert executive transition advisor reviewing rough notes from a "
        "client conversation, to extract and structure the client's hidden job network "
        "into the Hidden Market Map.\n\n"
        "From the notes, identify people, companies, and relationships. For each person:\n"
        "- Decide if they look like a Client Network, Advisor Network, or ViaNova Suggestion contact.\n"
        "- Identify dormant, weak, or warm ties based on how the relationship is described.\n"
        "- Identify bridge contacts (people who could connect to a company/sector/other people), "
        "market intelligence contacts, search consultants, board/investor connectors, and sponsors.\n"
        "- Suggest the right ask type and a confident, executive-level outreach angle that does "
        "not sound desperate.\n"
        "- Note what information is missing and what the advisor should ask the client to confirm.\n"
        "- Where relevant, connect the contact to the client's positioning, opportunities, or "
        "market radar context provided below.\n"
        "- Do not suggest a contact that duplicates someone already in the existing Hidden Market "
        "Map list below — if the notes update an existing contact, mention it in network_insights "
        "instead of creating a new suggestion.\n\n"
        "TRUST AND SAFETY RULES — strictly observed:\n"
        "- Do NOT claim to verify any person's current role or company. You have no way to confirm "
        "this — only the notes (and the client's existing workspace data below) are evidence.\n"
        "- Do NOT invent public facts, LinkedIn URLs, or biographical details not present in the notes.\n"
        "- Use 'Unknown' for any field the notes do not support — never guess to fill a field.\n"
        "- Keep evidence_from_notes strictly to what the notes actually say. Put your reasoning "
        "about why a contact might be useful in suggested_approach / opportunity_path_hypothesis / "
        "bridge_to instead — never blend inference into evidence_from_notes.\n"
        "- Treat everything in the notes as unverified, second-hand information from the client, "
        "not confirmed fact, unless it matches something already in the client's workspace data.\n\n"
        f"CLIENT WORKSPACE CONTEXT:\n{context}\n\n"
        f"CONVERSATION NOTES TO EXTRACT FROM:\n{notes}\n\n"
        "Use the submit_network_extraction tool to return your suggestions."
    )


# ── Public entry point ────────────────────────────────────────────────────────

def extract_network_from_notes(record: ClientRecord, notes: str) -> NotesExtractionResult:
    notes = (notes or "").strip()
    if not notes:
        raise ValueError("Notes are required.")

    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("anthropic SDK not installed — add it to requirements.txt") from exc

    anthropic_client = anthropic.Anthropic()
    context = _build_context(record)
    prompt = _build_prompt(context, notes)

    try:
        response = anthropic_client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "submit_network_extraction"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.error("notes_extraction: Claude call failed: %s", exc)
        raise RuntimeError(f"Extraction failed: {exc}") from exc

    tool_block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if tool_block is None:
        logger.warning("notes_extraction: no tool_use block; stop_reason=%s", response.stop_reason)
        return NotesExtractionResult()

    data = tool_block.input

    def lst(k: str) -> List[str]:
        v = data.get(k)
        return [str(i).strip() for i in v if i] if isinstance(v, list) else []

    suggested_contacts = []
    for item in (data.get("suggested_contacts") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        suggested_contacts.append(SuggestedNetworkContact(
            name=name,
            current_title=str(item.get("current_title") or "").strip(),
            company=str(item.get("company") or "").strip(),
            network_source=str(item.get("network_source") or "Unknown").strip(),
            relationship_owner=str(item.get("relationship_owner") or "Unknown").strip(),
            relationship_to_client=str(item.get("relationship_to_client") or "").strip(),
            relationship_to_advisor=str(item.get("relationship_to_advisor") or "").strip(),
            relationship_strength=str(item.get("relationship_strength") or "Unknown").strip(),
            role_in_search=str(item.get("role_in_search") or "Unknown").strip(),
            target_company=str(item.get("target_company") or "").strip(),
            target_sector=str(item.get("target_sector") or "").strip(),
            bridge_to=str(item.get("bridge_to") or "").strip(),
            warm_path_status=str(item.get("warm_path_status") or "Unknown").strip(),
            ask_type=str(item.get("ask_type") or "Unknown").strip(),
            suggested_approach=str(item.get("suggested_approach") or "").strip(),
            opportunity_path_hypothesis=str(item.get("opportunity_path_hypothesis") or "").strip(),
            next_action=str(item.get("next_action") or "").strip(),
            next_action_owner=str(item.get("next_action_owner") or "Advisor").strip(),
            status=str(item.get("status") or "To assess").strip(),
            advisor_only=bool(item.get("advisor_only", True)),
            client_shareable=bool(item.get("client_shareable", False)),
            approved_for_outreach=bool(item.get("approved_for_outreach", False)),
            include_in_advisor_brief=bool(item.get("include_in_advisor_brief", False)),
            include_in_weekly_plan=bool(item.get("include_in_weekly_plan", False)),
            missing_information=[str(i).strip() for i in (item.get("missing_information") or []) if i],
            follow_up_questions=[str(i).strip() for i in (item.get("follow_up_questions") or []) if i],
            confidence=str(item.get("confidence") or "Low").strip(),
            evidence_from_notes=str(item.get("evidence_from_notes") or "").strip(),
        ))

    result = NotesExtractionResult(
        suggested_contacts=suggested_contacts,
        network_insights=lst("network_insights"),
        recommended_follow_up_questions=lst("recommended_follow_up_questions"),
    )
    logger.info(
        "notes_extraction: returned %d suggested contact(s)", len(result.suggested_contacts)
    )
    return result
