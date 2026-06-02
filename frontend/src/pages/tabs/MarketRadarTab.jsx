import { useState } from 'react'
import { api } from '../../apiClient'

// ── Prefill helpers ───────────────────────────────────────────────────────────

function prefillFromCompany(company) {
  return {
    title: company.company,
    company: company.company,
    pathway: '',
    source_type: 'market_radar',
    source_section: 'target_companies',
    confidence: 'inferred',
    priority: company.priority || 'Medium',
    status: 'Monitor',
    fit_rationale: '',
    evidence: [company.why_relevant, company.signal_or_trigger].filter(Boolean).join(' — '),
    relationship_route: company.entry_route || '',
    next_action: '',
    advisor_note: '',
    sources: company.sources || [],
  }
}

function prefillFromTier1(company) {
  return {
    title: company.company,
    company: company.company,
    pathway: '',
    source_type: 'market_radar',
    source_section: 'target_companies',
    confidence: company.confidence || 'inferred',
    priority: company.priority || 'High',
    status: 'Monitor',
    fit_rationale: company.why_relevant || '',
    evidence: [company.signal_or_trigger, company.advisor_angle].filter(Boolean).join(' — '),
    relationship_route: company.entry_route || '',
    next_action: '',
    advisor_note: company.advisor_angle || '',
    sources: company.sources || [],
  }
}

function prefillFromTier2(company) {
  return {
    title: company.company,
    company: company.company,
    pathway: '',
    source_type: 'market_radar',
    source_section: 'target_companies',
    confidence: company.confidence || 'inferred',
    priority: company.priority || 'Medium',
    status: 'Monitor',
    fit_rationale: company.why_relevant || '',
    evidence: company.trigger_or_rationale || '',
    relationship_route: company.likely_role_angle || '',
    next_action: '',
    advisor_note: '',
    sources: company.sources || [],
  }
}

function prefillFromTier3(company) {
  return {
    title: company.company,
    company: company.company,
    pathway: '',
    source_type: 'market_radar',
    source_section: 'target_companies',
    confidence: 'hypothesis',
    priority: 'Low',
    status: 'Monitor',
    fit_rationale: company.why_it_may_be_relevant || '',
    evidence: company.notes || '',
    relationship_route: '',
    next_action: '',
    advisor_note: '',
    sources: [],
  }
}

function prefillFromSignal(signal) {
  return {
    title: signal.signal,
    company: signal.company || '',
    pathway: '',
    source_type: 'market_radar',
    source_section: 'market_signals',
    confidence: signal.confidence || 'hypothesis',
    priority: signal.confidence === 'verified' ? 'High' : 'Medium',
    status: 'Monitor',
    fit_rationale: '',
    evidence: signal.evidence_or_rationale || '',
    relationship_route: signal.recommended_action || '',
    next_action: '',
    advisor_note: '',
    sources: signal.sources || [],
  }
}

function prefillFromHypothesis(hypothesis) {
  return {
    title: hypothesis.hypothesis,
    company: '',
    pathway: '',
    source_type: 'market_radar',
    source_section: 'hidden_market_hypotheses',
    confidence: 'hypothesis',
    priority: hypothesis.confidence === 'High' ? 'Medium' : 'Low',
    status: 'Monitor',
    fit_rationale: hypothesis.why_client_fits || '',
    evidence: hypothesis.trigger || '',
    relationship_route: hypothesis.what_to_validate || '',
    next_action: '',
    advisor_note: '',
    sources: hypothesis.sources || [],
  }
}

function oppKey(section, title, company) {
  return `${section}|${title}|${company}`
}

// ── Tab component ─────────────────────────────────────────────────────────────

