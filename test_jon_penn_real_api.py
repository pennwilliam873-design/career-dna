"""
Jon Penn — Real Anthropic API test.

Usage (run in a terminal where the server is already running):
    python3 test_jon_penn_real_api.py

Expects:
    ANTHROPIC_API_KEY  — set via: export ANTHROPIC_API_KEY=sk-ant-...
    LLM_JUDGMENT_MODEL — optional override (default: claude-sonnet-4-5 if set, else haiku)

The script hits POST /generate-dna, then prints:
    - HTTP status
    - Real API vs mock confirmation
    - S1, S6, S7, S8, S9, S10, S11 extracted from formatted_report
    - Leakage check
"""
import json
import os
import re
import sys
import textwrap

try:
    import requests
except ImportError:
    sys.exit("requests not installed — run: pip3 install requests")

SERVER_URL = "http://127.0.0.1:8000"
ENDPOINT   = f"{SERVER_URL}/generate-dna"

# ---------------------------------------------------------------------------
# Jon Penn CV  — senior executive: Group CEO / Regional President / NED target
# ---------------------------------------------------------------------------
JON_PENN_CV = """
JON PENN
Group Chief Executive Officer | Regional President APAC | Non-Executive Director

LinkedIn: linkedin.com/in/jonpenn  |  Sydney, NSW, Australia
AICD Graduate Member

EXECUTIVE PROFILE
A Group CEO and Regional President with 20+ years of P&L accountability across APAC and global
enterprise contexts. Track record of large-scale commercial transformation, multi-country organisational
restructuring, and sustained revenue growth. Proven board-level engagement as both executive director
and NED candidate. Combines deep operating experience with strategic governance capability.

CAREER

Group Chief Executive Officer                                             2019 – present
Meridian Pacific Holdings | Sydney, NSW
 - Full P&L ownership for a diversified group with AUD 1.8 billion turnover and 4,200 staff across
   Australia, Singapore, Hong Kong, Malaysia and New Zealand.
 - Led a four-year enterprise transformation including a group restructure, two bolt-on acquisitions,
   and digitalisation of core operations — achieved 18% group revenue growth over three years.
 - Direct reports: 7 divisional CEOs / GMs. Accountable to a listed-company board of 9 directors.
 - Chaired the Group Risk and Audit Committee (executive chair role, 2021–2023).

Regional President, Asia Pacific                                         2014 – 2019
GlobalBridge Solutions (NYSE: GBR) | Singapore
 - P&L leadership for APAC region: USD 680 million revenue, 1,800 staff across 11 countries
   (Australia, Singapore, Japan, India, Indonesia, Thailand, Malaysia, China, Hong Kong, NZ, Korea).
 - Delivered three consecutive years of double-digit regional growth (CAGR 14%) against a flat
   global market, through country-specific go-to-market strategies and channel partnerships.
 - Led a regional restructure (2016) that reduced headcount by 220 while improving operating margin
   by 410 basis points; managed stakeholder communication with global board and local regulators.
 - Appointed to GlobalBridge Asia Advisory Council (2017–2019), advising the global CEO on
   APAC market strategy and regulatory environment.

Managing Director, Australia & New Zealand                               2010 – 2014
GlobalBridge Solutions (NYSE: GBR) | Sydney, NSW
 - Full country P&L: AUD 210 million revenue, 420 staff.
 - Grew ANZ market share from 14% to 21% over four years through a consultative sales transformation
   and investment in vertical market expertise (financial services and resources sectors).
 - Recruited and built the senior leadership team of 8 direct reports over 24 months.

General Manager, Commercial Excellence                                   2007 – 2010
Pinnacle Group | Melbourne, VIC
 - Led commercial transformation programme across five business units (AUD 380m combined revenue).
 - Introduced pricing governance, customer profitability analytics, and key account management
   frameworks that improved commercial margin by 280 basis points group-wide.

Senior Manager, Strategy & Business Development                          2003 – 2007
Pinnacle Group | Melbourne, VIC
 - Supported two strategic acquisitions, three divestments, and a category expansion into Asia.

BOARD & GOVERNANCE ENGAGEMENT
 - Non-Executive Director, Coastal Innovation Ltd (ASX listed) — appointed 2023, current
 - Board Observer, Fintech Bridge Pty Ltd — 2021 to present
 - Advisory Board Member, University of Melbourne Business School — 2020 to present
 - AICD Company Directors Course — completed 2019; Graduate Member (GAICD) active

EDUCATION
 - MBA, INSEAD (Fontainebleau) — 2002
 - Bachelor of Commerce (Finance & Economics), University of Melbourne — 1999

SELECTED ACHIEVEMENTS
 - Meridian Pacific Holdings: delivered AUD 280m in incremental group revenue over three years
   post-transformation; maintained investment-grade credit rating throughout restructure.
 - GlobalBridge APAC: top-ranked regional president globally for three consecutive years (2016–2018)
   on growth, margin, and engagement metrics.
 - Coastal Innovation NED: chaired the Audit and Risk Committee; oversaw CEO succession and a
   successful capital raise of AUD 45m in 2024.

TOOLS & SKILLS
P&L management | enterprise transformation | M&A integration | board governance | AICD |
stakeholder management | multi-country operations | digital transformation | executive team building |
commercial strategy | investor relations | regulatory engagement | strategic planning
"""

