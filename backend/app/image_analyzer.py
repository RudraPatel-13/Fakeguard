"""
FakeGuard -- Image Analyzer (Layers 1 and 2)
==============================================
Layer 1: OCR text extraction via Tesseract + Pillow.
Layer 2: Image metadata inspection and basic manipulation analysis (ELA).

Does NOT perform AI-based image generation detection or ML classification.

Architecture:
  validate_and_decode_image()  -- validate bytes, decode to PIL Image
  extract_ocr_text()           -- Tesseract OCR
  extract_metadata()           -- EXIF, dimensions, format, file size
  perform_ela()                -- Error Level Analysis (JPEG recompression diff)
  analyze_image()              -- full pipeline; never raises

Dependencies (Python):
  pip install pytesseract Pillow python-multipart

External requirement (must be installed separately by the user):
  Tesseract OCR executable for Windows:
  https://github.com/UB-Mannheim/tesseract/wiki
  Default Windows installation path:
    C:\\Program Files\\Tesseract-OCR\\tesseract.exe
  This module will auto-detect that path on Windows if Tesseract is not on PATH.
  Alternatively, set the environment variable TESSERACT_CMD to the full exe path.

Limitations documented:
  - OCR output may contain recognition errors.
  - ELA works by JPEG recompression; results on PNG/WebP include format
    conversion artifacts and must be interpreted with extra caution.
  - Missing EXIF does not prove manipulation; social-media uploads routinely
    strip metadata.
  - ELA bright regions do not prove tampering.
  - No AI-based detection is performed.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import platform
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("fakeguard.image_analyzer")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_IMAGE_SIZE_MB: int = 10
MAX_IMAGE_SIZE_BYTES: int = MAX_IMAGE_SIZE_MB * 1024 * 1024

SUPPORTED_FORMATS: set = {"JPEG", "PNG", "WEBP", "BMP"}

ELA_QUALITY: int = 75    # JPEG quality level for ELA recompression
ELA_SCALE: int = 10      # Pixel amplification factor for ELA visualisation

# EXIF tags to surface prominently in the response
_EXIF_INTEREST_TAGS: set = {
    "DateTime", "DateTimeOriginal", "DateTimeDigitized",
    "Make", "Model", "Software",
    "LensModel", "GPSInfo", "Copyright",
    "ImageDescription", "Artist",
    "XResolution", "YResolution",
    "Flash", "ExposureTime", "FNumber", "ISOSpeedRatings",
}


# ---------------------------------------------------------------------------
# Tesseract path auto-detection
# ---------------------------------------------------------------------------

def _configure_tesseract() -> None:
    """
    Ensure pytesseract can find the Tesseract executable.

    Priority:
    1. TESSERACT_CMD environment variable.
    2. Standard Windows installation paths (if os.path.isfile).
    3. PATH (pytesseract default — leave unchanged if nothing else found).
    """
    try:
        import pytesseract

        # 1. Explicit env override
        env_cmd = os.environ.get("TESSERACT_CMD")
        if env_cmd and os.path.isfile(env_cmd):
            pytesseract.pytesseract.tesseract_cmd = env_cmd
            logger.info("Tesseract configured from TESSERACT_CMD env var: %s", env_cmd)
            return

        # 2. Well-known Windows paths
        if platform.system() == "Windows":
            candidates = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for path in candidates:
                if os.path.isfile(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    logger.info("Tesseract auto-configured: %s", path)
                    return

        # 3. Fall back to PATH (no change needed)
    except ImportError:
        pass  # pytesseract not installed; handled in check_tesseract_available


# Run once at module load
_configure_tesseract()


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def check_tesseract_available() -> bool:
    """Return True iff Tesseract OCR is installed and accessible."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OcrResult:
    status: str                      # success | no_text | ocr_unavailable | error
    text: str = ""
    character_count: int = 0
    warning: Optional[str] = None
    words: list = field(default_factory=list)      # [{text, conf, x, y, w, h}] normalised 0-1 boxes
    mean_confidence: Optional[float] = None
    preprocessing: list = field(default_factory=list)


