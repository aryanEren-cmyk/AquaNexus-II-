import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  CircleAlert,
  Database,
  Info,
  Radar,
  ShieldCheck,
} from 'lucide-react'
import { useState } from 'react'

import { scanAlerts } from '../services/api.js'

const SUGGESTED_LOCATIONS = [
  'Kochi',
  'Goa',
  'Arabian Sea',
  '10N 75E',
]

const STATUS_META = {
  normal: {
    label: 'NORMAL',
    description:
      'No operational advisories were generated from the available evidence.',
    icon: CheckCircle2,
  },
  advisory: {
    label: 'ADVISORY',
    description:
      'One or more evidence-backed observation or coverage advisories require attention.',
    icon: Info,
  },
  attention: {
    label: 'ATTENTION',
    description:
      'One or more scientific data sources were unavailable for this scan.',
    icon: AlertTriangle,
  },
  information: {
    label: 'INFORMATION',
    description:
      'The scan returned informational scientific context.',
    icon: Info,
  },
}

const SEVERITY_META = {
  warning: {
    label: 'WARNING',
    icon: AlertTriangle,
  },
  advisory: {
    label: 'ADVISORY',
    icon: CircleAlert,
  },
  info: {
    label: 'INFO',
    icon: Info,
  },
}

function AlertsPage() {
  const [location, setLocation] = useState('Kochi')
  const [depth, setDepth] = useState(0)
  const [argoRadius, setArgoRadius] = useState(300)

  const [result, setResult] = useState(null)
  const [submittedQuery, setSubmittedQuery] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function handleScan(event) {
    event?.preventDefault()

    const trimmedLocation = location.trim()

    if (!trimmedLocation || isLoading) {
      return
    }

    const parsedDepth = Number(depth)
    const parsedRadius = Number(argoRadius)

    if (!Number.isFinite(parsedDepth) || parsedDepth < 0) {
      setError('Depth must be greater than or equal to 0 m.')
      setResult(null)
      setSubmittedQuery(null)
      return
    }

    if (!Number.isFinite(parsedRadius) || parsedRadius <= 0) {
      setError('ARGO radius must be greater than 0 km.')
      setResult(null)
      setSubmittedQuery(null)
      return
    }

    const querySnapshot = {
      location: trimmedLocation,
      depth: parsedDepth,
      argoRadius: parsedRadius,
    }

    setIsLoading(true)
    setError('')
    setResult(null)
    setSubmittedQuery(null)

    try {
      const response = await scanAlerts(
        querySnapshot.location,
        querySnapshot.depth,
        querySnapshot.argoRadius,
      )

      setSubmittedQuery(querySnapshot)
      setResult(response)
    } catch (requestError) {
      setError(
        requestError?.message ||
          'Unable to scan AquaNexus alerts.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  const statusMeta =
    STATUS_META[result?.status] ||
    STATUS_META.information

  const StatusIcon = statusMeta.icon

  return (
    <div className="alerts-page">
      <section className="alerts-workstation">
        <header className="alerts-header">
          <div>
            <p className="eyebrow">Operational Advisories</p>
            <h1>Scientific alert console</h1>
            <p className="alerts-intro">
              AquaNexus reports deterministic data-availability and
              observation-coverage advisories. This console does not infer
              environmental hazards from arbitrary ocean thresholds.
            </p>
          </div>

          <div className="console-chip">
            <ShieldCheck size={16} />
            Evidence-backed only
          </div>
        </header>

        <form
          className="alerts-control-bar"
          onSubmit={handleScan}
        >
          <label className="alerts-location-field">
            <span>Location</span>

            <input
              value={location}
              onChange={(event) =>
                setLocation(event.target.value)
              }
              disabled={isLoading}
              aria-label="Alert scan location"
            />
          </label>

          <label className="alerts-number-field">
            <span>Depth</span>

            <input
              type="number"
              min="0"
              step="1"
              value={depth}
              onChange={(event) =>
                setDepth(event.target.value)
              }
              disabled={isLoading}
              aria-label="Depth in meters"
            />

            <em>m</em>
          </label>

          <label className="alerts-number-field">
            <span>ARGO radius</span>

            <input
              type="number"
              min="1"
              step="1"
              value={argoRadius}
              onChange={(event) =>
                setArgoRadius(event.target.value)
              }
              disabled={isLoading}
              aria-label="ARGO radius in kilometers"
            />

            <em>km</em>
          </label>

          <button
            type="submit"
            disabled={
              isLoading ||
              !location.trim()
            }
          >
            <Radar size={15} />
            {isLoading ? 'Scanning...' : 'Scan alerts'}
          </button>
        </form>

        <div
          className="suggested-prompts"
          aria-label="Suggested alert locations"
        >
          {SUGGESTED_LOCATIONS.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setLocation(item)}
              disabled={isLoading}
            >
              {item}
            </button>
          ))}
        </div>

        {error && (
          <div
            className="dashboard-error alerts-error"
            role="alert"
          >
            <AlertTriangle size={16} />
            {error}
          </div>
        )}

        {!result && !error && !isLoading && (
          <section className="alerts-empty-state">
            <BellRing size={24} />

            <div>
              <strong>Ready to scan</strong>
              <p>
                Choose a supported location and run an evidence-backed
                operational advisory scan.
              </p>
            </div>
          </section>
        )}

        {isLoading && (
          <section
            className="alerts-empty-state"
            aria-live="polite"
          >
            <Radar
              size={24}
              className="is-spinning"
            />

            <div>
              <strong>Scanning scientific evidence</strong>
              <p>
                Checking Copernicus present-state availability and ARGO
                observation coverage.
              </p>
            </div>
          </section>
        )}

        {result && submittedQuery && (
          <div className="alerts-results">
            <section
              className={`alerts-status-card alerts-status-${result.status}`}
            >
              <div className="alerts-status-main">
                <StatusIcon size={22} />

                <div>
                  <span>SCAN STATUS</span>
                  <strong>{statusMeta.label}</strong>
                  <p>{statusMeta.description}</p>
                </div>
              </div>

              <div className="alerts-status-location">
                <span>Resolved location</span>
                <strong>
                  {result.location?.display_name ||
                    submittedQuery.location}
                </strong>
              </div>
            </section>

            <section className="alerts-summary-grid">
              <SummaryCard
                label="Total alerts"
                value={result.alert_count ?? 0}
              />

              <SummaryCard
                label="Warnings"
                value={result.severity_counts?.warning ?? 0}
              />

              <SummaryCard
                label="Advisories"
                value={result.severity_counts?.advisory ?? 0}
              />

              <SummaryCard
                label="Information"
                value={result.severity_counts?.info ?? 0}
              />
            </section>

            <section className="alerts-section">
              <div className="alerts-section-heading">
                <div>
                  <p className="eyebrow">Generated Signals</p>
                  <h2>Evidence-backed advisories</h2>
                </div>

                <span className="alerts-count">
                  {result.alert_count ?? 0} result
                  {(result.alert_count ?? 0) === 1 ? '' : 's'}
                </span>
              </div>

              {(result.alerts || []).length === 0 ? (
                <div className="alerts-normal-state">
                  <CheckCircle2 size={22} />

                  <div>
                    <strong>No advisories generated</strong>
                    <p>
                      Available evidence did not trigger any currently
                      implemented operational advisory rule.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="alerts-list">
                  {result.alerts.map((alert) => (
                    <AlertCard
                      key={alert.code}
                      alert={alert}
                    />
                  ))}
                </div>
              )}
            </section>

            <section className="alerts-section">
              <div className="alerts-section-heading">
                <div>
                  <p className="eyebrow">Evidence Status</p>
                  <h2>Sources used by this scan</h2>
                </div>

                <Database size={19} />
              </div>

              <div className="alerts-evidence-grid">
                <EvidenceAvailability
                  label="Copernicus present state"
                  available={
                    result.evidence_summary
                      ?.copernicus_present_state_available
                  }
                  description="Gridded analysis/forecast estimate"
                />

                <EvidenceAvailability
                  label="Live ARGO"
                  available={
                    result.evidence_summary
                      ?.live_argo_available
                  }
                  description="Near-real-time in-situ observation"
                />

                {result.location?.type === 'point' && (
                  <EvidenceAvailability
                    label="Historical ARGO context"
                    available={
                      result.evidence_summary
                        ?.historical_context_available
                    }
                    description="Historical in-situ comparison context"
                  />
                )}
              </div>

              <div className="alerts-query-evidence">
                <EvidenceRow
                  label="Requested depth"
                  value={`${formatNumber(
                    result.requested_depth_m,
                    2,
                  )} m`}
                />

                <EvidenceRow
                  label="ARGO radius"
                  value={`${formatNumber(
                    result.argo_radius_km,
                    2,
                  )} km`}
                />

                <EvidenceRow
                  label="Location type"
                  value={result.location?.type || '—'}
                />

                <EvidenceRow
                  label="Source runtime"
                  value={
                    Number.isFinite(
                      Number(
                        result.evidence_summary
                          ?.source_runtime_seconds,
                      ),
                    )
                      ? `${formatNumber(
                          result.evidence_summary
                            .source_runtime_seconds,
                          3,
                        )} s`
                      : '—'
                  }
                />
              </div>
            </section>

            <section className="alerts-scientific-note">
              <ShieldCheck size={17} />

              <div>
                <strong>Scientific interpretation</strong>
                <p>
                  These are operational scientific advisories, not hazard
                  warnings. Copernicus values are gridded analysis/forecast
                  estimates. ARGO values are in-situ observations, and ARGO
                  pressure remains expressed in dbar.
                </p>
              </div>
            </section>
          </div>
        )}
      </section>
    </div>
  )
}

