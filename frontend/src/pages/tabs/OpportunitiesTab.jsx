import { useState } from 'react'
import { api } from '../../apiClient'

const STATUS_ORDER = [
  'Monitor',
  'Research further',
  'Warm intro needed',
  'Outreach drafted',
  'Contacted',
  'Conversation held',
  'Paused',
  'Rejected',
]

const PRIORITY_RANK = { High: 0, Medium: 1, Low: 2 }

const EMPTY_OPP = {
  title: '',
  company: '',
  pathway: '',
  source_type: 'manual',
  source_section: '',
  confidence: 'hypothesis',
  priority: 'Medium',
  status: 'Monitor',
  fit_rationale: '',
  evidence: '',
  relationship_route: '',
  next_action: '',
  advisor_note: '',
  sources: [],
}

export default function OpportunitiesTab({ client, onUpdate }) {
  const opps = client.opportunities || []

  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingId, setEditingId]     = useState(null)
  const [priorityFilter, setFilter]   = useState('All')

  const filtered = priorityFilter === 'All'
    ? opps
    : opps.filter(o => o.priority === priorityFilter)

  const highCount = opps.filter(o => o.priority === 'High').length

  const groups = STATUS_ORDER
    .map(status => ({
      status,
      items: filtered
        .filter(o => o.status === status)
        .sort((a, b) => (PRIORITY_RANK[a.priority] ?? 1) - (PRIORITY_RANK[b.priority] ?? 1)),
    }))
    .filter(g => g.items.length > 0)

  async function handleCreate(formData) {
    setLoading(true)
    setError('')
    try {
      const updated = await api.createOpportunity(client.id, formData)
      onUpdate(updated)
      setShowAddForm(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleUpdate(oppId, formData) {
    setLoading(true)
    setError('')
    try {
      const updated = await api.updateOpportunity(client.id, oppId, formData)
      onUpdate(updated)
      setEditingId(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(oppId) {
    if (!window.confirm('Remove this opportunity?')) return
    setLoading(true)
    setError('')
    try {
      const updated = await api.deleteOpportunity(client.id, oppId)
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

      {/* ── Summary line ─────────────────────────────────────────────────── */}
      {opps.length > 0 && (
        <p className="os-opp-summary-line">
          {opps.length} {opps.length === 1 ? 'opportunity' : 'opportunities'}
          {highCount > 0 && ` · ${highCount} High priority`}
        </p>
      )}

      {/* ── Action bar ──────────────────────────────────────────────────── */}
      <div className="os-positioning-header" style={{ marginBottom: 20 }}>
        <button
          className="os-btn os-btn--primary"
          onClick={() => { setShowAddForm(v => !v); setEditingId(null) }}
          disabled={loading}
        >
          {showAddForm ? 'Cancel' : '+ Add Manual Opportunity'}
        </button>
        <div className="os-opp-filters">
          {['All', 'High', 'Medium', 'Low'].map(p => (
            <button
              key={p}
              className={`os-opp-filter-btn${priorityFilter === p ? ' os-opp-filter-btn--active' : ''}`}
              onClick={() => setFilter(p)}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* ── Add form ────────────────────────────────────────────────────── */}
      {showAddForm && (
        <OpportunityForm
          initialData={EMPTY_OPP}
          onSave={handleCreate}
          onCancel={() => setShowAddForm(false)}
          loading={loading}
        />
      )}

      {/* ── Empty state ──────────────────────────────────────────────────── */}
      {opps.length === 0 && !showAddForm && (
        <div className="os-generate-prompt">
          <p className="os-generate-prompt-title">No opportunities yet</p>
          <p className="os-generate-prompt-body">
            Add opportunities manually above, or save items from{' '}
            <strong>Market Radar</strong> using the "Save to Opportunities"
            button on company, signal, and hypothesis cards.
          </p>
        </div>
      )}

      {/* ── Status groups ────────────────────────────────────────────────── */}
      {groups.map(group => (
        <div key={group.status} className="os-opp-group">
          <div className="os-opp-group-header">
            <span className="os-opp-group-title">{group.status}</span>
            <span className="os-opp-group-count">{group.items.length}</span>
          </div>
          <div className="os-opp-cards">
            {group.items.map(opp =>
              editingId === opp.id ? (
                <OpportunityForm
                  key={opp.id}
                  initialData={opp}
                  onSave={data => handleUpdate(opp.id, data)}
                  onCancel={() => setEditingId(null)}
                  loading={loading}
                />
              ) : (
                <OpportunityCard
                  key={opp.id}
                  opp={opp}
                  onEdit={() => { setEditingId(opp.id); setShowAddForm(false) }}
                  onDelete={() => handleDelete(opp.id)}
                />
              )
            )}
          </div>
        </div>
      ))}

      {/* Filtered-out message */}
      {opps.length > 0 && filtered.length === 0 && (
        <p style={{ color: '#94a3b8', fontSize: 13, textAlign: 'center', marginTop: 32 }}>
          No {priorityFilter} priority opportunities.
        </p>
      )}
    </div>
  )
}

// ── OpportunityCard ───────────────────────────────────────────────────────────

function OpportunityCard({ opp, onEdit, onDelete }) {
  const [showDetails, setShowDetails] = useState(false)
  const [showSources, setShowSources] = useState(false)

  const priCls =
    opp.priority === 'High' ? 'os-priority-badge--high'   :
    opp.priority === 'Low'  ? 'os-priority-badge--low'    :
                              'os-priority-badge--medium'

  const confCls =
    opp.confidence === 'verified'  ? 'os-confidence-badge--verified'  :
    opp.confidence === 'inferred'  ? 'os-confidence-badge--inferred'  :
                                     'os-confidence-badge--hypothesis'

  const hasSecondary = !!(opp.evidence || opp.relationship_route || opp.advisor_note || opp.sources?.length)
  const hasSubheader = !!(opp.company || opp.confidence || (opp.source_type === 'market_radar' && opp.source_section))

  return (
    <div className="os-opp-card" style={{ gap: 0, padding: '12px 16px' }}>

      {/* ── Header: title + priority badge + Edit + Delete ─────────────── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: hasSubheader ? 4 : 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            {opp.priority && <span className={`os-priority-badge ${priCls}`}>{opp.priority}</span>}
            <p className="os-opp-card-title" style={{ margin: 0 }}>{opp.title || '(Untitled)'}</p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 5, flexShrink: 0, alignItems: 'center' }}>
          <button
            className="os-btn os-btn--secondary os-btn--sm"
            onClick={onEdit}
            style={{ padding: '3px 10px' }}
          >
            Edit
          </button>
          <button
            className="os-btn os-btn--danger os-btn--sm os-opp-delete-btn"
            onClick={onDelete}
            style={{ padding: '3px 10px' }}
          >
            ×
          </button>
        </div>
      </div>

      {/* ── Sub-header: company · confidence · source tag ──────────────── */}
      {hasSubheader && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
          {opp.company && (
            <span style={{ fontSize: 12, color: '#64748b', fontWeight: 500 }}>{opp.company}</span>
          )}
          {opp.confidence && (
            <span className={`os-confidence-badge ${confCls}`}>{opp.confidence}</span>
          )}
          {opp.source_type === 'market_radar' && opp.source_section && (
            <span style={{ fontSize: 10, color: '#94a3b8', fontStyle: 'italic' }}>
              from Market Radar · {opp.source_section.replace(/_/g, ' ')}
            </span>
          )}
        </div>
      )}

      {/* ── Fit rationale — always visible ──────────────────────────────── */}
      {opp.fit_rationale && (
        <p className="os-opp-field-value" style={{ marginBottom: 0 }}>
          {opp.fit_rationale}
        </p>
      )}

      {/* ── Next action — elevated strip, always visible ─────────────────── */}
      {opp.next_action && (
        <div className="os-opp-next-action" style={{ marginTop: 8 }}>
          <span className="os-opp-meta-label">Next Action</span>
          <span className="os-opp-next-action-text">{opp.next_action}</span>
        </div>
      )}

      {/* ── Secondary details — collapsed by default ────────────────────── */}
      {hasSecondary && (
        <div style={{ marginTop: 8 }}>
          <button
            className="os-opp-sources-toggle"
            onClick={() => setShowDetails(v => !v)}
          >
            {showDetails ? '▾ Less' : '▸ Details'}
          </button>

          {showDetails && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 6 }}>
              {opp.evidence && (
                <p style={{ fontSize: 12, color: '#64748b', lineHeight: 1.45, margin: 0 }}>
                  <span className="os-opp-meta-label">Evidence</span>
                  {opp.evidence}
                </p>
              )}
              {opp.relationship_route && (
                <p style={{ fontSize: 12, color: '#475569', lineHeight: 1.45, margin: 0 }}>
                  <span className="os-opp-meta-label">Route</span>
                  {opp.relationship_route}
                </p>
              )}
              {opp.advisor_note && (
                <p className="os-opp-advisor-note" style={{ fontSize: 11, padding: '3px 8px' }}>
                  {opp.advisor_note}
                </p>
              )}
              {opp.sources?.length > 0 && (
                <div>
                  <button
                    className="os-opp-sources-toggle"
                    onClick={() => setShowSources(v => !v)}
                  >
                    {showSources ? '▾' : '▸'} {opp.sources.length} source{opp.sources.length > 1 ? 's' : ''}
                  </button>
                  {showSources && opp.sources.map((src, i) => (
                    <div key={i} className="os-item-source" style={{ marginTop: 3 }}>
                      <span className="os-item-source-num">[{i + 1}]</span>
                      {src.url ? (
                        <a className="os-source-link" href={src.url} target="_blank" rel="noopener noreferrer"
                           title={src.snippet || src.title}>
                          {src.title || src.url}
                        </a>
                      ) : (
                        <span className="os-item-source-title">{src.title || src.snippet}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

    </div>
  )
}

// ── OpportunityForm ───────────────────────────────────────────────────────────

function OpportunityForm({ initialData, onSave, onCancel, loading }) {
  const [form, setForm] = useState({ ...EMPTY_OPP, ...initialData })

  function set(key, val) {
    setForm(f => ({ ...f, [key]: val }))
  }

  return (
    <div className="os-opp-form">
      <div className="os-opp-form-grid">

        <div className="os-form-field os-form-field--full">
          <label className="os-label">Title *</label>
          <input
            className="os-input"
            value={form.title}
            onChange={e => set('title', e.target.value)}
            placeholder="e.g. COO at Apax portfolio company"
          />
        </div>

        <div className="os-form-field">
          <label className="os-label">Company</label>
          <input
            className="os-input"
            value={form.company}
            onChange={e => set('company', e.target.value)}
            placeholder="Company name"
          />
        </div>

        <div className="os-form-field">
          <label className="os-label">Pathway</label>
          <input
            className="os-input"
            value={form.pathway}
            onChange={e => set('pathway', e.target.value)}
            placeholder="e.g. PE portfolio COO"
          />
        </div>

        <div className="os-form-field">
          <label className="os-label">Status</label>
          <select className="os-input" value={form.status} onChange={e => set('status', e.target.value)}>
            {STATUS_ORDER.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div className="os-form-field">
          <label className="os-label">Priority</label>
          <select className="os-input" value={form.priority} onChange={e => set('priority', e.target.value)}>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </div>

        <div className="os-form-field">
          <label className="os-label">Confidence</label>
          <select className="os-input" value={form.confidence} onChange={e => set('confidence', e.target.value)}>
            <option value="verified">Verified</option>
            <option value="inferred">Inferred</option>
            <option value="hypothesis">Hypothesis</option>
          </select>
        </div>

        <div className="os-form-field os-form-field--full">
          <label className="os-label">Fit Rationale</label>
          <textarea
            className="os-textarea"
            value={form.fit_rationale}
            onChange={e => set('fit_rationale', e.target.value)}
            rows={2}
            placeholder="Why this client fits this opportunity"
          />
        </div>

        <div className="os-form-field os-form-field--full">
          <label className="os-label">Evidence</label>
          <textarea
            className="os-textarea"
            value={form.evidence}
            onChange={e => set('evidence', e.target.value)}
            rows={2}
            placeholder="Market evidence or supporting signals"
          />
        </div>

        <div className="os-form-field os-form-field--full">
          <label className="os-label">Relationship Route</label>
          <input
            className="os-input"
            value={form.relationship_route}
            onChange={e => set('relationship_route', e.target.value)}
            placeholder="How to approach or entry route"
          />
        </div>

        <div className="os-form-field os-form-field--full">
          <label className="os-label">Next Action</label>
          <input
            className="os-input"
            value={form.next_action}
            onChange={e => set('next_action', e.target.value)}
            placeholder="Immediate next step"
          />
        </div>

        <div className="os-form-field os-form-field--full">
          <label className="os-label">Advisor Note (not for client)</label>
          <textarea
            className="os-textarea"
            value={form.advisor_note}
            onChange={e => set('advisor_note', e.target.value)}
            rows={2}
            placeholder="Internal note for advisor only"
          />
        </div>

      </div>

      <div className="os-form-actions">
        <button
          className="os-btn os-btn--primary"
          onClick={() => onSave(form)}
          disabled={loading || !form.title.trim()}
        >
          {loading ? 'Saving…' : 'Save'}
        </button>
        <button className="os-btn os-btn--secondary" onClick={onCancel} disabled={loading}>
          Cancel
        </button>
      </div>
    </div>
  )
}
