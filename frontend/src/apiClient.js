const PROXY_BASE    = '/api'
const RAILWAY_URL   = 'https://career-dna-production.up.railway.app'
// VITE_BACKEND_URL overrides the hardcoded URL if set in Vercel env vars.
// Falls back to RAILWAY_URL in production, or null in local dev (where PROD=false
// and the Vite proxy forwards /api/clients/* to localhost:8000).
const DIRECT_BASE = import.meta.env.VITE_BACKEND_URL || (import.meta.env.PROD ? RAILWAY_URL : null)

async function req(method, path, body, direct = false) {
  // When VITE_BACKEND_URL is set and the call is marked direct,
  // bypass the Vercel proxy and call Railway directly to avoid the 10s timeout.
  // Falls back to PROXY_BASE in local dev (where VITE_BACKEND_URL is unset).
  const base = (direct && DIRECT_BASE) ? DIRECT_BASE : PROXY_BASE

  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body !== undefined) opts.body = JSON.stringify(body)

  const res = await fetch(`${base}${path}`, opts)
  if (!res.ok) {
    let message = res.statusText
    try {
      const data = await res.json()
      message = data.detail || data.message || message
    } catch (_) {}
    throw new Error(message)
  }
  return res.json()
}

export const api = {
  // ── Fast CRUD — stay through Vercel proxy (well under 10s) ────────────────
  listClients:       ()              => req('GET',  '/clients'),
  createClient:      (name)          => req('POST', '/clients', { name }),
  getClient:         (id)            => req('GET',  `/clients/${id}`),
  updateClient:      (id, profile)   => req('PUT',  `/clients/${id}`, { profile }),
  deleteClient:      (id)            => req('DELETE', `/clients/${id}`),
  createNote:        (id, note)      => req('POST',   `/clients/${id}/notes`, note,      true),
  updateNote:        (id, nid, note) => req('PUT',    `/clients/${id}/notes/${nid}`, note, true),
  deleteNote:        (id, nid)       => req('DELETE', `/clients/${id}/notes/${nid}`, undefined, true),
  createAction:      (id, action)    => req('POST',   `/clients/${id}/actions`, action,    true),
  updateAction:      (id, aid, act)  => req('PUT',    `/clients/${id}/actions/${aid}`, act, true),
  deleteAction:      (id, aid)       => req('DELETE', `/clients/${id}/actions/${aid}`, undefined, true),
  createOpportunity: (id, opp)       => req('POST', `/clients/${id}/opportunities`, opp),
  updateOpportunity: (id, oppId, opp) => req('PUT', `/clients/${id}/opportunities/${oppId}`, opp),
  deleteOpportunity: (id, oppId)     => req('DELETE', `/clients/${id}/opportunities/${oppId}`),

  // ── Slow AI operations — call Railway directly to bypass Vercel 10s limit ─
  analyseCv:           (id)                  => req('POST', `/clients/${id}/analyse-cv`,            undefined, true),
  generatePositioning: (id)                  => req('POST', `/clients/${id}/generate-positioning`,  undefined, true),
  runMarketRadar:      (id, manualResearch)   => req('POST', `/clients/${id}/run-market-radar`,      { manual_research: manualResearch || null }, true),
  generateAdvisorBrief: (id)                 => req('POST', `/clients/${id}/generate-advisor-brief`, undefined, true),
}
