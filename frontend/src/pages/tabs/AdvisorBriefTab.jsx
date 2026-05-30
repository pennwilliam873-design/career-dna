import { useState } from 'react'
import { api } from '../../apiClient'

export default function AdvisorBriefTab({ client, onUpdate }) {
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  const b         = client.advisor_brief
  const rawText   = client.advisor_brief_raw
  const hasOutput = b || rawText

  async function handleGenerate() {
    setLoading(true)
    setError('')
    try {
      const updated = await api.generateAdvisorBrief(client.id)
      onUpdate(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const generatedAt = client.advisor_brief_generated_at
    ? new Date(client.advisor_brief_generated_at).toLocaleString('en-GB', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null

  return (
    <div>
      {error && <div className="os-error">{error}</div>}

      {!hasOutput ? (
        <div className="os-generate-prompt">
          <p className="os-generate-prompt-title">Generate Advisor Brief</p>
          <p className="os-generate-prompt-body">
            Synthesises all saved workspace data — CV, positioning, market radar and
            opportunities — into a private pre-session briefing for the advisor.
            Run CV Studio, Positioning, or Market Radar first for the best output.
          </p>
          <button
            className="os-btn os-btn--primary"
            onClick={handleGenerate}
            disabled={loading}
          >
            {loading ? 'Generating brief…' : 'Generate Advisor Brief'}
          </button>
        </div>
      ) : (
        <>
          {/* ── Action bar ────────────────────────────────────────────── */}
          <div className="os-positioning-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <span className="os-advisor-brief-badge">Advisor Eyes Only</span>
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

          {/* ── Confidential bar ─────────────────────────────────────── */}
          <div className="os-brief-confidential-bar">
            Advisor Eyes Only — Not for Distribution
          </div>

          {/* ── Fallback warning ─────────────────────────────────────── */}
          {rawText && !b && (
            <div className="os-raw-warning">
              <strong>Structured parse unavailable.</strong>{' '}
              Showing brief as formatted text. Click <strong>Regenerate</strong> to retry
              structured extraction.
            </div>
          )}

          {/* ── Raw markdown fallback ────────────────────────────────── */}
          {rawText && !b && (
            <div className="os-raw-analysis">
              <RawMarkdown text={rawText} />
            </div>
          )}

          {/* ── Structured output ───────────────────────────────────── */}
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
        </>
      )}
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
