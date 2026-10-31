import { useState } from 'react'
import { useApp } from '../appContext.js'
import { Panel } from './common.jsx'
import CredibilityReport from './CredibilityReport.jsx'
import { bandColor, exportJson, fmtDate } from '../utils.js'

const KIND = { article: 'TEXT', image: 'IMAGE', verify: 'VERIFY' }

export default function HistoryTab() {
  const { history, clearHistory, removeHistory, toast } = useApp()
  const [openId, setOpenId] = useState(null)
  const open = history.find((h) => h.id === openId)

  return (
    <div className="tab">
      <Panel
        title={`Audit history (${history.length})`}
        tip="Stored only in this browser (LocalStorage), last 50 scans. Bulky image data is not kept."
        actions={
          <>
            <button className="btn btn-ghost" disabled={!history.length}
              onClick={() => exportJson('fakeguard-audit-history', history)}>⬇ Export all (JSON)</button>
            <button className="btn btn-ghost" disabled={!history.length}
              onClick={() => { clearHistory(); setOpenId(null); toast('History cleared.', 'info') }}>Clear</button>
          </>
        }
      >
        {history.length === 0 && <p className="muted">No scans yet. Run an analysis and it will appear here.</p>}
        <ul className="history">
          {history.map((h) => (
            <li key={h.id} className={h.id === openId ? 'active' : ''}>
              <button className="history-main" onClick={() => setOpenId(h.id === openId ? null : h.id)}>
                <span className="chip">{KIND[h.kind] || h.kind}</span>
                <span className="history-title">{h.title}</span>
                <span className="muted">{fmtDate(h.at)}</span>
                <b style={{ color: bandColor(h.band) }}>{h.score != null ? Math.round(h.score) : '–'}</b>
                <span className="muted history-band">{h.band}</span>
              </button>
              <button className="btn btn-ghost" aria-label="Delete entry" onClick={() => removeHistory(h.id)}>✕</button>
            </li>
          ))}
        </ul>
      </Panel>
      {open && open.kind === 'article' && (
        <CredibilityReport result={open.result} text={open.text} name={`fakeguard-${open.id}`} />
      )}
      {open && open.kind !== 'article' && (
        <Panel title="Stored result" actions={<button className="btn btn-ghost" onClick={() => exportJson(`fakeguard-${open.id}`, open.result)}>⬇ JSON</button>}>
          <p className="muted">Image and verification scans are kept as JSON summaries. Re-run the scan for the interactive view.</p>
          <pre className="json">{JSON.stringify(open.result.dual_verdict || open.result.fact_check || open.result, null, 2)}</pre>
        </Panel>
      )}
    </div>
  )
}
