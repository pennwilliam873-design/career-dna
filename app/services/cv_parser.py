from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.schemas import ExtractedRole

# ---------------------------------------------------------------------------
# Keyword lookup tables
# ---------------------------------------------------------------------------

SECTOR_KEYWORDS: dict[str, list[str]] = {
    "technology":   ["tech", "software", "saas", "cloud", "ai", "data", "engineering"],
    "finance":      ["banking", "investment", "private equity", "hedge fund", "asset management", "insurance"],
    "consulting":   ["consulting", "advisory", "strategy", "mckinsey", "bcg", "bain", "deloitte"],
    "healthcare":   ["health", "pharma", "medtech", "nhs", "clinical", "biotech"],
    "retail":       ["retail", "ecommerce", "consumer", "fmcg", "brand"],
    "media":        ["media", "publishing", "broadcast", "entertainment", "content"],
    "education":    ["education", "university", "school", "edtech", "learning"],
    "government":   ["government", "public sector", "civil service", "ngo", "charity"],
    "real_estate":  ["real estate", "property", "construction", "infrastructure"],
}

SENIORITY_KEYWORDS: dict[str, list[str]] = {
    "c-suite":   ["ceo", "cto", "cfo", "coo", "chief"],
    "partner":   ["partner", "managing director", "md"],
    "vp":        ["vice president", "vp ", "evp", "svp"],
    "director":  ["director"],
    "manager":   ["manager", "head of", "lead"],
    "senior":    ["senior", "principal", "staff"],
    "mid":       ["associate", "consultant", "analyst ii", "engineer ii"],
    "junior":    ["junior", "graduate", "analyst", "engineer", "associate"],
}

# Regex patterns for date extraction
_YEAR_RANGE   = re.compile(r"((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2}|present|current|now)", re.I)
_SINGLE_YEAR  = re.compile(r"\b((?:19|20)\d{2})\b")
_BULLET_LINE  = re.compile(r"^\s*[-•*▪◦]\s+(.+)$", re.MULTILINE)
_BLANK_LINE   = re.compile(r"\n\s*\n")

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def parse_cv(cv_text: str) -> Tuple[List[ExtractedRole], List[str], List[str]]:
    """
    Extract structured data from raw CV text.

    Returns:
        roles                   — List[ExtractedRole]
        raw_skill_strings       — noun phrases from bullet lines
        raw_responsibility_strings — bullet lines verbatim
    """
    blocks = _segment_into_blocks(cv_text)
    roles: list[ExtractedRole] = []

    for block in blocks:
        role = _parse_role_block(block)
        if role:
            roles.append(role)

    if not roles:
        roles = [_fallback_role(cv_text)]

    bullets = _extract_bullets(cv_text)
    skill_strings = _extract_noun_phrases(bullets)

    return roles, skill_strings, bullets


# ---------------------------------------------------------------------------
# Block segmentation
# ---------------------------------------------------------------------------

def _segment_into_blocks(text: str) -> list[str]:
    """
    Split CV text into role blocks using date anchors.
    Each block is assumed to correspond to one role.
    """
    positions: list[int] = []
    for m in _YEAR_RANGE.finditer(text):
        positions.append(m.start())

    if len(positions) < 2:
        return [text]

    blocks: list[str] = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        block = text[pos:end].strip()
        if len(block) > 20:
            blocks.append(block)

    return blocks or [text]


# ---------------------------------------------------------------------------
# Role parsing
# ---------------------------------------------------------------------------

def _parse_role_block(block: str) -> Optional[ExtractedRole]:
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if not lines:
        return None

    start_year, end_year = _extract_years(block)
    duration = _compute_duration(start_year, end_year)

    title, organisation = _extract_title_org(lines)

    return ExtractedRole(
        title=title,
        organisation=organisation,
        start_year=start_year,
        end_year=end_year,
        sector=_infer_sector(block),
        seniority=_infer_seniority(title),
        duration_months=duration,
    )


def _extract_years(text: str) -> Tuple[Optional[int], Optional[int]]:
    m = _YEAR_RANGE.search(text)
    if m:
        start = int(m.group(1))
        end_raw = m.group(2).lower()
        end = 2025 if end_raw in ("present", "current", "now") else int(end_raw)
        return start, end

    years = [int(y) for y in _SINGLE_YEAR.findall(text)]
    if years:
        return min(years), max(years)
    return None, None


def _compute_duration(start: Optional[int], end: Optional[int]) -> Optional[int]:
    if start and end and end >= start:
        return (end - start) * 12
    return None


def _extract_title_org(lines: list[str]) -> Tuple[str, str]:
    # First non-date line is treated as title, second as organisation.
    non_date = [l for l in lines if not _YEAR_RANGE.search(l) and not _SINGLE_YEAR.fullmatch(l.strip())]
    title = non_date[0] if non_date else "Unknown Role"
    org   = non_date[1] if len(non_date) > 1 else "Unknown Organisation"
    return title[:120], org[:120]


def _infer_sector(text: str) -> Optional[str]:
    lower = text.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return sector
    return None


def _infer_seniority(title: str) -> Optional[str]:
    lower = title.lower()
    for level, keywords in SENIORITY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return level
    return None


# ---------------------------------------------------------------------------
# Bullet extraction + naive noun-phrase extraction
# ---------------------------------------------------------------------------

def _extract_bullets(text: str) -> list[str]:
    return [m.group(1).strip() for m in _BULLET_LINE.finditer(text)]


def _extract_noun_phrases(bullets: list[str]) -> list[str]:
    """
    Lightweight noun-phrase extraction using capitalised-word runs and
    known skill marker patterns. Replaces spaCy for initial implementation.
    """
    phrases: set[str] = set()
    skill_pattern = re.compile(
        r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\b"
    )
    for bullet in bullets:
        for m in skill_pattern.finditer(bullet):
            phrase = m.group(1).strip()
            if 2 < len(phrase) < 60:
                phrases.add(phrase)
    return list(phrases)


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback_role(cv_text: str) -> ExtractedRole:
    years = [int(y) for y in _SINGLE_YEAR.findall(cv_text)]
    return ExtractedRole(
        title="Career History",
        organisation="See CV",
        start_year=min(years) if years else None,
        end_year=max(years) if years else None,
        sector=_infer_sector(cv_text),
        seniority=None,
        duration_months=None,
    )
