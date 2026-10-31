"""
Phase 4 API + image-pipeline tests.

Legacy payload compatibility is asserted explicitly; new fields are additive.
Tesseract is mocked (word-level data) so tests are deterministic without the binary.
"""

import io

import pytest
from PIL import Image
from starlette.testclient import TestClient

import image_analyzer as ia
from main import app

SHOCK = "SHOCKING secret hoax EXPOSED!!! You won't believe this miracle. Share now!!!"
SOBER = ("The central bank held interest rates steady on Wednesday, officials said "
         "in a statement released after the meeting.")


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def _png(size=(300, 200), color=(240, 240, 240)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------
# /analyze
# --------------------------------------------------------------------------

class TestAnalyzePhase4:
    LEGACY = {"message", "text_length", "score", "classification", "indicators", "word_count"}

    def test_legacy_fields_unchanged(self, client):
        r = client.post("/analyze", json={"text": SHOCK}).json()
        assert self.LEGACY <= set(r)
        assert isinstance(r["score"], int) and r["classification"] in {"Credible", "Suspicious", "Likely Fake"}

    def test_new_fields_present(self, client):
        r = client.post("/analyze", json={"text": SHOCK}).json()
        assert r["ml"]["available"] and 0 <= r["ml"]["ml_score"] <= 100
        assert r["ml"]["attributions"]["supports_unreliable"]
        f = r["fusion"]
        assert 0 <= f["final_score"] <= 100 and f["band"] and f["formula"]
        assert set(f["axes"]) == {"sensationalism", "clickbait", "emotional_manipulation",
                                  "source_risk", "ml_risk", "forensic_risk", "corroboration_risk"}
        assert r["fact_check"]["mode"] == "offline"

    def test_suspicious_text_trusted_less_than_sober(self, client):
        bad = client.post("/analyze", json={"text": SHOCK}).json()["fusion"]["final_score"]
        good = client.post("/analyze", json={"text": SOBER}).json()["fusion"]["final_score"]
        assert bad < good

    def test_url_adds_domain_and_penalty(self, client):
        r = client.post("/analyze", json={"text": SOBER, "url": "https://infowars.com/x"}).json()
        assert r["domain"]["known"] and r["fusion"]["penalties"]["low_trust_source"] > 0

    def test_debunked_claim_penalised(self, client):
        r = client.post("/analyze", json={"text": "Officials say 5G towers spread the coronavirus."}).json()
        assert r["fact_check"]["overall"] == "contradicted"
        assert r["fusion"]["penalties"]["claim_contradicted"] > 0

    def test_empty_text_still_200(self, client):
        r = client.post("/analyze", json={"text": ""})
        assert r.status_code == 200 and r.json()["ml"]["available"] is False

    def test_missing_text_422(self, client):
        assert client.post("/analyze", json={}).status_code == 422


# --------------------------------------------------------------------------
# /verify-claim, /model-info, rules
# --------------------------------------------------------------------------

class TestNewEndpoints:
    def test_verify_claim_text(self, client):
        r = client.post("/verify-claim", json={"text": "The moon landing was faked by NASA."})
        assert r.status_code == 200
        j = r.json()
        assert j["mode"] == "offline" and j["fact_check"]["overall"] == "contradicted"

    def test_verify_claim_url_only_offline(self, client):
        j = client.post("/verify-claim", json={"url": "https://www.reuters.com/a"}).json()
        assert j["domain"]["known"] and j["page"] is None

    def test_verify_claim_requires_input(self, client):
        assert client.post("/verify-claim", json={}).status_code == 422
        assert client.post("/verify-claim", json={"text": "  ", "url": ""}).status_code == 422

    def test_verify_blocks_private_url_when_online(self, client, monkeypatch):
        monkeypatch.setenv("FAKEGUARD_ONLINE", "1")
        j = client.post("/verify-claim", json={"url": "http://169.254.169.254/"}).json()
        assert "blocked" in j["page"]["error"]

    def test_model_info(self, client):
        j = client.get("/model-info").json()
        assert j["available"] and j["fusion"]["w_rules"] == 0.6 and j["verification_mode"] == "offline"

    def test_keywords_rules_and_metadata_endpoint_still_hides_lists(self, client):
        assert "words" not in client.get("/keywords").json()
        rules = client.get("/keywords/rules").json()
        assert "hoax" in rules["suspicious_keywords"] and rules["text_patterns"]["caps_points"] > 0

    def test_reload(self, client):
        a = client.post("/keywords/reload").json()
        b = client.post("/keywords/reload").json()
        assert a["version"] == b["version"] and b["changed"] is False

    @pytest.mark.parametrize("path", ["/", "/health", "/keywords"])
    def test_legacy_get_endpoints(self, client, path):
        assert client.get(path).status_code == 200


# --------------------------------------------------------------------------
# Image pipeline
# --------------------------------------------------------------------------

class TestPreprocess:
    def test_output_is_binary_grayscale_and_upscaled(self):
        img = Image.new("RGB", (300, 100), (200, 200, 200))
        out, steps, scale = ia.preprocess_for_ocr(img)
        assert out.mode == "L" and scale > 1 and out.width > 300
        assert set(out.getdata()) <= {0, 255}
        assert "adaptive threshold" in steps and "grayscale" in steps

    def test_large_image_not_upscaled(self):
        _, steps, scale = ia.preprocess_for_ocr(Image.new("RGB", (1600, 900), (255, 255, 255)))
        assert scale == 1.0 and not any(s.startswith("upscale") for s in steps)


class TestOverlays:
    WORDS = [
        {"text": "SHOCKING", "conf": 90, "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05},
        {"text": "news,", "conf": 90, "x": 0.31, "y": 0.1, "w": 0.1, "h": 0.05},
        {"text": "you", "conf": 90, "x": 0.1, "y": 0.2, "w": 0.05, "h": 0.05},
        {"text": "won't", "conf": 90, "x": 0.16, "y": 0.2, "w": 0.08, "h": 0.05},
        {"text": "believe", "conf": 90, "x": 0.25, "y": 0.2, "w": 0.1, "h": 0.05},
    ]

    def test_keyword_and_phrase_boxes(self):
        o = ia.build_keyword_overlays(self.WORDS, {"keywords": ["shocking"], "wordnet": [],
                                                   "clickbait": ["you won't believe"]})
        by = {x["category"]: x for x in o}
        assert by["keyword"]["text"] == "SHOCKING" and by["keyword"]["x"] == 0.1
        c = by["clickbait"]
        assert c["x"] == 0.1 and c["w"] == pytest.approx(0.25, abs=1e-4) and c["y"] == 0.2

    def test_no_matches(self):
        assert ia.build_keyword_overlays(self.WORDS, {}) == []

    def test_phrase_words_not_double_counted(self):
        o = ia.build_keyword_overlays(self.WORDS, {"keywords": ["believe"], "clickbait": ["you won't believe"]})
        assert [x["category"] for x in o] == ["clickbait"]


class TestForensicsRisk:
    def _meta(self, **kw):
        base = dict(format="JPEG", width=800, height=600, file_size_bytes=1000, mode="RGB",
                    exif_available=True, exif_fields={}, observations=[])
        base.update(kw)
        return ia.MetadataResult(**base)

    def test_clean_jpeg_low(self):
        r = ia.compute_forensics_risk(self._meta(), ia.ElaResult(performed=True), "JPEG")
        assert r["risk_score"] == 0 and r["level"] == "Low"

    def test_editor_and_modified_timestamp_raise_risk(self):
        m = self._meta(exif_fields={"Software": "Adobe Photoshop 25", "DateTime": "2024:01:02 10:00:00",
                                    "DateTimeOriginal": "2023:12:01 09:00:00"})
        r = ia.compute_forensics_risk(m, ia.ElaResult(performed=True), "JPEG")
        assert r["risk_score"] == 27 and r["level"] == "Moderate"

    def test_ela_hot_regions_raise_risk_and_png_is_discounted(self):
        ela = ia.ElaResult(performed=True, max_diff=60, hot_fraction=0.05)
        jpeg = ia.compute_forensics_risk(self._meta(), ela, "JPEG")["risk_score"]
        png = ia.compute_forensics_risk(self._meta(), ela, "PNG")["risk_score"]
        assert jpeg == 35 and png == 17.5

    def test_no_exif_is_weak_signal_only(self):
        r = ia.compute_forensics_risk(self._meta(exif_available=False), ia.ElaResult(performed=True), "PNG")
        assert r["risk_score"] == 5 and r["level"] == "Low"

    def test_capped_at_100(self):
        ela = ia.ElaResult(performed=True, max_diff=255, hot_fraction=1.0)
        m = self._meta(exif_fields={"Software": "GIMP", "DateTime": "a", "DateTimeOriginal": "b"})
        assert ia.compute_forensics_risk(m, ela, "JPEG")["risk_score"] <= 100


class TestAnalyzeImageEndpoint:
    @staticmethod
    def _mock_tesseract(monkeypatch, words):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.0")
        monkeypatch.setattr(pytesseract, "image_to_string", lambda img, config="": " ".join(w[0] for w in words))

        def data(img, config="", output_type=None):
            W, H = img.size
            return {
                "text": [w[0] for w in words], "conf": [91] * len(words),
                "left": [int(w[1] * W) for w in words], "top": [int(0.1 * H)] * len(words),
                "width": [int(0.1 * W)] * len(words), "height": [int(0.05 * H)] * len(words),
            }
        monkeypatch.setattr(pytesseract, "image_to_data", data)

    def test_dual_verdict_overlays_and_legacy_keys(self, client, monkeypatch):
        self._mock_tesseract(monkeypatch, [("SHOCKING", 0.1), ("secret", 0.3), ("report", 0.5)])
        r = client.post("/analyze-image", files={"file": ("a.png", _png(), "image/png")}).json()
        assert {"status", "error", "file_name", "ocr", "text_analysis", "metadata", "ela"} <= set(r)
        assert r["ocr"]["mean_confidence"] == 91 and len(r["ocr"]["words"]) == 3
        assert {o["text"] for o in r["keyword_overlays"]} == {"SHOCKING", "secret"}
        for o in r["keyword_overlays"]:
            assert 0 <= o["x"] <= 1 and 0 <= o["y"] <= 1
        dv = r["dual_verdict"]
        assert dv["visual_integrity"]["level"] in {"Low", "Moderate", "Elevated"}
        assert dv["content_credibility"]["trust_score"] == r["fusion"]["final_score"]
        assert r["fusion"]["penalties"]["forensics"] == pytest.approx(0.25 * r["forensics"]["risk_score"], abs=0.01)

    def test_ocr_unavailable_still_has_visual_verdict(self, client, monkeypatch):
        import pytesseract

        def nope():
            raise RuntimeError("missing")
        monkeypatch.setattr(pytesseract, "get_tesseract_version", nope)
        r = client.post("/analyze-image", files={"file": ("a.png", _png(), "image/png")}).json()
        assert r["status"] == "ok" and r["ocr"]["status"] == "ocr_unavailable"
        assert r["dual_verdict"]["content_credibility"] is None
        assert r["dual_verdict"]["visual_integrity"]["risk_score"] >= 0 and r["keyword_overlays"] == []

    def test_invalid_file_error_shape_has_new_keys(self, client):
        r = client.post("/analyze-image", files={"file": ("a.png", b"junk", "image/png")}).json()
        assert r["status"] == "error" and r["dual_verdict"] is None and r["keyword_overlays"] == []

    def test_ela_numeric_stats_exposed(self, client, monkeypatch):
        self._mock_tesseract(monkeypatch, [("hello", 0.1)])
        r = client.post("/analyze-image", files={"file": ("a.png", _png(), "image/png")}).json()
        assert {"max_diff", "mean_diff", "hot_fraction"} <= set(r["ela"])
