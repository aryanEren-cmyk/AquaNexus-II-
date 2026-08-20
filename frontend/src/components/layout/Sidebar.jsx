import {
  Bell,
  BotMessageSquare,
  ChartSpline,
  Database,
  FileSearch,
  Map,
  Waves,
} from 'lucide-react'

const ICONS = {
  Chat: BotMessageSquare,
  Charts: ChartSpline,
  Map,
  Profiles: Waves,
  Alerts: Bell,
  Evidence: FileSearch,
  Data: Database,
}

function Sidebar({ modules, activeModule, onSelectModule }) {
  return (
    <aside className="sidebar" aria-label="AquaNexus modules">
      <nav className="sidebar-nav">
        {modules.map((module) => {
          const Icon = ICONS[module] || Database
          const active = module === activeModule
          return (
            <button
              className={`sidebar-button ${active ? 'is-active' : ''}`}
              key={module}
              type="button"
              onClick={() => onSelectModule(module)}
              aria-label={module}
              title={module}
            >
              <Icon size={21} />
              <span>{module}</span>
            </button>
          )
        })}
      </nav>
    </aside>
  )
}

export default Sidebar
