import { Tip } from './common.jsx'

const safeHref = (u) => (/^https?:\/\//i.test(u || '') ? u : undefined)

function Badge({ r }) {
  if (r.tier === 'fact_checker') {
    const v = r.fact_check_verdict
    if (v === 'debunked') return <span className="badge badge-bad">Fact-Check: Debunked</span>
    if (v === 'supported') return <span className="badge badge-ok">Fact-Check: Supported</span>
    return <span className="badge badge-info">Fact-Check: See article</span>
  }
  if (r.flagged_source) return <span className="badge badge-bad">Flagged source</span>
  if (r.tier === 'verified_outlet') {
    return r.disputes_claim
      ? <span className="badge badge-warn">Verified Outlet · disputes claim</span>
      : <span className="badge badge-ok">Verified Outlet</span>
  }
  return <span className="badge badge-gray">Unranked Blog</span>
}

const levelColor = (s) => (s == null ? 'var(--muted)' : s >= 80 ? 'var(--emerald)' : s >= 40 ? 'var(--amber)' : 'var(--rose)')

/** Corroboration meter + live feed of internet sources. */
export default function WebVerificationList({ web }) {
  if (!web) return null
  const c = web.corroboration
  return (
    <div className="web">
      <div className={`web-banner ${web.mode === 'live' ? 'live' : 'offline'}`}>
        <i className="pulse-dot" />
        {web.mode === 'live'
          ? <>Live internet search · query “{web.query}”</>
          : <><b>Offline mode / simulation mode.</b> Live search was not possible; only the bundled registry was used.</>}
      </div>

      <div className="corr">
        <div className="corr-score" style={{ color: levelColor(c.score) }}>
          {c.score == null ? '–' : c.score}<small>{c.score == null ? '' : '%'}</small>
        </div>
        <div className="grow">
          <div className="corr-head">
            <b>Web corroboration: {c.level}</b>
            <Tip text="High ≥80%: several verified outlets report it. Medium 40–79%: limited or mixed coverage. Low <40%: no credible coverage or flagged as debunked. Absence of coverage is not proof of falsehood." />
          </div>
          <div className="bar"><i style={{ width: `${c.score ?? 0}%`, background: levelColor(c.score) }} /></div>
          <p className="muted corr-text">{c.explanation}</p>
          {c.verified_outlets?.length > 0 && (
            <div className="chips">{c.verified_outlets.map((o) => <span key={o} className="badge badge-ok">{o}</span>)}</div>
          )}
        </div>
      </div>

      {web.results.length > 0 && (
        <ul className="feed">
          {web.results.map((r) => (
            <li key={r.url} className="feed-item">
              <div className="feed-top">
                <Badge r={r} />
                <span className="muted">{r.publisher || r.domain || 'unknown publisher'}</span>
                {r.published && <span className="muted">· {new Date(r.published).toLocaleDateString()}</span>}
              </div>
              <a href={safeHref(r.url)} target="_blank" rel="noreferrer noopener">{r.title} ↗</a>
              {r.snippet && <p className="muted">{r.snippet}</p>}
            </li>
          ))}
        </ul>
      )}
      {web.results.length === 0 && web.mode === 'live' && <p className="muted">No relevant articles found.</p>}
      {web.notes?.map((n) => <p key={n} className="note">ℹ {n}</p>)}
    </div>
  )
}
