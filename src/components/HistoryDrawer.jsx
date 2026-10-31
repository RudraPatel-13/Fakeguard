import { useEffect, useState } from 'react'
import { useAuth } from '../context/authContext.js'
import { getScanHistory, getScanStats } from '../api.js'
import { fmtDate } from '../utils.js'

const tone = (s) => (s == null ? 'gray' : s >= 70 ? 'good' : s >= 40 ? 'warn' : 'bad')

/** Slide-out list of the signed-in user's saved scans (server-side), with summary stats. */
export default function HistoryDrawer() {
  const { drawer, closeDrawer, scanTick, logout } = useAuth()
  const [data, setData] = useState({ scans: null, stats: null, error: '' })

  useEffect(() => {
    if (!drawer) return undefined
    let alive = true
    Promise.all([getScanHistory(50), getScanStats()])
      .then(([h, st]) => alive && setData({ scans: h.scans, stats: st, error: '' }))
      .catch((e) => {
        if (!alive) return
        if (e.status === 401) logout()
        else setData({ scans: [], stats: null, error: e.message })
      })
    return () => { alive = false }
  }, [drawer, scanTick, logout])

  useEffect(() => {
    if (!drawer) return undefined
    const onKey = (e) => e.key === 'Escape' && closeDrawer()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [drawer, closeDrawer])

  const { scans, stats, error } = data
  return (
    <div className={`drawer-wrap ${drawer ? 'open' : ''}`} aria-hidden={!drawer}>
      <div className="drawer-scrim" onClick={closeDrawer} />
      <aside className="drawer" role="dialog" aria-label="Scan history">
        <header>
          <h3>📜 Scan History</h3>
          <button className="auth-x static" onClick={closeDrawer} aria-label="Close history">✕</button>
        </header>
        <div className="drawer-stats">
          <div><b>{stats?.total_scans ?? '–'}</b><span>scans saved</span></div>
          <div><b>{stats?.average_score ?? '–'}</b><span>avg credibility</span></div>
        </div>
        <div className="drawer-body">
          {error && <p className="auth-error">⚠ {error}</p>}
          {!scans && !error && <p className="muted">Loading…</p>}
          {scans && !scans.length && !error && <p className="muted">No saved scans yet. Run an analysis while signed in and it appears here.</p>}
          <ul>
            {scans?.map((s, i) => (
              <li key={s.id} style={{ '--i': i }}>
                <span className={`dscore d-${tone(s.credibility_score)}`}>{s.credibility_score != null ? Math.round(s.credibility_score) : '–'}</span>
                <div>
                  <p>{s.summary || '(no summary)'}</p>
                  <small className="muted">{s.input_type === 'image' ? '🖼️ Image' : '📝 Text'} · {s.verdict} · {fmtDate(s.timestamp)}</small>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  )
}
