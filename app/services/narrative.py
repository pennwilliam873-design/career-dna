from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas import CareerDNAProfile
from app.services.pattern_detection import DetectedPattern, PatternType
from app.services.prioritisation import PrioritisedInsightSet


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class ConfidenceTier(str, Enum):
    high   = "high"
    medium = "medium"
    low    = "low"


class NarrativeBlock(BaseModel):
    section: str
    prose: str
    evidence_cited: List[str] = Field(default_factory=list)
    evidence_implicit: List[str] = Field(default_factory=list)
    confidence_tier: ConfidenceTier
    source_patterns: List[PatternType] = Field(default_factory=list)
    requires_ai_polish: bool = True


class NarrativeReport(BaseModel):
    executive_summary:      NarrativeBlock
    functional_narrative:   NarrativeBlock
    adaptive_narrative:     NarrativeBlock
    aspirational_narrative: NarrativeBlock
    tensions_narrative:     List[NarrativeBlock] = Field(default_factory=list)
    pivot_narratives:       List[NarrativeBlock] = Field(default_factory=list)
    action_plan:            NarrativeBlock


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def assemble_report(
    profile: CareerDNAProfile,
    patterns: List[DetectedPattern],
    prioritised: Optional[PrioritisedInsightSet] = None,
) -> NarrativeReport:
    raise NotImplementedError(
        "assemble_report: implement per narrative_engine.py — "
        "build each NarrativeBlock using parameterised templates, "
        "evidence visibility classification, and confidence-tier wording."
    )
