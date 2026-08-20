import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { Droplets, Thermometer } from 'lucide-react'
import { Line } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
)

function ProfileCharts({ points }) {
  const temperaturePoints = normalizeProfilePoints(
    points,
    'temperature',
  )

  const salinityPoints = normalizeProfilePoints(
    points,
    'salinity',
  )

  return (
    <section>
      <div className="profile-section-heading">
        <div>
          <p className="eyebrow">
            Measured Vertical Structure
          </p>

          <h2>Profile curves</h2>
        </div>

        <span className="module-chip">
          Pressure in dbar
        </span>
      </div>

      <div className="profile-chart-grid">
        <ChartCard
          icon={<Thermometer size={17} />}
          title="Temperature vs Pressure"
          subtitle={`${temperaturePoints.length} measured points`}
        >
          <Line
            data={buildTemperatureData(
              temperaturePoints,
            )}
            options={buildChartOptions(
              'Temperature (°C)',
              '°C',
              2,
            )}
          />
        </ChartCard>

        <ChartCard
          icon={<Droplets size={17} />}
          title="Salinity vs Pressure"
          subtitle={`${salinityPoints.length} measured points`}
        >
          <Line
            data={buildSalinityData(
              salinityPoints,
            )}
            options={buildChartOptions(
              'Salinity',
              '',
              3,
            )}
          />
        </ChartCard>
      </div>
    </section>
  )
}

function ChartCard({
  icon,
  title,
  subtitle,
  children,
}) {
  return (
    <div className="profile-chart-block">
      <div className="profile-chart-head">
        <div>
          <span className="profile-chart-title">
            {icon}
            {title}
          </span>

          <small>{subtitle}</small>
        </div>

        <span className="profile-chart-unit">
          Y: PRESSURE (DBAR)
        </span>
      </div>

      <div className="profile-chart-canvas">
        {children}
      </div>
    </div>
  )
}

function normalizeProfilePoints(
  points,
  variable,
) {
  if (!Array.isArray(points)) {
    return []
  }

  return points
    .filter(
      (point) =>
        isFiniteNumber(point?.pressure) &&
        isFiniteNumber(point?.[variable]),
    )
    .map((point) => ({
      x: point[variable],
      y: point.pressure,
    }))
    .sort((a, b) => a.y - b.y)
}

function buildTemperatureData(points) {
  return {
    datasets: [
      {
        label: 'ARGO temperature',
        data: points,
        parsing: false,

        borderColor: '#ff6b4a',
        backgroundColor: '#ff6b4a',

        borderWidth: 1.6,

        pointRadius: 2,
        pointHoverRadius: 4,

        showLine: true,

        // No smoothing/interpolation of scientific profile shape.
        tension: 0,

        spanGaps: false,
      },
    ],
  }
}

function buildSalinityData(points) {
  return {
    datasets: [
      {
        label: 'ARGO salinity',
        data: points,
        parsing: false,

        borderColor: '#e0b34d',
        backgroundColor: '#e0b34d',

        borderWidth: 1.6,

        pointRadius: 2,
        pointHoverRadius: 4,

        showLine: true,
        tension: 0,
        spanGaps: false,
      },
    ],
  }
}

function buildChartOptions(
  xAxisTitle,
  xUnit,
  xDigits,
) {
  return {
    responsive: true,
    maintainAspectRatio: false,

    animation: {
      duration: 250,
    },

    interaction: {
      mode: 'nearest',
      intersect: false,
    },

    plugins: {
      legend: {
        display: false,
      },

      tooltip: {
        displayColors: false,

        callbacks: {
          title(items) {
            const pressure =
              items?.[0]?.parsed?.y

            return isFiniteNumber(pressure)
              ? `Pressure: ${formatNumber(
                  pressure,
                  1,
                )} dbar`
              : ''
          },

          label(context) {
            const value =
              context?.parsed?.x

            if (!isFiniteNumber(value)) {
              return ''
            }

            return `${xAxisTitle}: ${formatNumber(
              value,
              xDigits,
            )}${xUnit ? ` ${xUnit}` : ''}`
          },
        },
      },
    },

    scales: {
      x: {
        type: 'linear',

        title: {
          display: true,
          text: xAxisTitle,
          color: '#a9bcc9',

          font: {
            size: 11,
          },
        },

        ticks: {
          color: '#7d96a8',

          font: {
            size: 10,
          },
        },

        grid: {
          color: 'rgba(28, 51, 72, 0.45)',
        },

        border: {
          color: '#1c3348',
        },
      },

      y: {
        type: 'linear',

        // Low pressure at top, high pressure at bottom.
        reverse: true,

        title: {
          display: true,
          text: 'Pressure (dbar)',
          color: '#a9bcc9',

          font: {
            size: 11,
          },
        },

        ticks: {
          color: '#7d96a8',

          font: {
            size: 10,
          },

          callback(value) {
            return `${value}`
          },
        },

        grid: {
          color: 'rgba(28, 51, 72, 0.45)',
        },

        border: {
          color: '#1c3348',
        },
      },
    },
  }
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

export default ProfileCharts