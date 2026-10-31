import { useCallback, useEffect, useState } from 'react'
import { analyzeText, getKeywordMeta, getKeywordRules, getModelInfo, reloadKeywords } from '../api.js'
import { useApp } from '../appContext.js'
import { Panel, HighlightedText, Legend } from './common.jsx'

export default function RuleStudio() {
  const { toast } = useApp()
  const [meta, setMeta] = useState(null)
  const [rules, setRules] = useState(null)
  const [model, setModel] = useState(null)
  const [filter, setFilter] = useState('')
  const [probe, setProbe] = useState('This shocking hoax was exposed by a whistleblower!')
  const [probeRes, setProbeRes] = useState(null)
  const [err, setErr] = useState(null)

  const load = useCallback(async () => {
    try {
      const [m, r, mi] = await Promise.all([getKeywordMeta(), getKeywordRules(), getModelInfo()])
      setMeta(m); setRules(r); setModel(mi); setErr(null)
    } catch (e) {
      setErr(e.message)
    }
  }, [])
  useEffect(() => {
    const t = setTimeout(load, 0)
    return () => clearTimeout(t)
  }, [load])

  async function reload() {
    try {
      const r = await reloadKeywords()
      await load()
      toast(r.changed ? `Library reloaded: now v${r.version}` : `Library checked: v${r.version} (no change detected)`, 'ok')
    } catch (e) { toast(e.message, 'err') }
  }

  async function test() {
    try { setProbeRes(await analyzeText(probe)) } catch (e) { toast(e.message, 'err') }
  }

  if (err) return <div className="panel"><p className="note">⚠ {err}</p><button className="btn" onClick={load}>Retry</button></div>
  if (!meta || !rules) return <div className="panel"><p className="muted">Loading rules…</p></div>

  const f = filter.trim().toLowerCase()
  const kws = rules.suspicious_keywords.filter((w) => w.includes(f))
  const phrases = rules.clickbait_phrases.filter((w) => w.includes(f))
  const tp = rules.text_patterns

  return (
    <div className="tab">
      <Panel
        title={`Keyword rule studio · v${meta.version}`}
        tip="Edit backend/app/keyword_library/keywords.json and the engine picks up the change on the next request. This view is read-only."
        actions={<button className="btn btn-primary" onClick={reload}>↻ Check for changes</button>}
      >
        <input className="input" placeholder="Filter rules…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <div className="grid-2">
          <div>
            <h4>Suspicious keywords <small className="muted">({kws.length}/{rules.suspicious_keywords.length}) · +{meta.scoring.points_per_suspicious_keyword} each, cap {meta.scoring.suspicious_keyword_cap}</small></h4>
            <div className="chips">{kws.map((w) => <span key={w} className="chip chip-kw">{w}</span>)}</div>
          </div>
          <div>
            <h4>Clickbait phrases <small className="muted">({phrases.length}/{rules.clickbait_phrases.length}) · +{meta.scoring.points_per_clickbait_phrase} each, cap {meta.scoring.clickbait_phrase_cap}</small></h4>
            <div className="chips">{phrases.map((w) => <span key={w} className="chip chip-cb">{w}</span>)}</div>
          </div>
        </div>
        <table className="mini-table">
          <tbody>
            <tr><td>Caps ratio &gt; {tp.caps_ratio_threshold}</td><td>+{tp.caps_points}</td></tr>
            <tr><td>Exclamation marks ≥ {tp.exclamation_min_count}</td><td>+{tp.exclamation_points}</td></tr>
            <tr><td>Question marks ≥ {tp.question_min_count}</td><td>+{tp.question_points}</td></tr>
          </tbody>
        </table>
        <div className="bands">
          {meta.classification_bands.map((b) => <span key={b.label} className="chip">{b.label}: {b.min}–{b.max}</span>)}
        </div>
        <p className="note">
          WordNet synonym expansion: {meta.wordnet_status.available ? 'active' : 'unavailable'} ·{' '}
          {meta.wordnet_status.synonym_map_entries} mapped synonyms. Synonyms are matched against the configured keywords as-is; the engine has no tunable similarity threshold.
        </p>
      </Panel>

      <div className="grid-2">
        <Panel title="Live rule tester" tip="Runs the real /analyze endpoint on a snippet so you can see which rules fire.">
          <textarea className="input area" rows={3} value={probe} onChange={(e) => setProbe(e.target.value)} />
          <button className="btn btn-primary" onClick={test}>Test rules</button>
          {probeRes && (
            <>
              <Legend />
              <HighlightedText text={probe} matched={probeRes.matched_terms} />
              <p className="kv"><span>Rule score</span><b>{probeRes.score}/100 · {probeRes.classification}</b></p>
            </>
          )}
        </Panel>
        <Panel title="ML engine" tip="Model metadata from GET /model-info.">
          {model?.available ? (
            <>
              <p className="kv"><span>Algorithm</span><b>{model.algorithm}</b></p>
              <p className="kv"><span>Training data</span><b>{model.training_source}</b></p>
              <p className="kv"><span>Samples</span><b>{model.training_samples}</b></p>
              <p className="kv"><span>CV accuracy</span><b>{model.cross_val_accuracy != null ? `${(model.cross_val_accuracy * 100).toFixed(1)}%` : 'n/a'}</b></p>
              <p className="kv"><span>Fusion weights</span><b>rules {model.fusion.w_rules} / ML {model.fusion.w_ml}</b></p>
              <p className="kv"><span>Verification mode</span><b>{model.verification_mode}</b></p>
              {model.limitations.map((l) => <p key={l} className="note">⚠ {l}</p>)}
            </>
          ) : <p className="muted">ML model unavailable.</p>}
        </Panel>
      </div>
    </div>
  )
}
