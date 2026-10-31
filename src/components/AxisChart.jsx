import { Tip } from './common.jsx'
import { riskColor } from '../utils.js'
import { AXES } from '../axes.js'

/** Hexagonal radar of the six risk axes (higher = riskier) plus labelled bars. */
export default function AxisChart({ axes }) {
  const n = AXES.length
  const cx = 130, cy = 120, R = 85
  const pt = (i, v) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n
    return [cx + R * (v / 100) * Math.cos(a), cy + R * (v / 100) * Math.sin(a)]
  }
  const poly = AXES.map(([k], i) => pt(i, axes[k] ?? 0).join(',')).join(' ')
  return (
    <div className="axis-wrap">
      <svg viewBox="0 0 260 240" className="radar" role="img" aria-label="Risk radar">
        {[25, 50, 75, 100].map((g) => (
          <polygon key={g} className="radar-grid" points={AXES.map((_, i) => pt(i, g).join(',')).join(' ')} />
        ))}
        {AXES.map(([k, label], i) => {
          const [x, y] = pt(i, 100)
          const [lx, ly] = pt(i, 118)
          return (
            <g key={k}>
              <line x1={cx} y1={cy} x2={x} y2={y} className="radar-grid" />
              <text x={lx} y={ly} className="radar-label" textAnchor={lx < cx - 5 ? 'end' : lx > cx + 5 ? 'start' : 'middle'}>
                {label.split(' ')[0]}
              </text>
            </g>
          )
        })}
        <polygon className="radar-shape" points={poly} />
        {AXES.map(([k], i) => {
          const [x, y] = pt(i, axes[k] ?? 0)
          return <circle key={k} cx={x} cy={y} r="3.5" fill={riskColor(axes[k])} />
        })}
      </svg>
      <ul className="axis-bars">
        {AXES.map(([k, label, tip]) => {
          const v = axes[k]
          return (
            <li key={k}>
              <div className="axis-row">
                <span>{label} <Tip text={tip} /></span>
                <b style={{ color: riskColor(v) }}>{v == null ? 'n/a' : `${Math.round(v)}%`}</b>
              </div>
              <div className="bar"><i style={{ width: `${v ?? 0}%`, background: riskColor(v) }} /></div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
