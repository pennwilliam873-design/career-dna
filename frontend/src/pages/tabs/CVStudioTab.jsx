import { useState } from 'react'
import { api } from '../../apiClient'

export default function CVStudioTab({ client, onUpdate }) {
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [showCv, setShowCv]   = useState(false)

  const cvText      = client.profile?.cv_text?.trim() || ''
  const intel       = client.cv_intelligence       // structured (primary path)
  const rawText     = client.cv_intelligence_raw   // markdown fallback
  const hasOutput   = intel || rawText
  const generatedAt = client.cv_intelligence_generated_at
    ? new Date(client.cv_intelligence_generated_at).toLocaleString('en-GB', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null

  async function handleAnalyse() {
    setLoading(true)
    setError('')
    try {
      const updated = await api.analyseCv(client.id)
      onUpdate(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // ── No CV saved yet ───────────────────────────────────────────────────────
  if (!cvText) {
    return (
      <div className="os-generate-prompt">
        <p className="os-generate-prompt-title">No CV text saved</p>
        <p className="os-generate-prompt-body">
          Go to the <strong>Profile</strong> tab, paste the client's CV, and click{' '}
          <strong>Save Profile</strong>. Then return here to run the analysis.
        </p>
      </div>
    )
  }

  return (
    <div>
      {error && <div className="os-error">{error}</div>}

      {/* ── Action bar ─────────────────────────────────────────────────── */}
      <div className="os-positioning-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            className="os-btn os-btn--primary"
            onClick={handleAnalyse}
            disabled={loading}
          >
            {loading ? 'Analysing CV…' : hasOutput ? 'Re-analyse CV' : 'Analyse CV'}
          </button>
          {generatedAt && (
            <span className="os-positioning-meta">Last run {generatedAt}</span>
          )}
        </div>

        <button
          className="os-btn os-btn--ghost"
          onClick={() => setShowCv(v => !v)}
          style={{ fontSize: 12 }}
        >
          {showCv ? 'Hide CV text' : 'Show CV text'}
        </button>
      </div>

      {/* ── Collapsed CV preview ────────────────────────────────────────── */}
      {showCv && (
        <div className="os-cv-preview">
          <pre className="os-cv-preview-text">{cvText}</pre>
        </div>
      )}

      {/* ── Empty state ─────────────────────────────────────────────────── */}
      {!hasOutput && !loading && (
        <div className="os-generate-prompt" style={{ marginTop: 16 }}>
          <p className="os-generate-prompt-title">CV ready to analyse</p>
          <p className="os-generate-prompt-body">
            Click <strong>Analyse CV</strong> above. The model will extract structured
            intelligence — what the CV proves, what is missing, and what needs to be
            repositioned for the client's next move.
          </p>
        </div>
      )}

      {/* ── Fallback warning banner ──────────────────────────────────────── */}
      {rawText && !intel && (
        <div className="os-raw-warning">
          <strong>Structured parse unavailable.</strong>{' '}
          Showing Claude's analysis as formatted text. Click <strong>Re-analyse CV</strong> to retry structured extraction.
        </div>
      )}

      {/* ── Raw markdown fallback output ────────────────────────────────── */}
      {rawText && !intel && (
        <div className="os-raw-analysis">
          <RawMarkdown text={rawText} />
        </div>
      )}

      {/* ── Structured intelligence output ──────────────────────────────── */}
      {intel && (
        <>
          {intel.executive_summary && (
            <div className="os-card">
              <p className="os-card-label">Executive Summary</p>
              <p className="os-card-value">{intel.executive_summary}</p>
            </div>
          )}
          {intel.career_arc && (
            <div className="os-card">
              <p className="os-card-label">Career Arc</p>
              <p className="os-card-value">{intel.career_arc}</p>
            </div>
          )}

          {hasAny(intel.leadership_scale) && (
            <>
              <div className="os-section-title">Leadership Scale</div>
              <div className="os-scale-grid">
                <ScaleItem label="Team Size"     value={intel.leadership_scale.team_size} />
                <ScaleItem label="Revenue / P&L" value={intel.leadership_scale.revenue_or_pnl} />
                <ScaleItem label="Geography"     value={intel.leadership_scale.geography} />
                <ScaleItem label="Stakeholders"  value={intel.leadership_scale.stakeholders} />
              </div>
            </>
          )}

          {intel.signature_achievements?.length > 0 && (
            <>
              <div className="os-section-title">Signature Achievements</div>
              <div className="os-card">
                <ul className="os-list-items" style={{ margin: 0 }}>
                  {intel.signature_achievements.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </div>
            </>
          )}

          {(intel.core_capabilities?.length > 0 || intel.sector_experience?.length > 0 || intel.role_patterns?.length > 0) && (
            <>
              <div className="os-section-title">Experience Profile</div>
              <div className="os-list-grid">
                <ListCard label="Core Capabilities" items={intel.core_capabilities} />
                <ListCard label="Sector Experience" items={intel.sector_experience} />
                <ListCard label="Role Patterns"     items={intel.role_patterns} />
              </div>
            </>
          )}

          {(intel.commercial_strengths?.length > 0 || intel.transformation_strengths?.length > 0) && (
            <>
              <div className="os-section-title">Functional Strengths</div>
              <div className="os-list-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <ListCard label="Commercial Strengths"     items={intel.commercial_strengths} />
                <ListCard label="Transformation Strengths" items={intel.transformation_strengths} />
              </div>
            </>
          )}

          {(intel.evidence_gaps?.length > 0 || intel.under_positioned_assets?.length > 0) && (
            <>
              <div className="os-section-title">Diagnosis</div>
              <div className="os-list-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <ListCard label="Evidence Gaps"           items={intel.evidence_gaps}           variant="risk" />
                <ListCard label="Under-positioned Assets" items={intel.under_positioned_assets} variant="highlight" />
              </div>
            </>
          )}

          {intel.cv_improvement_recommendations?.length > 0 && (
            <>
              <div className="os-section-title">CV Improvement Recommendations</div>
              <div className="os-card">
                <ul className="os-list-items" style={{ margin: 0 }}>
                  {intel.cv_improvement_recommendations.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              </div>
            </>
          )}

          {intel.advisor_only_notes?.length > 0 && (
            <>
              <div className="os-section-title">Advisor Notes (not for client)</div>
              <div className="os-advisor-card">
                <p className="os-card-label">For your eyes only</p>
                <ul className="os-advisor-notes">
                  {intel.advisor_only_notes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

// ── Simple inline markdown renderer ──────────────────────────────────────────
// Handles ## headings and - bullet lists. No library needed.
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

function hasAny(scale) {
  if (!scale) return false
  return scale.team_size || scale.revenue_or_pnl || scale.geography || scale.stakeholders
}

function ScaleItem({ label, value }) {
  if (!value) return null
  return (
    <div className="os-scale-item">
      <p className="os-card-label">{label}</p>
      <p className="os-scale-value">{value}</p>
    </div>
  )
}

function ListCard({ label, items, variant }) {
  if (!items?.length) return null
  const cls = variant === 'risk'
    ? 'os-list-card os-list-card--risk'
    : variant === 'highlight'
    ? 'os-list-card os-list-card--highlight'
    : 'os-list-card'
  return (
    <div className={cls}>
      <p className="os-card-label">{label}</p>
      <ul className="os-list-items">
        {items.map((item, i) => <li key={i}>{item}</li>)}
      </ul>
    </div>
  )
}