function SummaryCard({
  label,
  value,
}) {
  return (
    <article className="alerts-summary-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  )
}

function AlertCard({ alert }) {
  const severity =
    SEVERITY_META[alert.severity] ||
    SEVERITY_META.info

  const SeverityIcon = severity.icon
  const evidenceEntries =
    Object.entries(alert.evidence || {})

  return (
    <article
      className={`alert-card alert-${alert.severity || 'info'}`}
    >
      <div className="alert-card-header">
        <div className="alert-title-group">
          <SeverityIcon size={18} />

          <div>
            <span className="alert-severity">
              {severity.label}
            </span>
            <h3>{alert.title}</h3>
          </div>
        </div>

        <span className="alert-source">
          {alert.source || 'AquaNexus'}
        </span>
      </div>

      <p className="alert-message">
        {alert.message}
      </p>

      <div className="alert-code-row">
        <span>Rule</span>
        <code>{alert.code}</code>
      </div>

      {evidenceEntries.length > 0 && (
        <div className="alert-evidence-list">
          {evidenceEntries.map(
            ([key, value]) => (
              <EvidenceRow
                key={key}
                label={humanizeKey(key)}
                value={formatEvidenceValue(
                  key,
                  value,
                )}
              />
            ),
          )}
        </div>
      )}
    </article>
  )
}

function EvidenceAvailability({
  label,
  available,
  description,
}) {
  const isAvailable = available === true
  const isUnavailable = available === false

  return (
    <article
      className={`alerts-evidence-card ${
        isAvailable
          ? 'is-available'
          : isUnavailable
            ? 'is-unavailable'
            : 'is-not-applicable'
      }`}
    >
      <div>
        {isAvailable ? (
          <CheckCircle2 size={17} />
        ) : isUnavailable ? (
          <CircleAlert size={17} />
        ) : (
          <Info size={17} />
        )}

        <span>{label}</span>
      </div>

      <strong>
        {isAvailable
          ? 'AVAILABLE'
          : isUnavailable
            ? 'UNAVAILABLE'
            : 'NOT APPLICABLE'}
      </strong>

      <small>{description}</small>
    </article>
  )
}

function EvidenceRow({
  label,
  value,
}) {
  return (
    <div className="alert-evidence-row">
      <span>{label}</span>
      <strong>{value ?? '—'}</strong>
    </div>
  )
}

function humanizeKey(value) {
  return String(value)
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase(),
    )
}

function formatEvidenceValue(
  key,
  value,
) {
  if (value === null || value === undefined) {
    return '—'
  }

  const numericValue = Number(value)

  if (
    Number.isFinite(numericValue) &&
    typeof value !== 'boolean'
  ) {
    if (key.endsWith('_km')) {
      return `${formatNumber(
        numericValue,
        3,
      )} km`
    }

    if (key.endsWith('_dbar')) {
      return `${formatNumber(
        numericValue,
        3,
      )} dbar`
    }

    if (key.endsWith('_m')) {
      return `${formatNumber(
        numericValue,
        3,
      )} m`
    }

    return formatNumber(numericValue, 3)
  }

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }

  return String(value)
}

function formatNumber(
  value,
  decimals = 2,
) {
  const numericValue = Number(value)

  if (!Number.isFinite(numericValue)) {
    return '—'
  }

  return numericValue.toLocaleString(
    undefined,
    {
      maximumFractionDigits: decimals,
    },
  )
}

export default AlertsPage