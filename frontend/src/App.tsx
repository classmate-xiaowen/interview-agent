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
        <div className="brand">
          <span className="brand-mark">🎯</span>
          <span>
            Speak Agent
            <br />
            <small>Interview Coach</small>
          </span>
        </div>
        <nav>
          {(['chat', 'knowledge', 'profile'] as Tab[]).map((t) => (
            <button
              key={t}
              className={tab === t ? 'active' : ''}
              aria-current={tab === t ? 'page' : undefined}
              onClick={() => setTab(t)}
            >
              {t === 'chat' ? 'Coach' : t === 'knowledge' ? 'Knowledge' : 'Profile'}
            </button>
          ))}
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
