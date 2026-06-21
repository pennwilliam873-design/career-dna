import { useState, useRef, useEffect } from 'react'
import { api } from '../../apiClient'

// Split a textarea's newline-separated text into a trimmed, non-empty array.
function splitLines(text) {
  return (text || '').split('\n').map(s => s.trim()).filter(Boolean)
}

// Initialise the edit form from a structured AdvisorBrief object.
function briefToForm(b) {
  return {
    brief_summary:                  b.brief_summary || '',
    client_situation:               b.client_situation || '',
    session_focus_text:             (b.session_focus || []).join('\n'),
    key_positioning_insights_text:  (b.key_positioning_insights || []).join('\n'),
    priority_opportunities:         (b.priority_opportunities || []).map(o => ({ ...o })),
    market_signals_text:            (b.market_signals_to_discuss || []).join('\n'),
    questions_text:                 (b.questions_to_ask_client || []).join('\n'),
    challenges_text:                (b.advisor_challenges || []).join('\n'),
    next_actions_text:              (b.recommended_next_actions || []).join('\n'),
    advisor_notes_text:             (b.advisor_only_notes || []).join('\n'),
    network_strategy_summary:       b.network_strategy_summary || '',
  }
}

// Convert the edit form back to an AdvisorBrief payload.
function formToBrief(f) {
  return {
    brief_summary:              f.brief_summary,
    client_situation:           f.client_situation,
    session_focus:              splitLines(f.session_focus_text),
    key_positioning_insights:   splitLines(f.key_positioning_insights_text),
    priority_opportunities:     f.priority_opportunities,
    market_signals_to_discuss:  splitLines(f.market_signals_text),
    questions_to_ask_client:    splitLines(f.questions_text),
    advisor_challenges:         splitLines(f.challenges_text),
    recommended_next_actions:   splitLines(f.next_actions_text),
    advisor_only_notes:         splitLines(f.advisor_notes_text),
    network_strategy_summary:   f.network_strategy_summary,
  }
}

