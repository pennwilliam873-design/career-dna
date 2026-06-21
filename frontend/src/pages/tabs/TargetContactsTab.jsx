import { useMemo, useState } from 'react'
import { api } from '../../apiClient'

// ── Vocabularies ──────────────────────────────────────────────────────────────

const CONTACT_STATUSES = [
  'To assess', 'Warm path needed', 'Ready for outreach', 'Contacted',
  'Meeting booked', 'Active conversation', 'Parked', 'Not relevant',
]
const NETWORK_SOURCES = ['Client Network', 'Advisor Network', 'ViaNova Suggestion', 'Unknown']
const RELATIONSHIP_OWNERS = ['Client', 'Advisor', 'Both', 'Third-party', 'Unknown']
const RELATIONSHIP_STRENGTHS = ['Strong', 'Medium', 'Weak', 'Dormant', 'Unknown']
const ROLES_IN_SEARCH = [
  'Decision-maker', 'Introducer', 'Bridge contact', 'Market intelligence',
  'Search consultant', 'Board/investor connector', 'Potential sponsor',
  'Former colleague', 'Peer', 'Other', 'Unknown',
]
const WARM_PATH_STATUSES = ['Warm path known', 'Possible warm path', 'Warm path needed', 'Cold only', 'Unknown']
const ASK_TYPES = [
  'Market intelligence', 'Introduction', 'Reconnect', 'Search mandate',
  'Company insight', 'Role discussion', 'Direct opportunity', 'Referral', 'Other', 'Unknown',
]
const CAN_MAKE_INTRO_OPTIONS = ['unknown', 'yes', 'no']
const NEXT_ACTION_OWNERS = ['Advisor', 'Client', 'Both']
const MARKET_RADAR_TIERS = ['Unknown', 'Tier 1', 'Tier 2', 'Tier 3']

const SOURCE_SECTIONS = [
  { key: 'Client Network',     label: 'Client Network',     cls: 'client',
    hint: 'People the client already knows — former colleagues, peers, personal network.' },
  { key: 'Advisor Network',    label: 'Advisor Network',     cls: 'advisor',
    hint: "People the advisor knows — board contacts, search consultants, the advisor's own network." },
  { key: 'ViaNova Suggestion', label: 'ViaNova Suggestions', cls: 'vianova',
    hint: 'People ViaNova surfaced as potentially relevant — not yet a known relationship.' },
]

function sectionKeyFor(contact) {
  if (contact.network_source === 'Client Network') return 'Client Network'
  if (contact.network_source === 'Advisor Network') return 'Advisor Network'
  return 'ViaNova Suggestion' // covers 'ViaNova Suggestion', 'Unknown', and anything unrecognised
}

const EMPTY_CONTACT = {
  name: '', title: '', company: '',
  linkedin_url: '', source_url: '',
  related_opportunity_id: '',
  why_relevant: '', suggested_angle: '',
  confidence: 'Medium', status: 'To assess', notes: '',

  network_source: 'Unknown',
  relationship_owner: 'Unknown',
  relationship_to_client: '',
  relationship_to_advisor: '',
  relationship_strength: 'Unknown',
  last_contacted_at: '',

  role_in_search: 'Unknown',
  target_company: '',
  target_sector: '',
  linked_market_radar_company: '',
  linked_market_radar_tier: '',
  linked_opportunity_id: '',
  linked_opportunity_title: '',
  relevance_rationale: '',
  opportunity_path_hypothesis: '',
  can_make_intro: 'unknown',
  bridge_to: '',
  warm_path_status: 'Unknown',
  ask_type: 'Unknown',
  suggested_approach: '',

  next_action: '',
  next_action_owner: 'Advisor',
  next_action_due_date: '',
  follow_up_date: '',
  outreach_channel: '',
  response_notes: '',

  advisor_only: true,
  advisor_notes: '',
  client_shareable: false,
  approved_for_outreach: false,
  sensitive: false,
  do_not_contact_yet: false,
  include_in_advisor_brief: false,
  include_in_weekly_plan: false,
}

// ── Opportunity path (text version of the future graph) ───────────────────────

