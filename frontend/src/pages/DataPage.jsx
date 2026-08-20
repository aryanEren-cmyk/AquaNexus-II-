import {
  CheckCircle2,
  Database,
  HardDrive,
  RefreshCw,
  Server,
  Waves,
  XCircle,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import { getHealth } from '../services/api.js'

const DATASET_METADATA = [
  {
    title: 'Historical ARGO',
    rows: [
      ['Observation period', '2021–2025'],
      ['Measurement points', '6,454,064'],
      ['Indexed profiles', '14,100'],
      ['Variables', 'Pressure, Temperature, Salinity'],
      ['Vertical coordinate', 'Pressure (dbar)'],
    ],
  },
  {
    title: 'Copernicus Present State',
    rows: [
      ['Product', 'GLOBAL_ANALYSISFORECAST_PHY_001_024'],
      ['Variables', 'Temperature, Salinity, U/V currents'],
      ['Vertical coordinate', 'Model grid depth (m)'],
      ['Data type', 'Gridded analysis/forecast estimate'],
      ['Cache freshness target', '6 hours'],
    ],
  },
  {
    title: 'Operational Coverage',
    rows: [
      ['Longitude', '60°E–100°E'],
      ['Latitude', '0°N–30°N'],
      ['ARGO pressure range', '0–2000 dbar'],
      ['Copernicus depth range', '0–2000 m'],
    ],
  },
]

function DataPage() {
  const [health, setHealth] = useState(null)
  const [checkedAt, setCheckedAt] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function loadHealth() {
    if (isLoading) {
      return
    }

    setIsLoading(true)
    setError('')
    setHealth(null)

    try {
      const response = await getHealth()
      setHealth(response)
      setCheckedAt(new Date())
    } catch (requestError) {
      setCheckedAt(null)
      setError(
        requestError?.message ||
          'Unable to retrieve backend data status.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadHealth()
    // Run once on page mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const caches = health?.caches ?? {}

  return (
    <div className="data-console-page">
      <header className="data-console-hero">
        <div>
          <p className="eyebrow">Data Console</p>
          <h1>Ocean data infrastructure</h1>

          <p className="data-console-intro">
            Runtime cache availability is read directly from the AquaNexus
            backend health endpoint. Dataset metadata below describes the
            verified data products used by the project.
          </p>
        </div>

        <button
          className="data-refresh-button"
          type="button"
          onClick={loadHealth}
          disabled={isLoading}
        >
          <RefreshCw
            size={15}
            className={isLoading ? 'is-spinning' : ''}
          />
          {isLoading ? 'Checking...' : 'Refresh status'}
        </button>
      </header>

      {error && (
        <div
          className="dashboard-error data-console-error"
          role="alert"
        >
          {error}
        </div>
      )}

      <section className="data-runtime-section">
        <div className="data-section-heading">
          <div>
            <p className="eyebrow">Runtime Status</p>
            <h2>Backend &amp; scientific caches</h2>
          </div>

          {checkedAt && (
            <span className="data-checked-at">
              Checked {formatCheckTime(checkedAt)}
            </span>
          )}
        </div>

        <div className="data-status-grid">
          <StatusCard
            icon={<Server size={18} />}
            label="AquaNexus API"
            available={health?.status === 'ok'}
            detail={health?.service}
            loading={isLoading}
          />

          <StatusCard
            icon={<Waves size={18} />}
            label="Copernicus Present State"
            available={caches.copernicus_present_state}
            detail="Present-state model cache"
            loading={isLoading}
          />

          <StatusCard
            icon={<Database size={18} />}
            label="Live ARGO"
            available={caches.live_argo}
            detail="Near-real-time in-situ cache"
            loading={isLoading}
          />

          <StatusCard
            icon={<HardDrive size={18} />}
            label="Historical ARGO Profile Index"
            available={caches.historical_argo_profile_index}
            detail="Spatial profile search index"
            loading={isLoading}
          />
        </div>
      </section>

      <section className="data-runtime-section">
        <div className="data-section-heading">
          <div>
            <p className="eyebrow">Verified Metadata</p>
            <h2>Scientific datasets</h2>
          </div>
        </div>

        <div className="dataset-metadata-grid">
          {DATASET_METADATA.map((dataset) => (
            <article
              className="dataset-metadata-card"
              key={dataset.title}
            >
              <div className="dataset-metadata-title">
                <Database size={16} />
                {dataset.title}
              </div>

              <div className="dataset-row-list">
                {dataset.rows.map(([label, value]) => (
                  <div
                    className="dataset-row"
                    key={label}
                  >
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="data-runtime-section">
        <div className="data-section-heading">
          <div>
            <p className="eyebrow">Data Semantics</p>
            <h2>Observation vs model data</h2>
          </div>
        </div>

        <div className="data-semantics-grid">
          <article className="data-semantics-card">
            <span className="data-semantics-label">ARGO</span>
            <strong>In-situ observation</strong>
            <p>
              Direct ocean-profile observations. Pressure is reported in dbar.
            </p>
          </article>

          <article className="data-semantics-card">
            <span className="data-semantics-label">COPERNICUS</span>
            <strong>Gridded analysis/forecast estimate</strong>
            <p>
              Model-grid ocean fields. Vertical position is represented by model
              depth in meters.
            </p>
          </article>
        </div>
      </section>
    </div>
  )
}

function StatusCard({
  icon,
  label,
  available,
  detail,
  loading,
}) {
  const known = typeof available === 'boolean'

  let statusLabel = 'CHECKING'
  let statusClass = 'is-checking'

  if (!loading && known) {
    statusLabel = available ? 'AVAILABLE' : 'UNAVAILABLE'
    statusClass = available ? 'is-available' : 'is-unavailable'
  }

  return (
    <article className={`data-status-card ${statusClass}`}>
      <div className="data-status-card-top">
        <div className="data-status-icon">
          {icon}
        </div>

        {loading || !known ? (
          <RefreshCw
            size={16}
            className={loading ? 'is-spinning' : ''}
          />
        ) : available ? (
          <CheckCircle2 size={17} />
        ) : (
          <XCircle size={17} />
        )}
      </div>

      <span className="data-status-label">
        {label}
      </span>

      <strong>{statusLabel}</strong>

      <small>{detail || 'Status unavailable'}</small>
    </article>
  )
}

function formatCheckTime(date) {
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}

export default DataPage