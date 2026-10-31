"""
FakeGuard Phase 4 -- FastAPI Application
==========================================
HTTP routing, CORS, structured logging, and safe translation of keyword-library
failures into HTTP 503 responses.

Existing endpoints (/, /health, /analyze) are structurally unchanged so the
React frontend requires no modifications.
"""

import logging
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import fusion as fusion_mod
import ml_service
import verifier_service
import web_search_service
import wordnet_service
from analyzer import analyze_text
from image_analyzer import analyze_image
from keyword_loader import KeywordLibraryError, get_config
import auth_routes
from database import init_db

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
    description="Hybrid (rules + ML) News Credibility & Image Forensics Platform",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global safe error handler for keyword library failures
# ---------------------------------------------------------------------------

init_db()
app.include_router(auth_routes.router)


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
    url: Optional[str] = None      # optional source URL for domain-trust scoring


class VerifyRequest(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None


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
def analyze_article(article: ArticleRequest, verify_web: bool = False):
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

    # Phase 4 additive signals.  Failures here never break the legacy payload.
    ml = fact = domain = fusion = web = None
    claims: list = []
    try:
        ml = ml_service.predict(article.text)
        claims = verifier_service.extract_claims(article.text)
        fact = verifier_service.check_claims(claims)
        domain = verifier_service.assess_domain(article.url) if article.url else None
        if verify_web:
            web = web_search_service.verify_web(article.text)
        fusion = fusion_mod.fuse(result, ml, fact_check=fact, domain=domain, web=web)
    except Exception as exc:
        logger.error("Phase 4 enrichment failed: %s", exc)

    return {
        "message": "Article analyzed successfully",
        "text_length": len(article.text),
        "score": result["score"],
        "classification": result["classification"],
        "indicators": result["indicators"],
        "word_count": result["word_count"],
        "breakdown": result["breakdown"],
        "matched_terms": result["matched_terms"],
        "ml": ml,
        "claims": claims,
        "fact_check": fact,
        "domain": domain,
        "web": web,
        "fusion": fusion,
    }


@app.post("/verify-web")
async def verify_web_endpoint(req: VerifyRequest):
    """
    Live internet cross-check: are the claims reported by reputable outlets or
    addressed by fact-checkers?  Falls back to offline simulation mode if the
    network is unreachable.  Body: {text?, url?}; a URL contributes its domain
    assessment.
    """
    if not (req.text and req.text.strip()):
        raise HTTPException(status_code=422, detail="Provide 'text' (headline or claim) to verify.")
    web = await run_in_threadpool(web_search_service.verify_web, req.text)
    return {"web": web, "domain": verifier_service.assess_domain(req.url) if req.url else None}


@app.post("/verify-claim")
def verify_claim(req: VerifyRequest):
    """
    Extract claims from text and/or assess a URL's publisher, then cross-check
    against fact-check sources (offline registry by default; live sources when
    FAKEGUARD_ONLINE=1).  At least one of text/url is required.
    """
    if not (req.text and req.text.strip()) and not (req.url and req.url.strip()):
        raise HTTPException(status_code=422, detail="Provide 'text' and/or 'url'.")
    logger.info("POST /verify-claim  text=%s url=%s", bool(req.text), bool(req.url))
    return verifier_service.verify(text=req.text, url=req.url)


@app.get("/model-info")
def model_info():
    """Metadata about the ML credibility classifier and runtime mode."""
    info = ml_service.model_info()
    info["verification_mode"] = "online" if verifier_service.online_enabled() else "offline"
    info["fusion"] = {
        "w_rules": fusion_mod.W_RULES, "w_ml": fusion_mod.W_ML,
        "with_web": {"rules": fusion_mod.W3_RULES, "ml": fusion_mod.W3_ML, "web": fusion_mod.W3_WEB},
        "web_search": "disabled" if not web_search_service.web_enabled() else "live",
        "forensics_max_penalty": fusion_mod.FORENSICS_MAX_PENALTY,
        "claim_contradicted_penalty": fusion_mod.CLAIM_CONTRADICTED_PENALTY,
        "source_max_penalty": fusion_mod.SOURCE_MAX_PENALTY,
    }
    return info


@app.post("/analyze-image")
async def analyze_image_endpoint(file: UploadFile = File(...), verify_web: bool = True):
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

    result = await run_in_threadpool(analyze_image, file_bytes, filename, verify_web)    # never raises

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


@app.get("/keywords/rules")
def keyword_rules():
    """Loaded rule lists for the Rule Studio (read-only).  /keywords stays metadata-only."""
    cfg = get_config()
    return {
        "version": cfg.version,
        "suspicious_keywords": sorted(cfg.suspicious_keywords.words),
        "clickbait_phrases": list(cfg.clickbait_phrases.phrases),
        "text_patterns": {
            "caps_ratio_threshold": cfg.text_patterns.caps_ratio_threshold,
            "caps_points": cfg.text_patterns.caps_points,
            "exclamation_min_count": cfg.text_patterns.exclamation_min_count,
            "exclamation_points": cfg.text_patterns.exclamation_points,
            "question_min_count": cfg.text_patterns.question_min_count,
            "question_points": cfg.text_patterns.question_points,
        },
    }


_last_reload_version: Optional[str] = None


@app.post("/keywords/reload")
def keyword_reload():
    """Force a modification-time check now (the library also hot-reloads on every request)."""
    global _last_reload_version
    cfg = get_config()
    changed = _last_reload_version is not None and cfg.version != _last_reload_version
    _last_reload_version = cfg.version
    return {"version": cfg.version, "changed": changed,
            "suspicious_keyword_count": len(cfg.suspicious_keywords.words),
            "clickbait_phrase_count": len(cfg.clickbait_phrases.phrases)}
