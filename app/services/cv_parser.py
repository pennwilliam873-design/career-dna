from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.schemas import ExtractedRole
from app.services.role_classifier import classify_title
from app.services.skill_taxonomy import enrich_role_skills

# ---------------------------------------------------------------------------
# Keyword lookup tables
# ---------------------------------------------------------------------------

SECTOR_KEYWORDS: dict[str, list[str]] = {
    # Finance checked first — "banking" should beat "tech" for a bank's digital transformation role
    "finance":      ["banking", "financial services", "investment bank", "private equity",
                     "hedge fund", "asset management", "insurance", "capital markets"],
    # Media before consulting — "advisory" alone must not trigger consulting for a media executive
    "media":        ["television", "streaming", "content distribution", "fast channel",
                     "media and entertainment", "media company", "broadcasting", "entertainment",
                     "content production", "digital media", "media group", "media business",
                     "bbc", "fremantle", "foxtel", "media", "publishing", "broadcast", "content"],
    # Consulting requires explicit phrase or firm name — not bare "advisory" or "consulting"
    "consulting":   ["management consulting", "consulting firm", "advisory firm",
                     "management consultant", "mckinsey", "bcg", "bain", "deloitte",
                     "accenture", "kpmg", "pwc", "ey "],
    "technology":   ["tech", "software", "saas", "cloud", "artificial intelligence",
                     "machine learning", "data science", "engineering", "cybersecurity"],
    "healthcare":   ["health", "pharma", "medtech", "nhs", "clinical", "biotech"],
    "retail":       ["retail", "ecommerce", "consumer goods", "fmcg"],
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
_MONTH_RE = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
    r"|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\.?"
)
# Handles: YYYY–YYYY, YYYY–present, Month YYYY–Month YYYY, Month YYYY–present
_YEAR_RANGE = re.compile(
    r"(?:" + _MONTH_RE + r"\s+)?"        # optional month prefix on start date
    r"((?:19|20)\d{2})"                   # group 1: start year
    r"\s*[-–—]\s*"                        # separator (hyphen or en/em dash)
    r"(?:"
    r"(?:" + _MONTH_RE + r"\s+)?"        # optional month prefix on end date
    r"((?:19|20)\d{2})"                  # group 2: end year (numeric)
    r"|"
    r"(present|current|now)"             # group 3: open-ended tenure
    r")",
    re.I
)
# Strips the date portion (and everything after it) from a role header line
_HEADER_DATE_STRIP = re.compile(
    r"\s*(?:" + _MONTH_RE + r"\s+)?((?:19|20)\d{2})\s*(?:[-–—].*)?$",
    re.I
)
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
    Cuts at the start of the LINE containing each date range so that
    'Title | Organisation | 2021 – Present' stays in the same block as the date.

    Date ranges that appear inside parentheses mid-sentence are skipped —
    e.g. "(executive chair role, 2021–2023)" or "(2017–2019)" in a bullet.
    Heuristic: if the 30-char window before the match contains an unclosed "(",
    the match is inside a parenthetical and is not a role-header date.
    """
    positions: list[int] = []
    for m in _YEAR_RANGE.finditer(text):
        # Walk back to the start of this line
        line_start = text.rfind('\n', 0, m.start())
        pos = line_start + 1 if line_start >= 0 else 0

        # Skip parenthetical inline dates (not role-header dates)
        window = text[max(0, m.start() - 30): m.start()]
        last_open = window.rfind('(')
        if last_open >= 0 and ')' not in window[last_open + 1:]:
            continue

        positions.append(pos)

    # Deduplicate and sort (multiple dates on same line produce the same line_start)
    positions = sorted(set(positions))

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

# Matches "Title | Organisation | 2021 – Present" (pipe-delimited role header)
_PIPE_ROLE = re.compile(
    r"^([^|\n]{3,80}?)\s*\|\s*([^|\n]{2,80}?)\s*\|\s*(?:(?:19|20)\d{2})",
    re.MULTILINE,
)

_ACHIEVEMENT_PAT = re.compile(
    r"(?:£|€|\$|USD|GBP)?\s*\d+[\.,]?\d*\s*(?:m|bn|million|billion|k|%|x\b)",
    re.I
)
_LEADERSHIP_KW  = {"led", "managed", "directed", "built team", "hired", "grew team", "oversaw", "supervised"}
_COMMERCIAL_KW  = {"revenue", "p&l", "ebitda", "profit", "margin", "commercial", "sales", "budget"}
_STRATEGIC_KW   = {"strategy", "strategic", "transformation", "redesigned", "restructured", "advisory"}
_TECHNICAL_KW   = {"built", "engineered", "implemented", "deployed", "automated", "designed system"}
_BUILDER_KW     = {"founded", "launched", "created", "established", "built from", "scaled from"}

# Bullets that start with these words are self-commentary, not role achievements
_SIGNAL_EXCLUSION: frozenset[str] = frozenset({
    "left", "struggled", "sought", "failed", "missed", "despite",
    "did not", "unable", "unfortunately",
})

_MAX_SIGNAL_LEN = 90  # truncate verbose bullet text in signal display


def _is_excluded_bullet(bullet: str) -> bool:
    first = bullet.split()[0].lower() if bullet.split() else ""
    return first in _SIGNAL_EXCLUSION or bullet.lower().startswith("did not")


def _trim(text: str) -> str:
    return text if len(text) <= _MAX_SIGNAL_LEN else text[:_MAX_SIGNAL_LEN].rstrip() + "…"


def _extract_signals(bullets: list[str], keywords: set[str]) -> list[str]:
    return [
        _trim(b) for b in bullets
        if not _is_excluded_bullet(b) and any(kw in b.lower() for kw in keywords)
    ][:4]


def _extract_evidence_snippets(bullets: list[str]) -> list[str]:
    return [
        _trim(b) for b in bullets
        if not _is_excluded_bullet(b) and _ACHIEVEMENT_PAT.search(b)
    ][:5]


def _human_duration(months: Optional[int]) -> Optional[str]:
    if not months:
        return None
    if months < 12:
        return f"{months} months"
    years = months // 12
    rem = months % 12
    return f"{years} yr{'s' if years != 1 else ''}" + (f" {rem}m" if rem else "")


def _parse_role_block(block: str) -> Optional[ExtractedRole]:
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if not lines:
        return None

    start_year, end_year = _extract_years(block)
    duration = _compute_duration(start_year, end_year)
    title, organisation = _extract_title_org(lines)
    bullets = [m.group(1).strip() for m in _BULLET_LINE.finditer(block)]
    classifier = classify_title(title)

    role = ExtractedRole(
        title=title,
        organisation=organisation,
        start_year=start_year,
        end_year=end_year,
        sector=_infer_sector(block),
        seniority=_infer_seniority(title),
        duration_months=duration,
        # Enriched fields
        raw_title=title,
        inferred_duration=_human_duration(duration),
        inferred_seniority=classifier["inferred_seniority"],
        inferred_function=classifier["inferred_function"],
        inferred_industry=_infer_sector(block),
        role_type=classifier["role_type"],
        core_responsibilities=bullets[:4],
        achievement_signals=_extract_evidence_snippets(bullets),
        leadership_signals=_extract_signals(bullets, _LEADERSHIP_KW),
        commercial_signals=_extract_signals(bullets, _COMMERCIAL_KW),
        strategic_signals=_extract_signals(bullets, _STRATEGIC_KW),
        technical_signals=_extract_signals(bullets, _TECHNICAL_KW),
        entrepreneurial_or_building_signals=_extract_signals(bullets, _BUILDER_KW),
        evidence_snippets=_extract_evidence_snippets(bullets),
    )
    return enrich_role_skills(role)


def _extract_years(text: str) -> Tuple[Optional[int], Optional[int]]:
    m = _YEAR_RANGE.search(text)
    if m:
        start = int(m.group(1))
        if m.group(3):       # "present" / "current" / "now"
            end = 2025
        elif m.group(2):     # numeric end year
            end = int(m.group(2))
        else:
            end = 2025
        return start, end

    years = [int(y) for y in _SINGLE_YEAR.findall(text)]
    if years:
        return min(years), max(years)
    return None, None


def _compute_duration(start: Optional[int], end: Optional[int]) -> Optional[int]:
    if start and end and end >= start:
        return (end - start) * 12
    return None


# Geography qualifiers that appear after a comma in a title line and should NOT
# be treated as the organisation name. When matched, the full stripped line is kept
# as the title and the org is sourced from the next-line lookup instead.
_GEOGRAPHY_QUALIFIERS: frozenset[str] = frozenset({
    "apac", "asia pacific", "asia-pacific",
    "australia", "australia & new zealand", "anz", "new zealand",
    "nsw", "vic", "qld", "wa", "sa", "act", "nt",
    "singapore", "hong kong", "greater china", "china", "japan",
    "india", "malaysia", "thailand", "indonesia", "korea", "philippines",
    "vietnam", "north asia", "southeast asia",
    "europe", "uk", "emea", "usa", "north america",
    "latin america", "south america", "middle east", "africa",
    "global", "international", "worldwide",
})

_NEXT_LINE_ORG_RE = re.compile(r"^\s*[-•*▪◦]")


def _extract_org_from_next_lines(lines: list[str], title_idx: int) -> str:
    """
    Look for the organisation on lines following the title/date line.
    Recognises the "Org Name | City, Country" format used by many senior CVs.
    Returns "Unknown Organisation" if nothing suitable is found.
    """
    for line in lines[title_idx + 1:]:
        stripped = line.strip()
        if not stripped:
            continue
        # Stop at bullets — org line always comes before bullets
        if _NEXT_LINE_ORG_RE.match(stripped):
            break
        # Stop if this looks like another role header (contains a year range)
        if _YEAR_RANGE.search(stripped):
            break
        # "Org Name | City" — take what is before the first pipe
        if "|" in stripped:
            candidate = stripped.split("|")[0].strip()
            if 2 <= len(candidate) <= 80:
                return candidate[:120]
        # Not the expected "Org | City" pattern on this line — stop looking
        break
    return "Unknown Organisation"


def _extract_title_org(lines: list[str]) -> Tuple[str, str]:
    # 1. Pipe format: "Title | Organisation | Date"
    for line in lines:
        m = _PIPE_ROLE.match(line.strip())
        if m:
            title = m.group(1).strip()
            org   = m.group(2).strip()
            if title and org:
                return title[:120], org[:120]

    # 2. Header line with embedded date: strip date suffix, then resolve title and org.
    #    Handles:
    #      "Group Chief Executive Officer    2019 – present"  (org on next line)
    #      "Regional President, Asia Pacific 2014 – 2019"     (geography after comma)
    #      "Managing Director, Blue Ant Media Sept 2023 – present"  (org in same line)
    for i, line in enumerate(lines[:2]):
        if re.search(r"(?:19|20)\d{2}", line):
            stripped = _HEADER_DATE_STRIP.sub("", line).strip()
            if len(stripped) > 5 and not stripped.startswith("-"):
                stripped = re.sub(r"\s*\([^)]{2,40}\)\s*$", "", stripped).strip()
                stripped = stripped.rstrip(",;–—-").strip()

                # Priority: try to find org on the next line ("Org | City" format)
                org_next = _extract_org_from_next_lines(lines, i)
                if org_next != "Unknown Organisation":
                    # Next line gave us a clear org — use full stripped text as title
                    return stripped[:120], org_next

                # Fallback: comma-split the title line to find an embedded org
                parts = [p.strip() for p in stripped.split(",") if p.strip()]
                if len(parts) >= 2:
                    last_lower = parts[-1].lower()
                    if last_lower in _GEOGRAPHY_QUALIFIERS:
                        # Trailing geography is part of the title scope, not the org
                        return stripped[:120], "Unknown Organisation"
                    return ", ".join(parts[:-1])[:120], parts[-1][:120]
                elif parts and len(parts[0]) > 3:
                    return parts[0][:120], "Unknown Organisation"

    # 3. Fallback: first non-date line is title, second is organisation
    non_date = [l for l in lines if not _YEAR_RANGE.search(l) and not _SINGLE_YEAR.fullmatch(l.strip())]
    title = non_date[0] if non_date else "Unknown Role"
    org   = non_date[1] if len(non_date) > 1 else "Unknown Organisation"
    return title[:120], org[:120]


# Cache compiled boundary patterns for short keywords to avoid repeated re.compile calls
_SECTOR_KW_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _sector_kw_match(kw: str, lower: str) -> bool:
    """
    Match a sector keyword against lowercased text.
    Keywords shorter than 6 characters use word-boundary matching to prevent
    false positives — e.g. "tech" must not match inside "fintech", and "ey"
    must not match inside "key" or "they".
    """
    if len(kw) < 6:
        pat = _SECTOR_KW_PATTERN_CACHE.get(kw)
        if pat is None:
            _SECTOR_KW_PATTERN_CACHE[kw] = pat = re.compile(
                r'\b' + re.escape(kw.strip()) + r'\b'
            )
        return bool(pat.search(lower))
    return kw in lower


def _infer_sector(text: str) -> Optional[str]:
    """
    Infer sector from the role block header only — the lines before the first
    bullet marker. This captures the employer/org name and role title, which are
    the definitive signals for where the candidate actually worked.

    Bullet content (achievements, client verticals, board entries, credentials)
    is excluded entirely to prevent false positives from incidental mentions.
    """
    header_parts: list[str] = []
    for line in text.splitlines():
        if _NEXT_LINE_ORG_RE.match(line):
            break
        header_parts.append(line.lower())

    header_text = " ".join(header_parts)
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(_sector_kw_match(kw, header_text) for kw in keywords):
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


# Action verbs that start CV bullet points — not skills
_BULLET_VERB_NOISE: frozenset[str] = frozenset({
    "managed", "led", "built", "launched", "created", "developed", "designed",
    "implemented", "delivered", "supported", "introduced", "coordinated",
    "contributed", "presented", "prepared", "established", "left", "sought",
    "seconded", "reduced", "increased", "improved", "conducted", "worked",
    "provided", "owned", "used", "drove", "leading", "managing", "building",
    "growing", "oversaw", "supervised", "hired", "directed", "reported",
    "spearheaded", "championed", "partnered", "collaborated", "negotiated",
    "deployed", "automated", "scaled", "grew", "restructured", "transformed",
    "achieved", "executed", "defined", "identified", "resolved", "struggled",
    "ensured", "maintained", "responsible", "accountable", "left",
})

# Single-word capitalised tokens that are job titles or stop-words, not skills
_SINGLE_WORD_NOISE: frozenset[str] = frozenset({
    "manager", "director", "analyst", "consultant", "officer", "associate",
    "specialist", "coordinator", "executive", "president", "advisor",
    "engineer", "developer", "architect", "lead", "head", "member",
    "team", "group", "including", "following", "prior", "additional",
    "programme", "program", "project", "process", "system",
})


def _extract_noun_phrases(bullets: list[str]) -> list[str]:
    """
    Lightweight noun-phrase extraction: capitalised-word runs with verb and
    title noise filtered out. Requires ≥2 words unless it's a clearly
    meaningful single-token proper noun.
    """
    phrases: set[str] = set()
    skill_pattern = re.compile(
        r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})\b"
    )
    for bullet in bullets:
        for m in skill_pattern.finditer(bullet):
            phrase = m.group(1).strip()
            words = phrase.split()
            # Drop phrases that begin with a bullet action verb
            if words[0].lower() in _BULLET_VERB_NOISE:
                continue
            # Single-word tokens: only keep if not in the noise set and ≥5 chars
            if len(words) == 1:
                if phrase.lower() in _SINGLE_WORD_NOISE or len(phrase) < 5:
                    continue
            if 2 < len(phrase) < 60:
                phrases.add(phrase)
    return list(phrases)


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback_role(cv_text: str) -> ExtractedRole:
    years = [int(y) for y in _SINGLE_YEAR.findall(cv_text)]
    role = ExtractedRole(
        title="Career History",
        organisation="See CV",
        start_year=min(years) if years else None,
        end_year=max(years) if years else None,
        sector=_infer_sector(cv_text),
        seniority=None,
        duration_months=None,
    )
    return enrich_role_skills(role)
