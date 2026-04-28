from __future__ import annotations

import re
from typing import List

from app.schemas import (
    AchievementCategory, ClassifiedAchievement, ExtractedRole,
    InputSource, ProcessedProfile, RawInput, SignalTrace, WeightedSignal,
)

# ---------------------------------------------------------------------------
# Source weight floors  (mirrors scoring_engine.py SOURCE_WEIGHT_FLOOR)
# ---------------------------------------------------------------------------

SOURCE_WEIGHT: dict[str, float] = {
    "cv":                   1.0,
    "achievement":          1.5,
    "zone_of_genius":       1.8,
    "conflict_marker":      1.3,
    "never_again":          1.6,
    "industry_curiosity":   1.0,
    "lifestyle_preferences":1.0,
    "tools":                0.8,
    "questionnaire":        1.0,
}

# ---------------------------------------------------------------------------
# Achievement classification
# ---------------------------------------------------------------------------

_LEADERSHIP_KW = {
    "led", "managed", "directed", "built team", "hired", "recruited",
    "coached", "mentored", "developed", "oversaw", "supervised",
}
_FINANCIAL_KW = {
    "revenue", "profit", "cost", "saving", "budget", "million", "billion",
    "roi", "margin", "p&l", "ebitda", "raised", "generated", "grew",
}
_OPERATIONAL_KW = {
    "delivered", "launched", "implemented", "deployed", "shipped",
    "process", "efficiency", "optimised", "reduced", "scaled", "built",
}


