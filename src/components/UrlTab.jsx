import { useState } from 'react'
import { verifyClaim, verifyWeb } from '../api.js'
import { useApp } from '../appContext.js'
import { Panel } from './common.jsx'
import { DomainCard, FactCheckView } from './Verification.jsx'
import WebVerificationList from './WebVerificationList.jsx'
import LiveScanner from './LiveScanner.jsx'
import { exportJson } from '../utils.js'

export default function UrlTab() {
  const { toast, addHistory } = useApp()
  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    if (!url.trim() && !text.trim()) return toast('Enter a URL and/or a claim to verify.', 'warn')
    setLoading(true)
    try {
      const r = await verifyClaim(text.trim(), url.trim())
      let web = null
      const q = text.trim() || r.page?.title || ''
      if (q) {
        try { web = (await verifyWeb(q, url.trim())).web } catch { /* shown as missing */ }
      }
      r.web = web
      setRes(r)
      addHistory({
        kind: 'verify',
        title: url.trim() || text.trim().slice(0, 90),
        score: r.domain?.trust_score ?? null,
        band: r.fact_check.overall === 'contradicted' ? 'Claim contradicted' : r.domain?.rating ?? 'No match',
        result: r,
      })
    } catch (e) {
      toast(e.message, 'err')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="tab">
      <Panel title="URL & live web verifier" tip="Checks the publisher against a bundled reputation registry + heuristics and cross-checks claims against fact-check sources.">
        <input className="input" placeholder="https://example.com/news/article" value={url} onChange={(e) => setUrl(e.target.value)} />
        <textarea className="input area" rows={4} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="Optional: a specific claim or the article text to fact-check (with a URL in online mode, the page text is fetched if this is empty)" />
        <div className="row">
          <span className="muted grow">
            {res ? <>Mode: <span className={`chip ${res.mode === 'online' ? 'chip-ok' : ''}`}>{res.mode}</span></> : 'Enter a claim to search the live internet; a URL adds publisher trust.'}
          </span>
          <button className="btn btn-primary" onClick={run} disabled={loading}>{loading ? 'Verifying…' : 'Verify'}</button>
        </div>
      </Panel>
      {loading && <LiveScanner />}
      {!loading && res && (
        <div className="report">
          <div className="report-actions no-print">
            <button className="btn btn-ghost" onClick={() => exportJson('fakeguard-verification', res)}>⬇ JSON</button>
            <button className="btn btn-ghost" onClick={() => window.print()}>🖨 Print / PDF</button>
          </div>
          <div className="grid-2">
            <Panel title="Publisher trust">{res.domain ? <DomainCard domain={res.domain} /> : <p className="muted">No URL supplied.</p>}</Panel>
            <Panel title="Page metadata">
              {res.page?.error && <p className="note">⚠ {res.page.error}</p>}
              {res.page && !res.page.error && (
                <>
                  <h4>{res.page.title || '(no title)'}</h4>
                  <p className="muted">{res.page.site_name} {res.page.author && `· ${res.page.author}`} {res.page.published && `· ${res.page.published}`}</p>
                  <p>{res.page.description}</p>
                </>
              )}
              {!res.page && <p className="muted">Live page fetching is disabled in offline mode. Start the backend with <code>FAKEGUARD_ONLINE=1</code> to enable it.</p>}
            </Panel>
          </div>
          {res.web && <Panel title="Live web verification"><WebVerificationList web={res.web} /></Panel>}
          <Panel title="Claim cross-check"><FactCheckView fact={res.fact_check} claims={res.claims} /></Panel>
        </div>
      )}
    </div>
  )
}
