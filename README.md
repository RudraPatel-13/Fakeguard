# FakeGuard — Rule-Based News Credibility Analyzer

A college mini-project that analyzes the credibility of news articles using
a configurable, rule-based scoring engine.

---

## Project Phases

| Phase | Description |
|-------|-------------|
| **Phase 1** | Project setup — React + Vite frontend, FastAPI backend |
| **Phase 2** | Core analyzer — hardcoded keyword rules, article + image inspection UI |
| **Phase 3a** | Dynamic keyword library — external JSON config with hot-reload |
| **Phase 3b** | WordNet synonym detection — lexical expansion via NLTK |
| **Phase 3c** | Image forensics — OCR text extraction, metadata inspection, Error Level Analysis |
| **Phase 4** | Hybrid rules + ML scoring, OCR→credibility dual verdict, claim verification, cyber-intelligence dashboard — see [PHASE4_DOCUMENTATION.md](PHASE4_DOCUMENTATION.md) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite, plain CSS |
| Backend | Python 3.11, FastAPI, Uvicorn |
| Analyzer | Rule-based scoring engine (`analyzer.py`) |
| Config | External JSON keyword library (`keywords.json`) |
| Synonym detection | NLTK WordNet (`wordnet_service.py`) |
| Image analysis | Pillow 12, pytesseract 0.3.13, ELA (`image_analyzer.py`) |
| Tests | pytest 9, starlette TestClient |

---

## Repository Structure

```
FakeGuard/
├── src/                          # React frontend
│   ├── App.jsx                   # Main application component
│   ├── App.css                   # Component styles
│   └── index.css                 # Global styles
├── public/                       # Static assets
├── backend/
│   ├── requirements.txt          # Python dependencies
│   └── app/
│       ├── main.py               # FastAPI application + endpoints
│       ├── analyzer.py           # Scoring engine
│       ├── keyword_loader.py     # Dynamic keyword library loader (Phase 3)
│       ├── keyword_library/
│       │   └── keywords.json     # External keyword configuration (Phase 3)
│       ├── test_keyword_loader.py      # 69 loader unit tests
│       ├── test_analyzer_integration.py # 39 integration tests
│       └── test_api.py           # 69 HTTP API tests
├── acceptance_test.py            # Live end-to-end hot-reload test
├── pytest.ini                    # pytest configuration
├── package.json                  # Frontend dependencies
├── vite.config.js                # Vite configuration
└── .gitignore                    # Excludes .venv, node_modules, .env, __pycache__
```

---

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Start the API server
python -m uvicorn app.main:app --reload --app-dir app
```

The API is available at `http://localhost:8000`.

### Frontend

```bash
# From project root
npm install
npm run dev
```

The frontend is available at `http://localhost:5173`.

---

## API Reference

> **Phase 4 additions** (all additive): `POST /verify-web` (live news/fact-check search), `POST /verify-claim`, `GET /model-info`, `GET /keywords/rules`, `POST /keywords/reload`; `/analyze` accepts optional `url` and `?verify_web=true` and returns `ml`, `fusion`, `fact_check`, `domain`; `/analyze-image` returns `dual_verdict`, `forensics`, `keyword_overlays`. Details in [PHASE4_DOCUMENTATION.md](PHASE4_DOCUMENTATION.md). Set `FAKEGUARD_ONLINE=1` to enable live fact-check lookups.

### `GET /health`
Returns `{"status": "healthy"}`.

### `GET /`
Returns `{"message": "FakeGuard API is running", "status": "success"}`.

### `POST /analyze`
Analyzes a news article for credibility signals.

**Request body:**
```json
{ "text": "Article text here..." }
```

**Response:**
```json
{
  "message": "Article analyzed successfully",
  "text_length": 123,
  "score": 45,
  "classification": "Suspicious",
  "indicators": ["Suspicious keywords detected: fake, hoax", "Clickbait phrase detected"],
  "word_count": 20
}
```

**Classification bands:**

| Score | Classification |
|-------|---------------|
| 0 – 30 | Credible |
| 31 – 60 | Suspicious |
| 61 – 100 | Likely Fake |

### `GET /keywords`
Returns read-only metadata about the currently loaded keyword library —
version, counts, scoring parameters, and classification bands.
Does **not** expose the keyword list itself or any filesystem paths.

---

## Phase 3 — Dynamic Keyword Library

### Overview

Phase 3 replaces all hardcoded keyword and scoring constants with an external
JSON configuration file (`backend/app/keyword_library/keywords.json`).

The loader (`keyword_loader.py`):
- Validates every field in the JSON file on load.
- Caches the parsed configuration as an **immutable frozen dataclass**.
- Checks the file's modification time (`mtime`) before every analysis request.
- **Reloads automatically** when the file changes — no server restart needed.
- Is **thread-safe**: multiple concurrent requests share a single lock.
- Translates all library failures into HTTP **503** with a safe client message
  (no filesystem paths or Python tracebacks are exposed).

### keywords.json schema

```jsonc
{
  "version": "1.0.0",
  "suspicious_keywords": {
    "words": ["fake", "hoax", "..."],
    "scoring": { "points_per_distinct_keyword": 10, "max_contribution": 30 }
  },
  "clickbait_phrases": {
    "phrases": ["you won't believe", "..."],
    "scoring": { "points_per_phrase": 15, "max_contribution": 30 }
  },
  "text_pattern_rules": {
    "excessive_capitalization":   { "uppercase_ratio_threshold": 0.50, "points": 10 },
    "excessive_exclamation_marks":{ "min_count": 3, "points": 10 },
    "excessive_question_marks":   { "min_count": 3, "points": 5  }
  },
  "scoring": { "max_total_score": 100 },
  "classification": {
    "thresholds": [
      { "label": "Credible",    "min": 0,  "max": 30  },
      { "label": "Suspicious",  "min": 31, "max": 60  },
      { "label": "Likely Fake", "min": 61, "max": 100 }
    ]
  }
}
```

