import { useState } from 'react'

const STORAGE_KEY = 'etos_access_granted'

export default function AccessGate({ children }) {
  const [granted, setGranted] = useState(
    () => sessionStorage.getItem(STORAGE_KEY) === '1'
  )
  const [code, setCode]       = useState('')
  const [error, setError]     = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!code.trim()) return
    setLoading(true)
    setError('')
    try {
      const res  = await fetch('/api/auth', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ code: code.trim() }),
      })
      const data = await res.json()
      if (data.ok) {
        sessionStorage.setItem(STORAGE_KEY, '1')
        setGranted(true)
      } else {
        setError('Incorrect access code.')
        setCode('')
      }
    } catch {
      setError('Could not verify. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  if (granted) return children

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#f5f6f8',
      fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
    }}>
      <div style={{
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        padding: '40px 36px',
        width: '100%',
        maxWidth: 360,
        boxSizing: 'border-box',
      }}>
        <p style={{
          fontSize: 13, fontWeight: 700, color: '#0f172a',
          margin: '0 0 4px', letterSpacing: '-0.2px',
        }}>
          Executive Transition OS
        </p>
        <p style={{ fontSize: 12, color: '#94a3b8', margin: '0 0 28px' }}>
          Private testing access
        </p>

        <form onSubmit={handleSubmit}>
          <label style={{
            fontSize: 11, fontWeight: 700, color: '#475569',
            textTransform: 'uppercase', letterSpacing: '0.06em',
            display: 'block', marginBottom: 6,
          }}>
            Access Code
          </label>
          <input
            type="password"
            value={code}
            onChange={e => setCode(e.target.value)}
            autoFocus
            autoComplete="off"
            disabled={loading}
            style={{
              width: '100%', padding: '9px 11px',
              border: '1px solid #e2e8f0', borderRadius: 7,
              fontSize: 14, color: '#0f172a',
              marginBottom: error ? 8 : 16,
              boxSizing: 'border-box', fontFamily: 'inherit',
              outline: 'none',
            }}
          />
          {error && (
            <p style={{ fontSize: 12, color: '#be123c', margin: '0 0 12px' }}>
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading || !code.trim()}
            style={{
              width: '100%', padding: '9px 18px',
              background: '#0f172a', color: '#ffffff',
              border: 'none', borderRadius: 7,
              fontSize: 13, fontWeight: 600,
              cursor: loading || !code.trim() ? 'not-allowed' : 'pointer',
              opacity: loading || !code.trim() ? 0.5 : 1,
              fontFamily: 'inherit',
            }}
          >
            {loading ? 'Verifying…' : 'Enter'}
          </button>
        </form>
      </div>
    </div>
  )
}
