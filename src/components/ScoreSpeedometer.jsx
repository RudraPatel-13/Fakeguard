import { useEffect, useState } from 'react'

const easeOutCubic = (p) => 1 - Math.pow(1 - p, 3)
// Elastic ease-out: overshoots the target and settles with a wobble.
const easeOutElastic = (p) => {
  if (p === 0 || p === 1) return p
  const c = (2 * Math.PI) / 3
  return Math.pow(2, -10 * p) * Math.sin((p * 10 - 0.75) * c) + 1
}

/** Drives two progress values (smooth for the odometer, elastic for the arc) from 0 to `target`. */
function useGaugeAnimation(target, ms = 1600) {
  const [v, setV] = useState({ num: 0, arc: 0 })
  useEffect(() => {
    let raf
    const start = performance.now()
    const tick = (now) => {
      const p = Math.min(1, (now - start) / ms)
      setV({ num: target * easeOutCubic(p), arc: target * easeOutElastic(p) })
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return v
}

// Deterministic particle spread (golden angle) so renders are pure and repeatable.
const PARTICLES = Array.from({ length: 30 }, (_, i) => {
  const a = i * 2.39996
  const dist = 90 + ((i * 37) % 70)
  return {
    x: Math.round(Math.cos(a) * dist),
    y: Math.round(Math.sin(a) * dist - 30),
    r: (i * 53) % 360,
    c: ['#10b981', '#06b6d4', '#8b5cf6', '#f59e0b', '#f43f5e'][i % 5],
    d: (i % 6) * 60,
  }
})

function Confetti() {
  const [live, setLive] = useState(true)
  useEffect(() => {
    const t = setTimeout(() => setLive(false), 2600)
    return () => clearTimeout(t)
  }, [])
  if (!live) return null
  return (
    <div className="confetti" aria-hidden="true">
      {PARTICLES.map((p, i) => (
        <i key={i} style={{ '--x': `${p.x}px`, '--y': `${p.y}px`, '--r': `${p.r}deg`, background: p.c, animationDelay: `${900 + p.d}ms` }} />
      ))}
    </div>
  )
}

function tone(score) {
  if (score >= 70) return { id: 'good', a: '#10b981', b: '#06b6d4' }
  if (score >= 40) return { id: 'warn', a: '#f59e0b', b: '#ef4444' }
  return { id: 'bad', a: '#ef4444', b: '#d946ef' }
}

/** Animated 270-degree radial speedometer: elastic arc, odometer count-up, confetti for high credibility. */
export default function ScoreSpeedometer({ score, band, interval, size = 250 }) {
  const { num, arc: arcVal } = useGaugeAnimation(score)
  const t = tone(score)
  const r = 90
  const C = 2 * Math.PI * r
  const arcLen = C * 0.75
  const frac = Math.max(0, Math.min(100, arcVal)) / 100
  const ang = (135 + 270 * frac) * (Math.PI / 180)
  const nx = 110 + r * Math.cos(ang)
  const ny = 110 + r * Math.sin(ang)
  const gid = `sg-${t.id}`

  return (
    <figure className={`gauge gauge-${t.id}`} style={{ width: size }} aria-label={`Trust score ${score} out of 100, ${band}`}>
      {score >= 70 && <Confetti key={score} />}
      <svg viewBox="0 0 220 200" role="img">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={t.a} />
            <stop offset="1" stopColor={t.b} />
          </linearGradient>
          <filter id="gaugeGlow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="4.5" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <g transform="rotate(135 110 110)">
          <circle cx="110" cy="110" r={r} className="gauge-track" strokeDasharray={`${arcLen} ${C}`} />
          <circle cx="110" cy="110" r={r} className="gauge-bar" stroke={`url(#${gid})`} filter="url(#gaugeGlow)"
            strokeDasharray={`${arcLen} ${C}`} strokeDashoffset={arcLen * (1 - frac)} />
        </g>
        {[0, 25, 50, 75, 100].map((tk) => {
          const a = (135 + 2.7 * tk) * (Math.PI / 180)
          return <line key={tk} x1={110 + 100 * Math.cos(a)} y1={110 + 100 * Math.sin(a)}
            x2={110 + 107 * Math.cos(a)} y2={110 + 107 * Math.sin(a)} className="gauge-tick" />
        })}
        <circle cx={nx} cy={ny} r="7" fill="#fff" stroke={t.b} strokeWidth="3" filter="url(#gaugeGlow)" />
        <text x="110" y="116" textAnchor="middle" className="gauge-num" fill={`url(#${gid})`}>{Math.round(num)}</text>
        <text x="110" y="136" textAnchor="middle" className="gauge-sub">CREDIBILITY INDEX</text>
      </svg>
      <figcaption>
        <strong className={`band-pill band-${t.id}`}>{band}</strong>
        {interval && <span className="muted"> · likely {interval.low}–{interval.high}</span>}
      </figcaption>
    </figure>
  )
}
