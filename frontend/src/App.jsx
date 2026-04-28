import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

// ── Sample profile ────────────────────────────────────────────────────────────
const SAMPLE = {
  cv_text: `Managing Director – Infrastructure & Energy, Carlyle Advisory Partners (2019–2024)
Led strategic advisory mandates across European energy transition and infrastructure. Advised on £2.4bn of M&A transactions including two PE-backed portfolio exits. Managed relationships with 12 PE and infrastructure fund GPs. Built operating model for three portfolio company management teams.

VP Strategy & Corporate Development, National Grid PLC (2015–2019)
Drove corporate strategy and M&A pipeline for FTSE 20 regulated energy business. Led £680M acquisition of distributed energy assets. Built and led cross-functional deal execution teams of 25 across strategy, legal, and finance. Managed P&L of £1.2bn infrastructure assets. Delivered EBITDA improvement programme saving £45M.

Senior Associate, McKinsey & Company – Energy Practice (2011–2015)
Delivered operational transformation and commercial strategy engagements for European utilities and infrastructure funds. Specialised in energy transition, EBITDA improvement programmes, and regulatory strategy.

MBA, London Business School (2010). MEng Engineering, University of Cambridge (2007).`,
  top_achievements: `Advised on £2.4bn M&A mandate for PE-backed energy infrastructure exit, delivering 3.2x return to fund
Built corporate development function at National Grid from 0 to 8 people, completing 4 acquisitions in 3 years
Delivered operational transformation programme reducing OpEx by £45M across regulated network assets`,
  zone_of_genius: `Translating complex infrastructure and energy assets into investment-grade commercial narratives. I see the strategic angle others miss and move capital decisions forward at pace.`,
  conflict_marker: `I name the issue directly in the room, with data. I do not triangulate or avoid. I prefer to lose the argument with facts than win it with politics.`,
  never_again: `Large consensus-driven organisations where strategy is diluted before it reaches the market. I will not work where speed of decision is sacrificed for internal alignment theatre.`,
  industry_curiosity: `energy transition, infrastructure, private equity, climate`,
  lifestyle_preferences: `autonomy, board-level access, international mandates`,
  salary_floor: `300000`,
  upskilling_willingness: true,
  target_role: `PE Operating Partner`,
  target_sector: `Infrastructure & Energy`,
  target_seniority: `Partner`,
  transition_goal: `Move from strategic advisory into a PE operating partner seat focused on energy transition assets within 12 months`,
}

const INITIAL = {
  cv_text: '', top_achievements: '', zone_of_genius: '',
  conflict_marker: '', never_again: '', industry_curiosity: '',
  lifestyle_preferences: '', salary_floor: '', upskilling_willingness: false,
  target_role: '', target_sector: '', target_seniority: '', transition_goal: '',
}

// ── Loading stage messages ────────────────────────────────────────────────────
const LOAD_MSGS = [
  'Analysing profile…',
  'Comparing against target role…',
  'Identifying critical gaps…',
  'Building transition plan…',
]

// ── Verdict display maps ──────────────────────────────────────────────────────
const VERDICT_LABEL = {
  strong_yes: 'Strong',
  credible:   'Credible',
  borderline: 'Borderline',
  lean_no:    'No-Fit',
}
const VERDICT_CLS = {
  strong_yes: 'v-green',
  credible:   'v-blue',
  borderline: 'v-amber',
  lean_no:    'v-red',
}
const GAP_LABEL = {
  skill_gap:       'Skill Gap',
  credibility_gap: 'Credibility Gap',
  leadership_gap:  'Leadership Gap',
  commercial_gap:  'Commercial Gap',
  narrative_gap:   'Narrative Gap',
}

// ── Report rendering ─────────────────────────────────────────────────────────

const SCAN_MARKERS = {
  'DECISION':                       '◆',
  'CRITICAL GAPS':                  '▸',
  'UPGRADE STRATEGY':               '→',
  '90-DAY PLAN':                    '◯',
  'WHAT THE HIRING PANEL WILL ASK': '?',
}