@dataclass
class MetadataResult:
    format: str
    width: int
    height: int
    file_size_bytes: int
    mode: str
    exif_available: bool
    exif_fields: dict = field(default_factory=dict)
    observations: list = field(default_factory=list)


@dataclass
class ElaResult:
    performed: bool
    reason_skipped: Optional[str] = None
    observations: list = field(default_factory=list)
    ela_image: Optional[str] = None     # data:image/png;base64,...
    limitation_note: str = ""
    max_diff: int = 0
    mean_diff: float = 0.0
    hot_fraction: float = 0.0           # share of pixels with diff >= 20 (unamplified)


# ---------------------------------------------------------------------------
# Layer 1a: Validate and decode
# ---------------------------------------------------------------------------

def validate_and_decode_image(
    file_bytes: bytes, filename: str
) -> tuple:
    """
    Validate uploaded bytes and decode to a PIL Image.

    Returns (PIL.Image.Image, None) on success.
    Returns (None, error_string) on any failure.

    Does NOT permanently save the file.
    """
    if len(file_bytes) == 0:
        return None, "Uploaded file is empty."

    if len(file_bytes) > MAX_IMAGE_SIZE_BYTES:
        mb = len(file_bytes) / 1024 / 1024
        return None, (
            f"File exceeds the maximum allowed size of {MAX_IMAGE_SIZE_MB} MB "
            f"(received {mb:.1f} MB)."
        )

    try:
        from PIL import Image

        buffer = io.BytesIO(file_bytes)
        image = Image.open(buffer)
        image.load()                           # force full decode; catches corruption

        if image.format not in SUPPORTED_FORMATS:
            return None, (
                f"Image format '{image.format}' is not supported. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}."
            )

        return image, None

    except Exception as exc:
        logger.warning("Image decode failed for %r: %s", filename, exc)
        return None, (
            "The uploaded file could not be decoded as a valid image. "
            "The file may be corrupt, truncated, or not an image file."
        )


# ---------------------------------------------------------------------------
# Layer 1b: OCR text extraction
# ---------------------------------------------------------------------------

