export default function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const accessCode = process.env.ACCESS_CODE

  // If ACCESS_CODE is not configured, allow through (local dev or unconfigured)
  if (!accessCode) {
    return res.status(200).json({ ok: true })
  }

  const { code } = req.body || {}

  if (!code || code.trim() !== accessCode.trim()) {
    return res.status(200).json({ ok: false })
  }

  return res.status(200).json({ ok: true })
}