// Sharp, blunt opening line per verdict
const DECISION_HOOK = {
  strong_yes: 'This profile is ready. Activate your network now.',
  credible:   'You are a credible candidate. One gap stands between you and a hire decision.',
  borderline: 'You are within reach — one specific gap is blocking the decision.',
  lean_no:    'You are not yet credible for this role. A structured programme closes this.',
}

// Verbose phrase → sharp replacement
const COMPRESSIONS = [
  // Hedge starters
  [/\byou should consider\b/gi,          ''],
  [/\bit would be beneficial to\b/gi,    ''],
  [/\bconsider taking steps to\b/gi,     ''],
  [/\byou are encouraged to\b/gi,        ''],
  [/\bit is worth noting that\b/gi,      ''],
  [/\bit is important to\b/gi,           ''],
  [/\bit should be noted that\b/gi,      ''],
  [/\bplease note that\b/gi,             ''],
  [/\btake the time to\b/gi,             ''],
  [/\byou could consider\b/gi,           'consider'],
  [/\byou may want to\b/gi,              ''],
  // Filler connectives
  [/\bin order to\b/gi,                  'to'],
  [/\bso as to\b/gi,                     'to'],
  [/\bwith a view to\b/gi,               'to'],
  [/\bat this point in time\b/gi,        'now'],
  [/\bgoing forward\b/gi,                ''],
  [/\bmoving forward\b/gi,               ''],
  [/\bwith that said,?\s*/gi,            ''],
  [/\bto that end,?\s*/gi,               ''],
  [/\bin this regard\b/gi,               ''],
  [/\bin this context\b/gi,              ''],
  [/\bas mentioned\b/gi,                 ''],
  [/\bon an ongoing basis\b/gi,          'ongoing'],
  // Bloated constructions
  [/\bdue to the fact that\b/gi,         'because'],
  [/\bthe fact that\b/gi,                'that'],
  [/\bhas the potential to\b/gi,         'can'],
  [/\bthe ability to\b/gi,               ''],
  [/\byour ability to\b/gi,              ''],
  [/\bin a position to\b/gi,             ''],
  [/\bwith respect to\b/gi,              'on'],
  [/\bwith regard to\b/gi,               'on'],
  [/\ba number of\b/gi,                  'several'],
  [/\bon a regular basis\b/gi,           'regularly'],
  [/\bprovide support for\b/gi,          'support'],
]

function compressText(text) {
  let t = text
  for (const [pat, rep] of COMPRESSIONS) {
    t = t.replace(pat, rep)
  }
  // Collapse extra spaces left by removals, re-capitalise start
  t = t.replace(/\s{2,}/g, ' ').trim()
  return t ? t[0].toUpperCase() + t.slice(1) : t
}

// Auto-bold time ranges not already wrapped in **
function autoBold(text) {
  return text.replace(/(?<!\*)(\d+[–\-]\d+\s+days)(?!\*)/g, '**$1**')
}

function renderInline(text) {
  return text.split(/(\*\*[^*]+\*\*)/).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : part
  )
}

// Split the flat text into [{heading, lines}] pairs
function parseSections(text) {
  const raw = text.split('\n')
  const sections = []
  let heading = null
  let body = []
  let i = 0
  while (i < raw.length) {
    const line = raw[i]
    const next = raw[i + 1] ?? ''
    if (line.trim() && /^=+$/.test(next.trim())) {
      sections.push({ heading, body })
      heading = line.trim()
      body = []
      i += 2
    } else {
      body.push(line)
      i++
    }
  }
  sections.push({ heading, body })
  return sections.filter(s => s.heading || s.body.some(l => l.trim()))
}

