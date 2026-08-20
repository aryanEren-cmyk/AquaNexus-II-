import { Activity, Database, Waves } from 'lucide-react'
import { useState } from 'react'

import OceanDashboardCharts from '../components/charts/OceanDashboardCharts.jsx'
import { getOceanConditions } from '../services/api.js'

const SUGGESTED_LOCATIONS = [
  'Arabian Sea',
  'Kochi',
  'Goa',
  '10N 75E',
]

function DashboardPage() {
  const [location, setLocation] = useState('Arabian Sea')
  const [depth, setDepth] = useState(0)
  const [argoRadius, setArgoRadius] = useState(300)

  const [submittedQuery, setSubmittedQuery] = useState(null)
  const [result, setResult] = useState(null)

  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function analyze(event) {
    event?.preventDefault()

    if (isLoading) {
      return
    }

    const trimmedLocation = location.trim()
    const parsedDepth = Number(depth)
    const parsedRadius = Number(argoRadius)

    if (!trimmedLocation) {
      setError('Location cannot be empty.')
      setResult(null)
      setSubmittedQuery(null)
      return
    }

    if (
      !Number.isFinite(parsedDepth) ||
      parsedDepth < 0
    ) {
      setError('Depth must be greater than or equal to 0 m.')
      setResult(null)
      setSubmittedQuery(null)
      return
    }

    if (
      !Number.isFinite(parsedRadius) ||
      parsedRadius <= 0
    ) {
      setError('ARGO radius must be greater than 0 km.')
      setResult(null)
      setSubmittedQuery(null)
      return
    }

    const snapshot = {
      location: trimmedLocation,
      depth: parsedDepth,
      argoRadius: parsedRadius,
    }

    setIsLoading(true)
    setError('')

    // Do not leave stale scientific values visible while a new
    // request is running or when a request fails.
    setResult(null)
    setSubmittedQuery(null)

    try {
      const response = await getOceanConditions(
        snapshot.location,
        snapshot.depth,
        snapshot.argoRadius,
      )

      setSubmittedQuery(snapshot)
      setResult(response)
    } catch (requestError) {
      setError(
        requestError?.message ||
          'Ocean analytics request failed.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  const locationType = result?.location?.type

  return (
    <div className="ocean-dashboard-page">
      <section className="dashboard-hero">
        <div>
          <p className="eyebrow">
            Ocean Analytics
          </p>

          <h1>Regional ocean intelligence</h1>

          <span className="dashboard-query-meta">
            {submittedQuery
              ? `${submittedQuery.location} · ${formatMeters(
                  submittedQuery.depth,
                )} · ARGO ${formatKm(
                  submittedQuery.argoRadius,
                )}`
              : 'Awaiting verified ocean analysis'}
          </span>
        </div>

        <div className="console-chip">
          <Activity size={16} />
          Deterministic data products
        </div>
      </section>

      <form
        className="dashboard-controls"
        onSubmit={analyze}
      >
        <label>
          <span>Location</span>

          <input
            value={location}
            onChange={(event) =>
              setLocation(event.target.value)
            }
            disabled={isLoading}
            placeholder="Arabian Sea"
            aria-label="Ocean analytics location"
          />
        </label>

        <label>
          <span>Depth</span>

          <div className="input-with-unit">
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

            <b>m</b>
          </div>
        </label>

        <label>
          <span>ARGO radius</span>

          <div className="input-with-unit">
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

            <b>km</b>
          </div>
        </label>

        <button
          type="submit"
          disabled={isLoading || !location.trim()}
        >
          {isLoading ? 'Querying...' : 'Analyze'}
        </button>
      </form>

      <div
        className="suggested-locations"
        aria-label="Suggested locations"
      >
        {SUGGESTED_LOCATIONS.map((suggestion) => (
          <button
            type="button"
            key={suggestion}
            onClick={() => setLocation(suggestion)}
            disabled={isLoading}
          >
            {suggestion}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="dashboard-loading">
          <span />
          QUERYING OCEAN ANALYTICS...
        </div>
      )}

      {error && (
        <div
          className="dashboard-error"
          role="alert"
        >
          {error}
        </div>
      )}

      {!result && !isLoading && !error && (
        <DashboardEmptyState />
      )}

      {result && locationType === 'area' && (
        <AreaDashboard
          result={result}
          submittedQuery={submittedQuery}
        />
      )}

      {result && locationType === 'point' && (
        <PointDashboard
          result={result}
          submittedQuery={submittedQuery}
        />
      )}

      {result &&
        locationType !== 'area' &&
        locationType !== 'point' && (
          <div className="dashboard-error">
            Unsupported resolved location type.
          </div>
        )}
    </div>
  )
}

function DashboardEmptyState() {
  return (
    <section className="dashboard-empty-state">
      <Database size={22} />

      <div>
        <strong>
          Query verified ocean conditions
        </strong>

        <p>
          Analyze a named region, coastal location or coordinate.
          AquaNexus will render only the scientific values returned by
          the deterministic ocean-data backend.
        </p>
      </div>
    </section>
  )
}

function AreaDashboard({
  result,
  submittedQuery,
}) {
  const state = result?.present_state
  const location = result?.location

  return (
    <>
      <section className="dashboard-summary-grid">
        <SummaryCard
          label="Mean Temperature"
          value={formatCelsius(
            state?.temperature_c?.mean,
          )}
          detail="Copernicus regional estimate"
        />

        <SummaryCard
          label="Mean Salinity"
          value={formatSalinity(
            state?.salinity?.mean,
          )}
          detail="Copernicus regional estimate"
        />

        <SummaryCard
          label="Valid Grid Cells"
          value={formatInteger(
            state?.valid_grid_cells,
          )}
          detail="Valid model cells in resolved region"
        />

        <SummaryCard
          label="Model Time"
          value={formatTimestamp(
            state?.model_time,
          )}
          detail="Copernicus model timestamp"
        />
      </section>

      <OceanDashboardCharts result={result} />

      <section className="dashboard-area-context-grid">
        <DashboardPanel
          title="REGION CONTEXT"
          subtitle="Resolved spatial query"
        >
          <MetricRow
            label="Resolved"
            value={location?.display_name}
          />

          <MetricRow
            label="Bounding box"
            value={formatBoundingBox(
              location?.bounding_box,
            )}
          />

          <MetricRow
            label="Requested depth"
            value={formatMeters(
              result?.requested_depth_m ??
                submittedQuery?.depth,
            )}
          />

          <MetricRow
            label="Model grid depth"
            value={formatMeters(
              state?.depth_used_m,
            )}
          />

          <MetricRow
            label="Data type"
            value={
              state?.terminology ||
              'Copernicus Marine gridded analysis/forecast estimate'
            }
          />
        </DashboardPanel>

        <ArgoCoverage
          argo={result?.latest_argo}
          isArea
        />
      </section>

      <DataNotes notes={result?.data_notes}>
        Regional statistics are summaries and do not represent
        every point within the resolved area.
      </DataNotes>
    </>
  )
}

function PointDashboard({
  result,
  submittedQuery,
}) {
  const state = result?.present_state
  const resolvedLocation = result?.location

  return (
    <>
      <section className="dashboard-summary-grid">
        <SummaryCard
          label="Temperature"
          value={formatCelsius(
            state?.temperature_c,
          )}
          detail="Copernicus model estimate"
        />

        <SummaryCard
          label="Salinity"
          value={formatSalinity(
            state?.salinity,
          )}
          detail="Copernicus model estimate"
        />

        <SummaryCard
          label="Eastward Current"
          value={formatVelocity(
            state?.eastward_current_m_s,
          )}
          detail="Copernicus model estimate"
        />

        <SummaryCard
          label="Northward Current"
          value={formatVelocity(
            state?.northward_current_m_s,
          )}
          detail="Copernicus model estimate"
        />
      </section>

      <section className="dashboard-point-layout">
        <DashboardPanel
          title="LOCATION CONTEXT"
          subtitle="Resolved request"
        >
          <MetricRow
            label="Resolved"
            value={resolvedLocation?.display_name}
          />

          <MetricRow
            label="Requested coordinates"
            value={formatCoordinates(
              resolvedLocation?.latitude,
              resolvedLocation?.longitude,
            )}
          />

          <MetricRow
            label="Requested depth"
            value={formatMeters(
              result?.requested_depth_m ??
                submittedQuery?.depth,
            )}
          />
        </DashboardPanel>

        <DashboardPanel
          title="COPERNICUS MODEL GRID"
          subtitle="Gridded analysis/forecast estimate"
        >
          <MetricRow
            label="Grid coordinates"
            value={formatCoordinates(
              state?.latitude_used,
              state?.longitude_used,
            )}
          />

          <MetricRow
            label="Grid distance"
            value={formatKm(
              state?.grid_distance_km,
            )}
          />

          <MetricRow
            label="Model grid depth"
            value={formatMeters(
              state?.depth_used_m,
            )}
          />

          <MetricRow
            label="Model time"
            value={formatTimestamp(
              state?.model_time,
            )}
          />
        </DashboardPanel>
      </section>

      <ArgoCoverage
        argo={result?.latest_argo}
        isArea={false}
      />

      <HistoricalContext
        historical={result?.historical_context}
      />

      <DataNotes notes={result?.data_notes} />
    </>
  )
}

function ArgoCoverage({
  argo,
  isArea,
}) {
  if (!argo) {
    return (
      <DashboardPanel
        title="IN-SITU ARGO CONTEXT"
        subtitle="Observation availability"
      >
        <div className="dashboard-unavailable">
          ARGO context unavailable.
        </div>
      </DashboardPanel>
    )
  }

  if (argo.available === false) {
    return (
      <DashboardPanel
        title="IN-SITU ARGO CONTEXT"
        subtitle="Observation availability"
      >
        <MetricRow
          label="Status"
          value="No recent ARGO observation within radius"
        />

        <MetricRow
          label="Nearest distance"
          value={formatKm(
            argo.nearest_distance_km,
          )}
        />

        <p className="scientific-note">
          {argo.reason ||
            'No qualifying recent in-situ ARGO observation was returned.'}
        </p>
      </DashboardPanel>
    )
  }

  const latestProfile =
    argo?.latest_profile ??
    argo?.latest_observation ??
    null

  const surfaceObservation =
    latestProfile?.surface_like_observation ??
    argo?.surface_like_observation ??
    null

  return (
    <DashboardPanel
      title={
        isArea
          ? 'IN-SITU ARGO COVERAGE'
          : 'RECENT IN-SITU ARGO'
      }
      subtitle="In-situ observation context"
    >
      {isArea && (
        <>
          <MetricRow
            label="Profiles"
            value={formatInteger(
              argo?.profile_count,
            )}
          />

          <MetricRow
            label="Unique floats"
            value={formatInteger(
              argo?.unique_floats,
            )}
          />
        </>
      )}

      <MetricRow
        label="Latest observation"
        value={formatTimestamp(
          argo?.latest_observation_time ??
            argo?.latest_time ??
            latestProfile?.observation_time ??
            latestProfile?.time,
        )}
      />

      <MetricRow
        label="Float"
        value={
          argo?.float_id ??
          latestProfile?.float_id ??
          latestProfile?.platform_number
        }
      />

      <MetricRow
        label="Cycle"
        value={
          argo?.cycle ??
          latestProfile?.cycle ??
          latestProfile?.cycle_number
        }
      />

      <MetricRow
        label="Position"
        value={formatCoordinates(
          argo?.latitude ??
            latestProfile?.latitude,
          argo?.longitude ??
            latestProfile?.longitude,
        )}
      />

      <MetricRow
        label="Pressure"
        value={formatDbar(
          argo?.pressure_dbar ??
            surfaceObservation?.pressure_dbar,
        )}
      />

      <MetricRow
        label="Temperature"
        value={formatCelsius(
          argo?.temperature_c ??
            surfaceObservation?.temperature_c ??
            surfaceObservation?.temperature,
        )}
      />

      <MetricRow
        label="Salinity"
        value={formatSalinity(
          argo?.salinity ??
            surfaceObservation?.salinity,
        )}
      />

      <p className="scientific-note">
        ARGO values are in-situ observations. Pressure is reported
        in dbar and is not converted to exact depth in meters.
      </p>
    </DashboardPanel>
  )
}

function HistoricalContext({
  historical,
}) {
  if (!historical) {
    return null
  }

  return (
    <DashboardPanel
      title="HISTORICAL ARGO CONTEXT"
      subtitle="Historical in-situ observation"
    >
      <MetricRow
        label="Float"
        value={historical?.float_id}
      />

      <MetricRow
        label="Cycle"
        value={historical?.cycle}
      />

      <MetricRow
        label="Position"
        value={formatCoordinates(
          historical?.latitude,
          historical?.longitude,
        )}
      />

      <MetricRow
        label="Observation"
        value={formatTimestamp(
          historical?.observation_time,
        )}
      />

      <MetricRow
        label="Distance"
        value={formatKm(
          historical?.distance_km,
        )}
      />

      <p className="scientific-note">
        Historical context is not presented as a current observation.
      </p>
    </DashboardPanel>
  )
}

function DashboardPanel({
  title,
  subtitle,
  children,
}) {
  return (
    <section className="dashboard-panel">
      <div className="dashboard-panel__title">
        <span>{title}</span>
        {subtitle && <small>{subtitle}</small>}
      </div>

      <div className="dashboard-metric-list">
        {children}
      </div>
    </section>
  )
}

function MetricRow({
  label,
  value,
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  )
}

function SummaryCard({
  label,
  value,
  detail,
}) {
  return (
    <article className="dashboard-summary-card">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
      {detail && <small>{detail}</small>}
    </article>
  )
}

function DataNotes({
  notes,
  children,
}) {
  const returnedNotes = Array.isArray(notes)
    ? notes
    : []

  if (!returnedNotes.length && !children) {
    return null
  }

  return (
    <section className="dashboard-panel dashboard-data-notes">
      <div className="dashboard-panel__title">
        <span>DATA NOTES</span>
        <small>Scientific interpretation</small>
      </div>

      {returnedNotes.map((note) => (
        <p
          className="scientific-note"
          key={note}
        >
          {note}
        </p>
      ))}

      {children && (
        <p className="scientific-note">
          {children}
        </p>
      )}
    </section>
  )
}

function displayValue(value) {
  return value == null || value === ''
    ? 'Unavailable'
    : value
}

function formatCelsius(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(value, 2)} °C`
    : null
}

function formatSalinity(value) {
  return isFiniteNumber(value)
    ? formatNumber(value, 3)
    : null
}

function formatVelocity(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(value, 3)} m/s`
    : null
}

function formatMeters(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(value, 3)} m`
    : null
}

function formatKm(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(value, 3)} km`
    : null
}

function formatDbar(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(value, 1)} dbar`
    : null
}

function formatInteger(value) {
  return Number.isInteger(value)
    ? value.toLocaleString()
    : null
}

function formatCoordinates(
  latitude,
  longitude,
) {
  if (
    !isFiniteNumber(latitude) ||
    !isFiniteNumber(longitude)
  ) {
    return null
  }

  return `${formatCoordinate(
    latitude,
    'N',
    'S',
  )}, ${formatCoordinate(
    longitude,
    'E',
    'W',
  )}`
}

function formatCoordinate(
  value,
  positive,
  negative,
) {
  const direction =
    value >= 0
      ? positive
      : negative

  return `${Math.abs(value).toFixed(
    3,
  )}°${direction}`
}

function formatBoundingBox(box) {
  if (
    !box ||
    !isFiniteNumber(box.south) ||
    !isFiniteNumber(box.north) ||
    !isFiniteNumber(box.west) ||
    !isFiniteNumber(box.east)
  ) {
    return null
  }

  return (
    `${formatCoordinate(
      box.south,
      'N',
      'S',
    )} – ${formatCoordinate(
      box.north,
      'N',
      'S',
    )}, ` +
    `${formatCoordinate(
      box.west,
      'E',
      'W',
    )} – ${formatCoordinate(
      box.east,
      'E',
      'W',
    )}`
  )
}

function formatTimestamp(value) {
  if (typeof value !== 'string') {
    return value
  }

  const match = value.match(
    /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$/,
  )

  if (!match) {
    return value
  }

  return `${match[1]} ${match[2]}:${match[3]} UTC`
}

function formatNumber(
  value,
  digits,
) {
  return value
    .toFixed(digits)
    .replace(/0+$/, '')
    .replace(/\.$/, '')
}

function isFiniteNumber(value) {
  return (
    typeof value === 'number' &&
    Number.isFinite(value)
  )
}

export default DashboardPage