### Hot-reload demo

```bash
# Confirm baseline (no restart between these two commands)
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"hotreloadtest\"}" | python -m json.tool

# Add "hotreloadtest" to keywords.json, save the file, then:
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"hotreloadtest\"}" | python -m json.tool
# score jumps from 0 to 10 with no restart
```

Or run the automated end-to-end acceptance test:

```bash
python acceptance_test.py
```

---

## Running the Tests

```bash
# All five suites (280 tests total — 279 passed, 1 skipped)
backend\.venv\Scripts\python.exe -m pytest \
  backend/app/test_keyword_loader.py \
  backend/app/test_analyzer_integration.py \
  backend/app/test_api.py \
  backend/app/test_wordnet_service.py \
  backend/app/test_image_analyzer.py \
  -v
```

| Suite | Count | Covers |
|-------|-------|--------|
| `test_keyword_loader.py` | 69 | Loader validation, hot-reload, thread-safety |
| `test_analyzer_integration.py` | 39 | Scoring engine, config-change behavior |
| `test_api.py` | 69 | HTTP endpoints, frontend compatibility, 503 safety |
| `test_wordnet_service.py` | 57 | WordNet availability, synonym retrieval, deduplication, API compat |
| `test_image_analyzer.py` | 46 | Image validation, OCR, metadata, ELA, pipeline, API structure |
| **Total** | **280** | **279 passed, 1 skipped (real Tesseract integration)** |

> The skipped test (`test_real_ocr_on_text_image`) requires Tesseract to be installed.
> All 279 other tests pass with no external executables required.

---

## Image Analysis — Layers 1 and 2

### POST /analyze-image

Accepts a multipart image upload and returns a structured JSON result.

```bash
curl -X POST http://127.0.0.1:8000/analyze-image \
  -F "file=@/path/to/image.jpg"
```

Response structure:

```json
{
  "status": "ok",
  "error": null,
  "file_name": "image.jpg",
  "ocr": {
    "status": "success",
    "text": "SHOCKING REVELATION ...",
    "character_count": 42,
    "warning": "OCR output may contain recognition errors."
  },
  "text_analysis": {
    "score": 20,
    "classification": "Suspicious",
    "indicators": ["Suspicious keyword detected: \"shocking\""],
    "word_count": 3
  },
  "metadata": {
    "format": "JPEG",
    "width": 1920,
    "height": 1080,
    "file_size_bytes": 245760,
    "mode": "RGB",
    "exif_available": true,
    "exif_fields": { "Software": "Adobe Photoshop", "DateTime": "2024:01:01 12:00:00" },
    "observations": ["Software tag: 'Adobe Photoshop'. ..."]
  },
  "ela": {
    "performed": true,
    "observations": ["Moderate ELA variance...", "ELA does not prove tampering."],
    "ela_image": "data:image/png;base64,...",
    "limitation_note": "ELA highlights areas that recompressed differently..."
  }
}
```

---

## Tesseract OCR Installation (Windows)

The OCR feature requires Tesseract to be installed separately on your machine.
Python `pytesseract` is just a wrapper — it cannot function without the Tesseract executable.

**Step 1 — Download and install Tesseract:**

1. Go to: <https://github.com/UB-Mannheim/tesseract/wiki>
2. Download the latest Windows installer (e.g. `tesseract-ocr-w64-setup-5.x.x.exe`).
3. Run the installer. Note the installation path — default is:
   `C:\Program Files\Tesseract-OCR\tesseract.exe`
4. The backend auto-detects this path on Windows. No extra configuration needed.

**Step 2 — Alternative: add to PATH:**

If Tesseract is installed in a custom location, either:
- Add the folder to your Windows `PATH`, **or**
- Set environment variable `TESSERACT_CMD` to the full `.exe` path before starting the backend:

```powershell
$env:TESSERACT_CMD = "C:\Custom\Path\tesseract.exe"
backend\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend/app --host 127.0.0.1 --port 8000
```

**Without Tesseract:** The backend starts normally. OCR returns `status: "ocr_unavailable"` with
installation instructions. All other features (text analyzer, metadata, ELA) still work.

---

## Image Analysis Limitations

| Finding | What it means | What it does NOT mean |
|---------|--------------|----------------------|
| Suspicious OCR text | Extracted text matches credibility warning patterns | The image itself was manipulated |
| Missing EXIF | Metadata was not embedded or was stripped | The image is fake |
| Software tag (e.g. Photoshop) | The file was processed by that application | The content was fabricated |
| High ELA variance | Areas recompressed differently | Tampering is proven |
| Low ELA variance | Image appears uniformly compressed | Image is authentic |
| ELA on PNG | Always includes format-conversion artifacts | Direct evidence of editing |

---

## Git Workflow

### Branches

| Branch | Purpose |
|--------|---------|
| `master` | Stable baseline |
| `feature/phase3-dynamic-keyword-loader` | Phase 3a — dynamic keyword library |
| `feature/wordnet-synonym-detection` | Phase 3b — WordNet synonym expansion |
| `feature/image-forensics` | Phase 3c — OCR + metadata + ELA |

### Commit conventions

This project uses **Conventional Commits**:

```
<type>(<scope>): <short description>
```

Types used: `chore`, `feat`, `refactor`, `test`, `docs`.

---

## Author

College mini-project — FakeGuard.
