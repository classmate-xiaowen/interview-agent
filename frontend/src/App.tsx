import { useState } from 'react'
import KnowledgePage from './pages/KnowledgePage'
import ChatPage from './pages/ChatPage'
import ProfilePage from './pages/ProfilePage'
import './index.css'

type Tab = 'chat' | 'knowledge' | 'profile'

export default function App() {
  const [tab, setTab] = useState<Tab>('chat')
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">🎯 Speak Agent</div>
        <nav>
          <button className={tab === 'chat' ? 'active' : ''} onClick={() => setTab('chat')}>
            Coach
          </button>
          <button
            className={tab === 'knowledge' ? 'active' : ''}
            onClick={() => setTab('knowledge')}
          >
            Knowledge
          </button>
          <button className={tab === 'profile' ? 'active' : ''} onClick={() => setTab('profile')}>
            Profile
          </button>
        </nav>
      </header>
      <main className="content">
        {tab === 'chat' && <ChatPage />}
        {tab === 'knowledge' && <KnowledgePage />}
        {tab === 'profile' && <ProfilePage />}
      </main>
    </div>
  )
}