export default function AdvisorBriefTab({ client, onUpdate }) {
  const [generating, setGenerating] = useState(false)
  const [saving,     setSaving]     = useState(false)
  const [error,      setError]      = useState('')
  const [editForm,   setEditForm]   = useState(null)  // null = view mode

  const b         = client.advisor_brief
  const rawText   = client.advisor_brief_raw
  const hasOutput = b || rawText
  const isEdited  = client.advisor_brief_is_edited === true

  const generatedAt = client.advisor_brief_generated_at
    ? new Date(client.advisor_brief_generated_at).toLocaleString('en-GB', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null

  const editedAt = client.advisor_brief_edited_at
    ? new Date(client.advisor_brief_edited_at).toLocaleString('en-GB', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null

  // ── Handlers ──────────────────────────────────────────────────────────────

  async function handleGenerate() {
    if (isEdited) {
      if (!window.confirm(
        'This will replace your edited Advisor Brief with a newly generated version. Continue?'
      )) return
    }
    setGenerating(true)
    setError('')
    setEditForm(null)
    try {
      const updated = await api.generateAdvisorBrief(client.id)
      onUpdate(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  function enterEdit() {
    if (!b) return
    setEditForm(briefToForm(b))
    setError('')
  }

  function cancelEdit() {
    setEditForm(null)
    setError('')
  }

  async function handleSave() {
    setSaving(true)
    setError('')
    try {
      const payload = formToBrief(editForm)
      const updated = await api.updateAdvisorBrief(client.id, payload)
      onUpdate(updated)
      setEditForm(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  function setField(key, value) {
    setEditForm(f => ({ ...f, [key]: value }))
  }

  function updateOpp(idx, field, value) {
    setEditForm(f => ({
      ...f,
      priority_opportunities: f.priority_opportunities.map((opp, i) =>
        i === idx ? { ...opp, [field]: value } : opp
      ),
    }))
  }

  // ── Empty / generate prompt ───────────────────────────────────────────────

  if (!hasOutput) {
    return (
      <div>
        {error && <div className="os-error">{error}</div>}
        <div className="os-generate-prompt">
          <p className="os-generate-prompt-title">Generate Advisor Brief</p>
          <p className="os-generate-prompt-body">
            Synthesises all saved workspace data — CV, positioning, market radar,
            opportunities, and session notes — into a private pre-session briefing.
            Run CV Studio, Positioning, or Market Radar first for the best output.
          </p>
          <button
            className="os-btn os-btn--primary"
            onClick={handleGenerate}
            disabled={generating}
          >
            {generating ? 'Generating brief…' : 'Generate Advisor Brief'}
          </button>
        </div>
      </div>
    )
  }

  // ── Edit mode ─────────────────────────────────────────────────────────────

  if (editForm) {
    return (
      <div>
        {error && <div className="os-error">{error}</div>}

        <div className="os-positioning-header" style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <span className="os-advisor-brief-badge">Advisor Eyes Only</span>
            <span className="os-positioning-meta">Editing brief</span>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="os-btn os-btn--primary"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
            <button
              className="os-btn os-btn--secondary"
              onClick={cancelEdit}
              disabled={saving}
            >
              Cancel
            </button>
          </div>
        </div>

        <div className="os-brief-confidential-bar">
          Advisor Eyes Only — Not for Distribution
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginTop: 16 }}>

          <BriefEditField
            label="Brief Summary"
            value={editForm.brief_summary}
            onChange={v => setField('brief_summary', v)}
            minHeight={90}
          />

          <BriefEditField
            label="Client Situation"
            value={editForm.client_situation}
            onChange={v => setField('client_situation', v)}
            minHeight={90}
          />

          <BriefEditListField
            label="Session Focus"
            hint="One item per line"
            value={editForm.session_focus_text}
            onChange={v => setField('session_focus_text', v)}
            minHeight={130}
          />

          <BriefEditListField
            label="Key Positioning Insights"
            hint="One insight per line"
            value={editForm.key_positioning_insights_text}
            onChange={v => setField('key_positioning_insights_text', v)}
            minHeight={130}
          />

          <BriefEditField
            label="Network Strategy (Hidden Market Map)"
            value={editForm.network_strategy_summary}
            onChange={v => setField('network_strategy_summary', v)}
            minHeight={70}
          />

          {/* Priority Opportunities — per-subfield editing */}
          <div>
            <p className="os-label" style={{ marginBottom: 8 }}>Priority Opportunities</p>
            {editForm.priority_opportunities.map((opp, i) => (
              <div
                key={i}
                style={{
                  border: '1px solid #e2e8f0', borderRadius: 6,
                  padding: '12px 14px', marginBottom: 10,
                }}
              >
                <p style={{ fontSize: 10, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '0 0 10px' }}>
                  Opportunity {i + 1}
                </p>
                <BriefEditField
                  label="Opportunity"
                  value={opp.opportunity}
                  onChange={v => updateOpp(i, 'opportunity', v)}
                  minHeight={44}
                />
                <div style={{ marginTop: 8 }}>
                  <BriefEditField
                    label="Why it matters"
                    value={opp.why_it_matters}
                    onChange={v => updateOpp(i, 'why_it_matters', v)}
                    minHeight={64}
                  />
                </div>
                <div style={{ marginTop: 8 }}>
                  <BriefEditField
                    label="Recommended advisor action"
                    value={opp.recommended_advisor_action}
                    onChange={v => updateOpp(i, 'recommended_advisor_action', v)}
                    minHeight={64}
                  />
                </div>
                <div style={{ marginTop: 8 }}>
                  <BriefEditField
                    label="Risk / watch out"
                    value={opp.risk_or_watchout}
                    onChange={v => updateOpp(i, 'risk_or_watchout', v)}
                    minHeight={64}
                  />
                </div>
              </div>
            ))}
          </div>

          <BriefEditListField
            label="Market Signals to Discuss"
            hint="One signal per line"
            value={editForm.market_signals_text}
            onChange={v => setField('market_signals_text', v)}
            minHeight={130}
          />

          <BriefEditListField
            label="Questions to Ask the Client"
            hint="One question per line"
            value={editForm.questions_text}
            onChange={v => setField('questions_text', v)}
            minHeight={150}
          />

          <BriefEditListField
            label="Advisor Challenges"
            hint="One challenge per line"
            value={editForm.challenges_text}
            onChange={v => setField('challenges_text', v)}
            minHeight={110}
          />

          <BriefEditListField
            label="Recommended Next Actions"
            hint="One action per line"
            value={editForm.next_actions_text}
            onChange={v => setField('next_actions_text', v)}
            minHeight={110}
          />

          <BriefEditListField
            label="Advisor Notes (not for client)"
            hint="One note per line"
            value={editForm.advisor_notes_text}
            onChange={v => setField('advisor_notes_text', v)}
            minHeight={110}
          />

        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 24, paddingTop: 16, borderTop: '1px solid #e2e8f0' }}>
          <button
            className="os-btn os-btn--primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
          <button
            className="os-btn os-btn--secondary"
            onClick={cancelEdit}
            disabled={saving}
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  // ── View mode ─────────────────────────────────────────────────────────────

  return (
    <div>
      {error && <div className="os-error">{error}</div>}

      {/* ── Action bar ──────────────────────────────────────────────────── */}
      <div className="os-positioning-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span className="os-advisor-brief-badge">Advisor Eyes Only</span>
          {isEdited && editedAt ? (
            <span className="os-positioning-meta">Edited · {editedAt}</span>
          ) : generatedAt ? (
            <span className="os-positioning-meta">Generated {generatedAt}</span>
          ) : null}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {b && (
            <button
              className="os-btn os-btn--secondary"
              onClick={enterEdit}
              disabled={generating}
            >
              Edit Brief
            </button>
          )}
          <button
            className="os-btn os-btn--secondary"
            onClick={handleGenerate}
            disabled={generating}
          >
            {generating ? 'Regenerating…' : 'Regenerate'}
          </button>
        </div>
      </div>

      {/* ── Confidential bar ────────────────────────────────────────────── */}
      <div className="os-brief-confidential-bar">
        Advisor Eyes Only — Not for Distribution
      </div>

      {/* ── Fallback warning ─────────────────────────────────────────────── */}
      {rawText && !b && (
        <div className="os-raw-warning">
          <strong>Structured parse unavailable.</strong>{' '}
          Showing brief as formatted text. Click <strong>Regenerate</strong> to retry
          structured extraction.
        </div>
      )}

      {/* ── Raw markdown fallback ────────────────────────────────────────── */}
      {rawText && !b && (
        <div className="os-raw-analysis">
          <RawMarkdown text={rawText} />
        </div>
      )}

      {/* ── Structured output ────────────────────────────────────────────── */}
      {b && (
        <>
          {b.brief_summary && (
            <div className="os-brief-hero">
              <p className="os-brief-hero-label">Brief Summary</p>
              <p className="os-brief-hero-body">{b.brief_summary}</p>
            </div>
          )}

          {b.client_situation && (
            <div className="os-card os-card--accent-left">
              <p className="os-card-label">Client Situation</p>
              <p className="os-card-value">{b.client_situation}</p>
            </div>
          )}

          {b.session_focus?.length > 0 && (
            <div className="os-brief-session-focus">
              <p className="os-card-label" style={{ marginBottom: 10 }}>Session Focus</p>
              <ol className="os-brief-numbered-list">
                {b.session_focus.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ol>
            </div>
          )}

          {b.key_positioning_insights?.length > 0 && (
            <>
              <div className="os-section-title">Key Positioning Insights</div>
              <div className="os-list-card">
                <ul className="os-list-items">
                  {b.key_positioning_insights.map((insight, i) => (
                    <li key={i}>{insight}</li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {b.network_strategy_summary && (
            <div className="os-card os-card--accent-left">
              <p className="os-card-label">Network Strategy — Hidden Market Map</p>
              <p className="os-card-value">{b.network_strategy_summary}</p>
            </div>
          )}

          {b.priority_opportunities?.length > 0 && (
            <>
              <div className="os-section-title">Priority Opportunities</div>
              <div className="os-brief-opp-grid">
                {b.priority_opportunities.map((opp, i) => (
                  <BriefOpportunityCard key={i} opp={opp} />
                ))}
              </div>
            </>
          )}

          {b.market_signals_to_discuss?.length > 0 && (
            <>
              <div className="os-section-title">Market Signals to Discuss</div>
              <div className="os-list-card">
                <ul className="os-list-items">
                  {b.market_signals_to_discuss.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {b.questions_to_ask_client?.length > 0 && (
            <>
              <div className="os-section-title">Questions to Ask the Client</div>
              <div className="os-list-card os-brief-questions-card">
                <ol className="os-brief-numbered-list">
                  {b.questions_to_ask_client.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ol>
              </div>
            </>
          )}

          {b.advisor_challenges?.length > 0 && (
            <>
              <div className="os-section-title os-section-title--warning">Advisor Challenges</div>
              <div className="os-list-card os-list-card--risk">
                <p className="os-card-label">Things to pressure-test</p>
                <ul className="os-list-items">
                  {b.advisor_challenges.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {b.recommended_next_actions?.length > 0 && (
            <>
              <div className="os-section-title">Recommended Next Actions</div>
              <div className="os-list-card">
                <ul className="os-list-items">
                  {b.recommended_next_actions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </div>
            </>
          )}

          {b.advisor_only_notes?.length > 0 && (
            <>
              <div className="os-section-title">Advisor Notes (Not for Client)</div>
              <div className="os-advisor-card">
                <p className="os-card-label">For your eyes only</p>
                <ul className="os-advisor-notes">
                  {b.advisor_only_notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

// ── AutoTextarea — grows to fit content, never scrolls internally ─────────────

function AutoTextarea({ value, onChange, minHeight = 80, maxHeight = 560 }) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(Math.max(el.scrollHeight, minHeight), maxHeight)}px`
  }, [value, minHeight, maxHeight])

  return (
    <textarea
      ref={ref}
      className="os-textarea"
      value={value}
      onChange={onChange}
      style={{ minHeight, resize: 'vertical', overflowY: 'auto' }}
    />
  )
}

// ── Edit field helpers ────────────────────────────────────────────────────────

function BriefEditField({ label, value, onChange, minHeight = 80 }) {
  return (
    <div>
      <label className="os-label">{label}</label>
      <AutoTextarea
        value={value}
        onChange={e => onChange(e.target.value)}
        minHeight={minHeight}
      />
    </div>
  )
}

function BriefEditListField({ label, hint, value, onChange, minHeight = 130 }) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
        <label className="os-label" style={{ marginBottom: 0 }}>{label}</label>
        <span style={{ fontSize: 10, color: '#94a3b8' }}>{hint}</span>
      </div>
      <AutoTextarea
        value={value}
        onChange={e => onChange(e.target.value)}
        minHeight={minHeight}
      />
    </div>
  )
}

// ── BriefOpportunityCard ──────────────────────────────────────────────────────

function BriefOpportunityCard({ opp }) {
  return (
    <div className="os-brief-opp-card">
      <p className="os-brief-opp-title">{opp.opportunity}</p>
      {opp.why_it_matters && (
        <p className="os-brief-opp-body">{opp.why_it_matters}</p>
      )}
      {opp.recommended_advisor_action && (
        <>
          <span className="os-pathway-risk-label">Advisor Action</span>
          <p className="os-brief-opp-action">{opp.recommended_advisor_action}</p>
        </>
      )}
      {opp.risk_or_watchout && (
        <>
          <span className="os-pathway-risk-label">Risk / Watch Out</span>
          <p className="os-pathway-risk">{opp.risk_or_watchout}</p>
        </>
      )}
    </div>
  )
}

// ── RawMarkdown ───────────────────────────────────────────────────────────────

function RawMarkdown({ text }) {
  const lines = text.split('\n')
  const elements = []
  let bulletBuffer = []
  let key = 0

  function flushBullets() {
    if (!bulletBuffer.length) return
    elements.push(
      <ul key={key++} className="os-list-items os-raw-list">
        {bulletBuffer.map((b, i) => <li key={i}>{b}</li>)}
      </ul>
    )
    bulletBuffer = []
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('## ')) {
      flushBullets()
      elements.push(<p key={key++} className="os-raw-heading">{trimmed.slice(3)}</p>)
    } else if (trimmed.startsWith('### ')) {
      flushBullets()
      elements.push(
        <p key={key++} className="os-raw-heading" style={{ fontSize: 13 }}>
          {trimmed.slice(4)}
        </p>
      )
    } else if (trimmed.startsWith('- ')) {
      bulletBuffer.push(trimmed.slice(2))
    } else if (trimmed === '') {
      flushBullets()
    } else if (trimmed) {
      flushBullets()
      elements.push(<p key={key++} className="os-raw-body">{trimmed}</p>)
    }
  }
  flushBullets()
  return <>{elements}</>
}