def preprocess_for_ocr(image):
    """
    Pillow/numpy-only OCR preprocessing (no OpenCV dependency):
      grayscale -> upscale small images -> median denoise (edge-preserving
      stand-in for a bilateral filter) -> autocontrast -> adaptive (local-mean)
      threshold.  Returns (processed PIL image, list of applied steps, scale).
    """
    from PIL import Image, ImageFilter, ImageOps
    import numpy as np

    steps = ["grayscale"]
    gray = ImageOps.grayscale(image.convert("RGB"))
    scale = 1.0
    if max(gray.size) < 1200:
        scale = min(2.0, 1200 / max(gray.size))
        gray = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.LANCZOS)
        steps.append(f"upscale x{scale:.1f}")
    gray = gray.filter(ImageFilter.MedianFilter(3))
    steps.append("median denoise")
    gray = ImageOps.autocontrast(gray, cutoff=1)
    steps.append("autocontrast")
    radius = max(8, min(gray.size) // 16)
    local_mean = np.asarray(gray.filter(ImageFilter.BoxBlur(radius)), dtype=np.float32)
    arr = np.asarray(gray, dtype=np.float32)
    binary = np.where(arr > local_mean - 10, 255, 0).astype(np.uint8)
    steps.append("adaptive threshold")
    return Image.fromarray(binary, mode="L"), steps, scale


def _ocr_words(img, scale: float, orig_size: tuple) -> tuple:
    """Run image_to_data; return (words with normalised boxes, mean confidence)."""
    import pytesseract
    data = pytesseract.image_to_data(img, config="--psm 3", output_type=pytesseract.Output.DICT)
    pw, ph = img.size
    words, confs = [], []
    for i, txt in enumerate(data.get("text", [])):
        txt = (txt or "").strip()
        try:
            conf = float(data["conf"][i])
        except (ValueError, KeyError, IndexError):
            continue
        if not txt or conf < 0:
            continue
        words.append({
            "text": txt, "conf": round(conf, 1),
            "x": round(data["left"][i] / pw, 5), "y": round(data["top"][i] / ph, 5),
            "w": round(data["width"][i] / pw, 5), "h": round(data["height"][i] / ph, 5),
        })
        confs.append(conf)
    return words, (sum(confs) / len(confs) if confs else None)


def extract_ocr_text(image) -> OcrResult:
    """
    Extract text from a PIL Image using Tesseract OCR.

    Returns an OcrResult; never raises.
    If Tesseract is not installed, returns status='ocr_unavailable' with
    installation instructions.
    """
    if not check_tesseract_available():
        return OcrResult(
            status="ocr_unavailable",
            warning=(
                "Tesseract OCR is not installed or not reachable. "
                "Install it from: https://github.com/UB-Mannheim/tesseract/wiki  "
                "After installation, ensure tesseract.exe is on PATH or set "
                "the TESSERACT_CMD environment variable to its full path."
            ),
        )

    try:
        import pytesseract

        # --psm 3: automatic page segmentation (best for mixed text layouts)
        ocr_image = image.convert("RGB")
        raw_text = pytesseract.image_to_string(ocr_image, config="--psm 3")
        text = raw_text.strip()

        # Phase 4: word boxes + confidence, comparing raw vs preprocessed input.
        # Best-effort: any failure here leaves the plain-text result intact.
        words, mean_conf, applied = [], None, []
        try:
            w_raw, c_raw = _ocr_words(ocr_image, 1.0, image.size)
            words, mean_conf = w_raw, c_raw
            pre, steps, scale = preprocess_for_ocr(image)
            w_pre, c_pre = _ocr_words(pre, scale, image.size)
            if c_pre is not None and (c_raw is None or c_pre > c_raw + 3):
                alt = pytesseract.image_to_string(pre, config="--psm 3").strip()
                if alt:
                    text, words, mean_conf, applied = alt, w_pre, c_pre, steps
        except Exception as exc:
            logger.debug("OCR word-level pass skipped: %s", exc)

        if not text:
            return OcrResult(
                status="no_text",
                warning=(
                    "No readable text was detected in the image. "
                    "OCR accuracy depends on image resolution, contrast, and font clarity."
                ),
            )

        return OcrResult(
            status="success",
            text=text,
            character_count=len(text),
            warning=(
                "OCR output may contain recognition errors. "
                "Review extracted text carefully before relying on it."
            ),
            words=words,
            mean_confidence=round(mean_conf, 1) if mean_conf is not None else None,
            preprocessing=applied,
        )

    except Exception as exc:
        logger.error("OCR extraction error: %s", exc)
        return OcrResult(
            status="error",
            warning=(
                "OCR extraction encountered an error. "
                "The image may be too small, too blurry, or contain no recognisable text."
            ),
        )


# ---------------------------------------------------------------------------
# Layer 2a: Metadata inspection
# ---------------------------------------------------------------------------

def extract_metadata(image, file_bytes: bytes, filename: str) -> MetadataResult:
    """
    Inspect image metadata: format, dimensions, file size, EXIF.

    Treats all metadata as observations, not conclusions.
    Never executes embedded content or trusts metadata values as instructions.
    """
    from PIL import ExifTags

    fmt = image.format or "UNKNOWN"
    width, height = image.size
    mode = image.mode
    file_size = len(file_bytes)
    observations: list = []
    exif_fields: dict = {}
    exif_available = False

    # --- EXIF extraction ---
    try:
        raw_exif = image._getexif() if hasattr(image, "_getexif") else None
        if raw_exif:
            exif_available = True
            for tag_id, value in raw_exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, f"Tag_{tag_id}")
                # Sanitise: store only safe scalar / string values
                if isinstance(value, (str, int, float)):
                    exif_fields[tag_name] = str(value)[:200]   # cap length
                elif isinstance(value, bytes):
                    exif_fields[tag_name] = f"<binary {len(value)} bytes>"
                elif (
                    isinstance(value, (tuple, list))
                    and all(isinstance(v, (int, float)) for v in value)
                ):
                    exif_fields[tag_name] = str(value)
        else:
            observations.append(
                "No EXIF metadata was found. This is normal for images shared on "
                "social media, converted between formats, or processed by tools "
                "that strip metadata. Absence of EXIF does not indicate manipulation."
            )
    except Exception as exc:
        logger.debug("EXIF parse note for %r: %s", filename, exc)
        observations.append(
            "EXIF metadata could not be parsed. "
            "The file may use an unusual metadata structure."
        )

    # --- Timestamp ---
    ts_tags = ["DateTime", "DateTimeOriginal", "DateTimeDigitized"]
    found_ts = {t: exif_fields[t] for t in ts_tags if t in exif_fields}
    if found_ts:
        ts_str = "; ".join(f"{k}: {v}" for k, v in found_ts.items())
        observations.append(
            f"Timestamp metadata: {ts_str}. "
            "Timestamps record when the camera or software created/modified the file. "
            "They can be set or changed by editing software and do not independently "
            "verify when or where a photo was taken."
        )

    # --- Software ---
    if "Software" in exif_fields:
        sw = exif_fields["Software"]
        observations.append(
            f"Software tag: {sw!r}. "
            "This indicates which application processed the file. "
            "Common photo editors (Photoshop, GIMP, Lightroom) appear here after "
            "routine editing and do not by themselves indicate fabrication."
        )

    # --- Camera ---
    cam_tags = ["Make", "Model", "LensModel"]
    found_cam = {t: exif_fields[t] for t in cam_tags if t in exif_fields}
    if found_cam:
        cam_str = ", ".join(f"{t}: {v}" for t, v in found_cam.items())
        observations.append(f"Camera information: {cam_str}.")

    # --- GPS ---
    if "GPSInfo" in exif_fields:
        observations.append(
            "GPS coordinates are embedded in the file. "
            "GPS data can be added, modified, or removed by editing software."
        )

    # --- Dimension observations ---
    if width < 200 or height < 200:
        observations.append(
            f"Small image: {width}\u00d7{height} px. "
            "Low-resolution images reduce OCR accuracy and ELA reliability."
        )
    elif width > 5000 or height > 5000:
        observations.append(f"High-resolution image: {width}\u00d7{height} px.")

    # --- File size ---
    if file_size > 5 * 1024 * 1024:
        observations.append(
            f"Large file: {file_size / 1024 / 1024:.1f} MB. "
            "Uncompressed or lightly compressed originals are typically larger."
        )

    return MetadataResult(
        format=fmt,
        width=width,
        height=height,
        file_size_bytes=file_size,
        mode=mode,
        exif_available=exif_available,
        exif_fields={k: v for k, v in exif_fields.items() if k in _EXIF_INTEREST_TAGS},
        observations=observations,
    )


