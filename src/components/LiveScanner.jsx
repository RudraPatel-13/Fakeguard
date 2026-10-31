import { useEffect, useState } from 'react'

const SCAN_STEPS = [
  'Extracting Text & Running OCR...',
  'Heuristic & Sentiment Rule Evaluation...',
  'Querying ML Classification Engine...',
  'Searching Live Internet & Fact-Check Registries...',
  'Synthesizing Final Credibility Index.',
]

/**
 * Multi-step animated scanner. Mount it while a request is in flight: it walks
 * through the stages on a timer and parks on the final stage until unmounted.
 * (Progress is indicative; the backend runs the stages in a single request.)
 */
export default function LiveScanner({ skipWeb = false }) {
  const steps = skipWeb ? SCAN_STEPS.filter((_, i) => i !== 3) : SCAN_STEPS
  const [active, setActive] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setActive((a) => Math.min(a + 1, steps.length - 1)), 1100)
    return () => clearInterval(t)
  }, [steps.length])

  return (
    <div className="scanner" role="status" aria-live="polite">
      <div className="scanner-bar"><i style={{ width: `${((active + 1) / steps.length) * 100}%` }} /></div>
      <ol>
        {steps.map((s, i) => (
          <li key={s} className={i < active ? 'done' : i === active ? 'now' : ''}>
            <span className="step-dot">{i < active ? '✓' : i + 1}</span>
            <span>{s}</span>
            {i === active && <i className="spinner" />}
          </li>
        ))}
      </ol>
    </div>
  )
}
