const BACKEND_URL = process.env.BACKEND_URL || 'https://career-dna-production.up.railway.app'
const TRIAL_API_KEY = process.env.TRIAL_API_KEY || ''

export default async function handler(req, res) {
  const { id } = req.query
  const method = req.method

  if (method !== 'GET' && method !== 'PUT' && method !== 'DELETE') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  try {
    const fetchOpts = {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Trial-Key': TRIAL_API_KEY,
      },
    }
    if (method === 'PUT') {
      fetchOpts.body = JSON.stringify(req.body)
    }

    const response = await fetch(`${BACKEND_URL}/clients/${id}`, fetchOpts)
    const data = await response.json()
    return res.status(response.status).json(data)
  } catch (err) {
    return res.status(502).json({ error: 'Backend unavailable', message: err.message })
  }
}
