import { PRESETS, makeNewspaperClip } from '../presets.js'

/** Levitating one-click demo pills. `onText(preset)` loads a text sample; `onImage(file)` loads the sample clipping. */
export default function PresetBar({ onText, onImage, onError, disabled = false }) {
  async function clip() {
    try {
      onImage(await makeNewspaperClip())
    } catch (e) {
      onError?.(e.message)
    }
  }
  return (
    <div className="preset-ribbon no-print">
      <span className="muted">One-click demos</span>
      {PRESETS.map((p, i) => (
        <button key={p.id} disabled={disabled} className={`gpill gpill-${p.tone}`} style={{ '--i': i }} onClick={() => onText(p)}>
          <span aria-hidden="true">{p.icon}</span> {p.label}
        </button>
      ))}
      <button disabled={disabled} className="gpill gpill-ai" style={{ '--i': PRESETS.length }} onClick={clip}>
        <span aria-hidden="true">🖼️</span> Photoshopped Document (Newspaper)
      </button>
    </div>
  )
}