JON_PENN_PAYLOAD = {
    "cv_text": JON_PENN_CV,
    "target_role": "Group CEO / Regional President / NED",
    "llm_judgment_enabled": True,
    "top_achievements": [
        "Delivered AUD 280m incremental group revenue at Meridian Pacific Holdings through enterprise transformation",
        "Grew APAC region from USD 640m to USD 950m+ revenue over five years at GlobalBridge",
        "Led NED appointment to ASX-listed Coastal Innovation Ltd; chaired Audit and Risk Committee",
        "Regional restructure delivering 410bps margin improvement while managing 220 headcount reduction",
    ],
    "tools": [
        "P&L management", "enterprise transformation", "M&A integration",
        "board governance", "AICD", "digital transformation",
    ],
    "zone_of_genius": (
        "Commercial architecture at scale — I see the structural levers that unlock "
        "sustainable revenue growth and margin improvement, even in complex multi-country environments."
    ),
    "conflict_marker": (
        "I move quickly to establish facts, separate personalities from the issue, "
        "and drive toward a decision. I do not avoid conflict — I structure it."
    ),
    "never_again": (
        "Matrix organisations with no clear P&L accountability. "
        "I need to own the outcome and be accountable to a board."
    ),
    "industry_curiosity": [
        "infrastructure and utilities", "financial services", "health and aged care",
        "private equity-backed businesses", "listed ASX companies",
    ],
    "lifestyle_preferences": [
        "Sydney based preferred", "Asia Pacific travel acceptable",
        "board portfolio alongside executive role is ideal",
    ],
}


# ---------------------------------------------------------------------------
# Section extractor — splits formatted_report by section headers
# ---------------------------------------------------------------------------

SECTION_HEADERS = {
    "S1":  re.compile(r"^.*?(SECTION 1|EXECUTIVE CAREER|CAREER THESIS|THESIS|PATHWAY DECISION)", re.I | re.M),
    "S6":  re.compile(r"^.*?(SECTION 6|PATHWAY INTELLIGENCE|TARGET PATH)", re.I | re.M),
    "S7":  re.compile(r"^.*?(SECTION 7|TRANSFERABLE ADVANTAGE|TRANSFERABLE)", re.I | re.M),
    "S8":  re.compile(r"^.*?(SECTION 8|RISKS|BLIND SPOTS)", re.I | re.M),
    "S9":  re.compile(r"^.*?(SECTION 9|STRATEGIC OPTIONS)", re.I | re.M),
    "S10": re.compile(r"^.*?(SECTION 10|RECOMMENDED PATHWAY)", re.I | re.M),
    "S11": re.compile(r"^.*?(SECTION 11|30.60.90|ACTION PLAN)", re.I | re.M),
}

NEXT_SECTION_RE = re.compile(r"^.*?SECTION\s+\d+", re.I | re.M)


def extract_section(report: str, section_key: str) -> str:
    pat = SECTION_HEADERS.get(section_key)
    if not pat:
        return "(not found)"
    m = pat.search(report)
    if not m:
        return "(not found in report)"

    start = m.start()
    # Find next section header after this one
    rest = report[m.end():]
    next_m = NEXT_SECTION_RE.search(rest)
    end = m.end() + next_m.start() if next_m else len(report)

    snippet = report[start:end].strip()
    # Truncate very long sections
    if len(snippet) > 2000:
        snippet = snippet[:2000] + "\n  [... truncated ...]"
    return snippet


# ---------------------------------------------------------------------------
# Leakage check — internal fields / prompt fragments that must not appear
# ---------------------------------------------------------------------------

LEAKAGE_PATTERNS = [
    r"ANTHROPIC_API_KEY",
    r"sk-ant-",
    r"llm_judgment_enabled",
    r"evidence_package",
    r"hallucination_risk",
    r"score_verdict",
    r"score_adjustment",
    r"profile_tier",
    r"STRUCTURED EVIDENCE",
    r"STRICT RULES",
    r"RESPOND IN JSON",
    r"executive_thesis",          # JSON field name
    r"pathway_judgment",          # JSON field name
    r"action_plan_items",         # JSON field name
    r"LLM_JUDGMENT_MAX_ADJUSTMENT",
]


def leakage_check(report: str) -> list[str]:
    found = []
    for pattern in LEAKAGE_PATTERNS:
        if re.search(pattern, report, re.I):
            found.append(pattern)
    return found


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

SEP = "=" * 80
SUBSEP = "-" * 60


