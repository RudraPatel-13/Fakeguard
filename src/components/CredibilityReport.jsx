import ScoreSpeedometer from './ScoreSpeedometer.jsx'
import ResultCards from './ResultCards.jsx'
import AxisChart from './AxisChart.jsx'
import { Panel, Tip, HighlightedText, Legend } from './common.jsx'
import { FactCheckView, DomainCard } from './Verification.jsx'
import WebVerificationList from './WebVerificationList.jsx'
import { exportJson } from '../utils.js'
import { usePrintReport } from '../usePrintReport.js'


function Attribution({ ml }) {
  if (!ml?.available) {
    return <p className="muted">{ml?.warnings?.[0] || 'ML classifier unavailable.'}</p>
  }
  const rows = [
    ...ml.attributions.supports_unreliable.map((a) => ({ ...a, side: 'neg' })),
    ...ml.attributions.supports_credible.map((a) => ({ ...a, side: 'pos' })),
  ]
  const max = Math.max(0.0001, ...rows.map((r) => Math.abs(r.weight)))
  return (
    <>
      <div className="ml-head">
        <span className={`chip ${ml.label === 'credible-style' ? 'chip-ok' : 'chip-bad'}`}>{ml.label}</span>
        <span>P(credible) = <b>{(ml.credible_probability * 100).toFixed(1)}%</b></span>
        <span className="muted">
          90% interval {(ml.interval.low * 100).toFixed(0)}–{(ml.interval.high * 100).toFixed(0)}%
          <Tip text="5th–95th percentile of 15 bootstrap-resampled models. Reflects model uncertainty, not factual accuracy." />
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="muted">No vocabulary overlap with the model.</p>
      ) : (
        <ul className="attr">
          {rows.map((r) => (
            <li key={r.side + r.token}>
              <span className="attr-tok">{r.token}</span>
              <div className="attr-bar">
                <i className={r.side} style={{ width: `${(Math.abs(r.weight) / max) * 100}%` }} />
              </div>
              <span className="muted attr-w">{r.weight > 0 ? '+' : ''}{r.weight.toFixed(3)}</span>
            </li>
          ))}
        </ul>
      )}
      {ml.warnings?.map((w) => <p key={w} className="note">⚠ {w}</p>)}
    </>
  )
}

function Penalties({ fusion }) {
  const p = fusion.penalties
  const c = fusion.components
  return (
    <table className="mini-table">
      <tbody>
        <tr><td>Rule trust × {c.w_rules}</td><td>{c.rule_trust}</td></tr>
        {c.ml_trust != null && <tr><td>ML trust × {c.w_ml}</td><td>{c.ml_trust}</td></tr>}
        {c.web_trust != null && <tr><td>Web corroboration × {c.w_web}</td><td>{c.web_trust}</td></tr>}
        {Object.entries(p).filter(([, v]) => v > 0).map(([k, v]) => (
          <tr key={k} className="neg"><td>− {k.replaceAll('_', ' ')}</td><td>−{v}</td></tr>
        ))}
        <tr className="total"><td>FakeGuard Credibility Index</td><td>{fusion.final_score}</td></tr>
      </tbody>
    </table>
  )
}

/** Unified report for text scans (and the content half of image scans). */
export default function CredibilityReport({ result, text, title = 'FakeGuard Credibility Index', name = 'fakeguard-report' }) {
  const { isAuthenticated, printReport } = usePrintReport()
  const { fusion, ml } = result
  const matched = result.matched_terms || result.text_analysis?.matched_terms
  const indicators = result.indicators || result.text_analysis?.indicators || []
  const ruleScore = result.score ?? result.text_analysis?.score
  const ruleClass = result.classification ?? result.text_analysis?.classification

  return (
    <ResultCards className="report">
      <div className="report-actions no-print">
        <button className="btn btn-ghost" onClick={() => exportJson(name, result)}>⬇ JSON</button>
        <button className="btn btn-ghost" onClick={printReport}>{isAuthenticated ? '🖨' : '🔒'} Print / PDF</button>
      </div>

      {fusion && (
        <div className="grid-2">
          <Panel title={title} tip="Index = w·Rules + w·ML + w·Web corroboration − Penalties (forensics, debunked claim, low-trust source). See breakdown.">
            <div className="gauge-row">
              <ScoreSpeedometer score={fusion.final_score} band={fusion.band} interval={fusion.interval} />
              <div>
                <p className="kv"><span>Rule engine</span><b>{ruleClass} <small>({ruleScore}/100 suspicion)</small></b></p>
                <Penalties fusion={fusion} />
              </div>
            </div>
          </Panel>
          <Panel title="Risk breakdown" tip="Each axis is a 0–100% risk (higher = worse).">
            <AxisChart axes={fusion.axes} />
          </Panel>
        </div>
      )}

      <div className="grid-2">
        <Panel title="Rule indicators" tip="Signals from the editable keyword library, WordNet synonyms and text-pattern rules.">
          <ul className="indicators">{indicators.map((i) => <li key={i}>{i}</li>)}</ul>
          {text && matched && (<><Legend /><HighlightedText text={text} matched={matched} /></>)}
        </Panel>
        <Panel title="ML explainability" tip="Per-token contribution (coefficient × TF-IDF) in log-odds. Green pushes toward credible-style, red toward unreliable-style.">
          <Attribution ml={ml} />
        </Panel>
      </div>

      {result.web && (
        <Panel title="Live web verification" tip="Real-time search of news outlets and fact-checkers for this claim.">
          <WebVerificationList web={result.web} />
        </Panel>
      )}

      {result.fact_check && (
        <Panel title="Claim verification" tip="Verifiable sentences are extracted and matched against fact-check sources.">
          <FactCheckView fact={result.fact_check} claims={result.claims} />
        </Panel>
      )}
      {result.domain && (
        <Panel title="Source trust"><DomainCard domain={result.domain} /></Panel>
      )}
    </ResultCards>
  )
}
