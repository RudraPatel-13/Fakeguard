import { PRESETS, makeNewspaperClip } from '../presets.js'

/** One-click demo pills. `onText(preset)` loads a text sample; `onImage(file)` loads the sample clipping. */
export default function PresetBar({ onText, onImage, onError }) {
  async function clip() {
    try {
      onImage(await makeNewspaperClip())
    } catch (e) {
      onError?.(e.message)
    }
  }
  return (
    <div className="pills no-print">
      <span className="muted">Quick tests</span>
      {PRESETS.map((p) => (
        <button key={p.id} className="pill" onClick={() => onText(p)}>{p.label}</button>
      ))}
      <button className="pill pill-accent" onClick={clip}>Try Uploading Newspaper Clip</button>
    </div>
  )
}
