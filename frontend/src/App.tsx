import { Link, NavLink, Route, Routes, Navigate } from 'react-router-dom'
import KnowledgePage from './pages/KnowledgePage'
import ChatPage from './pages/ChatPage'
import ProfilePage from './pages/ProfilePage'
import ResumePage from './pages/ResumePage'
import './index.css'

const tabs = [
  { to: '/chat', label: 'Coach' },
  { to: '/knowledge', label: 'Knowledge' },
  { to: '/resume', label: 'Resume' },
  { to: '/profile', label: 'Profile' },
]

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/chat" className="brand">
          <span className="brand-mark">🎯</span>
          <span>
            Speak Agent
            <br />
            <small>Interview Coach</small>
          </span>
        </Link>
        <nav>
          {tabs.map((t) => (
            <NavLink key={t.to} to={t.to} className={({ isActive }) => (isActive ? 'active' : '')}>
              {t.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/resume" element={<ResumePage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </main>
    </div>
  )
}
