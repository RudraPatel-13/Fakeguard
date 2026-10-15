"""
FakeGuard Phase 3 -- FastAPI Application
==========================================
HTTP routing, CORS, structured logging, and safe translation of keyword-library
failures into HTTP 503 responses.

Existing endpoints (/, /health, /analyze) are structurally unchanged so the
React frontend requires no modifications.
"""

import logging

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import wordnet_service
from analyzer import analyze_text
from image_analyzer import analyze_image
from keyword_loader import KeywordLibraryError, get_config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("fakeguard.api")

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FakeGuard API",
    description="Rule-Based News Credibility Analyzer",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global safe error handler for keyword library failures
# ---------------------------------------------------------------------------

@app.exception_handler(KeywordLibraryError)
async def keyword_library_error_handler(
    request: Request, exc: KeywordLibraryError
) -> JSONResponse:
    """
    Translate any uncaught KeywordLibraryError into HTTP 503.
    The client message is safe: no filesystem paths, no stack traces.
    The full error is logged server-side for diagnostics.
    """
    logger.error(
        "Keyword library error on %s %s: %s",
        request.method,
        request.url.path,
        str(exc),
    )
    return JSONResponse(
        status_code=503,
        content={
            "error": "service_unavailable",
            "message": (
                "The analysis service is temporarily unavailable. "
                "Please try again shortly."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class ArticleRequest(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "FakeGuard API is running",
        "status": "success",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/analyze")
def analyze_article(article: ArticleRequest):
    """
    Analyze the credibility of a news article.

    Response structure is identical to Phase 2 for full frontend compatibility.
    On keyword library failure, KeywordLibraryError propagates to the global
    exception handler which converts it to HTTP 503 with a safe message.
    """
    logger.info("POST /analyze  text_length=%d", len(article.text))

    result = analyze_text(article.text)          # raises KeywordLibraryError on failure

    logger.info(
        "Analysis complete: score=%d  classification=%r",
        result["score"],
        result["classification"],
    )
    return {
        "message": "Article analyzed successfully",
        "text_length": len(article.text),
        "score": result["score"],
        "classification": result["classification"],
        "indicators": result["indicators"],
        "word_count": result["word_count"],
    }


@app.post("/analyze-image")
async def analyze_image_endpoint(file: UploadFile = File(...)):
    """
    Analyse an uploaded image.

    Accepts multipart/form-data with a single field named 'file'.

    Response structure:
      status        -- 'ok' | 'error'
      error         -- human-readable error string, or null
      file_name     -- original filename
      ocr           -- {status, text, character_count, warning}
      text_analysis -- score/classification/indicators (null if no OCR text)
      metadata      -- format, dimensions, file size, EXIF findings
      ela           -- Error Level Analysis result + visualisation

    Existing endpoints (/, /health, /analyze) are unchanged.
    Uploaded bytes are processed in-memory; no file is saved to disk.
    """
    filename = file.filename or "upload"
    logger.info(
        "POST /analyze-image  filename=%r  content_type=%r",
        filename, file.content_type,
    )

    try:
        file_bytes = await file.read()
    except Exception as exc:
        logger.error("File read error: %s", exc)
        raise HTTPException(status_code=400, detail="Could not read uploaded file.")

    result = analyze_image(file_bytes, filename)    # never raises

    logger.info(
        "Image analysis complete: status=%r  ocr_status=%r",
        result.get("status"),
        result.get("ocr", {}).get("status") if result.get("ocr") else "n/a",
    )
    return result


@app.get("/keywords")
def keyword_library_info():
    """
    Read-only metadata about the currently loaded keyword library.

    Returns version, keyword/phrase counts, active scoring parameters,
    and classification bands.  Does NOT expose the keyword lists themselves
    or any filesystem paths.
    """
    try:
        cfg = get_config()
    except KeywordLibraryError as exc:
        logger.error("Keyword library unavailable for GET /keywords: %s", str(exc))
        raise HTTPException(
            status_code=503,
            detail="Keyword library is currently unavailable.",
        )

    wn_stats = wordnet_service.cache_stats()

    return {
        "version": cfg.version,
        "suspicious_keyword_count": len(cfg.suspicious_keywords.words),
        "clickbait_phrase_count": len(cfg.clickbait_phrases.phrases),
        "max_total_score": cfg.max_total_score,
        "scoring": {
            "points_per_suspicious_keyword": cfg.suspicious_keywords.points_per_distinct_keyword,
            "suspicious_keyword_cap": cfg.suspicious_keywords.max_contribution,
            "points_per_clickbait_phrase": cfg.clickbait_phrases.points_per_phrase,
            "clickbait_phrase_cap": cfg.clickbait_phrases.max_contribution,
        },
        "classification_bands": [
            {"label": t.label, "min": t.min_score, "max": t.max_score}
            for t in cfg.thresholds
        ],
        "wordnet_status": {
            "available": wn_stats["wordnet_available"],
            "cached_word_lookups": wn_stats["cached_word_lookups"],
            "synonym_map_entries": wn_stats["synonym_map_entries"],
        },
    }
