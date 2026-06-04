import { useState, useEffect, Fragment } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../apiClient'
import ProfileTab from './tabs/ProfileTab'
import CVStudioTab from './tabs/CVStudioTab'
import PositioningTab from './tabs/PositioningTab'
import MarketRadarTab from './tabs/MarketRadarTab'
import OpportunitiesTab from './tabs/OpportunitiesTab'
import NotesActionsTab from './tabs/NotesActionsTab'
import AdvisorBriefTab from './tabs/AdvisorBriefTab'
import ComingSoon from './tabs/ComingSoon'

const TABS = [
  { key: 'profile',       label: 'Profile',        live: true  },
  { key: 'cv-studio',     label: 'CV Studio',       live: true  },
  { key: 'positioning',   label: 'Positioning',     live: true  },
  { key: 'radar',         label: 'Market Radar',    live: true  },
  { key: 'opportunities', label: 'Opportunities',   live: true  },
  { key: 'notes',         label: 'Notes & Actions', live: true  },
  { key: 'brief',         label: 'Advisor Brief',   live: true  },
]

const LIVE_KEYS = new Set(TABS.filter(t => t.live).map(t => t.key))

const STATUS_STEPS = [
  { label: 'Profile',     check: c => Boolean(c.profile?.name || c.profile?.current_role) },
  { label: 'CV',          check: c => Boolean(c.profile?.cv_text?.trim()) },
  { label: 'Positioning', check: c => Boolean(c.positioning) },
  { label: 'Radar',       check: c => Boolean(c.market_radar || c.market_radar_raw) },
  { label: 'Opps',        check: c => Boolean(c.opportunities?.length) },
  { label: 'Notes',       check: c => Boolean(c.session_notes?.length || c.action_items?.length) },
  { label: 'Brief',       check: c => Boolean(c.advisor_brief || c.advisor_brief_raw) },
]

function WorkspaceStatusBar({ client }) {
  return (
    <div className="os-workspace-status-bar">
      {STATUS_STEPS.map(step => {
        const done = step.check(client)
        return (
          <span
            key={step.label}
            className={`os-status-chip${done ? ' os-status-chip--done' : ''}`}
          >
            {done ? '✓' : '·'} {step.label}
          </span>
        )
      })}
    </div>
  )
}

export default function ClientWorkspace() {
  const { id } = useParams()
  const [client, setClient]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [activeTab, setTab]   = useState('profile')

  useEffect(() => {
    api.getClient(id)
      .then(setClient)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [id])

  const clientName = client?.profile?.name || 'Client'

  return (
    <div className="os-page">
      <nav className="os-nav">
        <Link to="/dashboard" className="os-nav-back">← Clients</Link>
        <span className="os-nav-sep">|</span>
        <span className="os-nav-label">{loading ? '…' : clientName}</span>
      </nav>

      <main className="os-main">
        {error && <div className="os-error">{error}</div>}

        {loading ? (
          <div className="os-loading">Loading client…</div>
        ) : client ? (
          <>
            <div className="os-page-header" style={{ marginBottom: 0 }}>
              <div>
                <h1 className="os-page-title">{clientName}</h1>
                {client.profile?.current_role && (
                  <p className="os-page-subtitle">{client.profile.current_role}</p>
                )}
              </div>
            </div>

            <WorkspaceStatusBar client={client} />

            <nav className="os-tabs">
              {TABS.map((tab, idx) => (
                <Fragment key={tab.key}>
                  {idx === 2 && <div className="os-tab-separator" />}
                  <button
                    className={[
                      'os-tab',
                      activeTab === tab.key ? 'os-tab--active' : '',
                      !tab.live ? 'os-tab--disabled' : '',
                    ].join(' ')}
                    onClick={() => tab.live && setTab(tab.key)}
                    aria-disabled={!tab.live}
                    title={!tab.live ? 'Coming soon' : undefined}
                  >
                    {tab.label}
                  </button>
                </Fragment>
              ))}
            </nav>

            {activeTab === 'profile' && (
              <ProfileTab client={client} onSave={setClient} />
            )}
            {activeTab === 'cv-studio' && (
              <CVStudioTab client={client} onUpdate={setClient} />
            )}
            {activeTab === 'positioning' && (
              <PositioningTab client={client} onUpdate={setClient} />
            )}
            {activeTab === 'radar' && (
              <MarketRadarTab client={client} onUpdate={setClient} />
            )}
            {activeTab === 'opportunities' && (
              <OpportunitiesTab client={client} onUpdate={setClient} />
            )}
            {activeTab === 'notes' && (
              <NotesActionsTab client={client} onUpdate={setClient} />
            )}
            {activeTab === 'brief' && (
              <AdvisorBriefTab client={client} onUpdate={setClient} />
            )}
            {!LIVE_KEYS.has(activeTab) && (
              <ComingSoon tab={TABS.find(t => t.key === activeTab)?.label} />
            )}
          </>
        ) : null}
      </main>
    </div>
  )
}
