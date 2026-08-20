import 'leaflet/dist/leaflet.css'

import L from 'leaflet'
import { Activity, MapPinned } from 'lucide-react'
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

import {
  getMineralInsights,
  getOceanConditions,
} from '../../services/api.js'

const COVERAGE_BOUNDS = [
  [0, 60],
  [30, 100],
]

const COVERAGE_CENTER = [15, 80]

const SUGGESTED_LOCATIONS = [
  'Kochi',
  'Goa',
  'Arabian Sea',
  '10N 75E',
]

function OceanMap() {
  const [location, setLocation] = useState('Kochi')
  const [depth, setDepth] = useState(0)
  const [argoRadius, setArgoRadius] = useState(300)
  const [mineralRadius, setMineralRadius] = useState(50)

  const [result, setResult] = useState(null)
  const [mineralResult, setMineralResult] = useState(null)

  // Stores the exact form values that produced the current result.
  // This prevents unsent form edits from changing evidence metadata.
  const [submittedQuery, setSubmittedQuery] = useState(null)

  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const mapData = useMemo(
    () => buildMapData(result, mineralResult),
    [result, mineralResult],
  )

  async function analyzeRegion(event) {
    event?.preventDefault()

    const trimmedLocation = location.trim()

    if (!trimmedLocation || isLoading) {
      return
    }

    const parsedDepth = Number(depth)
    const parsedArgoRadius = Number(argoRadius)
    const parsedMineralRadius = Number(mineralRadius)

    const querySnapshot = {
      location: trimmedLocation,

      depth:
        Number.isFinite(parsedDepth) && parsedDepth >= 0
          ? parsedDepth
          : 0,

      argoRadius:
        Number.isFinite(parsedArgoRadius) && parsedArgoRadius > 0
          ? parsedArgoRadius
          : 300,

      mineralRadius:
        Number.isFinite(parsedMineralRadius) && parsedMineralRadius > 0
          ? parsedMineralRadius
          : 50,
    }

    setIsLoading(true)
    setError('')

    // Remove old scientific evidence immediately.
    // A failed/new query must never leave stale evidence visible.
    setResult(null)
    setMineralResult(null)
    setSubmittedQuery(null)

    try {
      const [oceanRequest, mineralRequest] = await Promise.allSettled([
        getOceanConditions(
          querySnapshot.location,
          querySnapshot.depth,
          querySnapshot.argoRadius,
        ),
        getMineralInsights(
          querySnapshot.location,
          querySnapshot.mineralRadius,
        ),
      ])

      const warnings = []

      if (oceanRequest.status === 'fulfilled') {
        setResult(oceanRequest.value)
      } else {
        warnings.push(
          `Ocean evidence unavailable: ${
            oceanRequest.reason?.message || 'request failed'
          }`,
        )
      }

      if (mineralRequest.status === 'fulfilled') {
        setMineralResult(mineralRequest.value)
      } else {
        warnings.push(
          `Mineral evidence unavailable: ${
            mineralRequest.reason?.message || 'request failed'
          }`,
        )
      }

      if (
        oceanRequest.status === 'rejected' &&
        mineralRequest.status === 'rejected'
      ) {
        setError(warnings.join(' · '))
        return
      }

      setSubmittedQuery(querySnapshot)

      if (warnings.length) {
        setError(`Partial result · ${warnings.join(' · ')}`)
      }
    } finally {
      setIsLoading(false)
    }
  }

  function selectSuggestion(value) {
    setLocation(value)
  }

  return (
    <div className="map-layout">
      <section
        className="map-workstation"
        aria-label="AquaNexus ocean map"
      >
        <div className="console-header">
          <div>
            <p className="eyebrow">Ocean Map</p>
            <h1>Indian Ocean coverage</h1>
          </div>

          <div className="console-chip">
            <MapPinned size={16} />
            Live region analysis
          </div>
        </div>

        <form
          className="map-control-bar"
          onSubmit={analyzeRegion}
        >
          <label>
            <span>Location</span>

            <input
              value={location}
              onChange={(event) =>
                setLocation(event.target.value)
              }
              disabled={isLoading}
              aria-label="Location"
            />
          </label>

          <label className="map-number-field">
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

          <label className="map-number-field">
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

          <label className="map-number-field">
            <span>Mineral radius</span>

            <input
              type="number"
              min="1"
              step="1"
              value={mineralRadius}
              onChange={(event) =>
                setMineralRadius(event.target.value)
              }
              disabled={isLoading}
              aria-label="Marine mineral radius in kilometers"
            />

            <em>km</em>
          </label>

          <button
            type="submit"
            disabled={isLoading || !location.trim()}
          >
            {isLoading ? 'Analyzing...' : 'Analyze region'}
          </button>
        </form>

        <div
          className="suggested-prompts"
          aria-label="Suggested map locations"
        >
          {SUGGESTED_LOCATIONS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => selectSuggestion(value)}
              disabled={isLoading}
            >
              {value}
            </button>
          ))}
        </div>

        {isLoading && (
          <div className="querying-indicator">
            <span />
            QUERYING OCEAN + MINERAL DATA...
          </div>
        )}

        {error && (
          <div
            className="map-error"
            role="alert"
          >
            {error}
          </div>
        )}

        <div className="map-frame">
          <MapContainer
            className="ocean-leaflet-map"
            bounds={COVERAGE_BOUNDS}
            maxBounds={[
              [-8, 52],
              [38, 108],
            ]}
            scrollWheelZoom
          >
            <TileLayer
              attribution='&copy; <a href="https://carto.com/attributions">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            />

            <FitMap mapData={mapData} />

            {/* AquaNexus scientific coverage boundary */}
            <Rectangle
              bounds={COVERAGE_BOUNDS}
              pathOptions={{
                color: '#2dd4bf',
                weight: 1,
                opacity: 0.35,
                fillOpacity: 0,
              }}
            />

            {/* Resolved named region */}
            {mapData.areaBounds && (
              <Rectangle
                bounds={mapData.areaBounds}
                pathOptions={{
                  color: '#2dd4bf',
                  weight: 1,
                  opacity: 0.55,
                  fillOpacity: 0.08,
                }}
              />
            )}

            {/* Requested / resolved point */}
            {mapData.requestedPoint && result && (
              <Marker
                position={mapData.requestedPoint}
                icon={markerIcon('requested')}
                zIndexOffset={1000}
              >
                <Popup>
                  <PopupTitle>
                    REQUESTED LOCATION
                  </PopupTitle>

                  <PopupLine
                    value={
                      result.location?.display_name ||
                      result.location?.query
                    }
                  />

                  <PopupLine
                    value={formatCoordinates(
                      result.location?.latitude,
                      result.location?.longitude,
                    )}
                  />
                </Popup>
              </Marker>
            )}

            {/* Copernicus model grid cell */}
            {mapData.gridPoint && result && (
              <Marker
                position={mapData.gridPoint}
                icon={markerIcon('grid')}
                zIndexOffset={900}
              >
                <Popup>
                  <PopupTitle>
                    COPERNICUS MODEL GRID
                  </PopupTitle>

                  <PopupLine
                    label="Temperature"
                    value={formatCelsius(
                      result.present_state?.temperature_c,
                    )}
                  />

                  <PopupLine
                    label="Salinity"
                    value={formatSalinity(
                      result.present_state?.salinity,
                    )}
                  />

                  <PopupLine
                    label="Model grid depth"
                    value={formatMeters(
                      result.present_state?.depth_used_m,
                    )}
                  />

                  <PopupLine
                    label="Model time"
                    value={formatTimestamp(
                      result.present_state?.model_time,
                    )}
                  />

                  <PopupLine
                    label="Distance from requested location"
                    value={formatKm(
                      result.present_state?.grid_distance_km,
                    )}
                  />
                </Popup>
              </Marker>
            )}

            {/* Requested location → model grid relationship */}
            {mapData.requestedPoint &&
              mapData.gridPoint && (
                <Polyline
                  positions={[
                    mapData.requestedPoint,
                    mapData.gridPoint,
                  ]}
                  pathOptions={{
                    color: '#2dd4bf',
                    weight: 1,
                    opacity: 0.55,
                    dashArray: '4 6',
                  }}
                />
              )}

            {/* Current/recent ARGO observation.
                Only used for point queries when backend explicitly says
                the ARGO observation is available. */}
            {mapData.latestArgoPoint && result && (
              <Marker
                position={mapData.latestArgoPoint}
                icon={markerIcon('argo')}
              >
                <Popup>
                  <PopupTitle>
                    IN-SITU ARGO OBSERVATION
                  </PopupTitle>

                  <PopupLine
                    label="Float"
                    value={argoField(
                      result.latest_argo,
                      'float_id',
                    )}
                  />

                  <PopupLine
                    label="Cycle"
                    value={argoField(
                      result.latest_argo,
                      'cycle',
                    )}
                  />

                  <PopupLine
                    label="Pressure"
                    value={formatDbar(
                      argoPressure(result.latest_argo),
                    )}
                  />

                  <PopupLine
                    label="Observation time"
                    value={formatTimestamp(
                      argoObservationTime(
                        result.latest_argo,
                      ),
                    )}
                  />
                </Popup>
              </Marker>
            )}

            {/* Historical ARGO context */}
            {mapData.historicalPoint && result && (
              <Marker
                position={mapData.historicalPoint}
                icon={markerIcon('historical')}
              >
                <Popup>
                  <PopupTitle>
                    HISTORICAL ARGO CONTEXT
                  </PopupTitle>

                  <PopupLine
                    label="Float"
                    value={
                      result.historical_context
                        ?.float_id
                    }
                  />

                  <PopupLine
                    label="Cycle"
                    value={
                      result.historical_context?.cycle
                    }
                  />

                  <PopupLine
                    label="Observation time"
                    value={formatTimestamp(
                      result.historical_context
                        ?.observation_time,
                    )}
                  />

                  <PopupLine
                    label="Distance"
                    value={formatKm(
                      result.historical_context
                        ?.distance_km,
                    )}
                  />
                </Popup>
              </Marker>
            )}

            {/* Literature-reported marine mineral sites */}
            {mapData.mineralSites.map(({ site, point }) => (
              <Marker
                key={`mineral-site-${site.id}`}
                position={point}
                icon={markerIcon('mineral-site')}
                zIndexOffset={850}
              >
                <Popup>
                  <PopupTitle>
                    LITERATURE-REPORTED MINERAL SITE
                  </PopupTitle>

                  <PopupLine value={site.name} />

                  <PopupLine
                    label="Mineral type"
                    value={formatMineralType(site.mineral_type)}
                  />

                  <PopupLine
                    label="Metals / minerals"
                    value={formatList(site.metals)}
                  />

                  <PopupLine
                    label="Depth"
                    value={formatMeters(site.depth_m)}
                  />

                  <PopupLine
                    label="Distance"
                    value={formatKm(site.distance_km)}
                  />

                  <PopupLine
                    label="Citation"
                    value={site.citation}
                  />

                  {site.source_url && (
                    <a
                      className="mineral-source-link"
                      href={site.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open scientific source
                    </a>
                  )}
                </Popup>
              </Marker>
            ))}

            {/* Direct seafloor station samples, when available in coverage */}
            {mapData.mineralSamples.map(({ sample, point }, index) => (
              <Marker
                key={`mineral-sample-${sample.id || sample.station || index}`}
                position={point}
                icon={markerIcon('mineral-sample')}
                zIndexOffset={875}
              >
                <Popup>
                  <PopupTitle>
                    DIRECT SEAFLOOR SAMPLE
                  </PopupTitle>

                  <PopupLine
                    label="Station"
                    value={sample.station || sample.id}
                  />

                  <PopupLine
                    label="Coverage"
                    value={formatPercent(sample.seafloor_coverage_pct)}
                  />

                  <PopupLine
                    label="Nodule mass"
                    value={formatKg(sample.total_nodule_mass_kg)}
                  />
                </Popup>
              </Marker>
            ))}

            {/* Approximate mineral regions are context only, not deposit boundaries. */}
            {mapData.mineralRegions.map(({ region, bounds }) => (
              <Rectangle
                key={`mineral-region-${region.id}`}
                bounds={bounds}
                pathOptions={{
                  color: '#8b7fd6',
                  weight: 1.5,
                  opacity: 0.8,
                  fillColor: '#8b7fd6',
                  fillOpacity: 0.06,
                  dashArray: '8 6',
                }}
              >
                <Popup>
                  <PopupTitle>
                    APPROXIMATE MINERAL REGION CONTEXT
                  </PopupTitle>

                  <PopupLine value={region.region_name} />

                  <PopupLine
                    label="Mineral type"
                    value={formatMineralType(region.mineral_type)}
                  />

                  <PopupLine
                    label="Primary metals"
                    value={formatList(region.primary_metals)}
                  />

                  <PopupLine
                    label="Depth range"
                    value={formatDepthRange(region.depth_range_m)}
                  />

                  <p className="map-note">
                    Approximate documented regional context only. This rectangle
                    is not a confirmed deposit boundary.
                  </p>
                </Popup>
              </Rectangle>
            ))}
          </MapContainer>

          <MapLegend mapData={mapData} />
        </div>
      </section>

      <MapIntelligencePanel
        result={result}
        mineralResult={mineralResult}
        query={submittedQuery}
      />
    </div>
  )
}

