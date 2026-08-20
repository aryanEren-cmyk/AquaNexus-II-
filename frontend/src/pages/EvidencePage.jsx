import {
  Activity,
  Database,
  FlaskConical,
  MapPinned,
  ShieldCheck,
  Waves,
} from 'lucide-react'

const COPERNICUS_VARIABLES = [
  'Temperature',
  'Salinity',
  'Eastward current',
  'Northward current',
]

const ARGO_VARIABLES = [
  'Pressure',
  'Temperature',
  'Salinity',
]

const METHODS = [
  {
    title: 'Spatial ocean conditions',
    description:
      'Named locations and coordinates are resolved into point or area queries. Copernicus present-state values and ARGO context are then retrieved through deterministic backend tools.',
  },
  {
    title: 'ARGO value at pressure',
    description:
      'Temperature and salinity values at requested pressure levels use bounded linear interpolation. Values are not extrapolated outside the measured pressure range.',
  },
  {
    title: 'Thermocline heuristic',
    description:
      'The strongest temperature-gradient interval is surfaced as a simplified thermocline indicator. It is explicitly not presented as a formal oceanographic thermocline classification.',
  },
  {
    title: 'Historical temperature anomaly',
    description:
      'The current practical baseline compares the target observation against same-calendar-month historical ARGO observations within a spatial radius and pressure tolerance.',
  },
  {
    title: 'Nearest historical profile search',
    description:
      'Historical ARGO profile metadata is indexed and searched spatially with vectorized Haversine distance calculations.',
  },
]

function EvidencePage() {
  return (
    <div className="provenance-page">
      <header className="provenance-hero">
        <div>
          <p className="eyebrow">Evidence &amp; Provenance</p>
          <h1>Scientific traceability</h1>
          <p className="provenance-intro">
            AquaNexus separates model estimates, in-situ observations and
            analytical methods so that every displayed result can be interpreted
            with the correct scientific meaning.
          </p>
        </div>

        <div className="console-chip">
          <ShieldCheck size={16} />
          Evidence-first workflow
        </div>
      </header>

      <section className="provenance-source-grid">
        <SourceCard
          icon={<Waves size={18} />}
          title="Copernicus Marine"
          badge="MODEL ESTIMATE"
        >
          <EvidenceRow
            label="Product"
            value="GLOBAL_ANALYSISFORECAST_PHY_001_024"
          />
          <EvidenceRow
            label="Data type"
            value="Gridded analysis/forecast estimate"
          />
          <EvidenceRow
            label="Variables"
            value={COPERNICUS_VARIABLES.join(', ')}
          />
          <EvidenceRow
            label="Vertical coordinate"
            value="Model grid depth (m)"
          />
          <EvidenceRow
            label="Operational coverage"
            value="60°E–100°E, 0°N–30°N"
          />

          <p className="scientific-note">
            Copernicus values are model-grid estimates and are never labeled as
            direct ocean measurements.
          </p>
        </SourceCard>

        <SourceCard
          icon={<Database size={18} />}
          title="ARGO"
          badge="IN-SITU OBSERVATION"
        >
          <EvidenceRow
            label="Observation type"
            value="Physical ARGO in-situ profile observations"
          />
          <EvidenceRow
            label="Historical period"
            value="2021–2025"
          />
          <EvidenceRow
            label="Variables"
            value={ARGO_VARIABLES.join(', ')}
          />
          <EvidenceRow
            label="Vertical coordinate"
            value="Pressure (dbar)"
          />
          <EvidenceRow
            label="Quality control"
            value="Accepted QC flag: 1"
          />
          <EvidenceRow
            label="Near-real-time"
            value="Separate live ARGO cache"
          />

          <p className="scientific-note">
            ARGO pressure is preserved in dbar and is not treated as exact depth
            in meters.
          </p>
        </SourceCard>
      </section>

      <section className="provenance-section">
        <div className="provenance-section-heading">
          <div>
            <p className="eyebrow">Analysis Methods</p>
            <h2>Deterministic scientific processing</h2>
          </div>

          <FlaskConical size={20} />
        </div>

        <div className="method-grid">
          {METHODS.map((method) => (
            <article
              className="method-card"
              key={method.title}
            >
              <div className="method-card-title">
                <Activity size={15} />
                {method.title}
              </div>

              <p>{method.description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="provenance-section">
        <div className="provenance-section-heading">
          <div>
            <p className="eyebrow">Interpretation Guardrails</p>
            <h2>What AquaNexus does not claim</h2>
          </div>

          <MapPinned size={20} />
        </div>

        <div className="guardrail-grid">
          <Guardrail text="ARGO observations are not used as direct oil-spill, mineral-deposit or submarine-cable damage detections." />
          <Guardrail text="Copernicus gridded values are not described as measured values." />
          <Guardrail text="ARGO pressure in dbar is not converted into exact depth in meters by the frontend." />
          <Guardrail text="The thermocline detector is a simplified heuristic rather than a formal classification." />
          <Guardrail text="The historical anomaly baseline is a practical project baseline, not a formal climatology or statistical-significance product." />
          <Guardrail text="Evidence Trail exposes data provenance and tool results, not private model chain-of-thought." />
        </div>
      </section>
    </div>
  )
}

function SourceCard({
  icon,
  title,
  badge,
  children,
}) {
  return (
    <article className="provenance-source-card">
      <div className="provenance-source-header">
        <div className="provenance-source-title">
          {icon}
          <div>
            <span>DATA SOURCE</span>
            <h2>{title}</h2>
          </div>
        </div>

        <span className="module-chip">
          {badge}
        </span>
      </div>

      <div className="provenance-row-list">
        {children}
      </div>
    </article>
  )
}

function EvidenceRow({
  label,
  value,
}) {
  return (
    <div className="provenance-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function Guardrail({ text }) {
  return (
    <div className="guardrail-card">
      <ShieldCheck size={15} />
      <p>{text}</p>
    </div>
  )
}

export default EvidencePage