import { useEffect, useRef, useState } from 'react'
import { analyzeImage } from '../api.js'
import { useApp } from '../appContext.js'
import { Panel } from './common.jsx'
import ImageForensicsViewer from './ImageForensicsViewer.jsx'
import CredibilityReport from './CredibilityReport.jsx'
import LiveScannerHUD from './LiveScannerHUD.jsx'
import PresetBar from './PresetBar.jsx'

const MAX_MB = 10
const ACCEPT = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp']

/** `initialFile` (e.g. the sample newspaper clip) is analysed automatically on mount. */
export default function ImageTab({ initialFile, onOpenImage, onText }) {
  const { toast, addHistory } = useApp()
  const [file, setFile] = useState(initialFile || null)
  const [previewUrl, setPreviewUrl] = useState(() => (initialFile ? URL.createObjectURL(initialFile) : null))
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [over, setOver] = useState(false)
  const input = useRef(null)
  const started = useRef(false)

  useEffect(() => () => previewUrl && URL.revokeObjectURL(previewUrl), [previewUrl])

  function pick(f) {
    if (!f) return
    if (!ACCEPT.includes(f.type)) return toast('Unsupported file type. Use JPEG, PNG, WebP or BMP.', 'warn')
    if (f.size > MAX_MB * 1024 * 1024) return toast(`File is larger than ${MAX_MB} MB.`, 'warn')
    setFile(f)
    setResult(null)
    setPreviewUrl(URL.createObjectURL(f))
  }

  async function run(f = file) {
    if (!f) return
    setLoading(true)
    setResult(null)
    try {
      const r = await analyzeImage(f, true)
      if (r.status === 'error') {
        toast(r.error, 'err')
      } else {
        setResult(r)
        addHistory({
          kind: 'image',
          title: f.name,
          score: r.fusion?.final_score ?? null,
          band: r.fusion?.band ?? `${r.forensics.level} visual risk`,
          result: r,
        })
        toast('Image forensics complete.', 'ok')
      }
    } catch (e) {
      toast(e.message, 'err')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (initialFile && !started.current) {
      started.current = true
      const t = setTimeout(() => run(initialFile), 0)
      return () => clearTimeout(t)
    }
    // run once on mount for the injected sample file
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="tab">
      <Panel className={loading ? "scanning" : ""} title="Image & screenshot forensics" tip="Upload a newspaper clip, tweet screenshot or meme. EXIF + ELA forensics run alongside OCR, and the extracted text goes through rules, ML and live web verification.">
        <PresetBar onText={onText} onImage={onOpenImage} onError={(m) => toast(m, 'err')} />
        <div
          className={`drop ${over ? 'drop-over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true) }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files?.[0]) }}
          onClick={() => input.current?.click()}
          role="button" tabIndex={0}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
        >
          <input ref={input} type="file" hidden accept={ACCEPT.join(',')} onChange={(e) => pick(e.target.files?.[0])} />
          {previewUrl ? (
            <img src={previewUrl} alt="Selected upload" className="drop-preview" />
          ) : (
            <>
              <div className="drop-icon">⬆</div>
              <p><b>Drop an image here</b> or click to browse</p>
              <p className="muted">JPEG · PNG · WebP · BMP · up to {MAX_MB} MB · processed in memory, never stored</p>
            </>
          )}
        </div>
        <div className="row">
          <span className="muted grow">{file ? `${file.name} · ${(file.size / 1024).toFixed(0)} KB` : 'No file selected'}</span>
          <button className="btn btn-primary" disabled={!file || loading} onClick={() => run()}>{loading ? 'Scanning…' : 'Run forensics'}</button>
        </div>
      </Panel>
      {loading && <LiveScannerHUD mode="image" />}
      {!loading && result && (
        <>
          <ImageForensicsViewer result={result} previewUrl={previewUrl} />
          {result.fusion && (
            <CredibilityReport result={{ ...result, ...result.text_analysis, fusion: result.fusion, ml: result.ml, web: result.web }}
              text={result.ocr.text} title="FakeGuard Credibility Index (incl. forensics penalty)" name="fakeguard-image-audit" />
          )}
        </>
      )}
    </div>
  )
}
