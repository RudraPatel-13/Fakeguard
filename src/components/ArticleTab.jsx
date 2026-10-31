import { useEffect, useRef, useState } from 'react'
import { analyzeText } from '../api.js'
import { useApp } from '../appContext.js'
import CredibilityReport from './CredibilityReport.jsx'
import LiveScannerHUD from './LiveScannerHUD.jsx'
import PresetBar from './PresetBar.jsx'
import { Panel } from './common.jsx'

const MAX_CHARS = 20000

export default function ArticleTab({ state, setState, onOpenImage }) {
  const { toast, addHistory } = useApp()
  const { text, url, result, analyzedText, searchWeb } = state
  const [loading, setLoading] = useState(false)
  const patch = (p) => setState((s) => ({ ...s, ...p }))

  async function run(override) {
    const body = override?.text ?? text
    const src = override ? (override.url ?? '') : url
    if (!body.trim()) return toast('Enter or paste some text first.', 'warn')
    setLoading(true)
    patch({ result: null })
    try {
      const r = await analyzeText(body, src.trim(), searchWeb)
      patch({ result: r, analyzedText: body })
      addHistory({
        kind: 'article',
        title: body.trim().slice(0, 90),
        score: r.fusion?.final_score ?? null,
        band: r.fusion?.band ?? r.classification,
        result: r,
        text: body,
      })
      toast(`Credibility Index ${Math.round(r.fusion?.final_score ?? 0)}: ${r.fusion?.band ?? r.classification}`, 'ok')
    } catch (e) {
      toast(e.message, 'err')
    } finally {
      setLoading(false)
    }
  }

  // Types the preset into the box, then auto-runs the scan.
  const typer = useRef(null)
  useEffect(() => () => clearInterval(typer.current), [])
  const loadPreset = (p) => {
    clearInterval(typer.current)
    patch({ text: '', url: p.url || '', result: null })
    const step = Math.max(2, Math.ceil(p.text.length / 45))
    let n = 0
    typer.current = setInterval(() => {
      n += step
      if (n >= p.text.length) {
        clearInterval(typer.current)
        patch({ text: p.text })
        run(p)
      } else {
        patch({ text: p.text.slice(0, n) })
      }
    }, 16)
  }

  return (
    <div className="tab">
      <Panel className={loading ? "scanning" : ""} title="Article & text analysis" tip="Paste a headline or article. Rules, ML, live web corroboration and source trust are fused into one Credibility Index.">
        <PresetBar onText={loadPreset} onImage={onOpenImage} onError={(m) => toast(m, 'err')} />
        <textarea
          className="input area"
          rows={7}
          maxLength={MAX_CHARS}
          value={text}
          placeholder="Paste a news article, headline or forwarded message…"
          onChange={(e) => patch({ text: e.target.value })}
        />
        <div className="row">
          <input
            className="input"
            placeholder="Optional source URL (adds publisher-trust scoring)"
            value={url}
            onChange={(e) => patch({ url: e.target.value })}
          />
          <label className="switch no-print" title="Searches Google News for coverage and fact-checks">
            <input type="checkbox" checked={searchWeb} onChange={(e) => patch({ searchWeb: e.target.checked })} />
            Search live internet
          </label>
          <span className="muted counter">{text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}</span>
          <button className="btn btn-primary" disabled={loading} onClick={() => run()}>
            {loading ? 'Scanning…' : 'Analyze'}
          </button>
          <button className="btn" disabled={loading} onClick={() => patch({ text: '', url: '', result: null })}>Clear</button>
        </div>
      </Panel>
      {loading && <LiveScannerHUD skipWeb={!searchWeb} />}
      {!loading && result && <CredibilityReport result={result} text={analyzedText} name="fakeguard-credibility-audit" />}
    </div>
  )
}
