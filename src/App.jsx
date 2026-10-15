import { useState } from "react"
import "./App.css"

function App() {
  const [articleText, setArticleText] = useState("")
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const [selectedImage, setSelectedImage] = useState(null)
  const [imagePreview, setImagePreview] = useState(null)
  const [imageResult, setImageResult] = useState(null)

  // Backend image analysis state
  const [imageAnalyzing, setImageAnalyzing] = useState(false)
  const [backendImageResult, setBackendImageResult] = useState(null)

  const analyzeArticle = async () => {
    if (!articleText.trim()) {
      setResult({
        score: 0,
        classification: "No Input",
        word_count: 0,
        indicators: ["Please enter an article before analyzing."],
      })
      return
    }

    setLoading(true)

    try {
      const response = await fetch("http://127.0.0.1:8000/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: articleText,
        }),
      })

      if (!response.ok) {
        throw new Error("Unable to analyze article")
      }

      const data = await response.json()

      setResult(data)
    } catch (error) {
      setResult({
        score: 0,
        classification: "Error",
        word_count: 0,
        indicators: [
          "Could not connect to the FakeGuard analysis server.",
        ],
      })
    } finally {
      setLoading(false)
    }
  }

  const handleImageSelect = (event) => {
    const file = event.target.files[0]

    if (!file) {
      return
    }

    setSelectedImage(file)
    setImageResult(null)
    setBackendImageResult(null)

    const imageURL = URL.createObjectURL(file)
    setImagePreview(imageURL)

    const image = new Image()

    image.onload = () => {
      setImageResult({
        fileName: file.name,
        fileSize: (file.size / 1024).toFixed(2),
        fileType: file.type,
        width: image.width,
        height: image.height,
      })
    }

    image.src = imageURL
  }

  const analyzeImageBackend = async () => {
    if (!selectedImage) return

    setImageAnalyzing(true)
    setBackendImageResult(null)

    const formData = new FormData()
    formData.append("file", selectedImage)

    try {
      const response = await fetch("http://127.0.0.1:8000/analyze-image", {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        throw new Error("Server error")
      }

      const data = await response.json()
      setBackendImageResult(data)
    } catch (error) {
      setBackendImageResult({
        status: "error",
        error: "Could not connect to the FakeGuard analysis server.",
        ocr: null,
        text_analysis: null,
        metadata: null,
        ela: null,
      })
    } finally {
      setImageAnalyzing(false)
    }
  }

  const getResultClass = () => {
    if (!result) return ""

    if (result.classification === "Credible") {
      return "result-credible"
    }

    if (result.classification === "Suspicious") {
      return "result-suspicious"
    }

    if (result.classification === "Likely Fake") {
      return "result-fake"
    }

    return "result-neutral"
  }

  const getTextScoreClass = (classification) => {
    if (classification === "Credible") return "result-credible"
    if (classification === "Suspicious") return "result-suspicious"
    if (classification === "Likely Fake") return "result-fake"
    return "result-neutral"
  }

  const getOcrStatusLabel = (status) => {
    const labels = {
      success: "Text extracted",
      no_text: "No text found",
      ocr_unavailable: "OCR unavailable",
      error: "Extraction error",
    }
    return labels[status] || status
  }

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  }

  return (
    <div className="site">

      {/* ================= NAVIGATION ================= */}

      <header className="topbar">
        <div className="topbar-inner">

          <div className="brand">
            <div className="brand-mark">FG</div>

            <div>
              <div className="brand-name">FAKEGUARD</div>
              <div className="brand-subtitle">
                NEWS CREDIBILITY ANALYZER
              </div>
            </div>
          </div>

          <nav className="navigation">
            <a href="#analyzer">Analyzer</a>
            <a href="#image-analysis">Image Check</a>
            <a href="#about">About</a>
          </nav>

        </div>
      </header>

      {/* ================= HERO ================= */}

      <main>

        <section className="hero">
          <div className="page-width">

            <div className="hero-label">
              PHASE 3 • DYNAMIC RULES + LEXICAL DETECTION + IMAGE FORENSICS
            </div>

            <h1 className="hero-title">
              Before you share it,
              <br />
              <span>check it.</span>
            </h1>

            <div className="hero-bottom">

              <p className="hero-description">
                FakeGuard examines news content for observable
                credibility indicators using transparent,
                rule-based analysis and lexical synonym detection.
              </p>

              <div className="hero-note">
                <span>01</span>
                TEXT ANALYSIS
                <br />
                <span>02</span>
                IMAGE INSPECTION
              </div>

            </div>

          </div>
        </section>

        {/* ================= ARTICLE ANALYZER ================= */}

        <section id="analyzer" className="section">
          <div className="page-width">

            <div className="section-heading">
              <div>
                <div className="section-number">01</div>

                <h2>
                  Article
                  <br />
                  Analysis
                </h2>
              </div>

              <p>
                Paste the text of a news article below.
                FakeGuard checks for predefined patterns
                associated with suspicious content.
              </p>
            </div>

            <div className="article-layout">

              <div className="input-panel">

                <div className="panel-header">
                  <span>ARTICLE TEXT</span>
                  <span>
                    {articleText.length} characters
                  </span>
                </div>

                <textarea
                  value={articleText}
                  onChange={(e) => setArticleText(e.target.value)}
                  placeholder="Paste the news article here..."
                  className="article-input"
                />

                <div className="input-footer">

                  <span>
                    {articleText.trim()
                      ? `${articleText.trim().split(/\s+/).length} words`
                      : "No article entered"}
                  </span>

                  <button
                    onClick={analyzeArticle}
                    disabled={loading}
                    className="analyze-button"
                  >
                    {loading ? "ANALYZING..." : "ANALYZE ARTICLE →"}
                  </button>

                </div>

              </div>

              {/* RESULT */}

              {result && (
                <div className={`result-panel ${getResultClass()}`}>

                  <div className="result-top">
                    <span className="section-number">
                      RESULT
                    </span>

                    <span className="result-status">
                      {result.classification}
                    </span>
                  </div>

                  <div className="score-area">

                    <div className="score-number">
                      {result.score}
                    </div>

                    <div className="score-label">
                      CREDIBILITY
                      <br />
                      INDICATOR SCORE
                    </div>

                  </div>

                  <div className="result-divider" />

                  <div className="result-meta">

                    <div>
                      <span>CLASSIFICATION</span>
                      <strong>
                        {result.classification}
                      </strong>
                    </div>

                    <div>
                      <span>WORD COUNT</span>
                      <strong>
                        {result.word_count}
                      </strong>
                    </div>

                  </div>

                  <div className="indicators">

                    <div className="indicator-title">
                      OBSERVED INDICATORS
                    </div>

                    {result.indicators.map(
                      (indicator, index) => (
                        <div
                          key={index}
                          className="indicator"
                        >
                          <span>—</span>
                          <p>{indicator}</p>
                        </div>
                      )
                    )}

                  </div>

                </div>
              )}

            </div>

          </div>
        </section>

        {/* ================= IMAGE ANALYSIS ================= */}

        <section
          id="image-analysis"
          className="section image-section"
        >
          <div className="page-width">

            <div className="section-heading">
              <div>
                <div className="section-number">02</div>

                <h2>
                  Image
                  <br />
                  Inspection
                </h2>
              </div>

              <p>
                Upload a JPG, PNG or WebP image to extract
                embedded text, inspect metadata, and perform
                basic forensic analysis. Results are
                observations — not conclusions.
              </p>
            </div>

            <div className="image-layout">

              {/* UPLOAD */}

              <div className="upload-panel">

                <div className="panel-header">
                  <span>IMAGE INPUT</span>
                  <span>JPG / PNG / WEBP</span>
                </div>

                <label
                  htmlFor="image-upload"
                  className="upload-area"
                >

                  <div className="upload-symbol">
                    +
                  </div>

                  <h3>
                    Select an image
                  </h3>

                  <p>
                    Click here to browse your computer
                  </p>

                  <span className="upload-button">
                    CHOOSE IMAGE
                  </span>

                  <input
                    id="image-upload"
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={handleImageSelect}
                    hidden
                  />

                </label>

                {selectedImage && (
                  <div className="selected-file">
                    Selected:
                    <strong>
                      {selectedImage.name}
                    </strong>
                  </div>
                )}

                {selectedImage && (
                  <div className="image-analyze-footer">
                    <button
                      onClick={analyzeImageBackend}
                      disabled={imageAnalyzing}
                      className="analyze-image-button"
                    >
                      {imageAnalyzing
                        ? "ANALYZING..."
                        : "ANALYZE IMAGE →"}
                    </button>
                  </div>
                )}

              </div>

              {/* IMAGE RESULT */}

              {imagePreview && imageResult && (
                <div className="image-result-panel">

                  <div className="panel-header">
                    <span>IMAGE PREVIEW</span>
                    <span>BASIC INSPECTION</span>
                  </div>

                  <div className="image-preview-container">

                    <img
                      src={imagePreview}
                      alt="Selected news"
                      className="preview-image"
                    />

                  </div>

                  <div className="image-details">

                    <div className="detail-row">
                      <span>FILE NAME</span>
                      <strong>
                        {imageResult.fileName}
                      </strong>
                    </div>

                    <div className="detail-row">
                      <span>FILE TYPE</span>
                      <strong>
                        {imageResult.fileType}
                      </strong>
                    </div>

                    <div className="detail-row">
                      <span>FILE SIZE</span>
                      <strong>
                        {imageResult.fileSize} KB
                      </strong>
                    </div>

                    <div className="detail-row">
                      <span>DIMENSIONS</span>
                      <strong>
                        {imageResult.width} ×{" "}
                        {imageResult.height} px
                      </strong>
                    </div>

                  </div>

                  <div className="integrity-check">

                    <span className="check-symbol">
                      ✓
                    </span>

                    <div>
                      <strong>
                        BASIC INTEGRITY CHECK
                      </strong>

                      <p>
                        Image loaded successfully and
                        basic file properties were detected.
                      </p>
                    </div>

                  </div>

                </div>
              )}

            </div>

            {/* ---- BACKEND ANALYSIS RESULTS ---- */}

            {imageAnalyzing && (
              <div className="image-analyzing-notice">
                <span className="analyzing-spinner">◌</span>
                Extracting text, inspecting metadata and running ELA…
              </div>
            )}

            {backendImageResult && backendImageResult.status === "error" && (
              <div className="image-analysis-error">
                <span>ERROR</span>
                <p>{backendImageResult.error}</p>
              </div>
            )}

            {backendImageResult && backendImageResult.status === "ok" && (
              <div className="backend-results">

                {/* --- OCR SECTION --- */}
                <div className="analysis-block">

                  <div className="analysis-block-header">
                    <span className="block-tag">OCR</span>
                    <span className="block-title">
                      TEXT EXTRACTION
                    </span>
                    <span className={`ocr-status-badge ocr-${backendImageResult.ocr.status}`}>
                      {getOcrStatusLabel(backendImageResult.ocr.status)}
                    </span>
                  </div>

                  {backendImageResult.ocr.warning && (
                    <div className="analysis-notice">
                      {backendImageResult.ocr.warning}
                    </div>
                  )}

                  {backendImageResult.ocr.status === "success" && (
                    <div className="ocr-text-block">
                      <div className="ocr-text-label">
                        EXTRACTED TEXT
                        <span>
                          {backendImageResult.ocr.character_count} characters
                        </span>
                      </div>
                      <pre className="ocr-text-content">
                        {backendImageResult.ocr.text}
                      </pre>
                    </div>
                  )}

                </div>

                {/* --- TEXT ANALYSIS SECTION --- */}
                {backendImageResult.text_analysis && (
                  <div className="analysis-block">

                    <div className="analysis-block-header">
                      <span className="block-tag">TEXT</span>
                      <span className="block-title">
                        CONTENT ANALYSIS
                      </span>
                    </div>

                    <div
                      className={`image-text-result ${getTextScoreClass(
                        backendImageResult.text_analysis.classification
                      )}`}
                    >

                      <div className="image-score-row">
                        <div className="image-score-num">
                          {backendImageResult.text_analysis.score}
                        </div>
                        <div>
                          <div className="image-score-label">
                            CREDIBILITY INDICATOR SCORE
                          </div>
                          <div className="image-classification">
                            {backendImageResult.text_analysis.classification}
                          </div>
                        </div>
                      </div>

                      <div className="result-divider" />

                      <div className="indicators">
                        <div className="indicator-title">
                          OBSERVED INDICATORS (from OCR text)
                        </div>
                        {backendImageResult.text_analysis.indicators.map(
                          (ind, i) => (
                            <div key={i} className="indicator">
                              <span>—</span>
                              <p>{ind}</p>
                            </div>
                          )
                        )}
                      </div>

                    </div>

                    <div className="analysis-notice analysis-notice-dim">
                      Score reflects the extracted text only. Suspicious text
                      in an image does not confirm the image itself was manipulated.
                    </div>

                  </div>
                )}

                {/* --- METADATA SECTION --- */}
                {backendImageResult.metadata && (
                  <div className="analysis-block">

                    <div className="analysis-block-header">
                      <span className="block-tag">META</span>
                      <span className="block-title">
                        IMAGE METADATA
                      </span>
                    </div>

                    <div className="meta-grid">

                      <div className="detail-row">
                        <span>FORMAT</span>
                        <strong>
                          {backendImageResult.metadata.format}
                        </strong>
                      </div>

                      <div className="detail-row">
                        <span>DIMENSIONS</span>
                        <strong>
                          {backendImageResult.metadata.width} ×{" "}
                          {backendImageResult.metadata.height} px
                        </strong>
                      </div>

                      <div className="detail-row">
                        <span>FILE SIZE</span>
                        <strong>
                          {formatFileSize(
                            backendImageResult.metadata.file_size_bytes
                          )}
                        </strong>
                      </div>

                      <div className="detail-row">
                        <span>COLOUR MODE</span>
                        <strong>
                          {backendImageResult.metadata.mode}
                        </strong>
                      </div>

                      <div className="detail-row">
                        <span>EXIF DATA</span>
                        <strong>
                          {backendImageResult.metadata.exif_available
                            ? "Present"
                            : "Not found"}
                        </strong>
                      </div>

                    </div>

                    {/* EXIF fields */}
                    {backendImageResult.metadata.exif_available &&
                      Object.keys(backendImageResult.metadata.exif_fields).length > 0 && (
                        <div className="exif-block">
                          <div className="exif-block-label">
                            EXIF FIELDS
                          </div>
                          {Object.entries(
                            backendImageResult.metadata.exif_fields
                          ).map(([key, val]) => (
                            <div key={key} className="detail-row exif-row">
                              <span>{key}</span>
                              <strong>{val}</strong>
                            </div>
                          ))}
                        </div>
                      )}

                    {/* Observations */}
                    {backendImageResult.metadata.observations.length > 0 && (
                      <div className="observations-block">
                        <div className="observations-label">
                          OBSERVATIONS
                        </div>
                        {backendImageResult.metadata.observations.map(
                          (obs, i) => (
                            <div key={i} className="observation-item">
                              <span>—</span>
                              <p>{obs}</p>
                            </div>
                          )
                        )}
                      </div>
                    )}

                  </div>
                )}

                {/* --- ELA SECTION --- */}
                {backendImageResult.ela && (
                  <div className="analysis-block">

                    <div className="analysis-block-header">
                      <span className="block-tag">ELA</span>
                      <span className="block-title">
                        ERROR LEVEL ANALYSIS
                      </span>
                      <span className={`ocr-status-badge ocr-${backendImageResult.ela.performed ? "success" : "no_text"}`}>
                        {backendImageResult.ela.performed ? "Performed" : "Skipped"}
                      </span>
                    </div>

                    {!backendImageResult.ela.performed &&
                      backendImageResult.ela.reason_skipped && (
                        <div className="analysis-notice">
                          {backendImageResult.ela.reason_skipped}
                        </div>
                      )}

                    {backendImageResult.ela.ela_image && (
                      <div className="ela-image-block">
                        <div className="ela-image-label">
                          ELA VISUALISATION
                          <span>Brighter = larger recompression difference</span>
                        </div>
                        <img
                          src={backendImageResult.ela.ela_image}
                          alt="Error Level Analysis visualisation"
                          className="ela-image"
                        />
                      </div>
                    )}

                    {backendImageResult.ela.observations.length > 0 && (
                      <div className="observations-block">
                        <div className="observations-label">
                          ELA FINDINGS
                        </div>
                        {backendImageResult.ela.observations.map(
                          (obs, i) => (
                            <div key={i} className="observation-item">
                              <span>—</span>
                              <p>{obs}</p>
                            </div>
                          )
                        )}
                      </div>
                    )}

                  </div>
                )}

                {/* Disclaimer */}
                <div className="image-disclaimer">
                  <span>IMPORTANT LIMITATIONS</span>
                  <ul>
                    <li>Suspicious OCR text does not prove the image was manipulated.</li>
                    <li>A manipulated image does not necessarily contain false claims.</li>
                    <li>Missing metadata does not prove that an image is fake.</li>
                    <li>ELA anomalies do not prove tampering.</li>
                    <li>An image with no detected anomalies is not guaranteed authentic.</li>
                  </ul>
                </div>

              </div>
            )}

          </div>
        </section>

        {/* ================= HOW IT WORKS ================= */}

        <section id="about" className="section about-section">

          <div className="page-width">

            <div className="section-heading">
              <div>
                <div className="section-number">03</div>

                <h2>
                  How it
                  <br />
                  works
                </h2>
              </div>

              <p>
                FakeGuard uses deterministic rules rather
                than artificial intelligence to identify
                observable warning signs.
              </p>
            </div>

            <div className="rules-grid">

              <div className="rule-item">
                <span>01</span>
                <h3>
                  Suspicious Keywords
                </h3>
                <p>
                  Identifies predefined words that may
                  indicate sensational or suspicious content.
                </p>
              </div>

              <div className="rule-item">
                <span>02</span>
                <h3>
                  Clickbait Detection
                </h3>
                <p>
                  Checks the article for predefined
                  attention-grabbing phrases.
                </p>
              </div>

              <div className="rule-item">
                <span>03</span>
                <h3>
                  Text Patterns
                </h3>
                <p>
                  Examines capitalization and excessive
                  punctuation patterns.
                </p>
              </div>

              <div className="rule-item">
                <span>04</span>
                <h3>
                  Rule-Based Score
                </h3>
                <p>
                  Combines detected indicators into a
                  transparent credibility score.
                </p>
              </div>

            </div>

          </div>

        </section>

        {/* ================= DISCLAIMER ================= */}

        <section className="disclaimer-section">

          <div className="page-width">

            <div className="disclaimer">

              <span>IMPORTANT</span>

              <p>
                FakeGuard is an experimental rule-based
                analysis system. Its results indicate
                observable patterns and should not be
                treated as definitive proof that a news
                article is true or false.
              </p>

            </div>

          </div>

        </section>

      </main>

      {/* ================= FOOTER ================= */}

      <footer className="footer">

        <div className="page-width footer-inner">

          <div>
            <div className="brand-name">
              FAKEGUARD
            </div>

            <p>
              Rule-Based News Credibility Analyzer
            </p>
          </div>

          <div className="footer-right">
            <span>
              PHASE 3 PROJECT DEMO
            </span>

            <span>
              © 2026 FAKEGUARD
            </span>
          </div>

        </div>

      </footer>

    </div>
  )
}

export default App