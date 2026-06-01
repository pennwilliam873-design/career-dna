import { useState } from 'react'
import { api } from '../../apiClient'

const ACTION_STATUSES = ['To do', 'In progress', 'Done', 'Parked']

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

const EMPTY_NOTE   = () => ({ date: todayStr(), title: '', notes: '', advisor_only: false })
const EMPTY_ACTION = () => ({ action: '', owner: 'Advisor', due_date: '', status: 'To do', related_opportunity: '', advisor_note: '' })

export default function NotesActionsTab({ client, onUpdate }) {
  const notes   = client.session_notes || []
  const actions = client.action_items  || []

  const [loading,         setLoading]         = useState(false)
  const [error,           setError]           = useState('')
  const [showNoteForm,    setShowNoteForm]    = useState(false)
  const [showActionForm,  setShowActionForm]  = useState(false)
  const [editingNoteId,   setEditingNoteId]   = useState(null)
  const [editingActionId, setEditingActionId] = useState(null)

  // ── Notes CRUD ──────────────────────────────────────────────────────────────

  async function handleCreateNote(data) {
    setLoading(true); setError('')
    try {
      const updated = await api.createNote(client.id, data)
      onUpdate(updated); setShowNoteForm(false)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  async function handleUpdateNote(noteId, data) {
    setLoading(true); setError('')
    try {
      const updated = await api.updateNote(client.id, noteId, data)
      onUpdate(updated); setEditingNoteId(null)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  async function handleDeleteNote(noteId) {
    if (!window.confirm('Delete this note? This cannot be undone.')) return
    setLoading(true); setError('')
    try {
      const updated = await api.deleteNote(client.id, noteId)
      onUpdate(updated)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  // ── Actions CRUD ────────────────────────────────────────────────────────────

  async function handleCreateAction(data) {
    setLoading(true); setError('')
    try {
      const updated = await api.createAction(client.id, data)
      onUpdate(updated); setShowActionForm(false)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  async function handleUpdateAction(actionId, data) {
    setLoading(true); setError('')
    try {
      const updated = await api.updateAction(client.id, actionId, data)
      onUpdate(updated); setEditingActionId(null)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  async function handleDeleteAction(actionId) {
    if (!window.confirm('Delete this action item? This cannot be undone.')) return
    setLoading(true); setError('')
    try {
      const updated = await api.deleteAction(client.id, actionId)
      onUpdate(updated)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  // ── Sorted / grouped data ───────────────────────────────────────────────────

  const sortedNotes = [...notes].sort((a, b) =>
    (b.date || '').localeCompare(a.date || '')
  )

  const actionGroups = ACTION_STATUSES
    .map(status => ({ status, items: actions.filter(a => a.status === status) }))
    .filter(g => g.items.length > 0)

  const openCount = actions.filter(a => a.status === 'To do' || a.status === 'In progress').length

  return (
    <div>
      {error && <div className="os-error">{error}</div>}

      {/* ── Session Notes ─────────────────────────────────────────────────── */}
      <div className="os-positioning-header" style={{ marginBottom: 16 }}>
        <div>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#0f172a' }}>
            Session Notes
          </p>
          {notes.length > 0 && (
            <p style={{ margin: '2px 0 0', fontSize: 12, color: '#64748b' }}>
              {notes.length} note{notes.length === 1 ? '' : 's'}
            </p>
          )}
        </div>
        <button
          className="os-btn os-btn--primary"
          onClick={() => { setShowNoteForm(v => !v); setEditingNoteId(null) }}
          disabled={loading}
        >
          {showNoteForm ? 'Cancel' : '+ Add Note'}
        </button>
      </div>

      {showNoteForm && (
        <NoteForm
          initialData={EMPTY_NOTE()}
          onSave={handleCreateNote}
          onCancel={() => setShowNoteForm(false)}
          loading={loading}
        />
      )}

      {sortedNotes.length === 0 && !showNoteForm ? (
        <div className="os-generate-prompt" style={{ marginBottom: 32 }}>
          <p className="os-generate-prompt-title">No session notes yet</p>
          <p className="os-generate-prompt-body">
            Record what was discussed, decided, or agreed in each client session.
            Notes are included in the <strong>Advisor Brief</strong> so the brief
            reflects actual conversations.
          </p>
        </div>
      ) : (
        <div style={{ marginBottom: 32 }}>
          {sortedNotes.map(note =>
            editingNoteId === note.id ? (
              <NoteForm
                key={note.id}
                initialData={note}
                onSave={data => handleUpdateNote(note.id, data)}
                onCancel={() => setEditingNoteId(null)}
                loading={loading}
              />
            ) : (
              <NoteCard
                key={note.id}
                note={note}
                onEdit={() => { setEditingNoteId(note.id); setShowNoteForm(false) }}
                onDelete={() => handleDeleteNote(note.id)}
              />
            )
          )}
        </div>
      )}

      {/* ── Action Items ──────────────────────────────────────────────────── */}
      <div className="os-section-title">Action Items</div>

      <div className="os-positioning-header" style={{ marginBottom: 16 }}>
        <p style={{ margin: 0, fontSize: 12, color: '#64748b', fontWeight: 500 }}>
          {actions.length > 0
            ? `${actions.length} item${actions.length === 1 ? '' : 's'}${openCount > 0 ? ` · ${openCount} open` : ' · all closed'}`
            : ''}
        </p>
        <button
          className="os-btn os-btn--primary"
          onClick={() => { setShowActionForm(v => !v); setEditingActionId(null) }}
          disabled={loading}
        >
          {showActionForm ? 'Cancel' : '+ Add Action'}
        </button>
      </div>

      {showActionForm && (
        <ActionForm
          initialData={EMPTY_ACTION()}
          opportunities={client.opportunities || []}
          onSave={handleCreateAction}
          onCancel={() => setShowActionForm(false)}
          loading={loading}
        />
      )}

      {actions.length === 0 && !showActionForm ? (
        <div className="os-generate-prompt">
          <p className="os-generate-prompt-title">No action items yet</p>
          <p className="os-generate-prompt-body">
            Track what needs to happen before the next session — advisor tasks,
            client tasks, and follow-ups. Open action items are surfaced in the{' '}
            <strong>Advisor Brief</strong>.
          </p>
        </div>
      ) : (
        actionGroups.map(group => (
          <div key={group.status} className="os-opp-group">
            <div className="os-opp-group-header">
              <span className="os-opp-group-title">{group.status}</span>
              <span className="os-opp-group-count">{group.items.length}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {group.items.map(item =>
                editingActionId === item.id ? (
                  <ActionForm
                    key={item.id}
                    initialData={item}
                    opportunities={client.opportunities || []}
                    onSave={data => handleUpdateAction(item.id, data)}
                    onCancel={() => setEditingActionId(null)}
                    loading={loading}
                  />
                ) : (
                  <ActionCard
                    key={item.id}
                    item={item}
                    onEdit={() => { setEditingActionId(item.id); setShowActionForm(false) }}
                    onDelete={() => handleDeleteAction(item.id)}
                  />
                )
              )}
            </div>
          </div>
        ))
      )}
    </div>
  )
}

// ── NoteCard ──────────────────────────────────────────────────────────────────

function NoteCard({ note, onEdit, onDelete }) {
  return (
    <div className="os-card" style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: note.notes ? 10 : 0 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {note.date && (
              <span style={{ fontSize: 11, fontWeight: 600, color: '#64748b', background: '#f1f5f9', padding: '2px 8px', borderRadius: 4 }}>
                {note.date}
              </span>
            )}
            {note.advisor_only && (
              <span className="os-advisor-brief-badge">Advisor Only</span>
            )}
            {note.title && (
              <span style={{ fontSize: 14, fontWeight: 700, color: '#0f172a' }}>{note.title}</span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <button className="os-btn os-btn--secondary os-btn--sm" onClick={onEdit}>Edit</button>
          <button className="os-btn os-btn--danger os-btn--sm" onClick={onDelete}>Delete</button>
        </div>
      </div>
      {note.notes && (
        <p style={{ fontSize: 14, color: '#334155', lineHeight: 1.65, margin: 0, whiteSpace: 'pre-wrap' }}>
          {note.notes}
        </p>
      )}
    </div>
  )
}

// ── NoteForm ──────────────────────────────────────────────────────────────────

function NoteForm({ initialData, onSave, onCancel, loading }) {
  const [form, setForm] = useState({ ...initialData })
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="os-opp-form" style={{ marginBottom: 16 }}>
      <div className="os-opp-form-grid">
        <div className="os-form-field">
          <label className="os-label">Date</label>
          <input type="date" className="os-input" value={form.date} onChange={e => set('date', e.target.value)} />
        </div>
        <div className="os-form-field">
          <label className="os-label">Title</label>
          <input
            className="os-input"
            value={form.title}
            onChange={e => set('title', e.target.value)}
            placeholder="e.g. Session 3 — positioning review"
          />
        </div>
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Notes</label>
          <textarea
            className="os-textarea"
            value={form.notes}
            onChange={e => set('notes', e.target.value)}
            rows={6}
            placeholder="What was discussed, decided, agreed, or noted in this session…"
          />
        </div>
        <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 10 }}>
          <input
            type="checkbox"
            id="note_advisor_only"
            checked={form.advisor_only}
            onChange={e => set('advisor_only', e.target.checked)}
            style={{ width: 16, height: 16, flexShrink: 0 }}
          />
          <label htmlFor="note_advisor_only" style={{ fontSize: 13, fontWeight: 500, color: '#334155', cursor: 'pointer' }}>
            Advisor only — not for client
          </label>
        </div>
      </div>
      <div className="os-form-actions">
        <button
          className="os-btn os-btn--primary"
          onClick={() => onSave(form)}
          disabled={loading || !form.notes.trim()}
        >
          {loading ? 'Saving…' : 'Save Note'}
        </button>
        <button className="os-btn os-btn--secondary" onClick={onCancel} disabled={loading}>
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── ActionCard ────────────────────────────────────────────────────────────────

const _OWNER_STYLE = {
  Advisor: { background: '#fffbeb', color: '#92400e', border: '1px solid #fde68a' },
  Client:  { background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe' },
  Both:    { background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0' },
}

const _STATUS_STYLE = {
  'To do':       { background: '#faf5ff', color: '#7e22ce', border: '1px solid #e9d5ff' },
  'In progress': { background: '#fffbeb', color: '#b45309', border: '1px solid #fde68a' },
  'Done':        { background: '#f0fdf4', color: '#15803d', border: '1px solid #bbf7d0' },
  'Parked':      { background: '#f1f5f9', color: '#64748b', border: '1px solid #e2e8f0' },
}

const _BADGE = { display: 'inline-flex', alignItems: 'center', padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }

function ActionCard({ item, onEdit, onDelete }) {
  const ownerStyle  = _OWNER_STYLE[item.owner]  || _OWNER_STYLE['Both']
  const statusStyle = _STATUS_STYLE[item.status] || _STATUS_STYLE['To do']

  return (
    <div className="os-opp-card">
      <div className="os-opp-card-header">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 5 }}>
            <span style={{ ..._BADGE, ...ownerStyle }}>{item.owner}</span>
            <span style={{ ..._BADGE, ...statusStyle }}>{item.status}</span>
            {item.due_date && (
              <span style={{ fontSize: 11, color: '#64748b' }}>Due {item.due_date}</span>
            )}
          </div>
          <p style={{ fontSize: 14, fontWeight: 600, color: '#0f172a', margin: 0, lineHeight: 1.4 }}>
            {item.action || '(No action text)'}
          </p>
          {item.related_opportunity && (
            <p style={{ fontSize: 12, color: '#64748b', margin: '4px 0 0' }}>
              Re: {item.related_opportunity}
            </p>
          )}
        </div>
        {/* confidence badge slot intentionally empty — using status badge in title area */}
      </div>
      {item.advisor_note && (
        <p className="os-opp-advisor-note">{item.advisor_note}</p>
      )}
      <div className="os-opp-card-actions">
        <button className="os-btn os-btn--secondary os-btn--sm" onClick={onEdit}>Edit</button>
        <button className="os-btn os-btn--danger os-btn--sm os-opp-delete-btn" onClick={onDelete}>Delete</button>
      </div>
    </div>
  )
}

// ── ActionForm ────────────────────────────────────────────────────────────────

function ActionForm({ initialData, opportunities, onSave, onCancel, loading }) {
  const [form, setForm] = useState({ ...initialData })
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="os-opp-form" style={{ marginBottom: 16 }}>
      <div className="os-opp-form-grid">
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Action *</label>
          <input
            className="os-input"
            value={form.action}
            onChange={e => set('action', e.target.value)}
            placeholder="e.g. Draft outreach message to Alex at Bridgepoint"
          />
        </div>
        <div className="os-form-field">
          <label className="os-label">Owner</label>
          <select className="os-input" value={form.owner} onChange={e => set('owner', e.target.value)}>
            <option>Advisor</option>
            <option>Client</option>
            <option>Both</option>
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Status</label>
          <select className="os-input" value={form.status} onChange={e => set('status', e.target.value)}>
            {ACTION_STATUSES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="os-form-field">
          <label className="os-label">Due Date</label>
          <input
            type="date"
            className="os-input"
            value={form.due_date}
            onChange={e => set('due_date', e.target.value)}
          />
        </div>
        <div className="os-form-field">
          <label className="os-label">Related Opportunity</label>
          <input
            className="os-input"
            value={form.related_opportunity}
            onChange={e => set('related_opportunity', e.target.value)}
            placeholder="Optional"
            list="action-opp-titles"
          />
          {opportunities.length > 0 && (
            <datalist id="action-opp-titles">
              {opportunities.map(o => <option key={o.id} value={o.title} />)}
            </datalist>
          )}
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
          disabled={loading || !form.action.trim()}
        >
          {loading ? 'Saving…' : 'Save Action'}
        </button>
        <button className="os-btn os-btn--secondary" onClick={onCancel} disabled={loading}>
          Cancel
        </button>
      </div>
    </div>
  )
}
