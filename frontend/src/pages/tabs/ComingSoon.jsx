export default function ComingSoon({ tab }) {
  return (
    <div className="os-coming-soon">
      <p className="os-coming-soon-title">{tab || 'This section'} — Coming soon</p>
      <p className="os-coming-soon-body">
        This module is planned for a future version.
      </p>
    </div>
  )
}
