import { useCallback, useRef, useState } from 'react'

/** Drag (or use arrow keys) to compare the ELA heatmap (left) with the original (right). */
export default function ImageComparisonSlider({ original, ela, overlays = [], showBoxes = true, aspect }) {
  const [pos, setPos] = useState(50)
  const ref = useRef(null)
  const dragging = useRef(false)

  const move = useCallback((clientX) => {
    const rect = ref.current.getBoundingClientRect()
    setPos(Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100)))
  }, [])

  return (
    <div
      ref={ref}
      className="compare"
      style={{ aspectRatio: aspect }}
      onPointerDown={(e) => { dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); move(e.clientX) }}
      onPointerMove={(e) => dragging.current && move(e.clientX)}
      onPointerUp={() => { dragging.current = false }}
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