function renderLines(lines) {
  return lines.map((line, i) => {
    if (!line.trim()) return <div key={i} className="rpt-gap" />

    // Bullet: "  - text"
    if (/^  - /.test(line)) {
      const content = autoBold(compressText(line.slice(4)))
      return (
        <div key={i} className="rpt-bullet">
          <span className="rpt-bullet-dash">–</span>
          <span>{renderInline(content)}</span>
        </div>
      )
    }
    // Indented continuation: "    text"
    if (/^    \S/.test(line)) {
      const content = autoBold(compressText(line.trimStart()))
      return <div key={i} className="rpt-indent">{renderInline(content)}</div>
    }
    // Standalone label: "Blocked by:" / "Fix:" / "Risk:"
    if (/^[A-Z][A-Za-z ]{0,18}:$/.test(line.trim())) return (
      <div key={i} className="rpt-sublabel">{line.trim()}</div>
    )
    // Key-value line: "Verdict:         **Borderline**"  (alignment-sensitive — no compress)
    if (/^[A-Z][A-Za-z ]{0,25}:\s{2,}/.test(line)) return (
      <div key={i} className="rpt-kv">{renderInline(autoBold(line))}</div>
    )
    // Regular prose — compress + auto-bold
    const content = autoBold(compressText(line))
    return <div key={i} className="rpt-line">{renderInline(content)}</div>
  })
}

function renderSection(section, si, meta = {}) {
  const isDecision = section.heading === 'DECISION'
  const marker     = SCAN_MARKERS[section.heading]
  const hookLine   = isDecision ? DECISION_HOOK[meta.verdict] : null
  const gapLabel   = isDecision && meta.blockingGapType ? GAP_LABEL[meta.blockingGapType] : null

  return (
    <div key={si} className={`rpt-section${isDecision ? ' rpt-section--decision' : ''}`}>
      {section.heading && (
        <div className={`rpt-heading${isDecision ? ' rpt-heading--decision' : ''}`}>
          {marker && <span className="rpt-marker">{marker}</span>}
          {section.heading}
        </div>
      )}

      {/* Sharp opening line + primary constraint, injected at top of DECISION */}
      {hookLine && <div className="rpt-hook">{hookLine}</div>}
      {gapLabel && (
        <div className="rpt-constraint">
          <span className="rpt-constraint-label">Primary constraint</span>
          <span className="rpt-constraint-sep"> — </span>
          <span className="rpt-constraint-value">{gapLabel}</span>
        </div>
      )}

      {renderLines(section.body)}
    </div>
  )
}

function renderReport(text, meta = {}) {
  return parseSections(text).map((section, si) => renderSection(section, si, meta))
}

// Pull the first sentence of the executive summary as the key insight
function extractKeyInsight(summary) {
  if (!summary) return null
  const s = summary.split(/(?<=\.)\s+/)[0].trim()
  return s.endsWith('.') ? s : s + '.'
}

function parseList(str) {
  return str.split(/[\n,]/).map(s => s.trim()).filter(Boolean)
}

