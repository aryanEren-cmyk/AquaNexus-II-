import { Activity, Database, Gauge, Waves } from 'lucide-react'
import { useState } from 'react'

import ProfileCharts from '../components/profiles/ProfileCharts.jsx'
import {
  getArgoCycles,
  getArgoProfile,
} from '../services/api.js'

function ProfilesPage() {
  const [floatInput, setFloatInput] = useState('1901910')

  const [loadedFloatId, setLoadedFloatId] = useState(null)
  const [cycles, setCycles] = useState([])
  const [selectedCycle, setSelectedCycle] = useState('')

  const [profile, setProfile] = useState(null)
  const [submittedQuery, setSubmittedQuery] = useState(null)

  const [isLoadingCycles, setIsLoadingCycles] = useState(false)
  const [isLoadingProfile, setIsLoadingProfile] = useState(false)

  const [error, setError] = useState('')

  const isBusy = isLoadingCycles || isLoadingProfile

  function handleFloatChange(event) {
    setFloatInput(event.target.value)

    // Do not allow old cycles/profile evidence to remain associated
    // with a newly typed float ID.
    setLoadedFloatId(null)
    setCycles([])
    setSelectedCycle('')
    setProfile(null)
    setSubmittedQuery(null)
    setError('')
  }

  async function loadCycles() {
    if (isBusy) return

    const parsedFloatId = Number(floatInput)

    if (
      !Number.isInteger(parsedFloatId) ||
      parsedFloatId <= 0
    ) {
      setError('Enter a valid positive ARGO WMO float ID.')
      return
    }

    setIsLoadingCycles(true)
    setError('')

    // Clear previous scientific data immediately.
    setLoadedFloatId(null)
    setCycles([])
    setSelectedCycle('')
    setProfile(null)
    setSubmittedQuery(null)

    try {
      const response = await getArgoCycles(parsedFloatId)

      const returnedCycles = Array.isArray(response?.cycles)
        ? response.cycles
            .filter(
              (cycle) =>
                Number.isInteger(cycle) &&
                cycle >= 0,
            )
            .sort((a, b) => a - b)
        : []

      if (!returnedCycles.length) {
        throw new Error(
          'No ARGO cycles were returned for this float.',
        )
      }

      const platformNumber =
        response?.platform_number ?? parsedFloatId

      setLoadedFloatId(platformNumber)
      setCycles(returnedCycles)

      // Use latest returned cycle by default.
      setSelectedCycle(
        String(
          returnedCycles[
            returnedCycles.length - 1
          ],
        ),
      )
    } catch (requestError) {
      setError(
        requestError?.message ||
          'Unable to retrieve ARGO cycles.',
      )
    } finally {
      setIsLoadingCycles(false)
    }
  }

  async function loadProfile() {
    if (isBusy) return

    if (!loadedFloatId || !cycles.length) {
      setError(
        'Load cycles for the ARGO float before requesting a profile.',
      )
      return
    }

    const parsedFloatInput = Number(floatInput)

    if (parsedFloatInput !== loadedFloatId) {
      setError(
        'The float ID has changed. Load cycles again before loading a profile.',
      )
      return
    }

    const parsedCycle = Number(selectedCycle)

    if (
      !Number.isInteger(parsedCycle) ||
      !cycles.includes(parsedCycle)
    ) {
      setError(
        'Select a valid cycle returned by the backend.',
      )
      return
    }

    const querySnapshot = {
      floatId: loadedFloatId,
      cycle: parsedCycle,
    }

    setIsLoadingProfile(true)
    setError('')

    // Prevent a failed request from leaving stale profile charts visible.
    setProfile(null)
    setSubmittedQuery(null)

    try {
      const response = await getArgoProfile(
        querySnapshot.floatId,
        querySnapshot.cycle,
      )

      if (
        !response ||
        !Array.isArray(response.profile)
      ) {
        throw new Error(
          'The backend returned an invalid ARGO profile.',
        )
      }

      setSubmittedQuery(querySnapshot)
      setProfile(response)
    } catch (requestError) {
      setError(
        requestError?.message ||
          'Unable to retrieve the requested ARGO profile.',
      )
    } finally {
      setIsLoadingProfile(false)
    }
  }

  function changeCycle(event) {
    setSelectedCycle(event.target.value)

    // The selected control now differs from the currently rendered
    // scientific result, so remove the old profile until submitted.
    setProfile(null)
    setSubmittedQuery(null)
    setError('')
  }

  return (
    <div className="profiles-layout">
      <section
        className="profiles-workstation"
        aria-label="ARGO profile explorer"
      >
        <div className="console-header">
          <div>
            <p className="eyebrow">
              ARGO Profile Explorer
            </p>

            <h1>Vertical ocean profile observations</h1>
          </div>

          <div className="console-chip">
            <Waves size={16} />
            In-situ profile analysis
          </div>
        </div>

        <div className="profiles-control-bar">
          <label>
            <span>WMO Float ID</span>

            <input
              type="number"
              min="1"
              step="1"
              value={floatInput}
              onChange={handleFloatChange}
              disabled={isBusy}
              aria-label="ARGO WMO float ID"
            />
          </label>

          <button
            type="button"
            onClick={loadCycles}
            disabled={isBusy || !floatInput.trim()}
          >
            {isLoadingCycles
              ? 'Loading...'
              : 'Load cycles'}
          </button>

          <label>
            <span>Cycle</span>

            <select
              value={selectedCycle}
              onChange={changeCycle}
              disabled={
                isBusy || cycles.length === 0
              }
              aria-label="ARGO cycle"
            >
              {cycles.length === 0 ? (
                <option value="">
                  No cycles loaded
                </option>
              ) : (
                cycles.map((cycle) => (
                  <option
                    key={cycle}
                    value={cycle}
                  >
                    {cycle}
                  </option>
                ))
              )}
            </select>
          </label>

          <button
            type="button"
            onClick={loadProfile}
            disabled={
              isBusy ||
              !loadedFloatId ||
              !selectedCycle
            }
          >
            {isLoadingProfile
              ? 'Loading...'
              : 'Load profile'}
          </button>
        </div>

        {isBusy && (
          <div className="querying-indicator">
            <span />
            {isLoadingCycles
              ? 'LOADING ARGO CYCLES...'
              : 'LOADING ARGO PROFILE...'}
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

        <div className="profiles-scroll">
          {!profile && !isBusy && (
            <div className="profile-empty-state">
              <Database size={22} />

              <div>
                <strong>
                  Select a verified ARGO profile
                </strong>

                <p>
                  Load available cycles for a WMO
                  float, select a cycle, then retrieve
                  its measured temperature, salinity
                  and pressure profile.
                </p>
              </div>
            </div>
          )}

          {profile && (
            <>
              <ProfileMetadata profile={profile} />

              <ProfileCharts
                points={profile.profile}
              />

              <div className="profile-analysis-grid">
                <ThermoclineCard
                  thermocline={profile.thermocline}
                />

                <StatisticsCard
                  statistics={profile.statistics}
                />
              </div>
            </>
          )}
        </div>
      </section>

      <ProfileIntelligencePanel
        profile={profile}
        query={submittedQuery}
        cycleCount={cycles.length}
      />
    </div>
  )
}

function ProfileMetadata({ profile }) {
  const stats = profile?.statistics

  return (
    <section>
      <div className="profile-section-heading">
        <div>
          <p className="eyebrow">
            Profile Metadata
          </p>

          <h2>
            Float {profile.platform_number} · Cycle{' '}
            {profile.cycle_number}
          </h2>
        </div>

        <span className="module-chip">
          ARGO
        </span>
      </div>

      <div className="profile-metadata-grid">
        <MetricCard
          label="Position"
          value={formatCoordinates(
            profile.latitude,
            profile.longitude,
          )}
        />

        <MetricCard
          label="Observation"
          value={formatTimestamp(profile.time)}
        />

        <MetricCard
          label="Valid measurements"
          value={
            stats?.valid_temperature_points != null
              ? `${stats.valid_temperature_points} points`
              : null
          }
        />

        <MetricCard
          label="Pressure coverage"
          value={formatRange(
            stats?.min_pressure,
            stats?.max_pressure,
            'dbar',
            1,
          )}
        />
      </div>
    </section>
  )
}

function MetricCard({ label, value }) {
  return (
    <div className="profile-metric-card">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  )
}

function ThermoclineCard({ thermocline }) {
  const detected = thermocline?.detected === true

  return (
    <section
      className={`profile-analysis-card ${
        detected ? 'is-detected' : ''
      }`}
    >
      <div className="profile-card-heading">
        <Gauge size={17} />

        <div>
          <span>Thermocline Analysis</span>

          <strong
            className="profile-analysis-status"
          >
            {detected
              ? 'Thermocline detected'
              : 'No thermocline detected'}
          </strong>
        </div>
      </div>

      {detected ? (
        <div className="profile-stat-list">
          <ProfileRow
            label="Pressure interval"
            value={formatRange(
              thermocline.pressure_start,
              thermocline.pressure_end,
              'dbar',
              1,
            )}
          />

          <ProfileRow
            label="Strongest gradient"
            value={
              isFiniteNumber(
                thermocline.gradient_c_per_dbar,
              )
                ? `${formatNumber(
                    thermocline.gradient_c_per_dbar,
                    3,
                  )} °C/dbar`
                : null
            }
          />

          <ProfileRow
            label="Threshold"
            value={
              isFiniteNumber(
                thermocline.threshold,
              )
                ? `${formatNumber(
                    thermocline.threshold,
                    3,
                  )} °C/dbar`
                : null
            }
          />

          <ProfileRow
            label="Method"
            value={thermocline.method}
          />
        </div>
      ) : (
        <p className="profile-method-note">
          No thermocline was identified by the
          current heuristic.
        </p>
      )}

      <p className="profile-method-note">
        Simplified heuristic — not a formal
        oceanographic thermocline classification.
      </p>
    </section>
  )
}

function StatisticsCard({ statistics }) {
  return (
    <section className="profile-analysis-card">
      <div className="profile-card-heading">
        <Activity size={17} />

        <div>
          <span>Profile Statistics</span>

          <strong>
            Verified measurements
          </strong>
        </div>
      </div>

      <div className="profile-stat-list">
        <ProfileRow
          label="Temperature points"
          value={
            statistics?.valid_temperature_points
          }
        />

        <ProfileRow
          label="Salinity points"
          value={
            statistics?.valid_salinity_points
          }
        />

        <ProfileRow
          label="Temperature"
          value={formatMinMeanMax(
            statistics?.min_temperature,
            statistics?.mean_temperature,
            statistics?.max_temperature,
            '°C',
            2,
          )}
        />

        <ProfileRow
          label="Salinity"
          value={formatMinMeanMax(
            statistics?.min_salinity,
            statistics?.mean_salinity,
            statistics?.max_salinity,
            '',
            3,
          )}
        />

        <ProfileRow
          label="Pressure"
          value={formatRange(
            statistics?.min_pressure,
            statistics?.max_pressure,
            'dbar',
            1,
          )}
        />
      </div>
    </section>
  )
}

function ProfileRow({ label, value }) {
  return (
    <div className="profile-stat-row">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  )
}

function ProfileIntelligencePanel({
  profile,
  query,
  cycleCount,
}) {
  return (
    <aside
      className="evidence-panel profile-intelligence-panel"
      aria-label="ARGO profile intelligence"
    >
      <div className="evidence-header">
        <div>
          <p className="eyebrow">
            Profile Intelligence
          </p>

          <h2>Scientific context</h2>
        </div>

        <Database size={20} />
      </div>

      <div className="evidence-stack">
        <EvidenceBlock title="Source">
          <EvidenceLine
            label="Dataset"
            value={profile?.source || 'ARGO'}
          />

          <EvidenceLine
            label="Type"
            value="In-situ observation"
          />
        </EvidenceBlock>

        <EvidenceBlock title="Profile">
          <EvidenceLine
            label="Platform"
            value={
              profile?.platform_number ??
              query?.floatId
            }
          />

          <EvidenceLine
            label="Cycle"
            value={
              profile?.cycle_number ??
              query?.cycle
            }
          />

          <EvidenceLine
            label="Cycles available"
            value={
              cycleCount > 0
                ? cycleCount
                : null
            }
          />
        </EvidenceBlock>

        <EvidenceBlock title="Observation">
          <EvidenceLine
            label="Position"
            value={formatCoordinates(
              profile?.latitude,
              profile?.longitude,
            )}
          />

          <EvidenceLine
            label="Time"
            value={formatTimestamp(
              profile?.time,
            )}
          />

          <EvidenceLine
            label="Direction"
            value={profile?.direction}
          />

          <EvidenceLine
            label="Data mode"
            value={profile?.data_mode}
          />
        </EvidenceBlock>

        <EvidenceBlock title="Vertical coordinate">
          <EvidenceLine
            label="Coordinate"
            value="Pressure"
          />

          <EvidenceLine
            label="Unit"
            value="dbar"
          />

          <p className="map-note">
            ARGO pressure is displayed exactly in
            dbar and is not treated as exact depth
            in meters.
          </p>
        </EvidenceBlock>

        <EvidenceBlock title="Data integrity">
          <p className="map-note">
            Charts contain only profile measurements
            returned by the AquaNexus ARGO backend.
            No synthetic or interpolated points are
            added by the frontend.
          </p>
        </EvidenceBlock>
      </div>
    </aside>
  )
}

function EvidenceBlock({ title, children }) {
  return (
    <section className="evidence-block">
      <div className="evidence-block-title">
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

      <strong>{displayValue(value)}</strong>
    </div>
  )
}

function displayValue(value) {
  return value == null || value === ''
    ? 'Unavailable'
    : value
}

function formatCoordinates(latitude, longitude) {
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
  positiveDirection,
  negativeDirection,
) {
  const direction =
    value >= 0
      ? positiveDirection
      : negativeDirection

  return `${Math.abs(value).toFixed(
    3,
  )}°${direction}`
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

function formatRange(
  min,
  max,
  unit,
  digits,
) {
  if (
    !isFiniteNumber(min) ||
    !isFiniteNumber(max)
  ) {
    return null
  }

  return `${formatNumber(
    min,
    digits,
  )} – ${formatNumber(
    max,
    digits,
  )} ${unit}`
}

function formatMinMeanMax(
  min,
  mean,
  max,
  unit,
  digits,
) {
  if (
    !isFiniteNumber(min) ||
    !isFiniteNumber(mean) ||
    !isFiniteNumber(max)
  ) {
    return null
  }

  const suffix = unit ? ` ${unit}` : ''

  return (
    `${formatNumber(min, digits)} / ` +
    `${formatNumber(mean, digits)} / ` +
    `${formatNumber(max, digits)}${suffix}`
  )
}

function formatNumber(value, digits) {
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

export default ProfilesPage