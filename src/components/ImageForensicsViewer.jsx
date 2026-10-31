import { useState } from 'react'
import ImageComparisonSlider from './ImageComparisonSlider.jsx'
import { Panel, Tip, HighlightedText, Legend } from './common.jsx'
import { riskColor, exportJson } from '../utils.js'

export function DualVerdict({ result }) {
  const v = result.dual_verdict
  if (!v) return null
  const vi = v.visual_integrity
  const cc = v.content_credibility
  return (
    <div className="grid-2">
      <Panel title="Visual integrity verdict" tip="EXIF editing traces + ELA discrepancy. A triage heuristic, never proof of manipulation or authenticity.">
        <div className="verdict">
          <div className="verdict-num" style={{ color: riskColor(vi.risk_score) }}>{vi.risk_score}<small>/100 risk</small></div>
          <span className="chip" style={{ borderColor: riskColor(vi.risk_score) }}>{vi.level} risk</span>
        </div>
        <ul className="indicators">
          {result.forensics.factors.map((f) => (
            <li key={f.signal}><b>{f.signal}</b>{f.points ? ` (+${f.points})` : ''}: {f.detail}</li>
          ))}
          {!result.forensics.factors.length && <li>No tampering indicators found.</li>}
        </ul>
        <p className="note">{result.forensics.disclaimer}</p>
      </Panel>
      <Panel title="Extracted content credibility" tip="OCR text run through the rule engine and ML classifier; forensics risk is applied as a penalty.">
        {cc ? (
          <>
            <div className="verdict">
              <div className="verdict-num" style={{ color: riskColor(100 - cc.trust_score) }}>{cc.trust_score}<small>/100 trust</small></div>
              <span className="chip">{cc.band}</span>
            </div>
            <p className="kv"><span>Rule classification</span><b>{cc.rule_classification}</b></p>
            <p className="kv"><span>ML label</span><b>{result.ml?.label ?? 'n/a'}</b></p>
          </>
        ) : (
          <p className="muted">No readable text was extracted, so no content verdict is available.</p>
        )}
      </Panel>
    </div>
  )
}

export default function ImageForensicsViewer({ result, previewUrl }) {
  const [showBoxes, setShowBoxes] = useState(true)
  const { ocr, ela, metadata } = result
  const matched = result.text_analysis?.matched_terms
  const aspect = `${metadata.width} / ${metadata.height}`

  return (
    <div className="report">
      <div className="report-actions no-print">
        <button className="btn btn-ghost" onClick={() => exportJson('fakeguard-image-report', { ...result, ela: { ...result.ela, ela_image: null }, ocr: { ...result.ocr, words: [] } })}>⬇ JSON</button>
        <button className="btn btn-ghost" onClick={() => window.print()}>🖨 Print / PDF</button>
      </div>
      <DualVerdict result={result} />

      <div className="grid-2 img-grid">
        <Panel
          title="ELA comparison"
          tip="Drag across the image. Left of the handle shows the Error Level Analysis heatmap, right shows the original. Bright patches recompressed differently, which can hint at edits but also occurs naturally."
          actions={
            <label className="switch no-print">
              <input type="checkbox" checked={showBoxes} onChange={(e) => setShowBoxes(e.target.checked)} />
              keyword boxes ({result.keyword_overlays.length})
            </label>
          }
        >
          <ImageComparisonSlider original={previewUrl} ela={ela.ela_image} overlays={result.keyword_overlays}
            showBoxes={showBoxes} aspect={aspect} />
          {!ela.ela_image && <p className="note">ELA produced no visual (no measurable difference or skipped).</p>}
          <p className="note">{ela.limitation_note}</p>
          <p className="kv"><span>max diff</span><b>{ela.max_diff}</b></p>
          <p className="kv"><span>hot pixels</span><b>{(ela.hot_fraction * 100).toFixed(2)}%</b></p>
        </Panel>

        <Panel title="OCR text inspector" tip="Text read by Tesseract. Preprocessing (grayscale, denoise, contrast, adaptive threshold) is tried and kept only if it raises confidence.">
          <div className="chips">
            <span className="chip">status: {ocr.status}</span>
            {ocr.mean_confidence != null && <span className="chip">confidence {ocr.mean_confidence}%</span>}
            {ocr.preprocessing?.length > 0 && <span className="chip chip-ok">preprocessed</span>}
          </div>
          {ocr.status === 'success' ? (
            <>
              <Legend />
              <HighlightedText text={ocr.text} matched={matched} />
            </>
          ) : (
            <p className="muted">{ocr.warning}</p>
          )}
          {ocr.status === 'success' && ocr.warning && <p className="note">⚠ {ocr.warning}</p>}
        </Panel>
      </div>

      <Panel title="File & metadata">
        <div className="chips">
          <span className="chip">{metadata.format}</span>
          <span className="chip">{metadata.width}×{metadata.height}</span>
          <span className="chip">{(metadata.file_size_bytes / 1024).toFixed(0)} KB</span>
          <span className="chip">EXIF: {metadata.exif_available ? 'present' : 'none'}</span>
        </div>
        <ul className="indicators">{metadata.observations.map((o) => <li key={o}>{o}</li>)}</ul>
        {Object.keys(metadata.exif_fields).length > 0 && (
          <table className="mini-table"><tbody>
            {Object.entries(metadata.exif_fields).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}
          </tbody></table>
        )}
        <Tip text="Missing EXIF does not prove manipulation; social platforms routinely strip it." />
      </Panel>
    </div>
  )
}