function opportunityPath(c) {
  const ownerLabel = {
    Client: 'Client', Advisor: 'Advisor', Both: 'Client & Advisor', 'Third-party': 'Third-party',
  }[c.relationship_owner] || 'Unknown'
  const destination =
    c.opportunity_path_hypothesis || c.bridge_to || c.target_company ||
    c.linked_market_radar_company || c.linked_opportunity_title || 'hidden market'
  return `${ownerLabel} → ${c.name || 'Unnamed contact'} → ${destination}`
}

export default function TargetContactsTab({ client, onUpdate }) {
  const contacts      = client.target_contacts || []
  const opportunities  = client.opportunities  || []
  const marketRadar    = client.market_radar

  const radarCompanyOptions = useMemo(() => {
    if (!marketRadar) return []
    const seen = new Set()
    const list = []
    const add = company => {
      if (company && !seen.has(company)) { seen.add(company); list.push(company) }
    }
    ;(marketRadar.tier1_companies || []).forEach(c => add(c.company))
    ;(marketRadar.tier2_companies || []).forEach(c => add(c.company))
    ;(marketRadar.tier3_companies || []).forEach(c => add(c.company))
    ;(marketRadar.target_companies || []).forEach(c => add(c.company))
    return list
  }, [marketRadar])

  const [loading,        setLoading]        = useState(false)
  const [saving,         setSaving]         = useState(false)
  const [error,          setError]          = useState('')
  const [searchMessage,  setSearchMessage]  = useState('')
  const [actionMessage,  setActionMessage]  = useState('')

  // Search panel
  const [showSearch,     setShowSearch]     = useState(false)
  const [searchCompany,  setSearchCompany]  = useState('')
  const [searchOppId,    setSearchOppId]    = useState('')
  const [searchRole,     setSearchRole]     = useState('')
  const [searchResults,  setSearchResults]  = useState(null)

  // Add / edit
  const [showAddForm,    setShowAddForm]    = useState(false)
  const [addFormSource,  setAddFormSource]  = useState('Unknown')
  const [editingId,      setEditingId]      = useState(null)

  // ── Derive company from selected opportunity ──────────────────────────────

  function handleOppSelect(oppId) {
    setSearchOppId(oppId)
    if (oppId) {
      const opp = opportunities.find(o => o.id === oppId)
      if (opp?.company && !searchCompany) setSearchCompany(opp.company)
    }
  }

  // ── Search (AI / Find Contacts) ───────────────────────────────────────────

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

  // Suggested contacts always land in ViaNova Suggestions — never treated as a
  // warm contact until the advisor explicitly changes the source/relationship fields.
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
        target_company:  suggestion.company,
        network_source:  'ViaNova Suggestion',
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

  // Creates a Notes & Actions item from this contact's next_action fields.
  // No formal backlink to the contact yet — keeping this additive and simple.
  async function handleCreateAction(contact) {
    setSaving(true); setError(''); setActionMessage('')
    try {
      const actionText = contact.next_action?.trim()
        ? contact.next_action.trim()
        : `Reconnect with ${contact.name}` +
          (contact.company ? ` at ${contact.company}` : '') +
          (contact.ask_type && contact.ask_type !== 'Unknown' ? ` — ${contact.ask_type.toLowerCase()}` : '')
      const updated = await api.createAction(client.id, {
        action: actionText,
        owner: contact.next_action_owner || 'Advisor',
        due_date: contact.next_action_due_date || '',
        status: 'To do',
        related_opportunity: contact.target_company || contact.company || '',
        advisor_note: `From Hidden Market Map contact: ${contact.name}`,
      })
      onUpdate(updated)
      setActionMessage(`Action created for ${contact.name}. See Notes & Actions.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // ── Saved contacts already match suggestion? ─────────────────────────────

  const savedKeys = new Set(contacts.map(c => `${c.name}|${c.company}`.toLowerCase()))
  function isSaved(s) {
    return savedKeys.has(`${s.name}|${s.company}`.toLowerCase())
  }

  // ── Summary stats ─────────────────────────────────────────────────────────

  const clientCount   = contacts.filter(c => c.network_source === 'Client Network').length
  const advisorCount  = contacts.filter(c => c.network_source === 'Advisor Network').length
  const vianovaCount  = contacts.length - clientCount - advisorCount
  const warmPathCount = contacts.filter(c => c.warm_path_status === 'Warm path known' || c.warm_path_status === 'Possible warm path').length
  const actionsDue    = contacts.filter(c => c.next_action_due_date).length

  // ── Group + sort by network source section ───────────────────────────────

  const confRank = { High: 0, Medium: 1, Low: 2 }
  const warmRank = {
    'Warm path known': 0, 'Possible warm path': 1, 'Warm path needed': 2, 'Cold only': 3, Unknown: 4,
  }
  function sortSection(list) {
    return [...list].sort((a, b) => {
      const wa = warmRank[a.warm_path_status] ?? 4
      const wb = warmRank[b.warm_path_status] ?? 4
      if (wa !== wb) return wa - wb
      return (confRank[a.confidence] ?? 1) - (confRank[b.confidence] ?? 1)
    })
  }

  const grouped = { 'Client Network': [], 'Advisor Network': [], 'ViaNova Suggestion': [] }
  contacts.forEach(c => grouped[sectionKeyFor(c)].push(c))

  function openAddForm(source) {
    setAddFormSource(source)
    setShowAddForm(true)
    setEditingId(null)
  }

  return (
    <div>
      {error && <div className="os-error">{error}</div>}
      {actionMessage && <div className="os-raw-warning" style={{ background: '#f0fdf4', borderColor: '#bbf7d0', color: '#15803d' }}>{actionMessage}</div>}

      {/* ── Heading ─────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 18 }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 800, color: '#0f172a' }}>Hidden Market Map</h2>
        <p style={{ margin: 0, fontSize: 13, color: '#64748b', maxWidth: 680 }}>
          Map the people, relationships and warm paths that can create or uncover executive opportunities.
        </p>
      </div>

      {/* ── Summary cards ───────────────────────────────────────────────── */}
      <div className="os-hmm-summary-grid">
        <SummaryCard label="Total Mapped" value={contacts.length} />
        <SummaryCard label="Client Network" value={clientCount} />
        <SummaryCard label="Advisor Network" value={advisorCount} />
        <SummaryCard label="ViaNova Suggestions" value={vianovaCount} />
        <SummaryCard label="Warm Paths" value={warmPathCount} />
        <SummaryCard label="Actions Due" value={actionsDue} />
      </div>

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
          onClick={() => { if (showAddForm) { setShowAddForm(false) } else { openAddForm('Unknown') } }}
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
              <p style={{ fontSize: 11, color: '#94a3b8', margin: '-4px 0 10px' }}>
                Saved contacts land in <strong>ViaNova Suggestions</strong> until you confirm a known relationship.
              </p>
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
          initialData={{ ...EMPTY_CONTACT, network_source: addFormSource }}
          opportunities={opportunities}
          radarCompanyOptions={radarCompanyOptions}
          onSave={handleCreate}
          onCancel={() => setShowAddForm(false)}
          loading={saving}
        />
      )}

      {/* ── Empty state ──────────────────────────────────────────────────── */}
      {contacts.length === 0 && !showAddForm && searchResults === null && (
        <div className="os-generate-prompt">
          <p className="os-generate-prompt-title">No contacts mapped yet</p>
          <p className="os-generate-prompt-body">
            Use <strong>Find Contacts</strong> to search for real people at target companies,
            or <strong>Add Manually</strong> to record someone the client or advisor already knows.
          </p>
        </div>
      )}

      {/* ── Three source sections ───────────────────────────────────────── */}
      {SOURCE_SECTIONS.map(section => {
        const items = sortSection(grouped[section.key])
        return (
          <div key={section.key} className="os-hmm-section">
            <div className={`os-hmm-section-header os-hmm-section-header--${section.cls}`}>
              <div>
                <span>{section.label}</span>
                <span className="os-opp-group-count" style={{ marginLeft: 8 }}>{items.length}</span>
                <div style={{ fontSize: 11, fontWeight: 400, marginTop: 2, opacity: 0.85 }}>{section.hint}</div>
              </div>
              <button
                className="os-btn os-btn--secondary os-btn--sm"
                onClick={() => openAddForm(section.key)}
                disabled={loading || saving}
              >
                + Add
              </button>
            </div>

            {items.length === 0 ? (
              <p style={{ fontSize: 12, color: '#94a3b8', padding: '0 4px 8px' }}>No contacts in this section yet.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {items.map(contact =>
                  editingId === contact.id ? (
                    <ContactForm
                      key={contact.id}
                      initialData={contact}
                      opportunities={opportunities}
                      radarCompanyOptions={radarCompanyOptions}
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
                      onCreateAction={() => handleCreateAction(contact)}
                      saving={saving}
                    />
                  )
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── SummaryCard ─────────────────────────────────────────────────────────────

function SummaryCard({ label, value }) {
  return (
    <div className="os-hmm-summary-card">
      <p className="os-hmm-summary-value">{value}</p>
      <p className="os-hmm-summary-label">{label}</p>
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
            <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="os-source-link" style={{ fontSize: 11 }}>
              LinkedIn
            </a>
          )}
          {contact.source_url && !contact.linkedin_url && (
            <a href={contact.source_url} target="_blank" rel="noopener noreferrer" className="os-source-link" style={{ fontSize: 11 }}>
              Source
            </a>
          )}
        </div>
      )}
    </div>
  )
}

// ── ContactCard ───────────────────────────────────────────────────────────────

function ContactCard({ contact, onEdit, onDelete, onStatusChange, onCreateAction, saving }) {
  const isBridge = contact.role_in_search === 'Bridge contact' || Boolean(contact.bridge_to)

  return (
    <div className="os-opp-card" style={{ gap: 0, padding: '12px 14px' }}>
      {/* Header: name + title/company + Edit/Delete */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 5 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>{contact.name || '(No name)'}</span>
            {(contact.title || contact.company) && (
              <span style={{ fontSize: 12, color: '#64748b' }}>
                {contact.title}{contact.title && contact.company ? ' — ' : ''}{contact.company}
              </span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 5, flexShrink: 0 }}>
          <button className="os-btn os-btn--secondary os-btn--sm" onClick={onEdit} style={{ padding: '3px 10px' }} disabled={saving}>Edit</button>
          <button className="os-btn os-btn--danger os-btn--sm os-opp-delete-btn" onClick={onDelete} style={{ padding: '3px 10px' }} disabled={saving}>×</button>
        </div>
      </div>

      {/* Badge row */}
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 6 }}>
        <span className="os-hmm-pill">{contact.relationship_owner}</span>
        <span className="os-hmm-pill">{contact.relationship_strength} relationship</span>
        {contact.role_in_search && contact.role_in_search !== 'Unknown' && (
          <span className={`os-hmm-pill ${isBridge ? 'os-hmm-pill--bridge' : ''}`}>{contact.role_in_search}</span>
        )}
        {contact.warm_path_status && contact.warm_path_status !== 'Unknown' && (
          <span className={`os-hmm-pill ${contact.warm_path_status === 'Warm path known' ? 'os-hmm-pill--success' : ''}`}>
            {contact.warm_path_status}
          </span>
        )}
        {contact.ask_type && contact.ask_type !== 'Unknown' && (
          <span className="os-hmm-pill os-hmm-pill--muted">Ask: {contact.ask_type}</span>
        )}
        {contact.advisor_only && <span className="os-advisor-brief-badge" style={{ padding: '2px 8px', fontSize: 9 }}>Advisor Only</span>}
        {contact.client_shareable && <span className="os-hmm-pill os-hmm-pill--success">Client-shareable</span>}
        {contact.approved_for_outreach && <span className="os-hmm-pill os-hmm-pill--success">Approved for outreach</span>}
        {contact.sensitive && <span className="os-hmm-pill os-hmm-pill--warn">Sensitive</span>}
        {contact.do_not_contact_yet && <span className="os-hmm-pill os-hmm-pill--warn">Do not contact yet</span>}
      </div>

      {/* Target company/sector */}
      {(contact.target_company || contact.target_sector) && (
        <p style={{ fontSize: 11, color: '#64748b', margin: '0 0 4px' }}>
          <span style={{ fontWeight: 700, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8', marginRight: 3 }}>Target</span>
          {[contact.target_company, contact.target_sector].filter(Boolean).join(' · ')}
        </p>
      )}

      {/* Why relevant / rationale */}
      {(contact.relevance_rationale || contact.why_relevant) && (
        <p style={{ fontSize: 12, color: '#334155', lineHeight: 1.45, margin: '0 0 3px' }}>
          {contact.relevance_rationale || contact.why_relevant}
        </p>
      )}

      {/* Bridge detail */}
      {isBridge && contact.bridge_to && (
        <p style={{ fontSize: 11, color: '#7e22ce', lineHeight: 1.4, margin: '0 0 3px' }}>
          <span style={{ fontWeight: 700, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', marginRight: 3 }}>Bridge to</span>
          {contact.bridge_to}
        </p>
      )}

      {/* Opportunity path */}
      <p className="os-hmm-path">{opportunityPath(contact)}</p>

      {/* Links */}
      {(contact.linkedin_url || contact.source_url) && (
        <div style={{ display: 'flex', gap: 10, marginTop: 4, marginBottom: 2 }}>
          {contact.linkedin_url && (
            <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="os-source-link" style={{ fontSize: 11 }}>LinkedIn ↗</a>
          )}
          {contact.source_url && (
            <a href={contact.source_url} target="_blank" rel="noopener noreferrer" className="os-source-link" style={{ fontSize: 11 }}>Source ↗</a>
          )}
        </div>
      )}

      {/* Status + next action */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 7, marginTop: 6, borderTop: '1px solid #f1f5f9', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Status</span>
        <select
          className="os-input"
          value={contact.status}
          onChange={e => onStatusChange(e.target.value)}
          disabled={saving}
          style={{ fontSize: 12, padding: '3px 8px', height: 'auto', flex: '0 1 220px' }}
        >
          {CONTACT_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button className="os-btn os-btn--secondary os-btn--sm" onClick={onCreateAction} disabled={saving} style={{ marginLeft: 'auto' }}>
          + Create Action
        </button>
      </div>

      {contact.next_action && (
        <p style={{ fontSize: 12, color: '#334155', margin: '6px 0 0' }}>
          <span style={{ fontWeight: 700, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8', marginRight: 3 }}>Next action</span>
          {contact.next_action}
          <span style={{ color: '#94a3b8' }}>
            {' '}({contact.next_action_owner}{contact.next_action_due_date ? `, due ${contact.next_action_due_date}` : ''})
          </span>
        </p>
      )}

      {/* Suggested angle / notes (legacy) */}
      {contact.suggested_angle && (
        <p style={{ fontSize: 11, color: '#64748b', lineHeight: 1.4, margin: '4px 0 0' }}>
          <span style={{ fontWeight: 700, fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#94a3b8', marginRight: 3 }}>Angle</span>
          {contact.suggested_angle}
        </p>
      )}
      {contact.notes && (
        <p style={{ fontSize: 11, color: '#64748b', margin: '4px 0 0', fontStyle: 'italic', lineHeight: 1.4 }}>
          {contact.notes}
        </p>
      )}

      {/* Private advisor notes */}
      {contact.advisor_notes && (
        <div className="os-hmm-private">
          <p className="os-hmm-private-label">Advisor only — not for client</p>
          <p style={{ fontSize: 12, color: '#92400e', margin: 0, lineHeight: 1.4 }}>{contact.advisor_notes}</p>
        </div>
      )}
    </div>
  )
}

// ── ContactForm ───────────────────────────────────────────────────────────────

function FormSectionHeading({ children, first }) {
  return (
    <div style={{
      gridColumn: '1 / -1', fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
      letterSpacing: '0.05em', color: '#94a3b8',
      marginTop: first ? 0 : 14, paddingTop: first ? 0 : 10,
      borderTop: first ? 'none' : '1px solid #e2e8f0',
    }}>
      {children}
    </div>
  )
}

function ContactForm({ initialData, opportunities, radarCompanyOptions, onSave, onCancel, loading }) {
  const [form, setForm] = useState({ ...EMPTY_CONTACT, ...initialData })
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const setChecked = (k, e) => set(k, e.target.checked)

  function handleLinkedOpportunity(oppId) {
    const opp = opportunities.find(o => o.id === oppId)
    set('linked_opportunity_id', oppId)
    set('linked_opportunity_title', opp ? (opp.title || opp.company) : '')
  }

  return (
    <div className="os-opp-form" style={{ marginBottom: 12 }}>
      <div className="os-opp-form-grid">

        <FormSectionHeading first>Basics</FormSectionHeading>
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
          <label className="os-label">LinkedIn URL</label>
          <input className="os-input" value={form.linkedin_url} onChange={e => set('linkedin_url', e.target.value)} placeholder="https://linkedin.com/in/…" />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Source URL</label>
          <input className="os-input" value={form.source_url} onChange={e => set('source_url', e.target.value)} placeholder="Where you found this person" />
        </div>

        <FormSectionHeading>Network &amp; Relationship</FormSectionHeading>
        <div className="os-form-field">
          <label className="os-label">Network Source</label>
          <select className="os-input" value={form.network_source} onChange={e => set('network_source', e.target.value)}>
            {NETWORK_SOURCES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Relationship Owner</label>
          <select className="os-input" value={form.relationship_owner} onChange={e => set('relationship_owner', e.target.value)}>
            {RELATIONSHIP_OWNERS.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Relationship to Client</label>
          <input className="os-input" value={form.relationship_to_client} onChange={e => set('relationship_to_client', e.target.value)} placeholder="e.g. Former colleague at Acme" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Relationship to Advisor</label>
          <input className="os-input" value={form.relationship_to_advisor} onChange={e => set('relationship_to_advisor', e.target.value)} placeholder="e.g. Board contact" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Relationship Strength</label>
          <select className="os-input" value={form.relationship_strength} onChange={e => set('relationship_strength', e.target.value)}>
            {RELATIONSHIP_STRENGTHS.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Last Contacted</label>
          <input type="date" className="os-input" value={form.last_contacted_at} onChange={e => set('last_contacted_at', e.target.value)} />
        </div>

        <FormSectionHeading>Strategic Role</FormSectionHeading>
        <div className="os-form-field">
          <label className="os-label">Role in Search</label>
          <select className="os-input" value={form.role_in_search} onChange={e => set('role_in_search', e.target.value)}>
            {ROLES_IN_SEARCH.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Can Make Intro</label>
          <select className="os-input" value={form.can_make_intro} onChange={e => set('can_make_intro', e.target.value)}>
            {CAN_MAKE_INTRO_OPTIONS.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Target Company</label>
          <input className="os-input" value={form.target_company} onChange={e => set('target_company', e.target.value)} placeholder="Company this contact could unlock" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Target Sector</label>
          <input className="os-input" value={form.target_sector} onChange={e => set('target_sector', e.target.value)} placeholder="e.g. PE-backed services" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Warm Path Status</label>
          <select className="os-input" value={form.warm_path_status} onChange={e => set('warm_path_status', e.target.value)}>
            {WARM_PATH_STATUSES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Ask Type</label>
          <select className="os-input" value={form.ask_type} onChange={e => set('ask_type', e.target.value)}>
            {ASK_TYPES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Bridge To</label>
          <input className="os-input" value={form.bridge_to} onChange={e => set('bridge_to', e.target.value)} placeholder="Who, which company, or which sector this person may bridge to" />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Relevance Rationale</label>
          <textarea className="os-textarea" rows={2} value={form.relevance_rationale} onChange={e => set('relevance_rationale', e.target.value)} placeholder="Why this contact matters for this client, specifically" />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Opportunity Path Hypothesis</label>
          <input className="os-input" value={form.opportunity_path_hypothesis} onChange={e => set('opportunity_path_hypothesis', e.target.value)} placeholder="e.g. Qantas transformation network" />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Suggested Approach</label>
          <textarea className="os-textarea" rows={2} value={form.suggested_approach} onChange={e => set('suggested_approach', e.target.value)} placeholder="How to approach or frame this contact" />
        </div>

        <FormSectionHeading>Link to Market Radar / Opportunities</FormSectionHeading>
        <div className="os-form-field">
          <label className="os-label">Market Radar Company</label>
          <input
            className="os-input"
            value={form.linked_market_radar_company}
            onChange={e => set('linked_market_radar_company', e.target.value)}
            placeholder="Company name from Market Radar"
            list="hmm-radar-companies"
          />
          {radarCompanyOptions.length > 0 && (
            <datalist id="hmm-radar-companies">
              {radarCompanyOptions.map(c => <option key={c} value={c} />)}
            </datalist>
          )}
        </div>
        <div className="os-form-field">
          <label className="os-label">Market Radar Tier</label>
          <select className="os-input" value={form.linked_market_radar_tier} onChange={e => set('linked_market_radar_tier', e.target.value)}>
            {MARKET_RADAR_TIERS.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Linked Opportunity</label>
          <select className="os-input" value={form.linked_opportunity_id} onChange={e => handleLinkedOpportunity(e.target.value)}>
            <option value="">— none —</option>
            {opportunities.map(o => <option key={o.id} value={o.id}>{o.title || o.company}</option>)}
          </select>
        </div>

        <FormSectionHeading>Execution</FormSectionHeading>
        <div className="os-form-field">
          <label className="os-label">Status</label>
          <select className="os-input" value={form.status} onChange={e => set('status', e.target.value)}>
            {CONTACT_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Confidence</label>
          <select className="os-input" value={form.confidence} onChange={e => set('confidence', e.target.value)}>
            <option>High</option>
            <option>Medium</option>
            <option>Low</option>
          </select>
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Next Action</label>
          <input className="os-input" value={form.next_action} onChange={e => set('next_action', e.target.value)} placeholder="e.g. Reconnect with Sarah Jones at Qantas — ask for market intelligence" />
        </div>
        <div className="os-form-field">
          <label className="os-label">Next Action Owner</label>
          <select className="os-input" value={form.next_action_owner} onChange={e => set('next_action_owner', e.target.value)}>
            {NEXT_ACTION_OWNERS.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Next Action Due Date</label>
          <input type="date" className="os-input" value={form.next_action_due_date} onChange={e => set('next_action_due_date', e.target.value)} />
        </div>
        <div className="os-form-field">
          <label className="os-label">Follow-up Date</label>
          <input type="date" className="os-input" value={form.follow_up_date} onChange={e => set('follow_up_date', e.target.value)} />
        </div>
        <div className="os-form-field">
          <label className="os-label">Outreach Channel</label>
          <input className="os-input" value={form.outreach_channel} onChange={e => set('outreach_channel', e.target.value)} placeholder="e.g. LinkedIn, email, intro call" />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Response Notes</label>
          <textarea className="os-textarea" rows={2} value={form.response_notes} onChange={e => set('response_notes', e.target.value)} placeholder="What they said / how it went" />
        </div>

        <FormSectionHeading>Visibility &amp; Privacy</FormSectionHeading>
        <div className="os-form-field os-form-field--full" style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <Checkbox id="advisor_only" label="Advisor only" checked={form.advisor_only} onChange={e => setChecked('advisor_only', e)} />
          <Checkbox id="client_shareable" label="Client-shareable" checked={form.client_shareable} onChange={e => setChecked('client_shareable', e)} />
          <Checkbox id="approved_for_outreach" label="Approved for outreach" checked={form.approved_for_outreach} onChange={e => setChecked('approved_for_outreach', e)} />
          <Checkbox id="sensitive" label="Sensitive" checked={form.sensitive} onChange={e => setChecked('sensitive', e)} />
          <Checkbox id="do_not_contact_yet" label="Do not contact yet" checked={form.do_not_contact_yet} onChange={e => setChecked('do_not_contact_yet', e)} />
          <Checkbox id="include_in_advisor_brief" label="Include in Advisor Brief" checked={form.include_in_advisor_brief} onChange={e => setChecked('include_in_advisor_brief', e)} />
          <Checkbox id="include_in_weekly_plan" label="Include in weekly plan" checked={form.include_in_weekly_plan} onChange={e => setChecked('include_in_weekly_plan', e)} />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Advisor Notes (private, not for client)</label>
          <textarea className="os-textarea" rows={2} value={form.advisor_notes} onChange={e => set('advisor_notes', e.target.value)} placeholder="Sensitive notes for the advisor only" />
        </div>

        <FormSectionHeading>General</FormSectionHeading>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Why relevant (legacy)</label>
          <input className="os-input" value={form.why_relevant} onChange={e => set('why_relevant', e.target.value)} placeholder="Why this contact matters for this client" />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Suggested angle (legacy)</label>
          <input className="os-input" value={form.suggested_angle} onChange={e => set('suggested_angle', e.target.value)} placeholder="How to approach or frame contact" />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Notes</label>
          <textarea className="os-textarea" value={form.notes} onChange={e => set('notes', e.target.value)} rows={2} placeholder="General notes" />
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

function Checkbox({ id, label, checked, onChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <input type="checkbox" id={id} checked={checked} onChange={onChange} style={{ width: 15, height: 15 }} />
      <label htmlFor={id} style={{ fontSize: 12, fontWeight: 500, color: '#334155', cursor: 'pointer' }}>{label}</label>
    </div>
  )
}
