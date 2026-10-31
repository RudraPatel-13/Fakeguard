import { useEffect, useState } from 'react'

function useCountUp(target, ms = 900) {
  const [v, setV] = useState(0)
  useEffect(() => {
    let raf
    const start = performance.now()
    const from = 0
    const tick = (now) => {
      const p = Math.min(1, (now - start) / ms)
      setV(from + (target - from) * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return v
}

/** Animated 270-degree speedometer for the 0-100 trust score. */
export default function ScoreGauge({ score, band, interval, size = 240 }) {
  const shown = useCountUp(score)
  const r = 90
  const C = 2 * Math.PI * r
  const arc = C * 0.75
  const color = `hsl(${Math.round(Math.max(0, Math.min(100, shown)) * 1.45)}, 78%, 40%)`
  const offset = arc * (1 - shown / 100)
  const ang = (135 + 2.7 * shown) * (Math.PI / 180)
  const nx = 110 + 74 * Math.cos(ang)
  const ny = 110 + 74 * Math.sin(ang)

  return (
    <figure className="gauge" style={{ width: size }} aria-label={`Trust score ${score} out of 100, ${band}`}>
      <svg viewBox="0 0 220 200" role="img">
        <defs>
          <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <g transform="rotate(135 110 110)">
          <circle cx="110" cy="110" r={r} className="gauge-track" strokeDasharray={`${arc} ${C}`} />
          <circle cx="110" cy="110" r={r} className="gauge-bar" stroke={color} filter="url(#glow)"
            strokeDasharray={`${arc} ${C}`} strokeDashoffset={offset} />
        </g>
        {[0, 25, 50, 75, 100].map((t) => {
          const a = (135 + 2.7 * t) * (Math.PI / 180)
          return <line key={t} x1={110 + 100 * Math.cos(a)} y1={110 + 100 * Math.sin(a)}
            x2={110 + 107 * Math.cos(a)} y2={110 + 107 * Math.sin(a)} className="gauge-tick" />
        })}
        <circle cx={nx} cy={ny} r="5" fill={color} filter="url(#glow)" />
        <text x="110" y="112" textAnchor="middle" className="gauge-num" fill={color}>{Math.round(shown)}</text>
        <text x="110" y="134" textAnchor="middle" className="gauge-sub">CREDIBILITY INDEX</text>
      </svg>
      <figcaption>
        <strong style={{ color }}>{band}</strong>
        {interval && <span className="muted"> · likely {interval.low}–{interval.high}</span>}
      </figcaption>
    </figure>
  )
}
