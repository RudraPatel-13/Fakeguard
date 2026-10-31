import { Tip } from './common.jsx'

export function DomainCard({ domain }) {
  if (!domain) return null
  if (domain.rating === 'invalid') return <p className="muted">{domain.flags?.[0]}</p>
  const t = domain.trust_score
  const color = t == null ? 'var(--muted)' : t >= 70 ? 'var(--emerald)' : t >= 40 ? 'var(--amber)' : 'var(--crimson)'
  return (
    <div className="domain">
      <div className="domain-top">
        <div>
          <h4>{domain.name || domain.domain}</h4>
          <span className="muted">{domain.domain}</span>
        </div>
        <div className="domain-score" style={{ color, borderColor: color }}>{t ?? '–'}<small>/100</small></div>
      </div>
      <div className="chips">
        <span className="chip">{domain.known ? `rated: ${domain.rating}` : 'not in registry'}</span>
        {domain.bias && <span className="chip">bias: {domain.bias}</span>}
        {domain.fact_checker && <span className="chip chip-ok">fact-checker</span>}
        <span className="chip">
          age: {domain.estimated_domain_age_years ? `${domain.estimated_domain_age_years} yrs (approx.)` : 'unknown'}
          <Tip text="No live WHOIS lookup is performed. Age is shown only for registry domains, as an approximate founding era." />
        </span>
      </div>
      <ul className="indicators">{domain.flags.map((f) => <li key={f}>{f}</li>)}</ul>
      <p className="note">Source: {domain.source}</p>
    </div>
  )
}

export function FactCheckView({ fact, claims }) {
  if (!fact) return null
  return (
    <div>
      <p className="muted">
        Mode: <span className={`chip ${fact.mode === 'online' ? 'chip-ok' : ''}`}>{fact.mode}</span>
        {' '}{claims?.length ? `${claims.length} claim(s) extracted` : 'No verifiable claims extracted'}
      </p>
      <ul className="claims">
        {fact.results.map((r) => (
          <li key={r.claim} className={`claim claim-${r.status}`}>
            <p>“{r.claim}”</p>
            {r.status === 'contradicted' ? r.matches.map((m, i) => (
              <div key={i} className="claim-match">
                <span className="chip chip-bad">{m.rating}</span>
                <span className="muted"> {m.publisher}</span>
                {m.explanation && <p>{m.explanation}</p>}
                {m.url && <a href={m.url} target="_blank" rel="noreferrer noopener">source ↗</a>}
              </div>
            )) : <span className="chip">no known fact-check found</span>}
          </li>
        ))}
      </ul>
      {fact.notes?.map((n) => <p key={n} className="note">ℹ {n}</p>)}
    </div>
  )
}
