import { useState } from "react"
import "./App.css"

function App() {
  const [articleText, setArticleText] = useState("")
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const [selectedImage, setSelectedImage] = useState(null)
  const [imagePreview, setImagePreview] = useState(null)
  const [imageResult, setImageResult] = useState(null)

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
              PHASE 2 • RULE-BASED ANALYSIS SYSTEM
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
                rule-based analysis.
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
                Upload a JPG or PNG image to inspect
                basic file and image properties.
              </p>
            </div>

            <div className="image-layout">

              {/* UPLOAD */}

              <div className="upload-panel">

                <div className="panel-header">
                  <span>IMAGE INPUT</span>
                  <span>JPG / PNG</span>
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
                    accept="image/png,image/jpeg"
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
              PHASE 2 PROJECT DEMO
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