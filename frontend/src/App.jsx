import { useState } from 'react'
import { Database, FlaskConical } from 'lucide-react'

import ChatView from './components/chat/ChatView.jsx'
import Sidebar from './components/layout/Sidebar.jsx'
import TopBar from './components/layout/TopBar.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import MapPage from './pages/MapPage.jsx'
import ProfilesPage from './pages/ProfilesPage.jsx'

import './styles/variables.css'
import './styles/global.css'
import './styles/components.css'

const MODULES = ['Chat', 'Charts', 'Map', 'Profiles', 'Alerts', 'Evidence', 'Data']

function App() {
  const [activeModule, setActiveModule] = useState('Chat')

  return (
    <div className="app-shell">
      <TopBar />

      <div className="workspace">
        <Sidebar
          modules={MODULES}
          activeModule={activeModule}
          onSelectModule={setActiveModule}
        />

        <main className="page-surface">
          {activeModule === 'Chat' ? (
            <ChatView />
          ) : activeModule === 'Charts' ? (
            <DashboardPage />
          ) : activeModule === 'Map' ? (
            <MapPage />
          ) : activeModule === 'Profiles' ? (
            <ProfilesPage />
          ) : (
            <section className="module-placeholder" aria-live="polite">
              <div className="placeholder-kicker">
                <FlaskConical size={16} />
                {activeModule}
              </div>

              <h1>Module interface coming online</h1>

              <p>
                This console is reserved for verified AquaNexus data products.
                The interface will activate once the supporting backend module is ready.
              </p>

              <div className="placeholder-status">
                <Database size={16} />
                Awaiting module data contracts
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  )
}

export default App