# ---------------------------------------------------------------------------
# Layer 2b: Error Level Analysis
# ---------------------------------------------------------------------------

_ELA_LIMITATION = (
    "ELA highlights areas that recompressed differently from the rest of the image. "
    "Bright ELA regions can result from natural image content variations, "
    "resizing, format conversion, heavy recompression, or image editing. "
    "ELA does not prove tampering, and the absence of bright regions does not "
    "guarantee that an image is unmodified."
)


def perform_ela(image) -> ElaResult:
    """
    Perform Error Level Analysis by recompressing the image at a known JPEG
    quality and measuring pixel-level differences from the original.

    Produces a visualisation (base64-encoded PNG) where brighter regions
    indicate larger differences after recompression.

    If the source image is not JPEG, a strong caveat is added because the
    format conversion itself introduces compression artefacts.
    """
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return ElaResult(
            performed=False,
            reason_skipped="Pillow is not installed.",
            limitation_note=_ELA_LIMITATION,
        )

    source_format = image.format  # may be None if loaded from bytes

    try:
        rgb = image.convert("RGB")

        # Re-save at reduced quality
        recomp_buf = io.BytesIO()
        rgb.save(recomp_buf, format="JPEG", quality=ELA_QUALITY)
        recomp_buf.seek(0)
        recomp = Image.open(recomp_buf)
        recomp.load()

        # Pixel-level absolute difference
        diff = ImageChops.difference(rgb, recomp)
        extrema = diff.getextrema()
        max_diff = max(ch[1] for ch in extrema) if extrema else 0
        try:
            import numpy as _np
            _d = _np.asarray(diff, dtype=_np.float32).max(axis=2)
            mean_diff = float(_d.mean())
            hot_fraction = float((_d >= 20).mean())
        except Exception:
            mean_diff, hot_fraction = 0.0, 0.0

        observations: list = []

        # Format caveat for non-JPEG
        if source_format and source_format != "JPEG":
            observations.append(
                f"Source format is {source_format} (lossless or different codec). "
                "ELA was performed after converting to JPEG, so the output includes "
                "format-conversion artefacts. Interpret these results with extra caution."
            )

        ela_b64: Optional[str] = None

        if max_diff == 0:
            observations.append(
                "No measurable difference after recompression. "
                "The image may already be heavily compressed or contain very uniform regions."
            )
        else:
            # Amplify for human visibility
            ela_display = diff.point(lambda px: min(px * ELA_SCALE, 255))
            ela_buf = io.BytesIO()
            ela_display.save(ela_buf, format="PNG")
            ela_b64 = "data:image/png;base64," + base64.b64encode(
                ela_buf.getvalue()
            ).decode("utf-8")

            if max_diff < 8:
                observations.append(
                    "Low ELA variance (max pixel diff: %d). "
                    "The image appears uniformly compressed. "
                    "This is typical of heavily compressed or low-detail images." % max_diff
                )
            elif max_diff < 25:
                observations.append(
                    "Moderate ELA variance (max pixel diff: %d). "
                    "Some areas recompressed differently, which is common in "
                    "images containing text, graphics, or mixed content types." % max_diff
                )
            else:
                observations.append(
                    "High ELA variance (max pixel diff: %d). "
                    "Significant areas recompressed differently from others. "
                    "This CAN indicate compositing or heavy editing, but also "
                    "occurs naturally in images with varied content, multiple "
                    "compression cycles, or different source regions." % max_diff
                )

        observations.append(_ELA_LIMITATION)

        return ElaResult(
            performed=True,
            observations=observations,
            ela_image=ela_b64,
            limitation_note=_ELA_LIMITATION,
            max_diff=int(max_diff),
            mean_diff=round(mean_diff, 3),
            hot_fraction=round(hot_fraction, 5),
        )

    except Exception as exc:
        logger.error("ELA failed: %s", exc)
        return ElaResult(
            performed=False,
            reason_skipped=(
                "ELA could not be completed. An error occurred during recompression."
            ),
            limitation_note=_ELA_LIMITATION,
        )
