import { useEffect, useState } from 'react'

const STEPS = {
  tokenize: 'Neural Tokenizing & Lexical Scan...',
  ela: 'Running Error Level Analysis (ELA)...',
  rules: 'Scoring Sensationalism & ML Signals...',
  web: 'Searching Live Fact-Check Registries...',
  synth: 'Synthesizing Verdict...',
}

/**
 * Holographic HUD shown while a request is in flight. It walks through the stages on a timer and
 * parks on the last one (progress is indicative: the backend runs the stages in a single request).
 * The laser sweep over the input card is a CSS class (`scanning`) applied by the parent panel.
 */
export default function LiveScannerHUD({ mode = 'text', skipWeb = false }) {
  const keys = ['tokenize', mode === 'image' ? 'ela' : 'rules', ...(skipWeb ? [] : ['web']), 'synth']
  const [active, setActive] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setActive((a) => Math.min(a + 1, keys.length - 1)), 1200)
    return () => clearInterval(t)
  }, [keys.length])

  return (
    <div className="hud" role="status" aria-live="polite">
      <div className="hud-laser" aria-hidden="true" />
      <div className="hud-bar"><i style={{ width: `${((active + 1) / keys.length) * 100}%` }} /></div>
      <ol>
        {keys.map((k, i) => (
          <li key={k} className={i < active ? 'done' : i === active ? 'now' : ''} style={{ '--i': i }}>
            <span className="hud-dot">{i < active ? '✓' : '●'}</span>
            <span>Step {i + 1}: {STEPS[k]}</span>
            {i === active && <span className="hud-eq" aria-hidden="true"><b /><b /><b /></span>}
          </li>
        ))}
      </ol>
    </div>
  )
}
