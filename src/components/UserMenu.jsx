import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/authContext.js'
import { useApp } from '../appContext.js'
import { getScanStats } from '../api.js'

const initials = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase()

/** Header account area: Sign In button + guest pill when logged out, avatar dropdown when logged in. */
export default function UserMenu() {
  const { user, isAuthenticated, openAuth, openDrawer, logout, scanTick } = useAuth()
  const { toast } = useApp()
  const [open, setOpen] = useState(false)
  const [stats, setStats] = useState(null) // null = hidden
  const box = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const down = (e) => !box.current?.contains(e.target) && setOpen(false)
    const key = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', down)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('pointerdown', down); document.removeEventListener('keydown', key) }
  }, [open])

  async function showStats() {
    if (stats) return setStats(null)
    try {
      setStats(await getScanStats())
    } catch (e) {
      toast(e.message, 'err')
    }
  }
  // keep an open stats panel in step with newly saved scans
  useEffect(() => {
    if (!stats) return undefined
    let alive = true
    getScanStats().then((s) => alive && setStats(s)).catch(() => {})
    return () => { alive = false }
    // refresh only when a scan is saved
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanTick])

  if (!isAuthenticated) {
    return (
      <div className="usermenu">
        <span className="guest-pill" title="Sign in to save scans, use Rule Studio and export reports">Guest Mode (Scans Not Saved)</span>
        <button className="signin-btn" onClick={() => openAuth('login')}>Sign In</button>
      </div>
    )
  }

  return (
    <div className="usermenu" ref={box}>
      <button className="avatar-btn" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
        <span className="avatar">{initials(user.username)}</span>
        <span className="uname">{user.username}</span>
        <span className="vbadge" title="Signed in">✓</span>
      </button>
      {open && (
        <div className="umenu" role="menu">
          <div className="umenu-head">
            <span className="avatar big">{initials(user.username)}</span>
            <div><b>{user.username}</b><small>{user.email}</small></div>
          </div>
          <button role="menuitem" onClick={() => { setOpen(false); openDrawer() }}>📜 Scan History</button>
          <button role="menuitem" onClick={showStats}>📊 My Credibility Stats</button>
          {stats && (
            <div className="umenu-stats">
              <div><b>{stats.total_scans}</b><span>scans</span></div>
              <div><b>{stats.average_score ?? '–'}</b><span>avg score</span></div>
            </div>
          )}
          <button role="menuitem" className="danger" onClick={() => { setOpen(false); logout(); toast('Signed out. You are now in guest mode.', 'info') }}>🚪 Sign Out</button>
        </div>
      )}
    </div>
  )
}
