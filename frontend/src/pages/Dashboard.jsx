import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api } from '../apiClient'

export default function Dashboard() {
  const [clients, setClients]         = useState([])
  const [loading, setLoading]         = useState(true)
  const [creating, setCreating]       = useState(false)
  const [newName, setNewName]         = useState('')
  const [error, setError]             = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    api.listClients()
      .then(setClients)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  async function handleCreate(e) {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    setError('')
    try {
      const client = await api.createClient(name)
      navigate(`/client/${client.id}`)
    } catch (err) {
      setError(err.message)
      setCreating(false)
    }
  }

  function handleToggleAdd() {
    setShowAddForm(v => !v)
    setNewName('')
  }

  async function handleDelete(clientId) {
    if (!window.confirm('Delete this client? This cannot be undone.')) return
    try {
      await api.deleteClient(clientId)
      setClients(prev => prev.filter(c => c.id !== clientId))
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="os-page">
      <nav className="os-nav">
        <span className="os-nav-brand">Executive Transition OS</span>
      </nav>

      <main className="os-main">
        <div className="os-page-header">
          <div>
            <h1 className="os-page-title">Client Portfolio</h1>
            <p className="os-page-subtitle">
              {clients.length > 0
                ? `${clients.length} client${clients.length === 1 ? '' : 's'}`
                : 'No clients yet'}
            </p>
          </div>
          <button
            className="os-btn os-btn--primary"
            onClick={handleToggleAdd}
          >
            {showAddForm ? 'Cancel' : '+ New Client'}
          </button>
        </div>

        {showAddForm && (
          <form onSubmit={handleCreate} className="os-add-client-form">
            <input
              className="os-input"
              style={{ width: 220 }}
              placeholder="Client name"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              disabled={creating}
              required
              autoFocus
            />
            <button
              type="submit"
              className="os-btn os-btn--primary"
              disabled={creating || !newName.trim()}
            >
              {creating ? 'Creating…' : 'Create Client'}
            </button>
          </form>
        )}

        {error && <div className="os-error">{error}</div>}

        {loading ? (
          <div className="os-loading">Loading clients…</div>
        ) : clients.length === 0 ? (
          <div className="os-empty">
            <p className="os-empty-title">No clients yet</p>
            <p className="os-empty-body">
              Click <strong>+ New Client</strong> above to get started.
            </p>
          </div>
        ) : (
          <div className="os-client-grid">
            {clients.map(client => (
              <ClientCard key={client.id} client={client} onDelete={handleDelete} />
            ))}
          </div>
        )}
        <p style={{
          marginTop: 48, fontSize: 11, color: '#94a3b8',
          textAlign: 'center', lineHeight: 1.6,
        }}>
          Private MVP testing only. Data is stored for testing purposes and may be deleted during development.
        </p>
      </main>
    </div>
  )
}

function ClientCard({ client, onDelete }) {
  const name    = client.profile?.name || 'Unnamed'
  const role    = client.profile?.current_role || ''
  const created = client.created_at
    ? new Date(client.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
    : ''

  const steps = [
    { label: 'Profile',     done: Boolean(client.profile?.name || client.profile?.current_role) },
    { label: 'CV',          done: Boolean(client.profile?.cv_text?.trim()) },
    { label: 'Positioning', done: Boolean(client.positioning) },
    { label: 'Radar',       done: Boolean(client.market_radar || client.market_radar_raw) },
    { label: 'Opps',        done: Boolean(client.opportunities?.length) },
    { label: 'Brief',       done: Boolean(client.advisor_brief || client.advisor_brief_raw) },
  ]

  const doneCount = steps.filter(s => s.done).length
  const accentClass =
    doneCount === 0 ? '' :
    doneCount >= 4  ? 'os-client-card--positioned' :
                      'os-client-card--progress'

  return (
    <Link to={`/client/${client.id}`} className={`os-client-card ${accentClass}`}>
      <p className="os-client-card-name">{name}</p>
      <p className="os-client-card-role">{role || <span style={{ color: '#cbd5e1' }}>No role set</span>}</p>
      <div className="os-client-progress-track">
        {steps.map(step => (
          <span
            key={step.label}
            className={`os-progress-dot${step.done ? ' os-progress-dot--done' : ''}`}
            title={step.label}
          />
        ))}
      </div>
      <div className="os-client-card-meta">
        <span>{created}</span>
      </div>
      <button
        className="os-btn os-btn--danger os-btn--sm"
        style={{ marginTop: 10, alignSelf: 'flex-start' }}
        onClick={e => {
          e.preventDefault()
          e.stopPropagation()
          onDelete(client.id)
        }}
      >
        Delete
      </button>
    </Link>
  )
}