export default function MarketRadarTab({ client, onUpdate }) {
  const [loading, setLoading]               = useState(false)
  const [error, setError]                   = useState('')
  const [manualResearch, setManualResearch]  = useState('')
  const [showAllSources, setShowAllSources]  = useState(false)
  const [savingKey, setSavingKey]           = useState(null)
  const [saveError, setSaveError]           = useState('')
  const [showResearch, setShowResearch]     = useState(false)

  const radar       = client.market_radar
  const rawText     = client.market_radar_raw
  const hasOutput   = radar || rawText
  const scanWarning = client.market_radar_scan_warning
  const isDraft     = client.market_radar_is_complete === false

  const savedKeys = new Set(
    (client.opportunities || []).map(o =>
      oppKey(o.source_section, o.title, o.company)
    )
  )

  async function handleSaveTo(prefill) {
    const key = oppKey(prefill.source_section, prefill.title, prefill.company)
    setSavingKey(key)
    setSaveError('')
    try {
      const updated = await api.createOpportunity(client.id, prefill)
      onUpdate(updated)
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setSavingKey(null)
    }
  }

  const hasMinContext = !!(
    client.profile?.cv_text?.trim() ||
    client.profile?.desired_next_move?.trim() ||
    client.profile?.current_role?.trim()
  )

  const generatedAt = client.market_radar_generated_at
    ? new Date(client.market_radar_generated_at).toLocaleString('en-GB', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null

  async function handleRun() {
    setLoading(true)
    setError('')
    try {
      const updated = await api.runMarketRadar(client.id, manualResearch)
      onUpdate(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Minimum context guard ─────────────────────────────────────────────────
  if (!hasMinContext) {
    return (
      <div className="os-generate-prompt">
        <p className="os-generate-prompt-title">Complete earlier steps first</p>
        <p className="os-generate-prompt-body">
          Add a CV, current role, or desired next move in the{' '}
          <strong>Profile</strong> tab. Running{' '}
          <strong>CV Studio</strong> and <strong>Positioning</strong> first will
          produce significantly better market intelligence.
        </p>
      </div>
    )
  }

  return (
    <div>
      {error    && <div className="os-error">{error}</div>}
      {saveError && <div className="os-error">{saveError}</div>}

      {/* ── Action bar ──────────────────────────────────────────────────── */}
      <div className="os-positioning-header">
        <div>
          <button
            className="os-btn os-btn--primary"
            onClick={handleRun}
            disabled={loading}
          >
            {loading
              ? 'Running market scan…'
              : hasOutput ? 'Refresh Market Scan' : 'Run Market Scan'}
          </button>
          {generatedAt && (
            <span className="os-positioning-meta" style={{ marginLeft: 12 }}>
              Last run {generatedAt}
              {isDraft && <span className="os-draft-badge">Draft</span>}
            </span>
          )}
        </div>
      </div>

      {/* ── Manual research textarea (collapsible) ───────────────────── */}
      <div className="os-manual-research">
        <button
          className="os-research-toggle"
          onClick={() => setShowResearch(v => !v)}
          aria-expanded={showResearch}
        >
          {showResearch ? '▾ Hide research context' : '+ Add research context'}
        </button>
        {showResearch && (
          <>
            <textarea
              id="manual-research"
              className="os-manual-research-textarea"
              style={{ marginTop: 8 }}
              value={manualResearch}
              onChange={e => setManualResearch(e.target.value)}
              placeholder="Paste any research you've gathered — news articles, LinkedIn posts, board announcements, company updates. Included alongside web search results, or used alone if no search API is configured."
              rows={4}
            />
            <p className="os-manual-research-hint">
              Used in addition to web search when available, or as the sole research source if no search API is configured.
            </p>
          </>
        )}
        <p className="os-radar-disclaimer" style={{ marginTop: 6 }}>
          Signals are based on search snippets and advisor-provided context. Verify before acting.
        </p>
      </div>

      {/* ── Empty state ──────────────────────────────────────────────────── */}
      {!hasOutput && !loading && (
        <div className="os-generate-prompt" style={{ marginTop: 8 }}>
          <p className="os-generate-prompt-title">Market Radar not yet generated</p>
          <p className="os-generate-prompt-body">
            Click <strong>Run Market Scan</strong> above. The system will generate targeted
            search queries, run live web searches, and synthesise results into actionable
            market intelligence with item-level source attribution.
          </p>
        </div>
      )}

      {/* ── Scan warning banner (incomplete result or preserved previous) ── */}
      {scanWarning && (
        <div className="os-raw-warning">
          <strong>Incomplete scan.</strong> {scanWarning}
        </div>
      )}

      {/* ── Fallback warning banner ──────────────────────────────────────── */}
      {rawText && !radar && (
        <div className="os-raw-warning">
          <strong>Structured parse unavailable.</strong>{' '}
          Showing market analysis as formatted text. Click{' '}
          <strong>Refresh Market Scan</strong> to retry structured extraction.
        </div>
      )}

      {/* ── Raw markdown fallback output ────────────────────────────────── */}
      {rawText && !radar && (
        <div className="os-raw-analysis">
          <RawMarkdown text={rawText} />
        </div>
      )}

      {/* ── Structured output ────────────────────────────────────────────── */}
      {radar && (
        <>
          {/* Market Summary */}
          {radar.market_summary && (
            <div className="os-card">
              <p className="os-card-label">Market Summary</p>
              <p className="os-card-value">{radar.market_summary}</p>
            </div>
          )}

          {/* Priority Pathways */}
          {radar.priority_pathways?.length > 0 && (
            <>
              <div className="os-section-title">Priority Pathways ({radar.priority_pathways.length})</div>
              <div className="os-pathway-list">
                {radar.priority_pathways.map((pw, i) => (
                  <RadarPathwayCard key={i} pathway={pw} />
                ))}
              </div>
            </>
          )}

          {/* ── Tiered Target Companies (new records) ────────────────────── */}
          {(radar.tier1_companies?.length > 0 || radar.tier2_companies?.length > 0 || radar.tier3_companies?.length > 0) ? (
            <>
              {radar.tier1_companies?.length > 0 && (
                <>
                  <div className="os-section-title">
                    Tier 1 — Priority Targets ({radar.tier1_companies.length})
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                    {radar.tier1_companies.map((c, i) => {
                      const key = oppKey('target_companies', c.company, c.company)
                      return (
                        <Tier1Card
                          key={i}
                          company={c}
                          isSaved={savedKeys.has(key)}
                          isSaving={savingKey === key}
                          onSaveTo={() => handleSaveTo(prefillFromTier1(c))}
                        />
                      )
                    })}
                  </div>
                </>
              )}

              {radar.tier2_companies?.length > 0 && (
                <>
                  <div className="os-section-title">
                    Tier 2 — Strong Adjacent Targets ({radar.tier2_companies.length})
                  </div>
                  <div className="os-company-grid">
                    {radar.tier2_companies.map((c, i) => {
                      const key = oppKey('target_companies', c.company, c.company)
                      return (
                        <Tier2Card
                          key={i}
                          company={c}
                          isSaved={savedKeys.has(key)}
                          isSaving={savingKey === key}
                          onSaveTo={() => handleSaveTo(prefillFromTier2(c))}
                        />
                      )
                    })}
                  </div>
                </>
              )}

              {radar.tier3_companies?.length > 0 && (
                <>
                  <div className="os-section-title">
                    Tier 3 — Exploratory / Watchlist ({radar.tier3_companies.length})
                  </div>
                  <div className="os-company-grid">
                    {radar.tier3_companies.map((c, i) => {
                      const key = oppKey('target_companies', c.company, c.company)
                      return (
                        <Tier3Card
                          key={i}
                          company={c}
                          isSaved={savedKeys.has(key)}
                          isSaving={savingKey === key}
                          onSaveTo={() => handleSaveTo(prefillFromTier3(c))}
                        />
                      )
                    })}
                  </div>
                </>
              )}
            </>
          ) : radar.target_companies?.length > 0 ? (
            /* ── Legacy flat list (old records without tier data) ─────────── */
            <>
              <div className="os-section-title">Target Companies ({radar.target_companies.length})</div>
              <div className="os-company-grid">
                {radar.target_companies.map((c, i) => {
                  const key = oppKey('target_companies', c.company, c.company)
                  return (
                    <CompanyCard
                      key={i}
                      company={c}
                      isSaved={savedKeys.has(key)}
                      isSaving={savingKey === key}
                      onSaveTo={() => handleSaveTo(prefillFromCompany(c))}
                    />
                  )
                })}
              </div>
            </>
          ) : null}

          {/* Market Signals */}
          {radar.market_signals?.length > 0 && (
            <>
              <div className="os-section-title">Market Signals ({radar.market_signals.length})</div>
              {radar.market_signals.map((sig, i) => {
                const key = oppKey('market_signals', sig.signal, sig.company || '')
                return (
                  <SignalCard
                    key={i}
                    signal={sig}
                    isSaved={savedKeys.has(key)}
                    isSaving={savingKey === key}
                    onSaveTo={() => handleSaveTo(prefillFromSignal(sig))}
                  />
                )
              })}
            </>
          )}

          {/* Hidden Market Hypotheses */}
          {radar.hidden_market_hypotheses?.length > 0 && (
            <>
              <div className="os-section-title">Hidden Market Hypotheses ({radar.hidden_market_hypotheses.length})</div>
              {radar.hidden_market_hypotheses.map((h, i) => {
                const key = oppKey('hidden_market_hypotheses', h.hypothesis, '')
                return (
                  <HypothesisCard
                    key={i}
                    hypothesis={h}
                    isSaved={savedKeys.has(key)}
                    isSaving={savingKey === key}
                    onSaveTo={() => handleSaveTo(prefillFromHypothesis(h))}
                  />
                )
              })}
            </>
          )}

          {/* Relationship Strategy */}
          {radar.relationship_strategy?.length > 0 && (
            <>
              <div className="os-section-title">Relationship Strategy ({radar.relationship_strategy.length})</div>
              <div className="os-company-grid">
                {radar.relationship_strategy.map((r, i) => (
                  <RelationshipCard key={i} item={r} />
                ))}
              </div>
            </>
          )}

          {/* Next Research Actions */}
          {radar.next_research_actions?.length > 0 && (
            <>
              <div className="os-section-title">Next Research Actions</div>
              <div className="os-card">
                <ul className="os-list-items" style={{ margin: 0 }}>
                  {radar.next_research_actions.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </div>
            </>
          )}

          {/* Advisor Notes */}
          {radar.advisor_only_notes?.length > 0 && (
            <>
              <div className="os-section-title">Advisor Notes (not for client)</div>
              <div className="os-advisor-card">
                <p className="os-card-label">For your eyes only</p>
                <ul className="os-advisor-notes">
                  {radar.advisor_only_notes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
              </div>
            </>
          )}

          {/* Global sources — collapsed, secondary to item-level */}
          {radar.source_urls?.length > 0 && (
            <div className="os-sources-list">
              <button
                className="os-card-label"
                style={{ cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
                onClick={() => setShowAllSources(v => !v)}
              >
                {showAllSources ? '▾' : '▸'} All sources ({radar.source_urls.length})
              </button>
              {showAllSources && (
                <ul>
                  {radar.source_urls.map((url, i) => (
                    <li key={i}>
                      <a className="os-source-link" href={url} target="_blank" rel="noopener noreferrer">
                        {url}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── ItemSources — shared compact source list ──────────────────────────────────
// Used at the bottom of Signal, Company, and Hypothesis cards.
// Sources are numbered [1], [2], … matching superscript markers in the card body.

function ItemSources({ sources, noBorder = false }) {
  if (!sources?.length) return null
  return (
    <div className="os-item-sources" style={noBorder ? { borderTop: 'none', marginTop: 4, paddingTop: 0 } : {}}>
      {sources.map((src, i) => (
        <div key={i} className="os-item-source">
          <span className="os-item-source-num">[{i + 1}]</span>
          {src.url ? (
            <a
              className="os-source-link"
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              title={src.snippet || src.title}
            >
              {src.title || src.url}
            </a>
          ) : (
            <span className="os-item-source-title">{src.title || src.snippet}</span>
          )}
        </div>
      ))}
    </div>
  )
}

// Superscript footnote refs appended after evidence text
function FootnoteRefs({ count }) {
  if (!count) return null
  return (
    <span className="os-footnote-refs">
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className="os-footnote-ref">[{i + 1}]</span>
      ))}
    </span>
  )
}

// ── Shared save button ────────────────────────────────────────────────────────

function SaveToOppsBtn({ isSaved, isSaving, onSaveTo, compact = false }) {
  const mt = compact ? { marginTop: 0 } : {}
  if (isSaved) {
    return <div className="os-save-to-opp-btn os-save-to-opp-btn--saved" style={mt}>✓ Saved to Opportunities</div>
  }
  return (
    <button
      className={`os-save-to-opp-btn${isSaving ? ' os-save-to-opp-btn--saving' : ''}`}
      onClick={onSaveTo}
      disabled={isSaving}
      style={mt}
    >
      {isSaving ? 'Saving…' : 'Save to Opportunities'}
    </button>
  )
}

// ── Card components ───────────────────────────────────────────────────────────

function RadarPathwayCard({ pathway }) {
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
      {pathway.why_relevant && (
        <p className="os-pathway-rationale">{pathway.why_relevant}</p>
      )}
      {pathway.market_pull && (
        <>
          <span className="os-pathway-risk-label">Market Pull</span>
          <p className="os-pathway-risk">{pathway.market_pull}</p>
        </>
      )}
      {pathway.watchouts && (
        <>
          <span className="os-pathway-risk-label">Watch Out</span>
          <p className="os-pathway-risk">{pathway.watchouts}</p>
        </>
      )}
    </div>
  )
}

// ── Tier 1 Card — full detail, single-column, compact ────────────────────────

function Tier1Card({ company, isSaved, isSaving, onSaveTo }) {
  const [showSources, setShowSources] = useState(false)

  const pri = (company.priority || '').toLowerCase()
  const priCls = pri === 'high' ? 'os-priority-badge--high' : 'os-priority-badge--medium'
  const conf = (company.confidence || '').toLowerCase()
  const confCls =
    conf === 'verified'  ? 'os-confidence-badge--verified'  :
    conf === 'inferred'  ? 'os-confidence-badge--inferred'  :
                           'os-confidence-badge--hypothesis'
  const hasSources = company.sources?.length > 0

  return (
    <div className="os-company-card" style={{ padding: '12px 16px' }}>
      {/* Header: name + category + priority + confidence all on one row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
        <p className="os-company-name" style={{ margin: 0 }}>{company.company}</p>
        {company.category && (
          <span className="os-signal-type-badge">{company.category}</span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4, flexShrink: 0 }}>
          {company.priority && <span className={`os-priority-badge ${priCls}`}>{company.priority}</span>}
          {company.confidence && <span className={`os-confidence-badge ${confCls}`}>{company.confidence}</span>}
        </div>
      </div>

      {/* Why relevant — primary body */}
      {company.why_relevant && (
        <p className="os-company-detail" style={{ marginTop: 0, marginBottom: 0 }}>
          {company.why_relevant}
        </p>
      )}

      {/* Signal + Entry — compact two-column meta row */}
      {(company.signal_or_trigger || company.entry_route) && (
        <div style={{
          display: 'flex', gap: 16, flexWrap: 'wrap',
          marginTop: 6, paddingTop: 6, borderTop: '1px solid #f1f5f9',
        }}>
          {company.signal_or_trigger && (
            <span style={{ fontSize: 11, color: '#64748b', lineHeight: 1.45, flex: '1 1 40%', minWidth: 0 }}>
              <span style={{ fontWeight: 700, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8', marginRight: 3 }}>Signal</span>
              {company.signal_or_trigger}
              {hasSources && <FootnoteRefs count={company.sources.length} />}
            </span>
          )}
          {company.entry_route && (
            <span style={{ fontSize: 11, color: '#64748b', lineHeight: 1.45, flex: '1 1 40%', minWidth: 0 }}>
              <span style={{ fontWeight: 700, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8', marginRight: 3 }}>Entry</span>
              {company.entry_route}
            </span>
          )}
        </div>
      )}

      {/* Advisor angle — reduced amber infobox */}
      {company.advisor_angle && (
        <p style={{
          fontSize: 11, color: '#92400e', background: '#fffbeb',
          border: '1px solid #fde68a', borderRadius: 4,
          padding: '3px 8px', margin: '6px 0 0', lineHeight: 1.45,
        }}>
          {company.advisor_angle}
        </p>
      )}

      {/* Footer: sources toggle on left, save button on right */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginTop: 8, paddingTop: 6, borderTop: '1px solid #f1f5f9', gap: 8,
      }}>
        {hasSources ? (
          <button className="os-opp-sources-toggle" onClick={() => setShowSources(v => !v)}>
            {showSources ? '▾' : '▸'} {company.sources.length} source{company.sources.length > 1 ? 's' : ''}
          </button>
        ) : <span />}
        <SaveToOppsBtn isSaved={isSaved} isSaving={isSaving} onSaveTo={onSaveTo} compact />
      </div>

      {showSources && <ItemSources sources={company.sources} noBorder />}
    </div>
  )
}

// ── Tier 2 Card — concise ─────────────────────────────────────────────────────

function Tier2Card({ company, isSaved, isSaving, onSaveTo }) {
  const [showSources, setShowSources] = useState(false)

  const pri = (company.priority || '').toLowerCase()
  const priCls =
    pri === 'high'   ? 'os-priority-badge--high'   :
    pri === 'medium' ? 'os-priority-badge--medium'  :
                       'os-priority-badge--low'
  const hasSources = company.sources?.length > 0

  return (
    <div className="os-company-card" style={{ padding: '11px 14px' }}>
      {/* Header: name + priority */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 6, marginBottom: 2 }}>
        <p className="os-company-name" style={{ margin: 0, fontSize: 13 }}>{company.company}</p>
        {company.priority && <span className={`os-priority-badge ${priCls}`} style={{ flexShrink: 0 }}>{company.priority}</span>}
      </div>

      {/* Category · role angle — single muted line */}
      {(company.category || company.likely_role_angle) && (
        <p style={{ fontSize: 11, color: '#94a3b8', margin: '0 0 4px', fontWeight: 500 }}>
          {[company.category, company.likely_role_angle].filter(Boolean).join(' · ')}
        </p>
      )}

      {/* Why relevant */}
      {company.why_relevant && (
        <p className="os-company-detail" style={{ marginTop: 0, marginBottom: 0 }}>{company.why_relevant}</p>
      )}

      {/* Trigger / rationale */}
      {company.trigger_or_rationale && (
        <p className="os-company-detail os-company-detail--muted" style={{ marginTop: 3, fontSize: 11 }}>
          {company.trigger_or_rationale}
          {hasSources && <FootnoteRefs count={company.sources.length} />}
        </p>
      )}

      {/* Footer */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginTop: 7, paddingTop: 5, borderTop: '1px solid #f1f5f9', gap: 8,
      }}>
        {hasSources ? (
          <button className="os-opp-sources-toggle" onClick={() => setShowSources(v => !v)}>
            {showSources ? '▾' : '▸'} {company.sources.length} source{company.sources.length > 1 ? 's' : ''}
          </button>
        ) : <span />}
        <SaveToOppsBtn isSaved={isSaved} isSaving={isSaving} onSaveTo={onSaveTo} compact />
      </div>

      {showSources && <ItemSources sources={company.sources} noBorder />}
    </div>
  )
}

// ── Tier 3 Card — compact watchlist ──────────────────────────────────────────

function Tier3Card({ company, isSaved, isSaving, onSaveTo }) {
  const conf = (company.confidence || '').toLowerCase()
  const confCls =
    conf === 'inferred'  ? 'os-confidence-badge--inferred'  :
                           'os-confidence-badge--hypothesis'

  return (
    <div className="os-company-card" style={{ padding: '9px 12px' }}>
      {/* Name + confidence on one row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, marginBottom: 3 }}>
        <p className="os-company-name" style={{ margin: 0, fontSize: 12 }}>{company.company}</p>
        {company.confidence && (
          <span className={`os-confidence-badge ${confCls}`} style={{ flexShrink: 0 }}>{company.confidence}</span>
        )}
      </div>

      {/* Category · relevance on one line */}
      {(company.category || company.why_it_may_be_relevant) && (
        <p style={{ fontSize: 11, color: '#64748b', margin: 0, lineHeight: 1.4 }}>
          {company.category && (
            <span style={{ fontWeight: 600, color: '#475569' }}>{company.category}</span>
          )}
          {company.category && company.why_it_may_be_relevant && ' · '}
          {company.why_it_may_be_relevant}
        </p>
      )}

      {/* Notes */}
      {company.notes && (
        <p style={{ fontSize: 10, color: '#94a3b8', margin: '2px 0 0', fontStyle: 'italic', lineHeight: 1.3 }}>
          {company.notes}
        </p>
      )}

      <SaveToOppsBtn isSaved={isSaved} isSaving={isSaving} onSaveTo={onSaveTo} compact />
    </div>
  )
}

// ── Legacy Tier (flat target_companies for old records) ───────────────────────

function CompanyCard({ company, isSaved, isSaving, onSaveTo }) {
  const pri = (company.priority || '').toLowerCase()
  const priCls =
    pri === 'high'   ? 'os-priority-badge--high'   :
    pri === 'medium' ? 'os-priority-badge--medium'  :
                       'os-priority-badge--low'
  const hasSources = company.sources?.length > 0

  return (
    <div className="os-company-card">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
        <p className="os-company-name">{company.company}</p>
        {company.priority && (
          <span className={`os-priority-badge ${priCls}`}>{company.priority}</span>
        )}
      </div>
      {company.category && (
        <span className="os-signal-type-badge" style={{ marginBottom: 8, display: 'inline-block' }}>
          {company.category}
        </span>
      )}
      {company.why_relevant && (
        <p className="os-company-detail">{company.why_relevant}</p>
      )}
      {company.signal_or_trigger && (
        <p className="os-company-detail os-company-detail--muted">
          <strong>Signal:</strong>{' '}
          {company.signal_or_trigger}
          {hasSources && <FootnoteRefs count={company.sources.length} />}
        </p>
      )}
      {company.entry_route && (
        <p className="os-company-detail os-company-detail--muted">
          <strong>Entry:</strong> {company.entry_route}
        </p>
      )}
      <ItemSources sources={company.sources} />
      <SaveToOppsBtn isSaved={isSaved} isSaving={isSaving} onSaveTo={onSaveTo} />
    </div>
  )
}

function SignalCard({ signal, isSaved, isSaving, onSaveTo }) {
  const conf = (signal.confidence || '').toLowerCase()
  const confCls =
    conf === 'verified'   ? 'os-confidence-badge--verified'   :
    conf === 'inferred'   ? 'os-confidence-badge--inferred'   :
                            'os-confidence-badge--hypothesis'
  const sigType = (signal.signal_type || '').replace(/_/g, ' ')
  const hasSources = signal.sources?.length > 0

  return (
    <div className="os-signal-card">
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
        <span className="os-signal-type-badge">{sigType}</span>
        {signal.confidence && (
          <span className={`os-confidence-badge ${confCls}`}>{signal.confidence}</span>
        )}
      </div>
      <p className="os-company-name" style={{ fontSize: 14, marginBottom: 4 }}>{signal.signal}</p>
      {signal.company && (
        <p className="os-company-detail os-company-detail--muted">{signal.company}</p>
      )}
      {signal.evidence_or_rationale && (
        <p className="os-company-detail">
          {signal.evidence_or_rationale}
          {hasSources && <FootnoteRefs count={signal.sources.length} />}
        </p>
      )}
      {signal.recommended_action && (
        <p className="os-company-detail" style={{ color: '#0f172a', fontWeight: 500, marginTop: 6 }}>
          → {signal.recommended_action}
        </p>
      )}
      <ItemSources sources={signal.sources} />
      <SaveToOppsBtn isSaved={isSaved} isSaving={isSaving} onSaveTo={onSaveTo} />
    </div>
  )
}

function HypothesisCard({ hypothesis, isSaved, isSaving, onSaveTo }) {
  const conf = (hypothesis.confidence || '').toLowerCase()
  const confCls =
    conf === 'high'   ? 'os-fit-badge--high'    :
    conf === 'medium' ? 'os-fit-badge--medium'   :
                        'os-fit-badge--stretch'
  const hasSources = hypothesis.sources?.length > 0

  return (
    <div className="os-hypothesis-card">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
        <p className="os-company-name" style={{ fontSize: 14 }}>{hypothesis.hypothesis}</p>
        {hypothesis.confidence && (
          <span className={`os-fit-badge ${confCls}`} style={{ flexShrink: 0 }}>
            {hypothesis.confidence}
          </span>
        )}
      </div>
      {hypothesis.trigger && (
        <p className="os-company-detail os-company-detail--muted">
          <strong>Trigger:</strong>{' '}
          {hypothesis.trigger}
          {hasSources && <FootnoteRefs count={hypothesis.sources.length} />}
        </p>
      )}
      {hypothesis.why_client_fits && (
        <p className="os-company-detail">
          <strong>Why this client:</strong> {hypothesis.why_client_fits}
        </p>
      )}
      {hypothesis.what_to_validate && (
        <p className="os-company-detail os-company-detail--muted">
          <strong>Validate by:</strong> {hypothesis.what_to_validate}
        </p>
      )}
      <ItemSources sources={hypothesis.sources} />
      <SaveToOppsBtn isSaved={isSaved} isSaving={isSaving} onSaveTo={onSaveTo} />
    </div>
  )
}

function RelationshipCard({ item }) {
  return (
    <div className="os-company-card">
      <p className="os-company-name">{item.target}</p>
      {item.relationship_angle && (
        <p className="os-company-detail os-company-detail--muted">{item.relationship_angle}</p>
      )}
      {item.suggested_conversation && (
        <p className="os-company-detail" style={{ fontStyle: 'italic', marginTop: 6 }}>
          "{item.suggested_conversation}"
        </p>
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
      elements.push(<p key={key++} className="os-raw-heading">{trimmed.slice(3)}</p>)
    } else if (trimmed.startsWith('### ')) {
      flushBullets()
      elements.push(<p key={key++} className="os-raw-heading" style={{ fontSize: 13 }}>{trimmed.slice(4)}</p>)
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
