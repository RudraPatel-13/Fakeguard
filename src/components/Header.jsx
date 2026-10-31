import { useEffect, useState } from 'react'
import { getModelInfo } from '../api.js'
import UserMenu from './UserMenu.jsx'

const TABS = [
  ['article', 'Article & Text'],
  ['image', 'Image Forensics'],
  ['url', 'URL Verifier'],
  ['rules', 'Rule Studio'],
  ['history', 'Audit History'],
]

export default function Header({ tab, setTab }) {
  const [status, setStatus] = useState({ state: 'checking' })

  useEffect(() => {
    let alive = true
    getModelInfo()
      .then((m) => alive && setStatus({ state: 'up', mode: m.fusion?.web_search === 'live' ? 'live web' : 'offline' }))
      .catch(() => alive && setStatus({ state: 'down' }))
    return () => { alive = false }
  }, [])

  return (
    <header className="header no-print">
      <div className="brand">
        <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
          <path d="M16 2 4 7v8c0 7.5 5 13 12 15 7-2 12-7.5 12-15V7z" fill="none" stroke="var(--cyan)" strokeWidth="2" />
          <path d="m10.5 16 4 4 7-8" fill="none" stroke="var(--emerald)" strokeWidth="2.4" strokeLinecap="round" />
        </svg>
        <div>
          <h1>FAKE<span>GUARD</span></h1>
          <p>Credibility &amp; forensics workstation</p>
        </div>
      </div>
      <nav className="tabs" role="tablist">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </nav>
      <div className={`status status-${status.state}`} title="Backend connection">
        <i /> {status.state === 'up' ? `API online · ${status.mode}` : status.state === 'down' ? 'API offline' : 'connecting…'}
      </div>
      <UserMenu />
    </header>
  )
}
