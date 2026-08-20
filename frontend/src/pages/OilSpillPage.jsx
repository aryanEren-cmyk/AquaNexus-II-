import 'leaflet/dist/leaflet.css'
import '../styles/oil-spill.css'

import L from 'leaflet'
import {
  AlertTriangle,
  Crosshair,
  Database,
  MapPinned,
  Radar,
  Satellite,
  ShieldCheck,
  Waves,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  MapContainer,
  Marker,
  Polyline,
  Popup,
  Rectangle,
  TileLayer,
  useMap,
} from 'react-leaflet'

import { getOilSpillInsights } from '../services/api.js'

const DEFAULT_CENTER = [19.054999, 72.8692035]

const SUGGESTED_LOCATIONS = [
  'Mumbai',
  'Kochi',
  'Goa',
  '15N 70E',
]

function OilSpillPage() {
  const [location, setLocation] = useState('Mumbai')
  const [sceneDays, setSceneDays] = useState(30)
  const [result, setResult] = useState(null)
  const [submittedQuery, setSubmittedQuery] = useState(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const mapData = useMemo(
    () => buildOilMapData(result),
    [result],
  )

  async function runScreening(event) {
    event?.preventDefault()

    const trimmedLocation = location.trim()
    const parsedDays = Number(sceneDays)

    if (!trimmedLocation || isLoading) {
      return
    }

    if (
      !Number.isInteger(parsedDays) ||
      parsedDays < 1 ||
      parsedDays > 365
    ) {
      setError(
        'Scene window must be a whole number between 1 and 365 days.',
      )
      setResult(null)
      setSubmittedQuery(null)
      return
    }

    setIsLoading(true)
    setError('')
    setResult(null)
    setSubmittedQuery(null)

    const querySnapshot = {
      location: trimmedLocation,
      sceneDays: parsedDays,
    }

    try {
      const response = await getOilSpillInsights(
        querySnapshot.location,
        querySnapshot.sceneDays,
      )

      setResult(response)
      setSubmittedQuery(querySnapshot)
    } catch (requestError) {
      setError(
        requestError?.message ||
          'Sentinel-1 slick-candidate screening failed.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  const status = getStatusMeta(result)
  const StatusIcon = status.Icon

  return (
    <div className="oil-layout">
      <section className="oil-workstation">
        <header className="console-header">
          <div>
            <p className="eyebrow">Sentinel-1 SAR</p>
            <h1>Oil-slick candidate screening</h1>
          </div>

          <div className={`oil-status-chip ${status.className}`}>
            <StatusIcon size={16} />
            {status.label}
          </div>
        </header>

        <p className="oil-lead">
          Screen recent Sentinel-1 SAR imagery for coherent dark-slick
          candidates over mapped water. A candidate is a low-backscatter
          anomaly — <strong>not a confirmed oil spill.</strong>
        </p>

        <form
          className="oil-control-bar"
          onSubmit={runScreening}
        >
          <label>
            <span>Location</span>
            <input
              value={location}
              onChange={(event) =>
                setLocation(event.target.value)
              }
              placeholder="Mumbai, Kochi, 19N 72.8E..."
            />
          </label>

          <label>
            <span>Scene window</span>
            <div className="oil-number-field">
              <input
                type="number"
                min="1"
                max="365"
                step="1"
                value={sceneDays}
                onChange={(event) =>
                  setSceneDays(event.target.value)
                }
              />
              <span>days</span>
            </div>
          </label>

          <button
            type="submit"
            disabled={isLoading}
          >
            <Radar size={16} />
            {isLoading ? 'Screening…' : 'Screen SAR'}
          </button>
        </form>

        <div className="suggested-prompts oil-suggestions">
          {SUGGESTED_LOCATIONS.map((value) => (
            <button
              key={value}
              type="button"
              disabled={isLoading}
              onClick={() => setLocation(value)}
            >
              {value}
            </button>
          ))}
        </div>

        {error ? (
          <div
            className="oil-error"
            role="alert"
          >
            <AlertTriangle size={17} />
            <span>{error}</span>
          </div>
        ) : null}

        <section className="oil-map-panel">
          <div className="oil-map-heading">
            <div>
              <span>Analysis geometry</span>
              <strong>
                {submittedQuery
                  ? submittedQuery.location
                  : 'Awaiting query'}
              </strong>
            </div>

            <div className="oil-map-summary">
              {result?.screening_performed
                ? `${result?.candidate_count ?? 0} candidate region(s)`
                : result
                  ? 'Screening not performed'
                  : 'No analysis yet'}
            </div>
          </div>

          <div className="oil-map-canvas">
            <MapContainer
              center={DEFAULT_CENTER}
              zoom={9}
              scrollWheelZoom
              className="oil-leaflet-map"
            >
              <TileLayer
                attribution='&copy; OpenStreetMap contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              <FitOilMap mapData={mapData} />

              {mapData.requestedPoint ? (
                <Marker
                  position={mapData.requestedPoint}
                  icon={oilMarkerIcon('requested')}
                >
                  <Popup>
                    <PopupTitle>REQUESTED LOCATION</PopupTitle>
                    <PopupLine
                      label="Place"
                      value={result?.location?.display_name}
                    />
                    <PopupLine
                      label="Coordinates"
                      value={formatCoordinates(
                        result?.location?.latitude,
                        result?.location?.longitude,
                      )}
                    />
                  </Popup>
                </Marker>
              ) : null}

              {mapData.targetPoint ? (
                <Marker
                  position={mapData.targetPoint}
                  icon={oilMarkerIcon('target')}
                >
                  <Popup>
                    <PopupTitle>SAR ANALYSIS TARGET</PopupTitle>
                    <PopupLine
                      label="Coordinates"
                      value={formatCoordinates(
                        result?.analysis_target?.latitude,
                        result?.analysis_target?.longitude,
                      )}
                    />
                    <PopupLine
                      label="Shift"
                      value={
                        result?.analysis_target
                          ?.shifted_from_requested_location
                          ? `${formatNumber(
                              result?.analysis_target
                                ?.shift_distance_km,
                              2,
                            )} km from requested point`
                          : 'Requested point retained'
                      }
                    />
                    <PopupLine
                      label="Water estimate"
                      value={formatPercent(
                        result?.analysis_target
                          ?.estimated_water_fraction,
                      )}
                    />
                  </Popup>
                </Marker>
              ) : null}

              {mapData.requestedPoint &&
              mapData.targetPoint &&
              result?.analysis_target
                ?.shifted_from_requested_location ? (
                <Polyline
                  positions={[
                    mapData.requestedPoint,
                    mapData.targetPoint,
                  ]}
                  pathOptions={{
                    color: '#ff6b4a',
                    weight: 2,
                    opacity: 0.78,
                    dashArray: '6 7',
                  }}
                />
              ) : null}

              {mapData.analysisBounds ? (
                <Rectangle
                  bounds={mapData.analysisBounds}
                  pathOptions={{
                    color: '#2dd4bf',
                    weight: 1,
                    opacity: 0.85,
                    fillOpacity: 0.04,
                    dashArray: '5 5',
                  }}
                >
                  <Popup>
                    <PopupTitle>ANALYZED SAR PATCH</PopupTitle>
                    <PopupLine
                      label="Raster"
                      value={`${result?.analysis_patch?.width ?? '—'} × ${
                        result?.analysis_patch?.height ?? '—'
                      }`}
                    />
                    <PopupLine
                      label="Bands"
                      value={
                        result?.analysis_patch?.bands?.join(', ') ||
                        '—'
                      }
                    />
                  </Popup>
                </Rectangle>
              ) : null}

              {mapData.candidates.map((candidate) => (
                <CandidateLayer
                  candidate={candidate}
                  key={candidate.candidate_id}
                />
              ))}
            </MapContainer>

            <OilLegend
              hasRequested={Boolean(mapData.requestedPoint)}
              hasTarget={Boolean(mapData.targetPoint)}
              hasCandidates={mapData.candidates.length > 0}
            />
          </div>
        </section>
      </section>

      <OilEvidencePanel
        result={result}
        query={submittedQuery}
        isLoading={isLoading}
      />
    </div>
  )
}

function CandidateLayer({ candidate }) {
  const bounds = candidateBounds(candidate)
  const centroid = candidatePoint(candidate)

  return (
    <>
      {bounds ? (
        <Rectangle
          bounds={bounds}
          pathOptions={{
            color: '#ff6b4a',
            weight: 1.4,
            opacity: 0.9,
            fillColor: '#ff6b4a',
            fillOpacity: 0.13,
          }}
        />
      ) : null}

      {centroid ? (
        <Marker
          position={centroid}
          icon={oilMarkerIcon('candidate')}
        >
          <Popup>
            <PopupTitle>
              SAR DARK-SLICK CANDIDATE #{candidate.candidate_id}
            </PopupTitle>
            <PopupLine
              label="Centroid"
              value={formatCoordinates(
                candidate?.centroid?.latitude,
                candidate?.centroid?.longitude,
              )}
            />
            <PopupLine
              label="Pixel count"
              value={candidate?.pixel_count}
            />
            <div className="oil-popup-warning">
              Screening candidate only — not confirmed petroleum.
            </div>
          </Popup>
        </Marker>
      ) : null}
    </>
  )
}

function OilEvidencePanel({
  result,
  query,
  isLoading,
}) {
  const satellite = result?.satellite_observation
  const water = result?.water_context
  const target = result?.analysis_target
  const screening = result?.screening
  const notes = result?.data_notes || []

  return (
    <aside className="oil-evidence-panel">
      <div className="oil-evidence-header">
        <div>
          <p className="eyebrow">Evidence Trail</p>
          <h2>Satellite screening</h2>
        </div>

        <ShieldCheck size={20} />
      </div>

      <div className="oil-evidence-scroll">
        <EvidenceBlock
          icon={<MapPinned size={16} />}
          title="Query & targeting"
        >
          <EvidenceLine
            label="Requested"
            value={query?.location}
          />
          <EvidenceLine
            label="Scene window"
            value={
              query?.sceneDays
                ? `${query.sceneDays} days`
                : null
            }
          />
          <EvidenceLine
            label="Target"
            value={formatCoordinates(
              target?.latitude,
              target?.longitude,
            )}
          />
          <EvidenceLine
            label="Shifted offshore"
            value={
              target
                ? target.shifted_from_requested_location
                  ? 'Yes'
                  : 'No'
                : null
            }
          />
          <EvidenceLine
            label="Shift distance"
            value={
              target?.shift_distance_km != null
                ? `${formatNumber(
                    target.shift_distance_km,
                    2,
                  )} km`
                : null
            }
          />
        </EvidenceBlock>

        <EvidenceBlock
          icon={<Satellite size={16} />}
          title="Sentinel-1 observation"
        >
          <EvidenceLine
            label="Scene"
            value={satellite?.scene_id}
          />
          <EvidenceLine
            label="Acquired"
            value={formatTimestamp(
              satellite?.acquisition_time,
            )}
          />
          <EvidenceLine
            label="Platform"
            value={satellite?.platform}
          />
          <EvidenceLine
            label="Mode"
            value={satellite?.instrument_mode}
          />
          <EvidenceLine
            label="Polarizations"
            value={satellite?.polarizations?.join(', ')}
          />
        </EvidenceBlock>

        <EvidenceBlock
          icon={<Waves size={16} />}
          title="Water context"
        >
          <EvidenceLine
            label="Mapped water"
            value={formatPercent(
              water?.water_fraction,
            )}
          />
          <EvidenceLine
            label="Reference year"
            value={water?.source?.reference_year}
          />
          <EvidenceLine
            label="Source"
            value={water?.source?.name}
          />
        </EvidenceBlock>

        <EvidenceBlock
          icon={<Crosshair size={16} />}
          title="Candidate screening"
        >
          <EvidenceLine
            label="Status"
            value={humanize(result?.status)}
          />
          <EvidenceLine
            label="Performed"
            value={
              result
                ? result.screening_performed
                  ? 'Yes'
                  : 'No'
                : null
            }
          />
          <EvidenceLine
            label="Candidate regions"
            value={result?.candidate_count}
          />
          <EvidenceLine
            label="Candidate pixels"
            value={
              screening?.statistics?.candidate_pixels
            }
          />
          <EvidenceLine
            label="Ocean fraction flagged"
            value={formatPercent(
              screening?.statistics
                ?.candidate_fraction_of_ocean,
            )}
          />
          <EvidenceLine
            label="Adaptive VV threshold"
            value={
              screening?.thresholds
                ?.derived_vv_threshold_db != null
                ? `${formatNumber(
                    screening.thresholds
                      .derived_vv_threshold_db,
                    2,
                  )} dB`
                : null
            }
          />
        </EvidenceBlock>

        {result?.summary ? (
          <EvidenceBlock
            icon={<Database size={16} />}
            title="Result summary"
          >
            <p className="oil-summary">
              {result.summary}
            </p>
          </EvidenceBlock>
        ) : null}

        {result?.provenance?.length ? (
          <EvidenceBlock
            icon={<ShieldCheck size={16} />}
            title="Provenance"
          >
            {result.provenance.map((item, index) => (
              <div
                className="oil-provenance-entry"
                key={`${item?.evidence_type || 'evidence'}-${index}`}
              >
                <span>
                  {humanize(item?.evidence_type)}
                </span>
                <strong>
                  {provenanceSource(item)}
                </strong>
              </div>
            ))}
          </EvidenceBlock>
        ) : null}

        <EvidenceBlock
          icon={<AlertTriangle size={16} />}
          title="Interpretation limits"
        >
          <p className="oil-critical-note">
            SAR dark-slick candidates are low-backscatter
            anomalies. They are not confirmed oil spills,
            verified petroleum leakage, or pollution events.
          </p>

          <p className="oil-critical-note">
            Calm water, natural surfactants, biological films,
            rain effects, current boundaries and atmospheric
            conditions can produce similar signatures.
          </p>

          {result &&
          result.screening_performed === false ? (
            <p className="oil-critical-note">
              No screening was performed. Missing or unsuitable
              satellite coverage must not be interpreted as
              evidence that oil is absent.
            </p>
          ) : null}
        </EvidenceBlock>

        {notes.length ? (
          <EvidenceBlock
            icon={<Database size={16} />}
            title="Data notes"
          >
            {notes.map((note, index) => (
              <p
                className="oil-data-note"
                key={`${index}-${note}`}
              >
                {note}
              </p>
            ))}
          </EvidenceBlock>
        ) : null}

        {!result && !isLoading ? (
          <div className="oil-empty-evidence">
            Run a screening query to populate the satellite
            evidence trail.
          </div>
        ) : null}

        {isLoading ? (
          <div className="oil-empty-evidence">
            Resolving location, selecting water-dominated
            context and processing recent Sentinel-1 evidence…
          </div>
        ) : null}
      </div>
    </aside>
  )
}

function EvidenceBlock({
  icon,
  title,
  children,
}) {
  return (
    <section className="oil-evidence-block">
      <div className="oil-evidence-title">
        {icon}
        <span>{title}</span>
      </div>
      {children}
    </section>
  )
}

function EvidenceLine({
  label,
  value,
}) {
  return (
    <div className="oil-evidence-line">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  )
}

function PopupTitle({ children }) {
  return (
    <div className="oil-popup-title">
      {children}
    </div>
  )
}

function PopupLine({
  label,
  value,
}) {
  return (
    <div className="oil-popup-line">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  )
}

function OilLegend({
  hasRequested,
  hasTarget,
  hasCandidates,
}) {
  if (
    !hasRequested &&
    !hasTarget &&
    !hasCandidates
  ) {
    return null
  }

  return (
    <div
      className="oil-map-legend"
      aria-label="Oil screening map legend"
    >
      {hasRequested ? (
        <LegendItem
          type="requested"
          label="Requested location"
        />
      ) : null}

      {hasTarget ? (
        <LegendItem
          type="target"
          label="SAR analysis target"
        />
      ) : null}

      {hasCandidates ? (
        <LegendItem
          type="candidate"
          label="Dark-slick candidate"
        />
      ) : null}
    </div>
  )
}

function LegendItem({
  type,
  label,
}) {
  return (
    <div>
      <span
        className={`oil-legend-symbol is-${type}`}
      />
      {label}
    </div>
  )
}

function FitOilMap({ mapData }) {
  const map = useMap()

  useEffect(() => {
    const bounds = []

    if (mapData.analysisBounds) {
      bounds.push(
        mapData.analysisBounds[0],
        mapData.analysisBounds[1],
      )
    }

    if (mapData.requestedPoint) {
      bounds.push(mapData.requestedPoint)
    }

    if (mapData.targetPoint) {
      bounds.push(mapData.targetPoint)
    }

    for (const candidate of mapData.candidates) {
      const point = candidatePoint(candidate)

      if (point) {
        bounds.push(point)
      }
    }

    if (bounds.length > 1) {
      map.fitBounds(bounds, {
        padding: [45, 45],
        maxZoom: 13,
      })
      return
    }

    if (bounds.length === 1) {
      map.setView(bounds[0], 10)
    }
  }, [map, mapData])

  return null
}

function buildOilMapData(result) {
  if (!result) {
    return {
      requestedPoint: null,
      targetPoint: null,
      analysisBounds: null,
      candidates: [],
    }
  }

  return {
    requestedPoint: validPoint(
      result?.location?.latitude,
      result?.location?.longitude,
    ),
    targetPoint: validPoint(
      result?.analysis_target?.latitude,
      result?.analysis_target?.longitude,
    ),
    analysisBounds: bboxToBounds(
      result?.analysis_patch?.bbox,
    ),
    candidates: Array.isArray(
      result?.candidate_locations,
    )
      ? result.candidate_locations
      : [],
  }
}

function bboxToBounds(bbox) {
  if (!bbox) {
    return null
  }

  const south = Number(bbox.south)
  const north = Number(bbox.north)
  const west = Number(bbox.west)
  const east = Number(bbox.east)

  if (
    ![south, north, west, east].every(
      Number.isFinite,
    )
  ) {
    return null
  }

  return [
    [south, west],
    [north, east],
  ]
}

function candidateBounds(candidate) {
  const bounds =
    candidate?.geographic_bounds

  if (!bounds) {
    return null
  }

  const south = Number(bounds.south)
  const north = Number(bounds.north)
  const west = Number(bounds.west)
  const east = Number(bounds.east)

  if (
    ![south, north, west, east].every(
      Number.isFinite,
    )
  ) {
    return null
  }

  return [
    [south, west],
    [north, east],
  ]
}

function candidatePoint(candidate) {
  return validPoint(
    candidate?.centroid?.latitude,
    candidate?.centroid?.longitude,
  )
}

function validPoint(latitude, longitude) {
  const lat = Number(latitude)
  const lon = Number(longitude)

  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lon)
  ) {
    return null
  }

  return [lat, lon]
}

function oilMarkerIcon(type) {
  return L.divIcon({
    className: `oil-marker oil-marker-${type}`,
    html: '<span></span>',
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -10],
  })
}

function getStatusMeta(result) {
  if (!result) {
    return {
      label: 'AWAITING SCREEN',
      className: 'is-idle',
      Icon: Radar,
    }
  }

  if (!result.screening_performed) {
    return {
      label: 'NOT SCREENED',
      className: 'is-limited',
      Icon: AlertTriangle,
    }
  }

  if ((result.candidate_count ?? 0) > 0) {
    return {
      label: 'CANDIDATES FOUND',
      className: 'is-candidate',
      Icon: Crosshair,
    }
  }

  return {
    label: 'NO CANDIDATES',
    className: 'is-clear',
    Icon: ShieldCheck,
  }
}

function provenanceSource(item) {
  if (!item) {
    return '—'
  }

  const source = item.source

  if (typeof source === 'string') {
    return source
  }

  if (source && typeof source === 'object') {
    return (
      source.name ||
      source.provider ||
      source.collection ||
      'Structured source metadata'
    )
  }

  return (
    item.scene_id ||
    item.api ||
    'AquaNexus deterministic evidence'
  )
}

function formatCoordinates(
  latitude,
  longitude,
) {
  const lat = Number(latitude)
  const lon = Number(longitude)

  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lon)
  ) {
    return '—'
  }

  return `${lat.toFixed(5)}°, ${lon.toFixed(5)}°`
}

function formatPercent(value) {
  const number = Number(value)

  if (!Number.isFinite(number)) {
    return '—'
  }

  return `${(number * 100).toFixed(1)}%`
}

function formatNumber(value, digits = 2) {
  const number = Number(value)

  if (!Number.isFinite(number)) {
    return '—'
  }

  return number.toFixed(digits)
}

function formatTimestamp(value) {
  if (!value) {
    return '—'
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  return date.toISOString()
}

function humanize(value) {
  if (!value) {
    return '—'
  }

  return String(value)
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase(),
    )
}

function displayValue(value) {
  if (
    value === null ||
    value === undefined ||
    value === ''
  ) {
    return '—'
  }

  return String(value)
}

export default OilSpillPage