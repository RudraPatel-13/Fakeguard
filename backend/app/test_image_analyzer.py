"""
FakeGuard -- Image Analyzer Tests
===================================
Covers all requirements from Module 7:
  1. OCR extraction from image with known text (mocked Tesseract).
  2. Image with no readable text.
  3. OCR executable unavailable.
  4. Invalid image files (not an image, corrupt bytes).
  5. Oversized uploads.
  6. Metadata: EXIF present and absent.
  7. ELA for JPEG and PNG.
  8. OCR output passed to existing analyzer.
  9. Existing text analysis behavior preserved.
 10. API response structure and error handling.
 11. Frontend-compatible field names.

Test strategy:
  - Synthetic images built with Pillow so tests work without real images.
  - pytesseract is mocked in all unit tests so Tesseract exe is not required.
  - At least one integration test uses the real Tesseract pipeline (skipped
    if Tesseract is not installed).
  - API tests use Starlette TestClient (no live server needed).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Synthetic image helpers
# ---------------------------------------------------------------------------

def _make_png(size=(200, 100), text: str = "", mode: str = "RGB") -> bytes:
    """Create a minimal synthetic PNG."""
    from PIL import Image, ImageDraw

    img = Image.new(mode, size, color=(255, 255, 255))
    if text:
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg(size=(200, 100)) -> bytes:
    """Create a minimal synthetic JPEG."""
    from PIL import Image

    img = Image.new("RGB", size, color=(200, 180, 160))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_webp(size=(100, 100)) -> bytes:
    from PIL import Image

    img = Image.new("RGB", size, color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


# ===========================================================================
# 4 & 5. Validation
# ===========================================================================

class TestValidation:

    def test_empty_bytes_rejected(self):
        from image_analyzer import validate_and_decode_image
        img, err = validate_and_decode_image(b"", "test.png")
        assert img is None
        assert err is not None
        assert "empty" in err.lower()

    def test_oversized_file_rejected(self):
        from image_analyzer import validate_and_decode_image, MAX_IMAGE_SIZE_BYTES
        big = b"x" * (MAX_IMAGE_SIZE_BYTES + 1)
        img, err = validate_and_decode_image(big, "big.jpg")
        assert img is None
        assert err is not None
        assert "maximum" in err.lower() or "size" in err.lower() or "MB" in err

    def test_non_image_bytes_rejected(self):
        from image_analyzer import validate_and_decode_image
        img, err = validate_and_decode_image(b"not an image at all!!!", "test.jpg")
        assert img is None
        assert err is not None

    def test_corrupt_truncated_image_rejected(self):
        from image_analyzer import validate_and_decode_image
        corrupt = _make_jpeg()[:50]          # truncate to 50 bytes
        img, err = validate_and_decode_image(corrupt, "corrupt.jpg")
        assert img is None
        assert err is not None

    def test_valid_png_accepted(self):
        from image_analyzer import validate_and_decode_image
        img, err = validate_and_decode_image(_make_png(), "test.png")
        assert img is not None
        assert err is None

    def test_valid_jpeg_accepted(self):
        from image_analyzer import validate_and_decode_image
        img, err = validate_and_decode_image(_make_jpeg(), "test.jpg")
        assert img is not None
        assert err is None

    def test_valid_webp_accepted(self):
        from image_analyzer import validate_and_decode_image
        img, err = validate_and_decode_image(_make_webp(), "test.webp")
        assert img is not None
        assert err is None

    def test_filename_not_trusted_for_format_detection(self):
        """A PNG file renamed to .jpg must still be accepted (format from bytes)."""
        from image_analyzer import validate_and_decode_image
        img, err = validate_and_decode_image(_make_png(), "renamed.jpg")
        assert img is not None
        assert err is None


# ===========================================================================
# 3. OCR unavailable
# ===========================================================================

class TestOcrUnavailable:

    def test_unavailable_returns_correct_status(self, monkeypatch):
        import pytesseract
        from image_analyzer import extract_ocr_text
        from PIL import Image

        monkeypatch.setattr(
            pytesseract, "get_tesseract_version",
            lambda: (_ for _ in ()).throw(Exception("tesseract not found")),
        )
        img = Image.open(io.BytesIO(_make_png()))
        result = extract_ocr_text(img)
        assert result.status == "ocr_unavailable"
        assert result.text == ""
        assert result.character_count == 0
        assert result.warning is not None
        assert "Tesseract" in result.warning or "tesseract" in result.warning.lower()

    def test_unavailable_text_analysis_is_none(self, monkeypatch):
        """When OCR is unavailable, the full pipeline should not produce text analysis."""
        import pytesseract
        from image_analyzer import analyze_image

        monkeypatch.setattr(
            pytesseract, "get_tesseract_version",
            lambda: (_ for _ in ()).throw(Exception("not found")),
        )
        result = analyze_image(_make_png(), "test.png")
        assert result["status"] == "ok"
        assert result["ocr"]["status"] == "ocr_unavailable"
        assert result["text_analysis"] is None


# ===========================================================================
# 1. OCR extraction with known text
# ===========================================================================

class TestOcrExtraction:

    def test_success_returns_text(self, monkeypatch):
        import pytesseract
        from image_analyzer import extract_ocr_text
        from PIL import Image

        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "FAKE NEWS ALERT",
        )
        img = Image.open(io.BytesIO(_make_png()))
        result = extract_ocr_text(img)
        assert result.status == "success"
        assert result.text == "FAKE NEWS ALERT"
        assert result.character_count == len("FAKE NEWS ALERT")

    def test_success_includes_warning_about_ocr_errors(self, monkeypatch):
        import pytesseract
        from image_analyzer import extract_ocr_text
        from PIL import Image

        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "some text",
        )
        img = Image.open(io.BytesIO(_make_png()))
        result = extract_ocr_text(img)
        assert result.warning is not None
        # Must warn about possible OCR errors
        assert any(kw in result.warning.lower() for kw in ("error", "accurate", "carefully", "may"))

    def test_ocr_does_not_invent_text(self, monkeypatch):
        """OCR returns exactly what pytesseract reports, no additions."""
        import pytesseract
        from image_analyzer import extract_ocr_text
        from PIL import Image

        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "exactly this",
        )
        img = Image.open(io.BytesIO(_make_png()))
        result = extract_ocr_text(img)
        assert result.text == "exactly this"


# ===========================================================================
# 2. Image with no readable text
# ===========================================================================

class TestOcrNoText:

    def test_blank_image_returns_no_text(self, monkeypatch):
        import pytesseract
        from image_analyzer import extract_ocr_text
        from PIL import Image

        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "   \n\n  \t  ",   # whitespace only
        )
        img = Image.open(io.BytesIO(_make_png()))
        result = extract_ocr_text(img)
        assert result.status == "no_text"
        assert result.text == ""
        assert result.character_count == 0

    def test_no_text_pipeline_has_no_text_analysis(self, monkeypatch):
        import pytesseract
        from image_analyzer import analyze_image

        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "",
        )
        result = analyze_image(_make_png(), "blank.png")
        assert result["ocr"]["status"] == "no_text"
        assert result["text_analysis"] is None

    def test_ocr_error_does_not_crash_pipeline(self, monkeypatch):
        import pytesseract
        from image_analyzer import analyze_image

        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": (_ for _ in ()).throw(RuntimeError("crash")),
        )
        result = analyze_image(_make_png(), "error.png")
        assert result["status"] == "ok"
        assert result["ocr"]["status"] == "error"
        assert result["text_analysis"] is None


# ===========================================================================
# 8. OCR output passed to existing analyzer
# ===========================================================================

class TestOcrTextAnalysis:

    def test_suspicious_ocr_text_produces_positive_score(self, monkeypatch):
        import pytesseract
        from image_analyzer import analyze_image

        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "fake hoax scam",
        )
        result = analyze_image(_make_png(), "test.png")
        assert result["status"] == "ok"
        assert result["text_analysis"] is not None
        assert result["text_analysis"]["score"] > 0

    def test_text_analysis_contains_expected_fields(self, monkeypatch):
        import pytesseract
        from image_analyzer import analyze_image

        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "credible news report",
        )
        result = analyze_image(_make_png(), "test.png")
        ta = result["text_analysis"]
        assert ta is not None
        for field in ("score", "classification", "indicators", "word_count"):
            assert field in ta, f"Missing field in text_analysis: {field}"

    def test_text_score_kept_separate_from_image_findings(self, monkeypatch):
        """text_analysis and metadata/ela are at separate keys."""
        import pytesseract
        from image_analyzer import analyze_image

        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "fake hoax",
        )
        result = analyze_image(_make_png(), "test.png")
        assert "text_analysis" in result
        assert "metadata" in result
        assert "ela" in result
        # text_analysis must not be embedded inside metadata or ela
        assert "score" not in result["metadata"]
        assert "score" not in result["ela"]


# ===========================================================================
# 9. Existing text analysis behavior preserved
# ===========================================================================

class TestExistingAnalyzerUnchanged:

    @pytest.fixture
    def client(self):
        from starlette.testclient import TestClient
        from main import app
        return TestClient(app)

    def test_existing_analyze_endpoint_unchanged(self, client):
        r = client.post("/analyze", json={"text": "fake hoax scam"})
        assert r.status_code == 200
        data = r.json()
        for f in ("score", "classification", "indicators", "word_count"):
            assert f in data

    def test_health_endpoint_unchanged(self, client):
        assert client.get("/health").json() == {"status": "healthy"}

    def test_root_endpoint_unchanged(self, client):
        data = client.get("/").json()
        assert "message" in data and "status" in data


# ===========================================================================
# 6. Metadata
# ===========================================================================

class TestMetadata:

    def test_png_format_detected_correctly(self):
        from PIL import Image
        from image_analyzer import extract_metadata

        png_bytes = _make_png(size=(300, 150))
        img = Image.open(io.BytesIO(png_bytes))
        meta = extract_metadata(img, png_bytes, "test.png")
        assert meta.format == "PNG"
        assert meta.width == 300
        assert meta.height == 150
        assert meta.file_size_bytes == len(png_bytes)

    def test_jpeg_format_detected_correctly(self):
        from PIL import Image
        from image_analyzer import extract_metadata

        jpg_bytes = _make_jpeg(size=(400, 200))
        img = Image.open(io.BytesIO(jpg_bytes))
        meta = extract_metadata(img, jpg_bytes, "test.jpg")
        assert meta.format == "JPEG"
        assert meta.width == 400
        assert meta.height == 200

    def test_no_exif_observation_present_when_absent(self):
        from PIL import Image
        from image_analyzer import extract_metadata

        png_bytes = _make_png()                    # PNG has no EXIF
        img = Image.open(io.BytesIO(png_bytes))
        meta = extract_metadata(img, png_bytes, "test.png")
        assert not meta.exif_available
        # Should document that missing EXIF is normal
        obs_text = " ".join(meta.observations).lower()
        assert any(kw in obs_text for kw in ("exif", "metadata", "normal", "common", "stripped"))

    def test_small_image_observation(self):
        from PIL import Image
        from image_analyzer import extract_metadata

        tiny_bytes = _make_png(size=(50, 40))
        img = Image.open(io.BytesIO(tiny_bytes))
        meta = extract_metadata(img, tiny_bytes, "tiny.png")
        obs_text = " ".join(meta.observations).lower()
        # Should note small dimensions
        assert "50" in obs_text or "small" in obs_text or "low" in obs_text

    def test_metadata_observations_are_observations_not_conclusions(self):
        """No observation should claim an image is 'fake' or 'manipulated'."""
        from PIL import Image
        from image_analyzer import extract_metadata

        png_bytes = _make_png()
        img = Image.open(io.BytesIO(png_bytes))
        meta = extract_metadata(img, png_bytes, "test.png")
        forbidden = ["fake", "manipulated", "forged", "tampered", "fabricated"]
        obs_text = " ".join(meta.observations).lower()
        for word in forbidden:
            assert word not in obs_text, (
                f"Observation must not conclude manipulation; found {word!r} in: {obs_text}"
            )

    def test_exif_values_not_trusted_as_instructions(self):
        """EXIF fields are stored as plain strings, not evaluated."""
        from image_analyzer import extract_metadata
        from PIL import Image

        # Inject a "Software" field with a suspicious string via a mocked EXIF
        jpeg_bytes = _make_jpeg()
        img = Image.open(io.BytesIO(jpeg_bytes))

        # Monkeypatch _getexif to return a controlled dict
        exif_payload = {306: "2024:01:01 12:00:00", 305: "os.system('rm -rf /')"}
        img._getexif = lambda: exif_payload

        meta = extract_metadata(img, jpeg_bytes, "test.jpg")
        # The value must appear as a plain string in exif_fields
        sw = meta.exif_fields.get("Software", "")
        assert "os.system" in sw or sw == ""      # stored verbatim, not executed
        assert meta.exif_available is True


# ===========================================================================
# 7. ELA
# ===========================================================================

class TestEla:

    def test_ela_performed_on_png(self):
        from PIL import Image
        from image_analyzer import perform_ela

        img = Image.open(io.BytesIO(_make_png(size=(100, 100))))
        result = perform_ela(img)
        assert result.performed is True

    def test_ela_performed_on_jpeg(self):
        from PIL import Image
        from image_analyzer import perform_ela

        img = Image.open(io.BytesIO(_make_jpeg(size=(100, 100))))
        result = perform_ela(img)
        assert result.performed is True

    def test_ela_limitation_note_always_present(self):
        from PIL import Image
        from image_analyzer import perform_ela

        for fmt_bytes in [_make_png(), _make_jpeg()]:
            img = Image.open(io.BytesIO(fmt_bytes))
            result = perform_ela(img)
            assert result.limitation_note, "limitation_note must always be non-empty"

    def test_ela_observations_not_conclusions(self):
        """ELA observations must not claim 'proven tampering'."""
        from PIL import Image
        from image_analyzer import perform_ela

        img = Image.open(io.BytesIO(_make_jpeg()))
        result = perform_ela(img)
        obs_text = " ".join(result.observations).lower()
        assert "proves" not in obs_text
        assert "proven" not in obs_text

    def test_ela_image_is_base64_or_none(self):
        from PIL import Image
        from image_analyzer import perform_ela

        img = Image.open(io.BytesIO(_make_jpeg(size=(100, 100))))
        result = perform_ela(img)
        if result.ela_image is not None:
            assert result.ela_image.startswith("data:image/png;base64,"), (
                f"ela_image must be a data URI, got: {result.ela_image[:40]!r}"
            )

    def test_ela_on_uniform_image_handles_zero_diff(self):
        """A completely uniform JPEG may produce max_diff=0 without crashing."""
        from PIL import Image
        from image_analyzer import perform_ela

        # Solid red JPEG — very uniform, may produce near-zero ELA diff
        img = Image.new("RGB", (100, 100), color=(200, 50, 50))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)
        img2 = Image.open(buf)
        result = perform_ela(img2)
        assert result.performed is True        # should not crash

    def test_png_source_format_caveat_mentioned(self):
        """When ELA source is PNG, a caveat about format conversion must appear."""
        from PIL import Image
        from image_analyzer import perform_ela

        img = Image.open(io.BytesIO(_make_png()))
        result = perform_ela(img)
        obs_text = " ".join(result.observations).lower()
        assert any(kw in obs_text for kw in ("png", "lossless", "format", "caution"))


# ===========================================================================
# 10 & 11. API response structure and frontend compatibility
# ===========================================================================

class TestApiEndpoint:

    @pytest.fixture
    def client(self):
        from starlette.testclient import TestClient
        from main import app
        return TestClient(app)

    def _png_upload(self, client, extra_monkeypatch=None, text=""):
        import pytesseract
        if extra_monkeypatch:
            extra_monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
            extra_monkeypatch.setattr(
                pytesseract, "image_to_string",
                lambda img, config="": text,
            )
        return client.post(
            "/analyze-image",
            files={"file": ("test.png", _make_png(), "image/png")},
        )

    def test_valid_image_returns_200(self, client, monkeypatch):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(pytesseract, "image_to_string", lambda img, config="": "")
        r = self._png_upload(client)
        assert r.status_code == 200

    def test_response_has_required_top_level_fields(self, client, monkeypatch):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(pytesseract, "image_to_string", lambda img, config="": "")
        r = self._png_upload(client)
        data = r.json()
        for f in ("status", "error", "file_name", "ocr", "text_analysis", "metadata", "ela"):
            assert f in data, f"Missing top-level field: {f}"

    def test_ocr_block_has_required_fields(self, client, monkeypatch):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(pytesseract, "image_to_string", lambda img, config="": "")
        r = self._png_upload(client)
        ocr = r.json()["ocr"]
        for f in ("status", "text", "character_count", "warning"):
            assert f in ocr, f"Missing ocr field: {f}"

    def test_metadata_block_has_required_fields(self, client, monkeypatch):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(pytesseract, "image_to_string", lambda img, config="": "")
        r = self._png_upload(client)
        meta = r.json()["metadata"]
        for f in ("format", "width", "height", "file_size_bytes", "exif_available", "observations"):
            assert f in meta, f"Missing metadata field: {f}"

    def test_ela_block_has_required_fields(self, client, monkeypatch):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(pytesseract, "image_to_string", lambda img, config="": "")
        r = self._png_upload(client)
        ela = r.json()["ela"]
        for f in ("performed", "observations", "limitation_note"):
            assert f in ela, f"Missing ela field: {f}"

    def test_invalid_file_returns_200_with_error_status(self, client):
        """Non-image data returns HTTP 200 but status='error' in body."""
        r = client.post(
            "/analyze-image",
            files={"file": ("garbage.jpg", b"not an image", "image/jpeg")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "error"
        assert data["error"] is not None

    def test_analyze_with_ocr_text_includes_text_analysis(self, client, monkeypatch):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "fake hoax scam",
        )
        r = self._png_upload(client)
        data = r.json()
        assert data["text_analysis"] is not None
        assert data["text_analysis"]["score"] > 0
        # Frontend-compatible field names
        for f in ("score", "classification", "indicators", "word_count"):
            assert f in data["text_analysis"]

    def test_text_analysis_null_when_no_ocr_text(self, client, monkeypatch):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(pytesseract, "image_to_string", lambda img, config="": "")
        r = self._png_upload(client)
        assert r.json()["text_analysis"] is None

    def test_classification_values_are_known_labels(self, client, monkeypatch):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "4.1.0")
        monkeypatch.setattr(
            pytesseract, "image_to_string",
            lambda img, config="": "fake hoax",
        )
        r = self._png_upload(client)
        ta = r.json()["text_analysis"]
        if ta:
            assert ta["classification"] in ("Credible", "Suspicious", "Likely Fake")

    def test_existing_analyze_text_endpoint_still_works(self, client):
        r = client.post("/analyze", json={"text": "fake news hoax"})
        assert r.status_code == 200
        data = r.json()
        assert data["score"] > 0
        assert "message" in data


# ===========================================================================
# Real Tesseract integration test (skipped if not installed)
# ===========================================================================

class TestRealTesseractIntegration:

    def test_real_ocr_on_text_image(self):
        """
        Use the real Tesseract pipeline on a synthesised image.
        Skipped if Tesseract is not installed.
        The test only checks structural properties, not specific OCR output,
        since recognition accuracy varies with font size and renderer.
        """
        from image_analyzer import check_tesseract_available, extract_ocr_text
        from PIL import Image

        if not check_tesseract_available():
            pytest.skip(
                "Tesseract not installed. "
                "Install from https://github.com/UB-Mannheim/tesseract/wiki to run this test."
            )

        img = Image.open(io.BytesIO(_make_png(size=(400, 100), text="HELLO WORLD")))
        result = extract_ocr_text(img)

        # Status must be either success or no_text (never an exception)
        assert result.status in ("success", "no_text")
        assert isinstance(result.text, str)
        assert isinstance(result.character_count, int)
        assert result.character_count == len(result.text)
