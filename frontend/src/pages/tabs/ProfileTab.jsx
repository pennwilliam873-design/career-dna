import { useState, useRef } from 'react'
import { api } from '../../apiClient'

const EMPTY_PROFILE = {
  name: '',
  current_role: '',
  location: '',
  target_geography: '',
  desired_next_move: '',
  timeframe: '',
  roles_wanted: '',
  roles_not_wanted: '',
  constraints: '',
  relationship_assets: '',
  advisor_notes: '',
  cv_text: '',
}

export default function ProfileTab({ client, onSave }) {
  const [form, setForm]     = useState({ ...EMPTY_PROFILE, ...client.profile })
  const [saving,      setSaving]      = useState(false)
  const [saved,       setSaved]       = useState(false)
  const [error,       setError]       = useState('')
  const [extracting,  setExtracting]  = useState(false)
  const [extractWarn, setExtractWarn] = useState('')
  const fileRef = useRef(null)

  function handleChange(e) {
    const { name, value } = e.target
    setForm(prev => ({ ...prev, [name]: value }))
    setSaved(false)
  }

  async function handleFileUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''   // allow re-selecting the same file
    setExtracting(true)
    setExtractWarn('')
    setError('')
    try {
      const result = await api.extractCvFile(client.id, file)
      setForm(prev => ({ ...prev, cv_text: result.text || '' }))
      setSaved(false)
      if (result.warning) setExtractWarn(result.warning)
    } catch (err) {
      setError(err.message)
      // Leave existing cv_text unchanged on error
    } finally {
      setExtracting(false)
    }
  }

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const updated = await api.updateClient(client.id, form)
      onSave(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSave}>
      {error && <div className="os-error">{error}</div>}

      <div className="os-section-title">Identity</div>
      <div className="os-form-grid">
        <Field label="Client Name" name="name" value={form.name} onChange={handleChange} />
        <Field label="Current Role" name="current_role" value={form.current_role} onChange={handleChange} />
        <Field label="Location" name="location" value={form.location} onChange={handleChange} />
        <Field label="Target Geography" name="target_geography" value={form.target_geography} onChange={handleChange} />
      </div>

      <div className="os-section-title">Transition Goals</div>
      <div className="os-form-grid">
        <TextAreaField
          label="Desired Next Move"
          name="desired_next_move"
          value={form.desired_next_move}
          onChange={handleChange}
          rows={2}
          placeholder="e.g. Move from advisory into a PE operating partner seat"
        />
        <Field
          label="Timeframe"
          name="timeframe"
          value={form.timeframe}
          onChange={handleChange}
          placeholder="e.g. 12 months, Q4 2026"
        />
        <TextAreaField
          label="Roles They Want"
          name="roles_wanted"
          value={form.roles_wanted}
          onChange={handleChange}
          rows={2}
          placeholder="Role types, sectors, structures they are actively targeting"
        />
        <TextAreaField
          label="Roles They Do Not Want"
          name="roles_not_wanted"
          value={form.roles_not_wanted}
          onChange={handleChange}
          rows={2}
          placeholder="Role types, organisations, or situations to exclude"
        />
      </div>

      <div className="os-section-title">Context</div>
      <div className="os-form-grid">
        <TextAreaField
          label="Constraints"
          name="constraints"
          value={form.constraints}
          onChange={handleChange}
          rows={2}
          placeholder="Geography, compensation floor, notice period, family situation, etc."
        />
        <TextAreaField
          label="Relationship Assets"
          name="relationship_assets"
          value={form.relationship_assets}
          onChange={handleChange}
          rows={2}
          placeholder="Key networks, sponsors, board relationships, fund connections"
        />
        <div className="os-form-field os-form-field--full">
          <label className="os-label">Advisor Notes</label>
          <textarea
            className="os-textarea"
            name="advisor_notes"
            value={form.advisor_notes}
            onChange={handleChange}
            rows={3}
            placeholder="Private notes for the advisor — not shared with the client"
          />
        </div>
      </div>

      <div className="os-section-title">CV / Career History</div>
      <div className="os-form-grid">
        <div className="os-form-field os-form-field--full">
          <label className="os-label">CV Text</label>
          <textarea
            className="os-textarea"
            name="cv_text"
            value={form.cv_text}
            onChange={handleChange}
            rows={12}
            placeholder="Paste the full CV here, or upload a file below"
          />
          <div className="os-upload-row">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
              style={{ display: 'none' }}
              onChange={handleFileUpload}
            />
            <button
              type="button"
              className="os-btn os-btn--secondary"
              style={{ fontSize: 12, padding: '6px 12px' }}
              onClick={() => fileRef.current?.click()}
              disabled={extracting}
            >
              {extracting ? 'Extracting…' : 'Upload CV file'}
            </button>
            <span className="os-upload-hint">Replaces pasted text above</span>
          </div>
          {extractWarn && (
            <div className="os-raw-warning" style={{ marginTop: 6 }}>
              {extractWarn}
            </div>
          )}
        </div>
      </div>

      <p className="os-upload-hint" style={{ marginTop: 6, lineHeight: 1.55 }}>
        Private MVP testing only. Avoid uploading highly sensitive personal information.
        Outputs are generated using third-party AI (Anthropic Claude) and search (Tavily) APIs.
      </p>

      <div className="os-form-actions">
        <button type="submit" className="os-btn os-btn--primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save Profile'}
        </button>
        {saved && <span className="os-save-msg">Saved</span>}
      </div>
    </form>
  )
}

function Field({ label, name, value, onChange, placeholder }) {
  return (
    <div className="os-form-field">
      <label className="os-label">{label}</label>
      <input
        className="os-input"
        type="text"
        name={name}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
      />
    </div>
  )
}

function TextAreaField({ label, name, value, onChange, rows = 3, placeholder }) {
  return (
    <div className="os-form-field">
      <label className="os-label">{label}</label>
      <textarea
        className="os-textarea"
        name={name}
        value={value}
        onChange={onChange}
        rows={rows}
        placeholder={placeholder}
      />
    </div>
  )
}