function FitMap({ mapData }) {
  const map = useMap()

  useEffect(() => {
    if (mapData.areaBounds) {
      map.fitBounds(mapData.areaBounds, {
        padding: [22, 22],
      })

      return
    }

    const points = [
      mapData.requestedPoint,
      mapData.gridPoint,
      mapData.latestArgoPoint,
      mapData.historicalPoint,
      ...mapData.mineralSites.map((item) => item.point),
      ...mapData.mineralSamples.map((item) => item.point),
    ].filter(Boolean)

    if (points.length > 1) {
      map.fitBounds(points, {
        padding: [60, 60],
        maxZoom: 10,
      })

      return
    }

    if (points.length === 1) {
      map.setView(points[0], 7)
      return
    }

    map.fitBounds(COVERAGE_BOUNDS)
    map.setView(
      COVERAGE_CENTER,
      map.getZoom(),
    )
  }, [map, mapData])

  return null
}

function MapIntelligencePanel({
  result,
  mineralResult,
  query,
}) {
  const location = result?.location || mineralResult?.location
  const state = result?.present_state
  const recentArgo = result?.latest_argo

  const isArea = location?.type === 'area'

  return (
    <aside
      className="evidence-panel map-intelligence-panel"
      aria-label="Map intelligence"
    >
      <div className="evidence-header">
        <div>
          <p className="eyebrow">
            Map Intelligence
          </p>

          <h2>Ocean + mineral evidence</h2>
        </div>

        <Activity size={20} />
      </div>

      <div className="evidence-stack">
        <EvidenceBlock title="Query">
          <EvidenceLine
            label="Location"
            value={
              location?.query ||
              query?.location
            }
          />

          <EvidenceLine
            label="Depth"
            value={formatMeters(
              result?.requested_depth_m ??
                query?.depth,
            )}
          />

          <EvidenceLine
            label="ARGO radius"
            value={formatKm(
              query?.argoRadius,
            )}
          />

          <EvidenceLine
            label="Mineral radius"
            value={formatKm(
              query?.mineralRadius,
            )}
          />
        </EvidenceBlock>

        <EvidenceBlock title="Present state">
          {isArea ? (
            <>
              <EvidenceLine
                label="Temperature"
                value={formatStats(
                  state?.temperature_c,
                  'degC',
                )}
              />

              <EvidenceLine
                label="Salinity"
                value={formatStats(
                  state?.salinity,
                )}
              />

              <EvidenceLine
                label="Eastward current"
                value={formatStats(
                  state?.eastward_current_m_s,
                  'm/s',
                )}
              />

              <EvidenceLine
                label="Northward current"
                value={formatStats(
                  state?.northward_current_m_s,
                  'm/s',
                )}
              />

              <EvidenceLine
                label="Valid grid cells"
                value={
                  state?.valid_grid_cells
                }
              />
            </>
          ) : (
            <>
              <EvidenceLine
                label="Temperature"
                value={formatCelsius(
                  state?.temperature_c,
                )}
              />

              <EvidenceLine
                label="Salinity"
                value={formatSalinity(
                  state?.salinity,
                )}
              />

              <EvidenceLine
                label="Eastward current"
                value={formatVelocity(
                  state?.eastward_current_m_s,
                )}
              />

              <EvidenceLine
                label="Northward current"
                value={formatVelocity(
                  state?.northward_current_m_s,
                )}
              />
            </>
          )}

          <EvidenceLine
            label="Requested depth"
            value={formatMeters(
              result?.requested_depth_m,
            )}
          />

          <EvidenceLine
            label="Model grid depth"
            value={formatMeters(
              state?.depth_used_m,
            )}
          />

          <EvidenceLine
            label="Model time"
            value={formatTimestamp(
              state?.model_time,
            )}
          />
        </EvidenceBlock>

        <EvidenceBlock title="Location / Region">
          <EvidenceLine
            label="Resolved"
            value={location?.display_name}
          />

          <EvidenceLine
            label="Type"
            value={location?.type}
          />

          {isArea ? (
            <EvidenceLine
              label="Bounding box"
              value={formatBoundingBox(
                location?.bounding_box,
              )}
            />
          ) : (
            <>
              <EvidenceLine
                label="Coordinates"
                value={formatCoordinates(
                  location?.latitude,
                  location?.longitude,
                )}
              />

              <EvidenceLine
                label="Grid cell"
                value={formatCoordinates(
                  state?.latitude_used,
                  state?.longitude_used,
                )}
              />

              <EvidenceLine
                label="Grid distance"
                value={formatKm(
                  state?.grid_distance_km,
                )}
              />
            </>
          )}
        </EvidenceBlock>

        <EvidenceBlock title="Recent ARGO">
          <EvidenceLine
            label="Availability"
            value={argoAvailability(
              recentArgo,
            )}
          />

          <EvidenceLine
            label="Float"
            value={argoField(
              recentArgo,
              'float_id',
            )}
          />

          <EvidenceLine
            label="Cycle"
            value={argoField(
              recentArgo,
              'cycle',
            )}
          />

          <EvidenceLine
            label="Pressure"
            value={formatDbar(
              argoPressure(recentArgo),
            )}
          />

          <EvidenceLine
            label="Observation time"
            value={formatTimestamp(
              argoObservationTime(
                recentArgo,
              ),
            )}
          />

          <EvidenceLine
            label="Distance"
            value={formatKm(
              argoDistance(recentArgo),
            )}
          />

          {recentArgo?.profile_count != null && (
            <EvidenceLine
              label="Profiles"
              value={recentArgo.profile_count}
            />
          )}

          {recentArgo?.unique_floats != null && (
            <EvidenceLine
              label="Unique floats"
              value={recentArgo.unique_floats}
            />
          )}
        </EvidenceBlock>

        <EvidenceBlock title="Historical context">
          <EvidenceLine
            label="Float"
            value={
              result?.historical_context
                ?.float_id
            }
          />

          <EvidenceLine
            label="Cycle"
            value={
              result?.historical_context
                ?.cycle
            }
          />

          <EvidenceLine
            label="Observation time"
            value={formatTimestamp(
              result?.historical_context
                ?.observation_time,
            )}
          />

          <EvidenceLine
            label="Distance"
            value={formatKm(
              result?.historical_context
                ?.distance_km,
            )}
          />
        </EvidenceBlock>

        <EvidenceBlock title="Marine mineral evidence">
          <EvidenceLine
            label="Strongest evidence"
            value={formatEvidenceType(
              mineralResult?.strongest_evidence,
            )}
          />

          <EvidenceLine
            label="Direct samples"
            value={mineralResult?.counts?.station_samples}
          />

          <EvidenceLine
            label="Cited sites"
            value={mineralResult?.counts?.cited_sites}
          />

          <EvidenceLine
            label="Approx. regions"
            value={mineralResult?.counts?.estimated_regions}
          />

          {mineralResult?.summary && (
            <p className="map-note">
              {mineralResult.summary}
            </p>
          )}

          {(mineralResult?.cited_sites || []).map((site) => (
            <div
              className="mineral-evidence-entry"
              key={`evidence-${site.id}`}
            >
              <strong>{site.name}</strong>
              <span>{formatMineralType(site.mineral_type)}</span>
              <p>{site.citation}</p>
              {site.source_url && (
                <a
                  className="mineral-source-link"
                  href={site.source_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Scientific source
                </a>
              )}
            </div>
          ))}

          {(mineralResult?.estimated_regions || []).length > 0 && (
            <p className="map-note mineral-context-warning">
              Dashed mineral rectangles show approximate regional context only;
              they are not confirmed deposit boundaries.
            </p>
          )}
        </EvidenceBlock>

        <EvidenceBlock title="Data notes">
          {(
            result?.data_notes?.length
              ? result.data_notes
              : ['No returned data notes yet.']
          ).map((note) => (
            <p
              className="map-note"
              key={note}
            >
              {note}
            </p>
          ))}

          {(mineralResult?.data_notes || []).map((note) => (
            <p
              className="map-note mineral-data-note"
              key={`mineral-note-${note}`}
            >
              Mineral: {note}
            </p>
          ))}

          {isArea && (
            <p className="map-note">
              Regional statistics are summaries
              and do not represent every point in
              the region.
            </p>
          )}
        </EvidenceBlock>
      </div>
    </aside>
  )
}

function EvidenceBlock({
  title,
  children,
}) {
  return (
    <section className="evidence-block">
      <div className="evidence-block-title">
        {title}
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
    <div className="evidence-line">
      <span>{label}</span>

      <strong>
        {displayValue(value)}
      </strong>
    </div>
  )
}

function PopupTitle({ children }) {
  return (
    <div className="map-popup-title">
      {children}
    </div>
  )
}

function PopupLine({
  label,
  value,
}) {
  const rendered = displayValue(value)

  if (!label) {
    return (
      <div className="map-popup-value">
        {rendered}
      </div>
    )
  }

  return (
    <div className="map-popup-line">
      <span>{label}</span>
      <strong>{rendered}</strong>
    </div>
  )
}

function MapLegend({ mapData }) {
  const entries = [
    mapData.requestedPoint && [
      'requested',
      'Requested location',
    ],

    mapData.gridPoint && [
      'grid',
      'Copernicus grid',
    ],

    mapData.latestArgoPoint && [
      'argo',
      'Recent ARGO',
    ],

    mapData.historicalPoint && [
      'historical',
      'Historical ARGO',
    ],

    mapData.mineralSites.length > 0 && [
      'mineral-site',
      'Cited mineral site',
    ],

    mapData.mineralSamples.length > 0 && [
      'mineral-sample',
      'Direct mineral sample',
    ],

    mapData.mineralRegions.length > 0 && [
      'mineral-region',
      'Approx. mineral region',
    ],
  ].filter(Boolean)

  if (!entries.length) {
    return null
  }

  return (
    <div
      className="map-legend"
      aria-label="Map legend"
    >
      {entries.map(([type, label]) => (
        <span key={type}>
          <i
            className={`legend-symbol is-${type}`}
          />

          {label}
        </span>
      ))}
    </div>
  )
}

function buildMapData(result, mineralResult) {
  const location = result?.location
  const state = result?.present_state
  const latest = result?.latest_argo
  const historical =
    result?.historical_context

  const mineralLocation = mineralResult?.location

  const mineralSites = (mineralResult?.cited_sites || [])
    .map((site) => ({
      site,
      point: pointFrom(site.latitude, site.longitude),
    }))
    .filter((item) => item.point)

  const mineralSamples = (mineralResult?.station_samples || [])
    .map((sample) => ({
      sample,
      point: pointFrom(sample.latitude, sample.longitude),
    }))
    .filter((item) => item.point)

  const mineralRegions = (mineralResult?.estimated_regions || [])
    .map((region) => ({
      region,
      bounds: boundsFromMineralBox(region.bounding_box),
    }))
    .filter((item) => item.bounds)

  return {
    areaBounds:
      (location || mineralLocation)?.type === 'area'
        ? boundsFromBox(
            (location || mineralLocation).bounding_box,
          )
        : null,

    requestedPoint:
      (location || mineralLocation)?.type === 'point'
        ? pointFrom(
            (location || mineralLocation).latitude,
            (location || mineralLocation).longitude,
          )
        : null,

    gridPoint:
      location?.type === 'point'
        ? pointFrom(
            state?.latitude_used,
            state?.longitude_used,
          )
        : null,

    // Do not create live ARGO markers for area summaries.
    latestArgoPoint:
      location?.type === 'point' &&
      latest?.available === true
        ? pointFrom(
            argoField(latest, 'latitude'),
            argoField(latest, 'longitude'),
          )
        : null,

    historicalPoint:
      location?.type === 'point' &&
      historical
        ? pointFrom(
            historical.latitude,
            historical.longitude,
          )
        : null,

    mineralSites,
    mineralSamples,
    mineralRegions,
  }
}

function boundsFromBox(box) {
  if (
    !box ||
    !isFiniteNumber(box.south) ||
    !isFiniteNumber(box.west) ||
    !isFiniteNumber(box.north) ||
    !isFiniteNumber(box.east)
  ) {
    return null
  }

  return [
    [box.south, box.west],
    [box.north, box.east],
  ]
}

function boundsFromMineralBox(box) {
  if (
    !box ||
    !isFiniteNumber(box.lat_min) ||
    !isFiniteNumber(box.lat_max) ||
    !isFiniteNumber(box.lon_min) ||
    !isFiniteNumber(box.lon_max)
  ) {
    return null
  }

  return [
    [box.lat_min, box.lon_min],
    [box.lat_max, box.lon_max],
  ]
}


function pointFrom(
  latitude,
  longitude,
) {
  return isFiniteNumber(latitude) &&
    isFiniteNumber(longitude)
    ? [latitude, longitude]
    : null
}

function markerIcon(type) {
  return L.divIcon({
    className: `aqua-map-marker marker-${type}`,
    html: '<span></span>',
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -9],
  })
}

