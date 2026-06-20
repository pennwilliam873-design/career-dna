"""Round-trip tests: ClientRecord -> PostgreSQL -> ClientRecord.

Each test writes a ClientRecord via the real storage_postgres adapter
against a real PostgreSQL database (no mocking) and asserts the field(s)
under test survive unchanged. This is the main defence against the
mapping layer silently losing or corrupting data.
"""
from __future__ import annotations

from app.data import storage_postgres as pg
from app.models.client import (
    ActionItem,
    AdvisorBrief,
    ClientProfile,
    ClientRecord,
    CVIntelligence,
    HiddenMarketHypothesis,
    MarketRadarOutput,
    MarketRadarSignal,
    Opportunity,
    PositioningOutput,
    PositioningPathway,
    PriorityOpportunity,
    RelationshipStrategy,
    SessionNote,
    TargetCompany,
    TargetContact,
    Tier1Company,
    Tier2Company,
    Tier3Company,
)


def test_empty_minimal_client_round_trip(pg_database):
    record = ClientRecord(profile=ClientProfile(name="Empty Client"))
    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    assert fetched.profile.name == "Empty Client"
    assert fetched.positioning is None
    assert fetched.cv_intelligence is None
    assert fetched.market_radar is None
    assert fetched.advisor_brief is None
    assert fetched.opportunities == []
    assert fetched.target_contacts == []
    assert fetched.session_notes == []
    assert fetched.action_items == []


def test_fully_populated_client_round_trip(pg_database):
    profile = ClientProfile(
        name="Full Client",
        current_role="CFO",
        location="London",
        target_geography="EMEA",
        desired_next_move="CEO",
        timeframe="6 months",
        roles_wanted="CEO, COO",
        roles_not_wanted="CTO",
        constraints="Relocation limited",
        relationship_assets="Strong board network",
        advisor_notes="Internal notes",
        cv_text="Full CV text content",
    )
    record = ClientRecord(
        profile=profile,
        opportunities=[Opportunity(title="Opp", company="Acme")],
        target_contacts=[TargetContact(name="Contact")],
        session_notes=[SessionNote(date="2026-01-01", title="Kickoff", notes="Met client")],
        action_items=[ActionItem(action="Send brief")],
    )
    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    assert fetched.profile.model_dump() == profile.model_dump()
    assert len(fetched.opportunities) == 1
    assert len(fetched.target_contacts) == 1
    assert len(fetched.session_notes) == 1
    assert len(fetched.action_items) == 1
    assert fetched.session_notes[0].notes == "Met client"


def test_structured_ai_output_round_trip(pg_database):
    record = ClientRecord(profile=ClientProfile(name="Structured"))
    record.positioning = PositioningOutput(
        executive_positioning="Strong fit for regional CEO",
        core_strengths=["P&L ownership", "M&A"],
        recommended_pathways=[
            PositioningPathway(pathway="Regional CEO", fit_level="High", stretch_risk="Low")
        ],
    )
    record.cv_intelligence = CVIntelligence(
        executive_summary="20 years experience", core_capabilities=["Strategy"]
    )
    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    assert fetched.positioning.executive_positioning == "Strong fit for regional CEO"
    assert fetched.positioning.core_strengths == ["P&L ownership", "M&A"]
    assert len(fetched.positioning.recommended_pathways) == 1
    assert fetched.positioning.recommended_pathways[0].pathway == "Regional CEO"
    assert fetched.cv_intelligence.executive_summary == "20 years experience"


def test_raw_only_fallback_round_trip(pg_database):
    record = ClientRecord(profile=ClientProfile(name="Raw Fallback"))
    record.cv_intelligence = None
    record.cv_intelligence_raw = "Unparsed markdown from the LLM"
    record.cv_intelligence_generated_at = "2026-01-01T00:00:00+00:00"

    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    assert fetched.cv_intelligence is None
    assert fetched.cv_intelligence_raw == "Unparsed markdown from the LLM"
    assert fetched.cv_intelligence_generated_at is not None


def test_legacy_target_companies_round_trip(pg_database):
    record = ClientRecord(profile=ClientProfile(name="Legacy"))
    record.market_radar = MarketRadarOutput(
        target_companies=[
            TargetCompany(company="LegacyCo", category="Industrial", priority="High")
        ]
    )
    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    assert len(fetched.market_radar.target_companies) == 1
    assert fetched.market_radar.target_companies[0].company == "LegacyCo"
    assert fetched.market_radar.tier1_companies == []