# ---------------------------------------------------------------------------
# Phase 4: forensics risk, keyword overlay
# ---------------------------------------------------------------------------

_EDITOR_HINTS = ("photoshop", "gimp", "lightroom", "affinity", "pixlr", "canva", "snapseed", "paint.net")


def compute_forensics_risk(meta: MetadataResult, ela: ElaResult, source_format: Optional[str]) -> dict:
    """
    Heuristic 0-100 visual-integrity risk.  An indicator for triage,
    NOT proof of tampering (see the ELA limitation note).
    """
    factors, risk = [], 0.0

    if ela.performed and ela.max_diff:
        weight = 1.0 if source_format == "JPEG" else 0.5
        ela_part = 0.0
        if ela.max_diff >= 25:
            ela_part += 15
        elif ela.max_diff >= 8:
            ela_part += 5
        ela_part += min(35.0, ela.hot_fraction * 400)      # 8.75% hot pixels saturates
        ela_part *= weight
        if ela_part >= 1:
            risk += ela_part
            factors.append({
                "signal": "ELA discrepancy", "points": round(ela_part, 1),
                "detail": f"max diff {ela.max_diff}, {ela.hot_fraction * 100:.2f}% hot pixels"
                          + ("" if weight == 1.0 else " (halved: non-JPEG source)"),
            })
    elif not ela.performed:
        factors.append({"signal": "ELA not performed", "points": 0, "detail": ela.reason_skipped or ""})

    sw = (meta.exif_fields.get("Software") or "").lower()
    if any(h in sw for h in _EDITOR_HINTS):
        risk += 15
        factors.append({"signal": "Editing software in EXIF", "points": 15,
                        "detail": meta.exif_fields["Software"]})
    dt, dto = meta.exif_fields.get("DateTime"), meta.exif_fields.get("DateTimeOriginal")
    if dt and dto and dt != dto:
        risk += 12
        factors.append({"signal": "Modified after capture", "points": 12,
                        "detail": f"DateTime {dt} differs from DateTimeOriginal {dto}"})
    if not meta.exif_available:
        risk += 5
        factors.append({"signal": "No EXIF metadata", "points": 5,
                        "detail": "Weak signal: common for social-media re-uploads"})
    if meta.width < 200 or meta.height < 200:
        factors.append({"signal": "Low resolution", "points": 0,
                        "detail": "Reduces reliability of ELA and OCR"})

    risk = max(0.0, min(100.0, risk))
    level = "Low" if risk < 20 else "Moderate" if risk < 45 else "Elevated"
    return {
        "risk_score": round(risk, 1), "level": level, "factors": factors,
        "disclaimer": "Heuristic indicator only; not proof of manipulation or authenticity.",
    }


