import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  LinearScale,
  Tooltip,
} from 'chart.js'
import { Bar } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
)

const FIELDS = [
  {
    key: 'temperature_c',
    label: 'Temperature',
    unit: '°C',
    digits: 2,
  },
  {
    key: 'salinity',
    label: 'Salinity',
    unit: '',
    digits: 3,
  },
  {
    key: 'eastward_current_m_s',
    label: 'Eastward current',
    unit: 'm/s',
    digits: 3,
  },
  {
    key: 'northward_current_m_s',
    label: 'Northward current',
    unit: 'm/s',
    digits: 3,
  },
]

function OceanDashboardCharts({ result }) {
  const presentState = result?.present_state

  if (!presentState) {
    return null
  }

  return (
    <section className="ocean-dashboard-section">
      <div className="section-kicker">
        Regional Copernicus gridded analysis/forecast statistics
      </div>

      <div className="ocean-range-grid">
        {FIELDS.map((field) => (
          <RangeChart
            key={field.key}
            label={field.label}
            unit={field.unit}
            digits={field.digits}
            stats={presentState[field.key]}
          />
        ))}
      </div>

      <p className="scientific-note">
        Regional mean values are spatial summaries of the resolved model region
        and do not represent every point within that area.
      </p>
    </section>
  )
}

function RangeChart({
  label,
  unit,
  digits,
  stats,
}) {
  const min = finiteNumber(stats?.min)
  const mean = finiteNumber(stats?.mean)
  const max = finiteNumber(stats?.max)

  const values = [min, mean, max]
  const visibleValues = values.filter(
    (value) => value !== null,
  )

  if (!visibleValues.length) {
    return (
      <article className="ocean-range-card">
        <div className="ocean-range-card__header">
          <h3>{label}</h3>
          {unit && <span>{unit}</span>}
        </div>

        <div className="dashboard-unavailable">
          No regional statistics returned.
        </div>
      </article>
    )
  }

  const rawMin = Math.min(...visibleValues)
  const rawMax = Math.max(...visibleValues)
  const span = Math.max(Math.abs(rawMax - rawMin), 0.1)

  const data = {
    labels: ['Min', 'Mean', 'Max'],
    datasets: [
      {
        data: values,
        backgroundColor: [
          'rgba(45, 212, 191, 0.32)',
          'rgba(45, 212, 191, 0.68)',
          'rgba(224, 179, 77, 0.58)',
        ],
        borderColor: [
          'rgba(45, 212, 191, 0.72)',
          'rgba(45, 212, 191, 1)',
          'rgba(224, 179, 77, 0.9)',
        ],
        borderWidth: 1,
        borderRadius: 3,
        barThickness: 14,
      },
    ],
  }

  const options = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,

    animation: {
      duration: 250,
    },

    plugins: {
      legend: {
        display: false,
      },

      tooltip: {
        displayColors: false,

        callbacks: {
          label(context) {
            const value = finiteNumber(context.raw)

            if (value === null) {
              return 'Unavailable'
            }

            return `${formatNumber(value, digits)}${unit ? ` ${unit}` : ''}`
          },
        },
      },
    },

    scales: {
      x: {
        suggestedMin: rawMin - span * 0.08,
        suggestedMax: rawMax + span * 0.08,

        grid: {
          color: 'rgba(28, 51, 72, 0.45)',
        },

        ticks: {
          color: '#7d96a8',
          font: {
            size: 10,
          },
        },

        border: {
          color: '#1c3348',
        },
      },

      y: {
        grid: {
          display: false,
        },

        ticks: {
          color: '#a9bcc9',
          font: {
            size: 10,
          },
        },

        border: {
          color: '#1c3348',
        },
      },
    },
  }

  return (
    <article className="ocean-range-card">
      <div className="ocean-range-card__header">
        <h3>{label}</h3>
        {unit && <span>{unit}</span>}
      </div>

      <div className="ocean-range-values">
        <span>
          Min {displayNumber(min, digits, unit)}
        </span>

        <span>
          Mean {displayNumber(mean, digits, unit)}
        </span>

        <span>
          Max {displayNumber(max, digits, unit)}
        </span>
      </div>

      <div className="ocean-range-chart">
        <Bar data={data} options={options} />
      </div>
    </article>
  )
}

function displayNumber(value, digits, unit) {
  if (value === null) {
    return 'Unavailable'
  }

  return `${formatNumber(value, digits)}${unit ? ` ${unit}` : ''}`
}

function formatNumber(value, digits) {
  return value
    .toFixed(digits)
    .replace(/0+$/, '')
    .replace(/\.$/, '')
}

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value)
    ? value
    : null
}

export default OceanDashboardCharts