def test_tiered_market_radar_round_trip(pg_database):
    record = ClientRecord(profile=ClientProfile(name="Tiered"))
    record.market_radar = MarketRadarOutput(
        tier1_companies=[Tier1Company(company="TierOne", confidence="High")],
        tier2_companies=[Tier2Company(company="TierTwo", confidence="Medium")],
        tier3_companies=[Tier3Company(company="TierThree", confidence="Low")],
        market_signals=[MarketRadarSignal(signal="Restructuring", company="TierOne")],
        hidden_market_hypotheses=[
            HiddenMarketHypothesis(hypothesis="Hidden need", why_client_fits="Strong fit")
        ],
        relationship_strategy=[RelationshipStrategy(target="TierOne", relationship_angle="Warm intro")],
    )
    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    mr = fetched.market_radar
    assert mr.tier1_companies[0].company == "TierOne"
    assert mr.tier2_companies[0].company == "TierTwo"
    assert mr.tier3_companies[0].company == "TierThree"
    assert mr.market_signals[0].signal == "Restructuring"
    assert mr.hidden_market_hypotheses[0].hypothesis == "Hidden need"
    assert mr.relationship_strategy[0].target == "TierOne"


def test_edited_advisor_brief_round_trip(pg_database):
    record = ClientRecord(profile=ClientProfile(name="Brief"))
    record.advisor_brief = AdvisorBrief(
        brief_summary="Summary",
        priority_opportunities=[
            PriorityOpportunity(opportunity="Opp", why_it_matters="Important")
        ],
    )
    record.advisor_brief_is_edited = True
    record.advisor_brief_edited_at = "2026-01-02T00:00:00+00:00"

    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    assert fetched.advisor_brief.brief_summary == "Summary"
    assert fetched.advisor_brief.priority_opportunities[0].opportunity == "Opp"
    assert fetched.advisor_brief_is_edited is True
    assert fetched.advisor_brief_edited_at is not None


def test_null_fields_distinct_from_false_and_empty(pg_database):
    record = ClientRecord(profile=ClientProfile(name="Nulls"))
    record.market_radar_is_complete = None
    record.market_radar_scan_warning = None
    record.advisor_brief_is_edited = None

    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    assert fetched.market_radar_is_complete is None
    assert fetched.market_radar_scan_warning is None
    assert fetched.advisor_brief_is_edited is None

    record2 = ClientRecord(profile=ClientProfile(name="False not null"))
    record2.market_radar_is_complete = False
    created2 = pg.create_client(record2)
    fetched2 = pg.get_client(created2.id)
    assert fetched2.market_radar_is_complete is False


def test_unusual_but_valid_status_strings_round_trip(pg_database):
    record = ClientRecord(
        profile=ClientProfile(name="Unusual Statuses"),
        opportunities=[
            Opportunity(
                title="Odd",
                status="Some Brand New Status Nobody Defined Yet",
                priority="Extremely High",
                confidence="vaguely-confident",
                source_type="manual-but-weird",
            )
        ],
    )
    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    opp = fetched.opportunities[0]
    assert opp.status == "Some Brand New Status Nobody Defined Yet"
    assert opp.priority == "Extremely High"
    assert opp.confidence == "vaguely-confident"
    assert opp.source_type == "manual-but-weird"


def test_operational_list_order_preserved_on_create(pg_database):
    record = ClientRecord(
        profile=ClientProfile(name="Ordered"),
        opportunities=[
            Opportunity(title="Z"),
            Opportunity(title="A"),
            Opportunity(title="M"),
        ],
        session_notes=[
            SessionNote(title="Third"),
            SessionNote(title="First"),
            SessionNote(title="Second"),
        ],
    )
    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    assert [o.title for o in fetched.opportunities] == ["Z", "A", "M"]
    assert [n.title for n in fetched.session_notes] == ["Third", "First", "Second"]


def test_operational_list_order_preserved_on_reorder_update(pg_database):
    record = ClientRecord(
        profile=ClientProfile(name="Reordered"),
        opportunities=[Opportunity(title="One"), Opportunity(title="Two"), Opportunity(title="Three")],
    )
    created = pg.create_client(record)
    fetched = pg.get_client(created.id)

    # Reverse the order and update — the same items, new sequence.
    fetched.opportunities = list(reversed(fetched.opportunities))
    pg.update_client(fetched)

    refetched = pg.get_client(created.id)
    assert [o.title for o in refetched.opportunities] == ["Three", "Two", "One"]