def build_keyword_overlays(words: list, matched_terms: dict) -> list:
    """Map analyzer-detected keywords/phrases onto OCR word boxes (normalised 0-1 coordinates)."""
    import re as _re

    def norm(w):
        return _re.sub(r"[^a-z0-9'-]", "", w.lower())

    singles = {}
    for cat, key in (("keyword", "keywords"), ("synonym", "wordnet")):
        for t in matched_terms.get(key, []):
            singles[t.lower()] = cat
    overlays, used = [], set()
    norms = [norm(w["text"]) for w in words]

    for phrase in matched_terms.get("clickbait", []):
        toks = [norm(t) for t in phrase.split()]
        n = len(toks)
        for i in range(len(words) - n + 1):
            if norms[i:i + n] == toks and not used.intersection(range(i, i + n)):
                seg = words[i:i + n]
                x0 = min(w["x"] for w in seg)
                y0 = min(w["y"] for w in seg)
                x1 = max(w["x"] + w["w"] for w in seg)
                y1 = max(w["y"] + w["h"] for w in seg)
                overlays.append({"text": phrase, "category": "clickbait",
                                 "x": round(x0, 5), "y": round(y0, 5),
                                 "w": round(x1 - x0, 5), "h": round(y1 - y0, 5)})
                used.update(range(i, i + n))
    for i, w in enumerate(words):
        if i in used:
            continue
        cat = singles.get(norms[i])
        if cat:
            overlays.append({"text": w["text"], "category": cat,
                             "x": w["x"], "y": w["y"], "w": w["w"], "h": w["h"]})
    return overlays




# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def analyze_image(file_bytes: bytes, filename: str, verify_web: bool = True) -> dict:
    """
    Full image analysis pipeline.

    Steps:
      1. Validate and decode
      2. OCR text extraction
      3. Text analysis of OCR output (only when OCR succeeds)
      4. Metadata inspection
      5. ELA

    Returns a structured dict suitable for JSON serialisation.
    Never raises -- all failures are encoded in the returned dict.
    """
    # Step 1: Validate + decode
    image, decode_error = validate_and_decode_image(file_bytes, filename)
    if decode_error:
        return {
            "status": "error",
            "error": decode_error,
            "file_name": filename,
            "ocr": None,
            "text_analysis": None,
            "metadata": None,
            "ela": None,
            "forensics": None,
            "keyword_overlays": [],
            "ml": None,
            "fusion": None,
            "web": None,
            "dual_verdict": None,
        }

    # Step 2: OCR
    ocr = extract_ocr_text(image)

    # Step 3: Text analysis (only when readable text exists)
    text_analysis: Optional[dict] = None
    if ocr.status == "success" and ocr.text:
        try:
            from analyzer import analyze_text
            text_analysis = analyze_text(ocr.text)
        except Exception as exc:
            logger.error("Text analysis of OCR output failed: %s", exc)
            text_analysis = {"error": "Text analysis could not be completed for OCR output."}

    # Step 4: Metadata
    meta = extract_metadata(image, file_bytes, filename)

    # Step 5: ELA
    ela = perform_ela(image)

    forensics = compute_forensics_risk(meta, ela, image.format)

    overlays, ml, fusion, web = [], None, None, None
    ta_ok = bool(text_analysis) and "error" not in text_analysis
    if ta_ok:
        overlays = build_keyword_overlays(ocr.words, text_analysis.get("matched_terms", {}))
        try:
            import fusion as _fusion
            import ml_service
            ml = ml_service.predict(ocr.text)
            if verify_web:
                import web_search_service
                web = web_search_service.verify_web(ocr.text)
            fusion = _fusion.fuse(text_analysis, ml, forensics_risk=forensics["risk_score"], web=web)
        except Exception as exc:
            logger.error("ML/fusion step failed: %s", exc)

    dual_verdict = {
        "visual_integrity": {
            "risk_score": forensics["risk_score"],
            "level": forensics["level"],
            "summary": f"{forensics['level']} visual-integrity risk ({forensics['risk_score']}/100)",
        },
        "content_credibility": (
            {
                "trust_score": fusion["final_score"],
                "band": fusion["band"],
                "rule_classification": text_analysis["classification"],
                "summary": (f"{fusion['band']} ({fusion['final_score']}/100); "
                            f"{text_analysis['classification']} by rules"),
            }
            if fusion else None
        ),
    }

    return {
        "status": "ok",
        "error": None,
        "file_name": filename,
        "ocr": {
            "status": ocr.status,
            "text": ocr.text,
            "character_count": ocr.character_count,
            "warning": ocr.warning,
            "mean_confidence": ocr.mean_confidence,
            "words": ocr.words,
            "preprocessing": ocr.preprocessing,
        },
        "text_analysis": text_analysis,
        "metadata": {
            "format": meta.format,
            "width": meta.width,
            "height": meta.height,
            "file_size_bytes": meta.file_size_bytes,
            "mode": meta.mode,
            "exif_available": meta.exif_available,
            "exif_fields": meta.exif_fields,
            "observations": meta.observations,
        },
        "ela": {
            "performed": ela.performed,
            "reason_skipped": ela.reason_skipped,
            "observations": ela.observations,
            "ela_image": ela.ela_image,
            "limitation_note": ela.limitation_note,
            "max_diff": ela.max_diff,
            "mean_diff": ela.mean_diff,
            "hot_fraction": ela.hot_fraction,
        },
        "forensics": forensics,
        "keyword_overlays": overlays,
        "ml": ml,
        "web": web,
        "fusion": fusion,
        "dual_verdict": dual_verdict,
    }
