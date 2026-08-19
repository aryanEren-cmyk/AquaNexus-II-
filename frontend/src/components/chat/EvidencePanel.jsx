import { ClipboardList, Crosshair, Database, Gauge, History, Layers3 } from 'lucide-react'

function EvidencePanel({ evidence, toolsUsed, modulesUsed }) {
  const latest = evidence?.[evidence.length - 1]
  const result = latest?.result

  return (
    <aside className="evidence-panel" aria-label="Evidence trail">
      <div className="evidence-header">
        <div>
          <p className="eyebrow">Evidence Trail</p>
          <h2>Scientific context</h2>
        </div>
        <ClipboardList size={20} />
      </div>

      <div className="evidence-section">
        <h3>Tools</h3>
        <ChipList values={toolsUsed} emptyLabel="No tool call yet" />
      </div>

      <div className="evidence-section">
        <h3>Modules</h3>
        <ChipList values={modulesUsed} emptyLabel="Awaiting module evidence" uppercase />
      </div>

      {result ? (
        <div className="evidence-stack">
          <EvidenceBlock icon={Database} title="Data source">
            <EvidenceLine label="Source" value={sourceLabel(result)} />
            <EvidenceLine label="Grid cell" value={gridCellLabel(result)} />
            <EvidenceLine label="Distance" value={formatKm(result.present_state?.grid_distance_km)} />
            <EvidenceLine label="Model time" value={modelTime(result)} />
          </EvidenceBlock>

          <EvidenceBlock icon={Crosshair} title="Location">
            <EvidenceLine label="Resolved" value={result.location?.display_name} />
            <EvidenceLine label="Type" value={result.location?.type} />
            <EvidenceLine label="Coordinates" value={resolvedCoordinateLabel(result)} />
          </EvidenceBlock>

          <EvidenceBlock icon={Gauge} title="Depth">
            <EvidenceLine label="Requested" value={formatMeters(result.requested_depth_m)} />
            <EvidenceLine label="Used" value={formatMeters(result.present_state?.depth_used_m)} />
          </EvidenceBlock>

          <EvidenceBlock icon={Layers3} title="Recent ARGO">
            <EvidenceLine label="Availability" value={argoAvailability(result.latest_argo)} />
            <EvidenceLine
              label="Distance"
              value={formatKm(result.latest_argo?.distance_km ?? result.latest_argo?.nearest_distance_km)}
            />
            <EvidenceLine label="Observation time" value={latestArgoTime(result.latest_argo)} />
          </EvidenceBlock>

          <EvidenceBlock icon={History} title="Historical context">
            <EvidenceLine label="Float" value={result.historical_context?.float_id} />
            <EvidenceLine label="Cycle" value={result.historical_context?.cycle} />
            <EvidenceLine label="Distance" value={formatKm(result.historical_context?.distance_km)} />
            <EvidenceLine label="Observation time" value={formatTimestamp(result.historical_context?.observation_time)} />
          </EvidenceBlock>
        </div>
      ) : (
        <div className="empty-evidence">
          Ask a question to populate verified tool evidence from the backend.
        </div>
      )}
    </aside>
  )
}

function EvidenceBlock({ icon: Icon, title, children }) {
  return (
    <section className="evidence-block">
      <div className="evidence-block-title">
        <Icon size={16} />
        {title}
      </div>
      {children}
    </section>
  )
}

function EvidenceLine({ label, value }) {
  return (
    <div className="evidence-line">
      <span>{label}</span>
      <strong>{value ?? 'Not available'}</strong>
    </div>
  )
}

function ChipList({ values, emptyLabel, uppercase = false }) {
  if (!values?.length) return <div className="empty-mini">{emptyLabel}</div>
  return (
    <div className="chip-list">
      {values.map((value) => (
        <span key={value}>{uppercase ? value.toUpperCase() : value}</span>
      ))}
    </div>
  )
}

function sourceLabel(result) {
  return result.present_state?.source || result.source || 'Not available'
}

function modelTime(result) {
  return formatTimestamp(result.present_state?.model_time) || 'Not available'
}

function resolvedCoordinateLabel(result) {
  const location = result.location
  if (location?.latitude != null && location?.longitude != null) {
    return formatCoordinates(location.latitude, location.longitude)
  }
  return null
}

function gridCellLabel(result) {
  const state = result.present_state
  if (state?.latitude_used != null && state?.longitude_used != null) {
    return formatCoordinates(state.latitude_used, state.longitude_used)
  }
  return null
}

function argoAvailability(argo) {
  if (!argo) return 'No recent ARGO evidence'
  if (argo.available === false) return argo.reason || 'Unavailable'
  if (argo.profile_count != null) return `${argo.profile_count} profiles`
  return 'Available'
}

function latestArgoTime(argo) {
  if (!argo) return null
  return formatTimestamp(
    argo.observation_time || argo.latest_observation_time || argo.latest_profile?.observation_time,
  )
}

function formatMeters(value) {
  return value == null ? null : `${formatNumber(value)} m`
}

function formatKm(value) {
  return value == null ? null : `${formatNumber(value)} km`
}

function formatNumber(value) {
  if (typeof value !== 'number') return value
  return Number.isInteger(value) ? `${value}` : value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
}

function formatCoordinates(latitude, longitude) {
  return `${formatCoordinate(latitude, 'N', 'S')}, ${formatCoordinate(longitude, 'E', 'W')}`
}

function formatCoordinate(value, positive, negative) {
  const direction = value >= 0 ? positive : negative
  return `${Math.abs(value).toFixed(3)}°${direction}`
}

function formatTimestamp(value) {
  if (typeof value !== 'string') return value
  const match = value.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$/)
  if (!match) return value
  return `${match[1]} ${match[2]}:${match[3]} UTC`
}

export default EvidencePanel
