import { useState } from 'react'
import { api } from '../../apiClient'

export default function PositioningTab({ client, onUpdate }) {
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  const p        = client.positioning        // structured (primary path)
  const rawText  = client.positioning_raw    // markdown fallback
  const hasOutput = p || rawText

  async function handleGenerate() {
    setLoading(true)
    setError('')
    try {
      const updated = await api.generatePositioning(client.id)
      onUpdate(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const generatedAt = client.positioning_generated_at
    ? new Date(client.positioning_generated_at).toLocaleString('en-GB', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null

  return (
    <div>
      {error && <div className="os-error">{error}</div>}

      {!hasOutput ? (
        <div className="os-generate-prompt">
          <p className="os-generate-prompt-title">Generate Executive Positioning</p>
          <p className="os-generate-prompt-body">
            Save the client profile first, then generate a structured positioning assessment.
            The model will diagnose market positioning — not summarise the CV.
          </p>
          <button
            className="os-btn os-btn--primary"
            onClick={handleGenerate}
            disabled={loading}
          >
            {loading ? 'Generating positioning…' : 'Generate Positioning'}
          </button>
        </div>
      ) : (
        <>
          {/* ── Action bar ────────────────────────────────────────────── */}
          <div className="os-positioning-header">
            <div>
              {generatedAt && (
                <span className="os-positioning-meta">Generated {generatedAt}</span>
              )}
            </div>
            <button
              className="os-btn os-btn--secondary"
              onClick={handleGenerate}
              disabled={loading}
            >
              {loading ? 'Regenerating…' : 'Regenerate'}
            </button>
          </div>

          {/* ── Fallback warning banner ──────────────────────────────── */}
          {rawText && !p && (
            <div className="os-raw-warning">
              <strong>Structured parse unavailable.</strong>{' '}
              Showing Claude's analysis as formatted text. Click <strong>Regenerate</strong> to retry structured extraction.
            </div>
          )}

          {/* ── Raw markdown fallback output ────────────────────────── */}
          {rawText && !p && (
            <div className="os-raw-analysis">
              <RawMarkdown text={rawText} />
            </div>
          )}

          {/* ── Structured output ───────────────────────────────────── */}
          {p && (
            <>
              {p.executive_positioning && (
                <div className="os-card">
                  <p className="os-card-label">Executive Positioning</p>
                  <p className="os-card-value">{p.executive_positioning}</p>
                </div>
              )}

              {p.leadership_archetype && (
                <div className="os-card" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <p className="os-card-label" style={{ margin: 0, flexShrink: 0 }}>
                    Leadership Archetype
                  </p>
                  <span className="os-archetype-pill">{p.leadership_archetype}</span>
                </div>
              )}

              <div className="os-section-title">Market Diagnosis</div>
              <div className="os-list-grid">
                <ListCard label="Core Strengths"     items={p.core_strengths} />
                <ListCard label="Market Credibility" items={p.market_credibility} />
                <ListCard label="Positioning Risks"  items={p.positioning_risks} variant="risk" />
              </div>

              {(p.narrative_to_lead || p.narrative_to_avoid) && (
                <>
                  <div className="os-section-title">Narrative Direction</div>
                  <div className="os-narrative-grid">
                    {p.narrative_to_lead && (
                      <div className="os-card os-narrative-card--lead">
                        <p className="os-card-label">Lead With</p>
                        <p className="os-card-value">{p.narrative_to_lead}</p>
                      </div>
                    )}
                    {p.narrative_to_avoid && (
                      <div className="os-card os-narrative-card--avoid">
                        <p className="os-card-label">Avoid</p>
                        <p className="os-card-value">{p.narrative_to_avoid}</p>
                      </div>
                    )}
                  </div>
                </>
              )}

              {p.recommended_pathways?.length > 0 && (
                <>
                  <div className="os-section-title">Recommended Pathways</div>
                  <div className="os-pathway-list">
                    {p.recommended_pathways.map((pw, i) => (
                      <PathwayCard key={i} pathway={pw} />
                    ))}
                  </div>
                </>
              )}

              {p.advisor_only_notes?.length > 0 && (
                <>
                  <div className="os-section-title">Advisor Notes (not for client)</div>
                  <div className="os-advisor-card">
                    <p className="os-card-label">For your eyes only</p>
                    <ul className="os-advisor-notes">
                      {p.advisor_only_notes.map((note, i) => (
                        <li key={i}>{note}</li>
                      ))}
                    </ul>
                  </div>
                </>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}

// ── Simple inline markdown renderer ──────────────────────────────────────────
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
      elements.push(
        <p key={key++} className="os-raw-heading">{trimmed.slice(3)}</p>
      )
    } else if (trimmed.startsWith('### ')) {
      flushBullets()
      elements.push(
        <p key={key++} className="os-raw-heading" style={{ fontSize: 13 }}>{trimmed.slice(4)}</p>
      )
    } else if (trimmed.startsWith('- ')) {
      bulletBuffer.push(trimmed.slice(2))
    } else if (trimmed === '') {
      flushBullets()
    } else if (trimmed) {
      flushBullets()
      elements.push(
        <p key={key++} className="os-raw-body">{trimmed}</p>
      )
    }
  }
  flushBullets()
  return <>{elements}</>
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ListCard({ label, items, variant }) {
  if (!items?.length) return null
  return (
    <div className={`os-list-card${variant === 'risk' ? ' os-list-card--risk' : ''}`}>
      <p className="os-card-label">{label}</p>
      <ul className="os-list-items">
        {items.map((item, i) => <li key={i}>{item}</li>)}
      </ul>
    </div>
  )
}

function PathwayCard({ pathway }) {
  const fitKey = (pathway.fit_level || '').toLowerCase()
  const badgeCls =
    fitKey === 'high'    ? 'os-fit-badge--high'    :
    fitKey === 'stretch' ? 'os-fit-badge--stretch'  :
                           'os-fit-badge--medium'

  return (
    <div className="os-pathway-card">
      <p className="os-pathway-name">{pathway.pathway}</p>
      {pathway.fit_level && (
        <span className={`os-fit-badge ${badgeCls}`}>{pathway.fit_level}</span>
      )}
      {pathway.rationale && (
        <p className="os-pathway-rationale">{pathway.rationale}</p>
      )}
      {pathway.stretch_risk && (
        <>
          <span className="os-pathway-risk-label">Stretch Risk</span>
          <p className="os-pathway-risk">{pathway.stretch_risk}</p>
        </>
      )}
    </div>
  )
}