function displayValue(value) {
  return value == null || value === ''
    ? 'Unavailable'
    : value
}

/**
 * Area responses may place the latest actual
 * observation under latest_profile while point
 * responses may expose fields directly.
 */
function argoField(argo, field) {
  if (!argo) return null

  return (
    argo?.[field] ??
    argo?.latest_profile?.[field] ??
    argo?.surface_like_observation?.[field] ??
    null
  )
}

function argoAvailability(argo) {
  if (!argo) {
    return 'Unavailable'
  }

  if (argo.available === false) {
    return (
      argo.reason ||
      'Unavailable'
    )
  }

  if (argo.profile_count != null) {
    return `${argo.profile_count} profiles`
  }

  return 'Available'
}

function argoPressure(argo) {
  return (
    argo?.pressure_dbar ??
    argo?.surface_like_observation
      ?.pressure_dbar ??
    argo?.latest_profile
      ?.pressure_dbar ??
    argo?.latest_profile
      ?.surface_like_observation
      ?.pressure_dbar ??
    null
  )
}

function argoObservationTime(argo) {
  return (
    argo?.observation_time ??
    argo?.latest_observation_time ??
    argo?.latest_time ??
    argo?.latest_profile
      ?.observation_time ??
    argo?.latest_profile
      ?.latest_observation_time ??
    null
  )
}