def classify_achievement(text: str) -> AchievementCategory:
    lower = text.lower()
    scores = {
        AchievementCategory.leadership:  _count_hits(lower, _LEADERSHIP_KW),
        AchievementCategory.financial:   _count_hits(lower, _FINANCIAL_KW),
        AchievementCategory.operational: _count_hits(lower, _OPERATIONAL_KW),
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else AchievementCategory.other


def _count_hits(text: str, keywords: set[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


def _extract_impact_summary(text: str) -> str:
    # Take the first sentence or 120 chars — whichever is shorter.
    sentence = re.split(r"[.;]", text)[0].strip()
    return sentence[:120]


# ---------------------------------------------------------------------------
# Stage 3 — process_raw_inputs
# ---------------------------------------------------------------------------

def process_raw_inputs(
    raw: RawInput,
    roles: List[ExtractedRole],
    raw_skill_strings: List[str],
    raw_responsibility_strings: List[str],
) -> ProcessedProfile:
    """
    Construct a ProcessedProfile from parsed CV + questionnaire.
    Signals at this stage carry base confidence only — not yet enriched.
    """
    achievements = _build_achievements(raw.top_achievements)
    skills       = _build_cv_skills(raw_skill_strings)
    tools        = _build_tool_signals(raw.tools)
    stress       = _build_keyword_signals(raw.conflict_marker, "conflict_marker", 0.70, 1.3)
    avoidance    = _build_keyword_signals(raw.never_again, "never_again", 0.80, 1.6)

    return ProcessedProfile(
        roles=roles,
        achievements_classified=achievements,
        skills_inferred=skills + tools,
        stress_behaviours=stress,
        avoidance_patterns=avoidance,
    )


def _build_achievements(texts: List[str]) -> List[ClassifiedAchievement]:
    results = []
    for text in texts:
        results.append(
            ClassifiedAchievement(
                raw_text=text,
                category=classify_achievement(text),
                impact_summary=_extract_impact_summary(text),
                confidence_score=1.0,
                weight=SOURCE_WEIGHT["achievement"],
                source="achievement",
                traces=[SignalTrace(source="achievement", excerpt=text[:120])],
            )
        )
    return results


def _build_cv_skills(raw_strings: List[str]) -> List[WeightedSignal]:
    seen: set[str] = set()
    signals = []
    for value in raw_strings:
        key = value.lower()
        if key in seen or len(value) < 3:
            continue
        seen.add(key)
        signals.append(
            WeightedSignal(
                value=value,
                confidence_score=0.60,
                weight=SOURCE_WEIGHT["cv"],
                source="cv",
                traces=[SignalTrace(source="cv", excerpt=value)],
            )
        )
    return signals


def _build_tool_signals(tools: List[str]) -> List[WeightedSignal]:
    return [
        WeightedSignal(
            value=tool,
            confidence_score=0.90,
            weight=SOURCE_WEIGHT["tools"],
            source="tools",
            traces=[SignalTrace(source="tools", excerpt=tool)],
        )
        for tool in tools
        if tool.strip()
    ]


def _build_keyword_signals(
    text: str,
    source: InputSource,
    confidence: float,
    weight: float,
) -> List[WeightedSignal]:
    """
    Split a free-text field on punctuation/conjunctions into keyword phrases.
    Each phrase becomes a WeightedSignal.
    """
    if not text.strip():
        return []
    phrases = re.split(r"[,;.\n]|\band\b|\bor\b", text, flags=re.I)
    signals = []
    seen: set[str] = set()
    for phrase in phrases:
        value = phrase.strip()
        key = value.lower()
        if not value or len(value) < 3 or key in seen:
            continue
        seen.add(key)
        signals.append(
            WeightedSignal(
                value=value,
                confidence_score=confidence,
                weight=weight,
                source=source,
                traces=[SignalTrace(source=source, excerpt=value)],
            )
        )
    return signals


# ---------------------------------------------------------------------------
# Stage 4 — generate_weighted_signals
# ---------------------------------------------------------------------------

MIN_HIGH_CONFIDENCE_SIGNALS = 5


def generate_weighted_signals(
    processed: ProcessedProfile,
    raw: RawInput,
) -> ProcessedProfile:
    """
    Enrich ProcessedProfile with ZoG-derived signals and questionnaire fields.
    Applies aggregation and normalisation per category.
    Raises WeakSignalError (caught by orchestrator) if signal quality is too low.
    """
    from app.pipeline import WeakSignalError  # local import to avoid circular

    zog_signals     = _build_zog_signals(raw.zone_of_genius)
    industry_sigs   = _build_list_signals(raw.industry_curiosity, "industry_curiosity", 0.80, 1.0)
    lifestyle_sigs  = _build_list_signals(raw.lifestyle_preferences, "lifestyle_preferences", 0.75, 1.0)
    transferable    = _build_transferable_skills(processed.achievements_classified)

    processed.personality_traits = zog_signals
    processed.motivators         = zog_signals[:]   # ZoG informs both
    processed.transferable_skills = transferable

    # Store industry + lifestyle as questionnaire signals on career_themes
    # (AspirationalDNA consumes them from RawInput directly; this is for signal accounting)
    processed.career_themes = industry_sigs + lifestyle_sigs

    # Aggregate + normalise each category
    processed.skills_inferred    = _aggregate_and_normalise(processed.skills_inferred)
    processed.personality_traits = _aggregate_and_normalise(processed.personality_traits)
    processed.motivators         = _aggregate_and_normalise(processed.motivators)
    processed.stress_behaviours  = _aggregate_and_normalise(processed.stress_behaviours)
    processed.avoidance_patterns = _aggregate_and_normalise(processed.avoidance_patterns)
    processed.transferable_skills = _aggregate_and_normalise(processed.transferable_skills)

    all_signals = (
        processed.skills_inferred
        + processed.personality_traits
        + processed.motivators
        + processed.stress_behaviours
        + processed.avoidance_patterns
        + processed.transferable_skills
    )
    high_conf = sum(1 for s in all_signals if s.confidence_score >= 0.75)
    if high_conf < MIN_HIGH_CONFIDENCE_SIGNALS:
        raise WeakSignalError(
            f"Only {high_conf} high-confidence signals found (minimum {MIN_HIGH_CONFIDENCE_SIGNALS}). "
            "Enriching the CV or questionnaire will improve report quality."
        )

    return processed


def _build_zog_signals(zone_of_genius: str) -> List[WeightedSignal]:
    if not zone_of_genius.strip():
        return []
    phrases = re.split(r"[,;.\n]", zone_of_genius)
    signals = []
    seen: set[str] = set()
    for phrase in phrases:
        value = phrase.strip()
        key = value.lower()
        if not value or len(value) < 3 or key in seen:
            continue
        seen.add(key)
        signals.append(
            WeightedSignal(
                value=value,
                confidence_score=0.85,
                weight=SOURCE_WEIGHT["zone_of_genius"],
                source="zone_of_genius",
                traces=[SignalTrace(source="zone_of_genius", excerpt=zone_of_genius[:120])],
            )
        )
    return signals


def _build_list_signals(
    items: List[str],
    source: InputSource,
    confidence: float,
    weight: float,
) -> List[WeightedSignal]:
    return [
        WeightedSignal(
            value=item,
            confidence_score=confidence,
            weight=weight,
            source=source,
            traces=[SignalTrace(source=source, excerpt=item)],
        )
        for item in items
        if item.strip()
    ]


def _build_transferable_skills(
    achievements: List[ClassifiedAchievement],
) -> List[WeightedSignal]:
    signals = []
    for ach in achievements:
        phrases = _extract_verb_phrases(ach.raw_text)
        for phrase in phrases:
            signals.append(
                WeightedSignal(
                    value=phrase,
                    confidence_score=0.75,
                    weight=SOURCE_WEIGHT["achievement"],
                    source="achievement",
                    traces=[SignalTrace(source="achievement", excerpt=ach.raw_text[:120])],
                )
            )
    return signals


def _extract_verb_phrases(text: str) -> List[str]:
    """
    Naive verb-phrase extraction: capitalised word runs after common action verbs.
    Returns up to 5 phrases per achievement.
    """
    pattern = re.compile(
        r"\b(led|built|managed|created|delivered|drove|designed|developed|"
        r"launched|scaled|grew|reduced|improved|transformed)\s+([a-zA-Z\s]{3,40})",
        re.I,
    )
    return [m.group(0).strip()[:60] for m in pattern.finditer(text)][:5]


# ---------------------------------------------------------------------------
# Aggregation + normalisation helpers
# ---------------------------------------------------------------------------

def _aggregate_and_normalise(signals: List[WeightedSignal]) -> List[WeightedSignal]:
    merged = _merge_duplicates(signals)
    return _min_max_normalise(merged)


def _merge_duplicates(signals: List[WeightedSignal]) -> List[WeightedSignal]:
    """
    Group signals with identical lowercased values. For each group:
      merged_confidence = Σ(confidence * weight) / Σ(weight)
      frequency_boost   = min(1 + 0.1 * (n - 1), 1.5)
      final_confidence  = min(merged_confidence * frequency_boost, 1.0)
      weight            = max(weight in group)
    """
    groups: dict[str, List[WeightedSignal]] = {}
    for s in signals:
        key = s.value.lower().strip()
        groups.setdefault(key, []).append(s)

    result = []
    for group in groups.values():
        if len(group) == 1:
            result.append(group[0])
            continue

        total_weight = sum(s.weight for s in group)
        merged_conf  = sum(s.confidence_score * s.weight for s in group) / total_weight
        boost        = min(1.0 + 0.1 * (len(group) - 1), 1.5)
        final_conf   = min(merged_conf * boost, 1.0)
        all_traces   = [t for s in group for t in s.traces]

        result.append(
            WeightedSignal(
                value=group[0].value,
                confidence_score=final_conf,
                weight=max(s.weight for s in group),
                source=group[0].source,
                traces=all_traces,
            )
        )
    return result


def _min_max_normalise(signals: List[WeightedSignal]) -> List[WeightedSignal]:
    if not signals:
        return signals
    scores = [s.confidence_score for s in signals]
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return signals
    for s in signals:
        s.confidence_score = (s.confidence_score - lo) / (hi - lo)
    return signals
