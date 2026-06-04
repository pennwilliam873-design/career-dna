import { useState, useRef, useEffect } from 'react'
import { api } from '../../apiClient'

export default function CVStudioTab({ client, onUpdate }) {
  const savedCvText  = client.profile?.cv_text?.trim() || ''
  const intel        = client.cv_intelligence
  const rawText      = client.cv_intelligence_raw
  const hasOutput    = intel || rawText
  const generatedAt  = client.cv_intelligence_generated_at
    ? new Date(client.cv_intelligence_generated_at).toLocaleString('en-GB', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null

  const [localCvText,   setLocalCvText]  = useState(savedCvText)
  const [showEditor,    setShowEditor]   = useState(!savedCvText) // open by default when empty
  const [loading,       setLoading]      = useState(false)
  const [extracting,    setExtracting]   = useState(false)
  const [saving,        setSaving]       = useState(false)
  const [error,         setError]        = useState('')
  const [extractWarn,   setExtractWarn]  = useState('')
  const fileRef = useRef(null)

  // Re-sync local text when switching to a different client
  useEffect(() => {
    const t = client.profile?.cv_text?.trim() || ''
    setLocalCvText(t)
    setShowEditor(!t)
    setExtractWarn('')
  }, [client.id])  // eslint-disable-line react-hooks/exhaustive-deps

  const isDirty = localCvText !== savedCvText

  // ── File upload ───────────────────────────────────────────────────────────

  async function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''   // allow re-selecting the same file
    setExtracting(true)
    setExtractWarn('')
    setError('')
    try {
      const result = await api.extractCvFile(client.id, file)
      setLocalCvText(result.text || '')
      if (result.warning) setExtractWarn(result.warning)
      setShowEditor(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setExtracting(false)
    }
  }

  // ── Save CV text ──────────────────────────────────────────────────────────

  async function handleSaveCvText() {
    setSaving(true)
    setError('')
    try {
      const updatedProfile = { ...client.profile, cv_text: localCvText }
      const updated = await api.updateClient(client.id, updatedProfile)
      onUpdate(updated)
      setShowEditor(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // ── Analyse ───────────────────────────────────────────────────────────────

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

  return (
    <div>
      {error && <div className="os-error">{error}</div>}

      {/* ── CV Text section ─────────────────────────────────────────────── */}
      <div style={{ marginBottom: 20 }}>

        {/* Upload row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt"
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />
          <button
            className="os-btn os-btn--secondary os-btn--sm"
            onClick={() => fileRef.current?.click()}
            disabled={extracting || loading || saving}
          >
            {extracting ? 'Extracting…' : '↑ Upload CV file'}
          </button>
          <span style={{ fontSize: 11, color: '#94a3b8' }}>PDF, DOCX, or TXT</span>
          {savedCvText && (
            <button
              className="os-btn os-btn--ghost"
              onClick={() => setShowEditor(v => !v)}
              style={{ fontSize: 12, marginLeft: 'auto' }}
            >
              {showEditor ? 'Hide CV text' : 'Edit CV text'}
            </button>
          )}
        </div>

        {/* Extraction warning */}
        {extractWarn && (
          <div className="os-raw-warning" style={{ marginBottom: 8 }}>
            {extractWarn}
          </div>
        )}

        {/* Editor / paste area */}
        {showEditor && (
          <>
            <textarea
              className="os-textarea"
              value={localCvText}
              onChange={e => { setLocalCvText(e.target.value); setExtractWarn('') }}
              placeholder="Paste the client's CV text here, or upload a file above…"
              rows={20}
              style={{ minHeight: 280, resize: 'vertical' }}
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              {isDirty && (
                <button
                  className="os-btn os-btn--primary"
                  onClick={handleSaveCvText}
                  disabled={saving || !localCvText.trim()}
                >
                  {saving ? 'Saving…' : 'Save CV Text'}
                </button>
              )}
              {isDirty && savedCvText && (
                <button
                  className="os-btn os-btn--secondary"
                  onClick={() => { setLocalCvText(savedCvText); setExtractWarn('') }}
                  disabled={saving}
                >
                  Discard changes
                </button>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── No CV saved + not editing ────────────────────────────────────── */}
      {!savedCvText && !showEditor && (
        <div className="os-generate-prompt" style={{ marginBottom: 20 }}>
          <p className="os-generate-prompt-title">No CV text saved</p>
          <p className="os-generate-prompt-body">
            Upload a PDF, DOCX, or TXT file above, or paste the CV text into the
            editor to get started.
          </p>
        </div>
      )}

      {/* ── Analyse action bar ───────────────────────────────────────────── */}
      {savedCvText && (
        <div className="os-positioning-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button
              className="os-btn os-btn--primary"
              onClick={handleAnalyse}
              disabled={loading || isDirty}
              title={isDirty ? 'Save CV text first' : undefined}
            >
              {loading ? 'Analysing CV…' : hasOutput ? 'Re-analyse CV' : 'Analyse CV'}
            </button>
            {isDirty && (
              <span style={{ fontSize: 12, color: '#b45309' }}>Save CV text first</span>
            )}
            {!isDirty && generatedAt && (
              <span className="os-positioning-meta">Last run {generatedAt}</span>
            )}
          </div>
        </div>
      )}

      {/* ── Empty analysis state ─────────────────────────────────────────── */}
      {savedCvText && !hasOutput && !loading && (
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