function argoDistance(argo) {
  return (
    argo?.distance_km ??
    argo?.nearest_distance_km ??
    argo?.latest_profile
      ?.distance_km ??
    null
  )
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
  if (!isFiniteNumber(value)) {
    return null
  }

  const direction =
    value >= 0
      ? positive
      : negative

  return `${Math.abs(value).toFixed(
    3,
  )}\u00b0${direction}`
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
    )} - ${formatCoordinate(
      box.north,
      'N',
      'S',
    )}, ` +
    `${formatCoordinate(
      box.west,
      'E',
      'W',
    )} - ${formatCoordinate(
      box.east,
      'E',
      'W',
    )}`
  )
}

function formatCelsius(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(
        value,
        2,
      )}\u00b0C`
    : null
}

function formatSalinity(value) {
  return isFiniteNumber(value)
    ? formatNumber(value, 3)
    : null
}

function formatVelocity(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(
        value,
        3,
      )} m/s`
    : null
}

function formatMeters(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(
        value,
        3,
      )} m`
    : null
}

function formatKm(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(
        value,
        3,
      )} km`
    : null
}

function formatDbar(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(
        value,
        1,
      )} dbar`
    : null
}

function formatStats(
  stats,
  unit,
) {
  if (
    !stats ||
    typeof stats !== 'object'
  ) {
    return null
  }

  const values = [
    ['min', stats.min],
    ['mean', stats.mean],
    ['max', stats.max],
  ].filter(([, value]) =>
    isFiniteNumber(value),
  )

  if (!values.length) {
    return null
  }

  const digits =
    unit === 'm/s'
      ? 3
      : 2

  const displayUnit =
    unit === 'degC'
      ? '\u00b0C'
      : unit || ''

  return values
    .map(
      ([label, value]) =>
        `${label} ${formatNumber(
          value,
          digits,
        )}${
          displayUnit
            ? ` ${displayUnit}`
            : ''
        }`,
    )
    .join(' / ')
}

function formatList(values) {
  return Array.isArray(values) && values.length
    ? values.join(', ')
    : null
}

function formatMineralType(value) {
  return typeof value === 'string'
    ? value.replaceAll('_', ' ')
    : value
}

function formatEvidenceType(value) {
  const labels = {
    measured_seafloor_sample: 'Measured seafloor sample',
    peer_reviewed_reported_site: 'Literature-reported site',
    approximate_region_context: 'Approximate regional context',
    none: 'No stored mineral evidence',
  }

  return labels[value] || formatMineralType(value)
}

function formatDepthRange(value) {
  if (
    !Array.isArray(value) ||
    value.length < 2 ||
    !isFiniteNumber(value[0]) ||
    !isFiniteNumber(value[1])
  ) {
    return null
  }

  return `${formatNumber(value[0], 0)}-${formatNumber(value[1], 0)} m`
}

function formatPercent(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(value, 2)}%`
    : null
}

function formatKg(value) {
  return isFiniteNumber(value)
    ? `${formatNumber(value, 3)} kg`
    : null
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
  if (!isFiniteNumber(value)) {
    return ''
  }

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

export default OceanMap