import { useState } from 'react'
import { api } from '../../apiClient'

const CONTACT_STATUSES = [
  'Not contacted',
  'Warm path identified',
  'Contacted',
  'Responded',
  'Parked',
]

const EMPTY_CONTACT = {
  name: '', title: '', company: '',
  linkedin_url: '', source_url: '',
  related_opportunity_id: '',
  why_relevant: '', suggested_angle: '',
  confidence: 'Medium', status: 'Not contacted', notes: '',
}

export default function TargetContactsTab({ client, onUpdate }) {
  const contacts     = client.target_contacts || []
  const opportunities = client.opportunities  || []

  const [loading,         setLoading]        = useState(false)
  const [saving,          setSaving]          = useState(false)
  const [error,           setError]           = useState('')
  const [searchMessage,   setSearchMessage]   = useState('')

  // Search panel
  const [showSearch,      setShowSearch]      = useState(false)
  const [searchCompany,   setSearchCompany]   = useState('')
  const [searchOppId,     setSearchOppId]     = useState('')
  const [searchRole,      setSearchRole]      = useState('')
  const [searchResults,   setSearchResults]   = useState(null)   // null = not searched yet

  // Add / edit
  const [showAddForm,     setShowAddForm]     = useState(false)
  const [editingId,       setEditingId]       = useState(null)

  // ── Derive company from selected opportunity ──────────────────────────────

  function handleOppSelect(oppId) {
    setSearchOppId(oppId)
    if (oppId) {
      const opp = opportunities.find(o => o.id === oppId)
      if (opp?.company && !searchCompany) setSearchCompany(opp.company)
    }
  }

  // ── Search ────────────────────────────────────────────────────────────────

  async function handleSearch() {
    if (!searchCompany.trim()) { setError('Enter a company name to search.'); return }
    setLoading(true); setError(''); setSearchResults(null); setSearchMessage('')
    try {
      const res = await api.searchTargetContacts(client.id, {
        company: searchCompany.trim(),
        related_opportunity_id: searchOppId,
        role_context: searchRole.trim(),
        search_focus: '',
      })
      setSearchResults(res.contacts || [])
      if (res.message) setSearchMessage(res.message)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // ── Save a suggested contact ──────────────────────────────────────────────

  async function handleSaveSuggested(suggestion) {
    setSaving(true); setError('')
    try {
      const payload = {
        ...EMPTY_CONTACT,
        name:             suggestion.name,
        title:            suggestion.title,
        company:          suggestion.company,
        linkedin_url:     suggestion.linkedin_url,
        source_url:       suggestion.source_url,
        why_relevant:     suggestion.why_relevant,
        suggested_angle:  suggestion.suggested_angle,
        confidence:       suggestion.confidence,
        related_opportunity_id: searchOppId,
      }
      const updated = await api.createTargetContact(client.id, payload)
      onUpdate(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // ── CRUD ──────────────────────────────────────────────────────────────────

  async function handleCreate(formData) {
    setSaving(true); setError('')
    try {
      const updated = await api.createTargetContact(client.id, formData)
      onUpdate(updated); setShowAddForm(false)
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  async function handleUpdate(contactId, formData) {
    setSaving(true); setError('')
    try {
      const updated = await api.updateTargetContact(client.id, contactId, formData)
      onUpdate(updated); setEditingId(null)
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  async function handleStatusChange(contact, newStatus) {
    setSaving(true); setError('')
    try {
      const updated = await api.updateTargetContact(client.id, contact.id, {
        ...contact, status: newStatus,
      })
      onUpdate(updated)
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  async function handleDelete(contactId) {
    if (!window.confirm('Remove this contact?')) return
    setSaving(true); setError('')
    try {
      const updated = await api.deleteTargetContact(client.id, contactId)
      onUpdate(updated)
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  // ── Saved contacts already match suggestion? ─────────────────────────────

  const savedKeys = new Set(contacts.map(c => `${c.name}|${c.company}`.toLowerCase()))
  function isSaved(s) {
    return savedKeys.has(`${s.name}|${s.company}`.toLowerCase())
  }

  // ── Group saved contacts by company ──────────────────────────────────────

  const grouped = contacts.reduce((acc, c) => {
    const key = c.company || '(No company)'
    if (!acc[key]) acc[key] = []
    acc[key].push(c)
    return acc
  }, {})

  const confRank = { High: 0, Medium: 1, Low: 2 }
  const companies = Object.keys(grouped).sort()

  return (
    <div>
      {error && <div className="os-error">{error}</div>}

      {/* ── Action bar ──────────────────────────────────────────────────── */}
      <div className="os-positioning-header" style={{ marginBottom: 16 }}>
        <button
          className={`os-btn ${showSearch ? 'os-btn--secondary' : 'os-btn--primary'}`}
          onClick={() => { setShowSearch(v => !v); setSearchResults(null); setError('') }}
          disabled={loading || saving}
        >
          {showSearch ? 'Close Search' : '🔍 Find Contacts'}
        </button>
        <button
          className="os-btn os-btn--secondary"
          onClick={() => { setShowAddForm(v => !v); setEditingId(null) }}
          disabled={loading || saving}
        >
          {showAddForm ? 'Cancel' : '+ Add Manually'}
        </button>
      </div>

      {/* ── Search panel ────────────────────────────────────────────────── */}
      {showSearch && (
        <div className="os-opp-form" style={{ marginBottom: 20 }}>
          <div className="os-opp-form-grid">
            <div className="os-form-field">
              <label className="os-label">Company *</label>
              <input
                className="os-input"
                value={searchCompany}
                onChange={e => setSearchCompany(e.target.value)}
                placeholder="e.g. Apax Partners"
              />
            </div>
            <div className="os-form-field">
              <label className="os-label">Related Opportunity</label>
              <select
                className="os-input"
                value={searchOppId}
                onChange={e => handleOppSelect(e.target.value)}
              >
                <option value="">— none —</option>
                {opportunities.map(o => (
                  <option key={o.id} value={o.id}>{o.title || o.company}</option>
                ))}
              </select>
            </div>
            <div className="os-form-field os-form-field--full">
              <label className="os-label">Role context (optional)</label>
              <input
                className="os-input"
                value={searchRole}
                onChange={e => setSearchRole(e.target.value)}
                placeholder="e.g. COO, Chief Technology Officer, Operations"
              />
            </div>
          </div>
          <div className="os-form-actions">
            <button
              className="os-btn os-btn--primary"
              onClick={handleSearch}
              disabled={loading || !searchCompany.trim()}
            >
              {loading ? 'Searching…' : 'Find Contacts'}
            </button>
          </div>
        </div>
      )}

      {/* ── Search results ───────────────────────────────────────────────── */}
      {searchResults !== null && (
        <div style={{ marginBottom: 24 }}>
          {searchMessage && (
            <div className="os-raw-warning" style={{ marginBottom: 12 }}>
              {searchMessage}
            </div>
          )}
          {searchResults.length === 0 ? (
            <div className="os-generate-prompt" style={{ padding: '14px 18px' }}>
              <p className="os-generate-prompt-title">No contacts found</p>
              <p className="os-generate-prompt-body">
                Try a different company name or role context, or add contacts manually.
              </p>
            </div>
          ) : (
            <>
              <div className="os-section-title">
                Search Results — {searchResults.length} suggested contact{searchResults.length !== 1 ? 's' : ''}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {searchResults.map((s, i) => (
                  <SuggestedContactCard
                    key={i}
                    contact={s}
                    isSaved={isSaved(s)}
                    isSaving={saving}
                    onSave={() => handleSaveSuggested(s)}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Add form ────────────────────────────────────────────────────── */}
      {showAddForm && (
        <ContactForm
          initialData={{ ...EMPTY_CONTACT }}
          opportunities={opportunities}
          onSave={handleCreate}
          onCancel={() => setShowAddForm(false)}
          loading={saving}
        />
      )}

      {/* ── Empty state ──────────────────────────────────────────────────── */}
      {contacts.length === 0 && !showAddForm && searchResults === null && (
        <div className="os-generate-prompt">
          <p className="os-generate-prompt-title">No target contacts yet</p>
          <p className="os-generate-prompt-body">
            Use <strong>Find Contacts</strong> to search for real people at target companies,
            or <strong>Add Manually</strong> to record a contact you already know.
          </p>
        </div>
      )}

      {/* ── Saved contacts grouped by company ───────────────────────────── */}
      {companies.map(company => (
        <div key={company} className="os-opp-group">
          <div className="os-opp-group-header">
            <span className="os-opp-group-title">{company}</span>
            <span className="os-opp-group-count">{grouped[company].length}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[...grouped[company]]
              .sort((a, b) => (confRank[a.confidence] ?? 1) - (confRank[b.confidence] ?? 1))
              .map(contact =>
                editingId === contact.id ? (
                  <ContactForm
                    key={contact.id}
                    initialData={contact}
                    opportunities={opportunities}
                    onSave={data => handleUpdate(contact.id, data)}
                    onCancel={() => setEditingId(null)}
                    loading={saving}
                  />
                ) : (
                  <ContactCard
                    key={contact.id}
                    contact={contact}
                    onEdit={() => { setEditingId(contact.id); setShowAddForm(false) }}
                    onDelete={() => handleDelete(contact.id)}
                    onStatusChange={newStatus => handleStatusChange(contact, newStatus)}
                    saving={saving}
                  />
                )
              )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── SuggestedContactCard ──────────────────────────────────────────────────────

function SuggestedContactCard({ contact, isSaved, isSaving, onSave }) {
  const confCls =
    contact.confidence === 'High'   ? 'os-priority-badge--high'   :
    contact.confidence === 'Medium' ? 'os-priority-badge--medium'  :
                                      'os-priority-badge--low'

  return (
    <div className="os-opp-card" style={{ gap: 0, padding: '11px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span className={`os-priority-badge ${confCls}`}>{contact.confidence}</span>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>{contact.name}</span>
            {contact.title && (
              <span style={{ fontSize: 12, color: '#64748b' }}>— {contact.title}</span>
            )}
          </div>
        </div>
        {isSaved ? (
          <span style={{ fontSize: 11, color: '#15803d', fontWeight: 600, flexShrink: 0 }}>✓ Saved</span>
        ) : (
          <button
            className="os-save-to-opp-btn"
            style={{ marginTop: 0, flexShrink: 0 }}
            onClick={onSave}
            disabled={isSaving}
          >
            {isSaving ? 'Saving…' : 'Save Contact'}
          </button>
        )}
      </div>

      {contact.why_relevant && (
        <p style={{ fontSize: 12, color: '#334155', lineHeight: 1.45, margin: '0 0 3px' }}>
          {contact.why_relevant}
        </p>
      )}
      {contact.suggested_angle && (
        <p style={{ fontSize: 11, color: '#64748b', lineHeight: 1.4, margin: 0 }}>
          <span style={{ fontWeight: 700, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8', marginRight: 3 }}>Angle</span>
          {contact.suggested_angle}
        </p>
      )}
      {(contact.linkedin_url || contact.source_url) && (
        <div style={{ marginTop: 4, display: 'flex', gap: 10 }}>
          {contact.linkedin_url && (
            <a
              href={contact.linkedin_url}
              target="_blank"
              rel="noopener noreferrer"
              className="os-source-link"
              style={{ fontSize: 11 }}
            >
              LinkedIn
            </a>
          )}
          {contact.source_url && !contact.linkedin_url && (
            <a
              href={contact.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="os-source-link"
              style={{ fontSize: 11 }}
            >
              Source
            </a>
          )}
        </div>
      )}
    </div>
  )
}

// ── ContactCard ───────────────────────────────────────────────────────────────

function ContactCard({ contact, onEdit, onDelete, onStatusChange, saving }) {
  const confCls =
    contact.confidence === 'High'   ? 'os-priority-badge--high'   :
    contact.confidence === 'Medium' ? 'os-priority-badge--medium'  :
                                      'os-priority-badge--low'

  return (
    <div className="os-opp-card" style={{ gap: 0, padding: '11px 14px' }}>
      {/* Header: name + confidence + Edit/Delete */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 3 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span className={`os-priority-badge ${confCls}`}>{contact.confidence}</span>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>{contact.name || '(No name)'}</span>
            {contact.title && (
              <span style={{ fontSize: 12, color: '#64748b' }}>— {contact.title}</span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 5, flexShrink: 0 }}>
          <button
            className="os-btn os-btn--secondary os-btn--sm"
            onClick={onEdit}
            style={{ padding: '3px 10px' }}
            disabled={saving}
          >
            Edit
          </button>
          <button
            className="os-btn os-btn--danger os-btn--sm os-opp-delete-btn"
            onClick={onDelete}
            style={{ padding: '3px 10px' }}
            disabled={saving}
          >
            ×
          </button>
        </div>
      </div>

      {/* Why relevant + angle */}
      {contact.why_relevant && (
        <p style={{ fontSize: 12, color: '#334155', lineHeight: 1.45, margin: '0 0 3px' }}>
          {contact.why_relevant}
        </p>
      )}
      {contact.suggested_angle && (
        <p style={{ fontSize: 11, color: '#64748b', lineHeight: 1.4, margin: '0 0 5px' }}>
          <span style={{ fontWeight: 700, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8', marginRight: 3 }}>Angle</span>
          {contact.suggested_angle}
        </p>
      )}

      {/* Links */}
      {(contact.linkedin_url || contact.source_url) && (
        <div style={{ display: 'flex', gap: 10, marginBottom: 6 }}>
          {contact.linkedin_url && (
            <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="os-source-link" style={{ fontSize: 11 }}>
              LinkedIn ↗
            </a>
          )}
          {contact.source_url && (
            <a href={contact.source_url} target="_blank" rel="noopener noreferrer" className="os-source-link" style={{ fontSize: 11 }}>
              Source ↗
            </a>
          )}
        </div>
      )}

      {/* Status inline dropdown */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 6, borderTop: '1px solid #f1f5f9' }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Status</span>
        <select
          className="os-input"
          value={contact.status}
          onChange={e => onStatusChange(e.target.value)}
          disabled={saving}
          style={{ fontSize: 12, padding: '3px 8px', height: 'auto', flex: 1, maxWidth: 220 }}
        >
          {CONTACT_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* Notes */}
      {contact.notes && (
        <p style={{ fontSize: 11, color: '#64748b', margin: '6px 0 0', fontStyle: 'italic', lineHeight: 1.4 }}>
          {contact.notes}
        </p>
      )}
    </div>
  )
}

// ── ContactForm ───────────────────────────────────────────────────────────────

function ContactForm({ initialData, opportunities, onSave, onCancel, loading }) {
  const [form, setForm] = useState({ ...EMPTY_CONTACT, ...initialData })
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="os-opp-form" style={{ marginBottom: 12 }}>
      <div className="os-opp-form-grid">
        <div className="os-form-field">
          <label className="os-label">Name *</label>
          <input className="os-input" value={form.name} onChange={e => set('name', e.target.value)} placeholder="Full name" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Title</label>
          <input className="os-input" value={form.title} onChange={e => set('title', e.target.value)} placeholder="e.g. Chief Operating Officer" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Company</label>
          <input className="os-input" value={form.company} onChange={e => set('company', e.target.value)} placeholder="Company name" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Related Opportunity</label>
          <select className="os-input" value={form.related_opportunity_id} onChange={e => set('related_opportunity_id', e.target.value)}>
            <option value="">— none —</option>
            {opportunities.map(o => <option key={o.id} value={o.id}>{o.title || o.company}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">LinkedIn URL</label>
          <input className="os-input" value={form.linkedin_url} onChange={e => set('linkedin_url', e.target.value)} placeholder="https://linkedin.com/in/…" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Source URL</label>
          <input className="os-input" value={form.source_url} onChange={e => set('source_url', e.target.value)} placeholder="Where you found this person" />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Why relevant</label>
          <input className="os-input" value={form.why_relevant} onChange={e => set('why_relevant', e.target.value)} placeholder="Why this contact matters for this client" />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Suggested angle</label>
          <input className="os-input" value={form.suggested_angle} onChange={e => set('suggested_angle', e.target.value)} placeholder="How to approach or frame contact" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Confidence</label>
          <select className="os-input" value={form.confidence} onChange={e => set('confidence', e.target.value)}>
            <option>High</option>
            <option>Medium</option>
            <option>Low</option>
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Status</label>
          <select className="os-input" value={form.status} onChange={e => set('status', e.target.value)}>
            {CONTACT_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Notes</label>
          <textarea className="os-textarea" value={form.notes} onChange={e => set('notes', e.target.value)} rows={2} placeholder="Internal notes for advisor only" />
        </div>
      </div>
      <div className="os-form-actions">
        <button
          className="os-btn os-btn--primary"
          onClick={() => onSave(form)}
          disabled={loading || !form.name.trim()}
        >
          {loading ? 'Saving…' : 'Save Contact'}
        </button>
        <button className="os-btn os-btn--secondary" onClick={onCancel} disabled={loading}>
          Cancel
        </button>
      </div>
    </div>
  )
}
