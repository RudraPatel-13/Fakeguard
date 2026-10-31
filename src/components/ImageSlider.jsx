import { useCallback, useEffect, useRef, useState } from 'react'

const HOT = 150 // mean luminance (0-255) of the ELA patch above which we flag it

/**
 * Drag (or use arrow keys) to compare the ELA heatmap (left of the handle) with the original (right).
 * Hovering the heatmap samples its pixels and explains bright (high error-level) patches.
 */
export default function ImageSlider({ original, ela, overlays = [], showBoxes = true, aspect }) {
  const [pos, setPos] = useState(50)
  const [tip, setTip] = useState(null)
  const ref = useRef(null)
  const dragging = useRef(false)
  const sampler = useRef(null)

  // Decode the ELA image once into an offscreen canvas so hover can read pixel brightness.
  useEffect(() => {
    sampler.current = null
    if (!ela) return undefined
    const img = new Image()
    img.onload = () => {
      const c = document.createElement('canvas')
      c.width = img.naturalWidth
      c.height = img.naturalHeight
      const ctx = c.getContext('2d', { willReadFrequently: true })
      ctx.drawImage(img, 0, 0)
      sampler.current = { ctx, w: c.width, h: c.height }
    }
    img.src = ela
    return () => { img.onload = null }
  }, [ela])

  const move = useCallback((e) => {
    const rect = ref.current.getBoundingClientRect()
    const fx = (e.clientX - rect.left) / rect.width
    const fy = (e.clientY - rect.top) / rect.height
    if (dragging.current) setPos(Math.max(0, Math.min(100, fx * 100)))
    const s = sampler.current
    if (!s || fx * 100 > pos || fx < 0 || fy < 0 || fy > 1) return setTip(null)
    const px = Math.max(0, Math.min(s.w - 9, Math.round(fx * s.w) - 4))
    const py = Math.max(0, Math.min(s.h - 9, Math.round(fy * s.h) - 4))
    const d = s.ctx.getImageData(px, py, 9, 9).data
    let sum = 0
    for (let i = 0; i < d.length; i += 4) sum += 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]
    const lum = sum / (d.length / 4)
    setTip(lum > HOT
      ? { x: fx * 100, y: fy * 100, text: `High error level (${Math.round(lum)}/255): this patch recompressed differently — possible edit, or natural sharp-edge artifact.`, hot: true }
      : { x: fx * 100, y: fy * 100, text: `Consistent compression (${Math.round(lum)}/255)`, hot: false })
  }, [pos])

  return (
    <div
      ref={ref}
      className="compare"
      style={{ aspectRatio: aspect }}
      onPointerDown={(e) => { dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); move(e) }}
      onPointerMove={move}
      onPointerUp={() => { dragging.current = false }}
      onPointerLeave={() => setTip(null)}
    >
      <img src={original} alt="Original upload" draggable={false} />
      {ela && (
        <img src={ela} alt="Error level analysis heatmap" className="compare-top" draggable={false}
          style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }} />
      )}
      {showBoxes && overlays.map((o, i) => (
        <div key={i} className={`box box-${o.category}`} title={`${o.category}: ${o.text}`}
          style={{ left: `${o.x * 100}%`, top: `${o.y * 100}%`, width: `${o.w * 100}%`, height: `${o.h * 100}%` }} />
      ))}
      {tip && (
        <div className={`ela-tip ${tip.hot ? 'hot' : ''}`} style={{ left: `${Math.min(tip.x, 70)}%`, top: `${Math.min(tip.y + 4, 82)}%` }}>
          {tip.hot ? '⚠ ' : '✓ '}{tip.text}
        </div>
      )}
      {ela && (
        <>
          <span className="compare-tag tag-l">ELA HEATMAP</span>
          <span className="compare-tag tag-r">ORIGINAL</span>
          <div className="handle" style={{ left: `${pos}%` }} role="slider" aria-label="Compare ELA heatmap and original"
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pos)} tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'ArrowLeft') setPos((p) => Math.max(0, p - 3))
              if (e.key === 'ArrowRight') setPos((p) => Math.min(100, p + 3))
            }}>
            <span>⇆</span>
          </div>
        </>
      )}
    </div>
  )
}
