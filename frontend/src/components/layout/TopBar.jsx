import { Activity, CircleDot, Radio, Waves } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getHealth } from '../../services/api.js'

function TopBar() {
  const [status, setStatus] = useState('checking')

  useEffect(() => {
    let cancelled = false

    async function checkHealth() {
      try {
        await getHealth()
        if (!cancelled) setStatus('online')
      } catch {
        if (!cancelled) setStatus('offline')
      }
    }

    checkHealth()
    const interval = window.setInterval(checkHealth, 30000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [])

  const online = status === 'online'

  return (
    <header className="topbar">
      <div className="brand-lockup">
        <div className="brand-mark">
          <Waves size={24} />
        </div>
        <div>
          <div className="brand-title">AquaNexus-II</div>
          <div className="brand-subtitle">Ocean intelligence workstation</div>
        </div>
      </div>

      <div className="topbar-center">
        <span>
          <Radio size={15} />
          Indian Ocean coverage
        </span>
        <span>
          <Activity size={15} />
          Copernicus + ARGO
        </span>
      </div>

      <div className={`backend-status ${online ? 'is-online' : 'is-offline'}`}>
        <CircleDot size={15} />
        {online ? 'SYSTEM ONLINE' : status === 'checking' ? 'CHECKING SYSTEM' : 'BACKEND OFFLINE'}
      </div>
    </header>
  )
}

export default TopBar