// ── Main component ────────────────────────────────────────────────────────────
export default function App() {
  const [form, setForm]         = useState(INITIAL)
  const [result, setResult]     = useState(null)
  const [loading, setLoading]   = useState(false)
  const [loadStage, setStage]   = useState(0)
  const [error, setError]       = useState('')
  const [copied, setCopied]     = useState(false)
  const summaryRef              = useRef(null)

  useEffect(() => {
    if (!loading) return
    setStage(0)
    const id = setInterval(() => setStage(s => Math.min(s + 1, LOAD_MSGS.length - 1)), 2200)
    return () => clearInterval(id)
  }, [loading])

  function handleChange(e) {
    const { name, value, type, checked } = e.target
    setForm(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const achievements = parseList(form.top_achievements).slice(0, 3)
    if (!achievements.length) {
      setError('At least one achievement is required.')
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    const payload = buildPayload(form)
    try {
      const { data } = await axios.post('/generate-dna', payload)
      setResult(data)
      setTimeout(() => summaryRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120)
    } catch (err) {
      const detail = err.response?.data?.message
        || err.response?.data?.detail
        || err.message
        || 'Unknown error'
      setError(`Error: ${detail}`)
    } finally {
      setLoading(false)
    }
  }

  function buildPayload(data) {
    const achievements = parseList(data.top_achievements).slice(0, 3)
    return {
      cv_text:               data.cv_text,
      top_achievements:      achievements,
      zone_of_genius:        data.zone_of_genius,
      conflict_marker:       data.conflict_marker,
      never_again:           data.never_again,
      industry_curiosity:    parseList(data.industry_curiosity),
      lifestyle_preferences: parseList(data.lifestyle_preferences),
      salary_floor:          parseFloat(data.salary_floor) || 0,
      upskilling_willingness: data.upskilling_willingness,
      ...(data.target_role      && { target_role:      data.target_role }),
      ...(data.target_sector    && { target_sector:    data.target_sector }),
      ...(data.target_seniority && { target_seniority: data.target_seniority }),
      ...(data.transition_goal  && { transition_goal:  data.transition_goal }),
    }
  }

  async function handleSampleGenerate() {
    setForm(SAMPLE)
    setLoading(true)
    setError('')
    setResult(null)
    const payload = buildPayload(SAMPLE)
    try {
      const { data } = await axios.post('/generate-dna', payload)
      setResult(data)
      setTimeout(() => summaryRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120)
    } catch (err) {
      const detail = err.response?.data?.message
        || err.response?.data?.detail
        || err.message
        || 'Unknown error'
      setError(`Error: ${detail}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleCopy() {
    if (!result?.formatted_report) return
    await navigator.clipboard.writeText(result.formatted_report)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleDownload() {
    if (!result?.formatted_report) return
    const blob = new Blob([result.formatted_report], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'career-dna-report.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  const er         = result?.executive_report
  const fitPct     = result?.pivot_delta != null
    ? Math.round(result.pivot_delta.overall_fit_score * 100)
    : null
  const keyInsight = extractKeyInsight(er?.executive_summary)

  return (
    <div className="container">

      {/* ── Header ────────────────────────────────────────── */}
      <header>
        <div className="header-row">
          <div>
            <h1>Career DNA</h1>
            <p className="subtitle">Transition Analysis Engine</p>
            <p className="tagline">See exactly how close you are to your next role — and what's blocking you.</p>
          </div>
          <button type="button" className="btn-sample" onClick={handleSampleGenerate} disabled={loading}>
            Generate Sample Report
          </button>
        </div>
      </header>

      {/* ── Form ──────────────────────────────────────────── */}
      <form onSubmit={handleSubmit}>

        <section>
          <h2>CV &amp; Background</h2>
          <label>
            CV Text <Req />
            <textarea name="cv_text" value={form.cv_text} onChange={handleChange}
              rows={10} placeholder="Paste your full CV here…" required />
          </label>
          <label>
            Top Achievements <Req />
            <Hint>One per line, max 3</Hint>
            <textarea name="top_achievements" value={form.top_achievements} onChange={handleChange}
              rows={4} placeholder={"Led transformation programme saving £30M…\nScaled revenue from £50M to £200M…"} required />
          </label>
          <label>
            Zone of Genius <Req />
            <textarea name="zone_of_genius" value={form.zone_of_genius} onChange={handleChange}
              rows={3} placeholder="Your area of exceptional ability…" required />
          </label>
        </section>

        <section>
          <h2>Work Preferences</h2>
          <label>
            Conflict Marker <Req />
            <textarea name="conflict_marker" value={form.conflict_marker} onChange={handleChange}
              rows={2} placeholder="How you typically behave under conflict…" required />
          </label>
          <label>
            Never Again <Req />
            <textarea name="never_again" value={form.never_again} onChange={handleChange}
              rows={2} placeholder="Work situations you refuse to repeat…" required />
          </label>
          <label>
            Industry Curiosity
            <Hint>Comma-separated</Hint>
            <input type="text" name="industry_curiosity" value={form.industry_curiosity}
              onChange={handleChange} placeholder="Private equity, technology, healthcare" />
          </label>
          <label>
            Lifestyle Preferences
            <Hint>Comma-separated</Hint>
            <input type="text" name="lifestyle_preferences" value={form.lifestyle_preferences}
              onChange={handleChange} placeholder="Remote work, autonomy, travel" />
          </label>
          <div className="row">
            <label>
              Salary Floor (£) <Req />
              <input type="number" name="salary_floor" value={form.salary_floor}
                onChange={handleChange} placeholder="150000" min="0" required />
            </label>
            <label className="checkbox-label">
              <input type="checkbox" name="upskilling_willingness"
                checked={form.upskilling_willingness} onChange={handleChange} />
              Open to upskilling
            </label>
          </div>
        </section>

        <section>
          <h2>Target Role <span className="optional">(optional)</span></h2>
          <label>
            Target Role
            <input type="text" name="target_role" value={form.target_role}
              onChange={handleChange} placeholder="CEO, Private Equity Operating Partner…" />
          </label>
          <div className="row">
            <label>
              Target Sector
              <input type="text" name="target_sector" value={form.target_sector}
                onChange={handleChange} placeholder="Technology, Financial Services…" />
            </label>
            <label>
              Target Seniority
              <input type="text" name="target_seniority" value={form.target_seniority}
                onChange={handleChange} placeholder="C-suite, Director…" />
            </label>
          </div>
          <label>
            Transition Goal
            <textarea name="transition_goal" value={form.transition_goal} onChange={handleChange}
              rows={2} placeholder="Become a PE Operating Partner within 18 months…" />
          </label>
        </section>

        <button type="submit" className="btn-submit" disabled={loading}>
          {loading ? LOAD_MSGS[loadStage] : 'Generate Report'}
        </button>

      </form>

      {error && <div className="error">{error}</div>}

      {/* ── Loading placeholder / Empty state ────────────── */}
      {!result && !error && (
        loading ? (
          <div className="loading-area">
            <div className="loading-bar"><div className="loading-bar-fill" /></div>
            <p className="loading-label">{LOAD_MSGS[loadStage]}</p>
          </div>
        ) : (
          <div className="empty-state">
            <p className="empty-title">Paste your CV to get a decision-grade career assessment</p>
            <p className="empty-body">
              Or click <strong>Generate Sample Report</strong> above to see a live example instantly.
            </p>
          </div>
        )
      )}

      {/* ── Summary card ──────────────────────────────────── */}
      {er && (
        <div className={`summary-card summary-card--${er.verdict}`} ref={summaryRef}>
          <p className="summary-eyebrow">Analysis Complete</p>
          <div className="summary-grid">
            {fitPct !== null && (
              <div className="metric">
                <span className="metric-label">Fit Score</span>
                <span className="metric-score">{fitPct}%</span>
              </div>
            )}
            <div className="metric">
              <span className="metric-label">Verdict</span>
              <span className={`verdict-pill ${VERDICT_CLS[er.verdict] ?? ''}`}>
                {VERDICT_LABEL[er.verdict] ?? er.verdict}
              </span>
            </div>
            {er.target_role && (
              <div className="metric">
                <span className="metric-label">Target Role</span>
                <span className="metric-value">{er.target_role}</span>
              </div>
            )}
            {er.time_to_upgrade && (
              <div className="metric">
                <span className="metric-label">Time to Upgrade</span>
                <span className="metric-value">{er.time_to_upgrade.split('.')[0]}</span>
              </div>
            )}
            {er.blocking_gap_type && (
              <div className="metric">
                <span className="metric-label">Primary Blocker</span>
                <span className="metric-value metric-warn">
                  {GAP_LABEL[er.blocking_gap_type] ?? er.blocking_gap_type}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Key insight strip ─────────────────────────────── */}
      {keyInsight && (
        <div className="key-insight fade-up">
          <span className="key-insight-label">Key Insight</span>
          <p className="key-insight-text">{renderInline(keyInsight)}</p>
        </div>
      )}

      {/* ── Full report ───────────────────────────────────── */}
      {result?.formatted_report && (
        <section className="report-section">
          <div className="report-header">
            <h2>Executive Transition Report</h2>
            <div className="report-actions">
              <button type="button" className="btn-copy" onClick={handleCopy}>
                {copied ? '✓ Copied' : 'Copy Report'}
              </button>
              <button type="button" className="btn-copy" onClick={handleDownload}>
                Download .txt
              </button>
            </div>
          </div>
          <div className="report">
            {renderReport(result.formatted_report, {
              verdict:         er?.verdict,
              blockingGapType: er?.blocking_gap_type,
            })}
          </div>
        </section>
      )}

    </div>
  )
}

function Req() { return <span className="required"> *</span> }
function Hint({ children }) { return <span className="hint">{children}</span> }
