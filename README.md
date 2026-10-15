# FakeGuard — Rule-Based News Credibility Analyzer

A college mini-project that analyzes the credibility of news articles using
a configurable, rule-based scoring engine.

---

## Project Phases

| Phase | Description |
|-------|-------------|
| **Phase 1** | Project setup — React + Vite frontend, FastAPI backend |
| **Phase 2** | Core analyzer — hardcoded keyword rules, article + image inspection UI |
| **Phase 3** | Dynamic keyword library — external JSON config with hot-reload (no server restart required) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite, plain CSS |
| Backend | Python 3.11, FastAPI, Uvicorn |
| Analyzer | Rule-based scoring engine (`analyzer.py`) |
| Config | External JSON keyword library (`keywords.json`) |
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
# All three suites (177 tests total)
backend\.venv\Scripts\python.exe -m pytest \
  backend/app/test_keyword_loader.py \
  backend/app/test_analyzer_integration.py \
  backend/app/test_api.py \
  -v
```

| Suite | Count | Covers |
|-------|-------|--------|
| `test_keyword_loader.py` | 69 | Loader validation, hot-reload, thread-safety |
| `test_analyzer_integration.py` | 39 | Scoring engine, config-change behavior |
| `test_api.py` | 69 | HTTP endpoints, frontend compatibility, 503 safety |
| **Total** | **177** | |

---

## Git Workflow

### Branches

| Branch | Purpose |
|--------|---------|
| `master` | Stable baseline (Phase 2 complete) |
| `feature/phase3-dynamic-keyword-loader` | Phase 3 feature development |

Phase 3 was developed entirely on the feature branch and merged into `master`
after all 177 tests passed.

### Commit conventions

This project uses **Conventional Commits**:

```
<type>(<scope>): <short description>
```

Types used: `chore`, `feat`, `refactor`, `test`, `docs`.

---

## Author

College mini-project — FakeGuard Phase 3.