def banner(text: str) -> None:
    print(f"\n{SEP}")
    print(f"  {text}")
    print(SEP)


def section_block(label: str, content: str) -> None:
    print(f"\n{SUBSEP}")
    print(f"[ {label} ]")
    print(SUBSEP)
    for line in content.splitlines():
        print(textwrap.fill(line, width=100, subsequent_indent="  ") if len(line) > 100 else line)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    banner("Jon Penn — Career DNA Real API Test")

    # 1. Check env
    api_key_set = bool(os.getenv("ANTHROPIC_API_KEY", ""))
    model_set   = os.getenv("LLM_JUDGMENT_MODEL", "(not set — server default applies)")
    print(f"\n  ANTHROPIC_API_KEY set : {'YES ✓' if api_key_set else 'NO  ✗  — real API will NOT be used'}")
    print(f"  LLM_JUDGMENT_MODEL   : {model_set}")

    if not api_key_set:
        print("\n  WARNING: API key not detected. The server will fall back to mock mode.")
        print("  Export the key and restart the server before running this test.")

    # 2. Health check
    try:
        hc = requests.get(f"{SERVER_URL}/health", timeout=5)
        print(f"\n  Server health: {hc.status_code} {hc.json()}")
    except Exception as exc:
        sys.exit(f"\n  ERROR: Cannot reach server at {SERVER_URL}. Start it first.\n  {exc}")

    # 3. POST /generate-dna
    print(f"\n  Calling POST {ENDPOINT} ...")
    try:
        resp = requests.post(
            ENDPOINT,
            json=JON_PENN_PAYLOAD,
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
    except Exception as exc:
        sys.exit(f"\n  ERROR calling endpoint: {exc}")

    # 4. HTTP status
    banner(f"HTTP STATUS: {resp.status_code}")

    if resp.status_code != 200:
        print(f"\n  BODY: {resp.text[:2000]}")
        sys.exit(1)

    data = resp.json()

    # 5. LLM mode confirmation
    banner("LLM MODE CONFIRMATION")
    llm_j = data.get("llm_judgment") or {}
    if llm_j:
        profile_tier   = llm_j.get("profile_tier", "—")
        confidence     = llm_j.get("confidence_level", "—")
        hallucination  = llm_j.get("hallucination_risk", "—")
        score_adj      = llm_j.get("score_adjustment", "—")
        score_verdict  = llm_j.get("score_verdict", "—")
        baseline       = llm_j.get("baseline_score", "—")
        final          = llm_j.get("final_adjusted_score", "—")
        strongest      = llm_j.get("strongest_pathway", "—")
        warnings       = llm_j.get("warnings", [])

        # Heuristic: if warnings contain 'mock' or executive_thesis has generic phrasing, flag mock
        thesis_text    = llm_j.get("executive_thesis", "") or ""
        likely_mock    = "mock" in " ".join(warnings).lower()
        real_api_used  = api_key_set and not likely_mock

        print(f"\n  Real API used         : {'YES — real Anthropic call' if real_api_used else 'NO  — mock intelligence (no API key or LLM failed)'}")
        print(f"  Profile tier          : {profile_tier}")
        print(f"  Confidence level      : {confidence}")
        print(f"  Hallucination risk    : {hallucination}")
        print(f"  Score verdict         : {score_verdict}")
        print(f"  Baseline score        : {baseline}")
        print(f"  Score adjustment      : {score_adj:+d}" if isinstance(score_adj, int) else f"  Score adjustment      : {score_adj}")
        print(f"  Final adjusted score  : {final}")
        print(f"  Strongest pathway     : {strongest}")
        if warnings:
            print(f"  Warnings              : {'; '.join(warnings)}")
        evidence_used = llm_j.get("evidence_used", [])
        if evidence_used:
            print(f"\n  Evidence used by LLM:")
            for e in evidence_used:
                print(f"    • {e}")
    else:
        print("\n  llm_judgment block absent from response — LLM layer did not run.")

    # 6. Report sections
    report = data.get("formatted_report") or ""
    if not report:
        print("\n  WARNING: formatted_report is empty.")

    for code in ("S1", "S6", "S7", "S8", "S9", "S10", "S11"):
        content = extract_section(report, code)
        section_block(code, content)

    # 7. Leakage check
    banner("LEAKAGE CHECK")
    leaked = leakage_check(report)
    if leaked:
        print(f"\n  FAIL — internal fields found in formatted_report:")
        for p in leaked:
            print(f"    ✗  {p}")
    else:
        print("\n  PASS — no internal fields, prompt fragments, or API keys detected in formatted_report.")

    # 8. Pipeline warnings
    pipeline_warnings = data.get("pipeline_warnings", [])
    if pipeline_warnings:
        banner("PIPELINE WARNINGS")
        for w in pipeline_warnings:
            print(f"  • {w}")

    banner("TEST COMPLETE")
    print()


if __name__ == "__main__":
    main()
