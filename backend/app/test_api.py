"""
HTTP API tests for FakeGuard Phase 3
======================================
Uses starlette.testclient.TestClient (backed by httpx) to test all endpoints
in-process -- no running server needed.

Coverage focus: requirements 14-18 that were not covered at the HTTP layer
by the existing pytest suites, plus regression checks on all endpoints.

  TestHealthEndpoint         -- Req 17: /health and / always work
  TestAnalyzeEndpoint        -- Req 16, 18: /analyze fields, types, frontend compatibility
  TestAnalyzeScoringViaHttp  -- Reqs 7-13: scoring correctness confirmed at HTTP boundary
  TestBrokenLibraryHttp      -- Req 15: broken library -> 503, never misleading 200
  TestHotReloadViaApi        -- Req 14: temp library change detected without server restart
  TestKeywordsEndpoint       -- /keywords structural checks

All tests use isolated temp files or monkeypatching.
The real keywords.json is never modified.
"""

import json
import os
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

# --------------------------------------------------------------------------
# Import the FastAPI app and types needed for patching / temp loaders
# --------------------------------------------------------------------------
from main import app
from keyword_loader import (
    KeywordLibraryError,
    KeywordLibraryFileError,
    KeywordLibraryParseError,
    KeywordLibraryValidationError,
    KeywordLoader,
)


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

def _minimal_lib() -> dict:
    """Smallest keyword-library dict that passes full validation."""
    return {
        "version": "test-1.0",
        "suspicious_keywords": {
            "words": ["fake", "hoax"],
            "scoring": {
                "points_per_distinct_keyword": 10,
                "max_contribution": 30,
            },
        },
        "clickbait_phrases": {
            "phrases": ["you won't believe", "shocking truth"],
            "scoring": {
                "points_per_phrase": 15,
                "max_contribution": 30,
            },
        },
        "text_pattern_rules": {
            "excessive_capitalization": {
                "uppercase_ratio_threshold": 0.50,
                "points": 10,
            },
            "excessive_exclamation_marks": {
                "min_count": 3,
                "points": 10,
            },
            "excessive_question_marks": {
                "min_count": 3,
                "points": 5,
            },
        },
        "scoring": {"max_total_score": 100},
        "classification": {
            "thresholds": [
                {"label": "Credible",    "min": 0,  "max": 30},
                {"label": "Suspicious",  "min": 31, "max": 60},
                {"label": "Likely Fake", "min": 61, "max": 100},
            ]
        },
    }


def _write_lib(path: Path, lib: dict) -> None:
    path.write_text(json.dumps(lib), encoding="utf-8")


# TestClient fixture: raise_server_exceptions=False so our custom 503
# handler fires and is returned as a response instead of being re-raised.
@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ============================================================
# Requirement 17: /health and root endpoint always work
# ============================================================

class TestHealthEndpoint:
    """Req 17: /health and / continue working at all times."""

    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_body_is_healthy(self, client):
        assert client.get("/health").json() == {"status": "healthy"}

    def test_root_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_root_has_message_field(self, client):
        r = client.get("/").json()
        assert r["message"] == "FakeGuard API is running"

    def test_root_has_status_field(self, client):
        assert client.get("/").json()["status"] == "success"

    def test_health_is_unaffected_by_library_error(self, monkeypatch):
        """Even if the keyword library is broken, /health must return 200."""
        def _broken():
            raise KeywordLibraryError("library gone")
        monkeypatch.setattr("analyzer.get_config", _broken)
        monkeypatch.setattr("main.get_config", _broken)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.get("/health").status_code == 200


# ============================================================
# Requirement 16: /analyze returns the expected fields
# Requirement 18: frontend remains compatible with backend response
# ============================================================

class TestAnalyzeEndpoint:
    """
    Req 16: /analyze HTTP response structure.
    Req 18: all field names and types consumed by the React frontend.
    """

    def test_analyze_returns_200(self, client):
        r = client.post("/analyze", json={"text": "test article"})
        assert r.status_code == 200

    def test_analyze_response_has_all_required_fields(self, client):
        """All six fields the frontend reads must be present."""
        r = client.post("/analyze", json={"text": "test"}).json()
        for field in ("message", "text_length", "score",
                      "classification", "indicators", "word_count"):
            assert field in r, f"Missing required field: {field!r}"

    def test_analyze_message_is_correct_string(self, client):
        r = client.post("/analyze", json={"text": "test"}).json()
        assert r["message"] == "Article analyzed successfully"

    def test_analyze_text_length_equals_input_length(self, client):
        text = "hello world today"
        r = client.post("/analyze", json={"text": text}).json()
        assert r["text_length"] == len(text)

    def test_analyze_score_is_int(self, client):
        r = client.post("/analyze", json={"text": "test"}).json()
        assert isinstance(r["score"], int)

    def test_analyze_classification_is_str(self, client):
        r = client.post("/analyze", json={"text": "test"}).json()
        assert isinstance(r["classification"], str)

    def test_analyze_indicators_is_list(self, client):
        r = client.post("/analyze", json={"text": "test"}).json()
        assert isinstance(r["indicators"], list)

    def test_analyze_indicators_contains_only_strings(self, client):
        r = client.post("/analyze", json={"text": "fake news"}).json()
        assert all(isinstance(s, str) for s in r["indicators"])

    def test_analyze_word_count_is_int(self, client):
        r = client.post("/analyze", json={"text": "one two three"}).json()
        assert isinstance(r["word_count"], int)

    # -- Request validation --

    def test_analyze_missing_text_field_returns_422(self, client):
        """Pydantic rejects requests with missing required field."""
        r = client.post("/analyze", json={})
        assert r.status_code == 422

    def test_analyze_non_json_body_returns_error(self, client):
        """Non-JSON Content-Type is rejected before reaching the handler."""
        r = client.post(
            "/analyze",
            content=b"plain text body",
            headers={"Content-Type": "text/plain"},
        )
        assert r.status_code in (415, 422)

    # -- Req 18: Frontend compatibility --

    def test_frontend_compat_all_field_names_present(self, client):
        """
        The React frontend reads exactly these field names from the response.
        If any name changes, the UI breaks.
        """
        r = client.post("/analyze", json={"text": "fake"}).json()
        assert "score" in r           # displayed in ScoreCard
        assert "classification" in r  # used for colour-coding
        assert "indicators" in r      # rendered as indicator list
        assert "word_count" in r      # displayed in stats bar
        assert "message" in r         # used in success check
        assert "text_length" in r     # used in stats bar

    def test_frontend_compat_score_non_negative(self, client):
        r = client.post("/analyze", json={"text": "clean text"}).json()
        assert r["score"] >= 0

    def test_frontend_compat_indicators_never_empty_list(self, client):
        """Frontend always renders at least one indicator string."""
        r = client.post("/analyze", json={"text": "clean text"}).json()
        assert len(r["indicators"]) >= 1

    def test_frontend_compat_classification_one_of_known_values(self, client):
        """Frontend colour-codes on exactly these three strings."""
        r = client.post("/analyze", json={"text": "test"}).json()
        assert r["classification"] in ("Credible", "Suspicious", "Likely Fake")


# ============================================================
# Requirements 7-13 confirmed at the HTTP boundary
# ============================================================

class TestAnalyzeScoringViaHttp:
    """
    Scoring correctness verified via actual HTTP POST requests.
    Uses only the original Phase 2 keywords/phrases for determinism.
    """

    # Req 13: empty input
    def test_empty_text_returns_200(self, client):
        assert client.post("/analyze", json={"text": ""}).status_code == 200

    def test_empty_text_score_zero(self, client):
        assert client.post("/analyze", json={"text": ""}).json()["score"] == 0

    def test_empty_text_classification_credible(self, client):
        r = client.post("/analyze", json={"text": ""}).json()
        assert r["classification"] == "Credible"

    def test_empty_text_word_count_zero(self, client):
        assert client.post("/analyze", json={"text": ""}).json()["word_count"] == 0

    # Req 7: suspicious keywords
    def test_one_keyword_scores_10(self, client):
        r = client.post("/analyze", json={"text": "This is fake."}).json()
        assert r["score"] == 10

    def test_keyword_in_indicators(self, client):
        r = client.post("/analyze", json={"text": "fake article"}).json()
        assert any("fake" in ind.lower() for ind in r["indicators"])

    # Req 8: clickbait phrases
    def test_clickbait_phrase_in_response(self, client):
        r = client.post("/analyze", json={"text": "you won't believe this"}).json()
        assert r["score"] == 15
        assert any("clickbait" in ind.lower() for ind in r["indicators"])

    # Req 9: repeated keyword counting
    def test_repeated_keyword_counts_once(self, client):
        r = client.post("/analyze", json={"text": "fake fake fake fake"}).json()
        assert r["score"] == 10    # 1 distinct keyword x 10

    # Req 10: capitalization rule
    def test_all_caps_triggers_cap_rule(self, client):
        r = client.post("/analyze", json={"text": "ALL CAPS NO KEYWORDS"}).json()
        assert r["score"] == 10
        assert any("capitalization" in ind for ind in r["indicators"])

    def test_exclamation_rule(self, client):
        r = client.post("/analyze", json={"text": "Alert!!!"}).json()
        assert r["score"] == 10
        assert any("exclamation" in ind for ind in r["indicators"])

    def test_question_rule(self, client):
        r = client.post("/analyze", json={"text": "What??? Really??? Why???"}).json()
        assert r["score"] == 5
        assert any("question" in ind for ind in r["indicators"])

    # Req 11: score cap at 100
    def test_score_capped_at_100(self, client):
        text = "FAKE HOAX SCAM SHOCKING FRAUD YOU WON'T BELIEVE SHOCKING TRUTH!!!!!???"
        r = client.post("/analyze", json={"text": text}).json()
        assert r["score"] <= 100

    # Req 12: classification boundaries
    def test_boundary_score_30_is_credible(self, client):
        r = client.post("/analyze", json={"text": "fake hoax scam"}).json()
        assert r["score"] == 30
        assert r["classification"] == "Credible"

    def test_boundary_score_31_is_suspicious(self, client):
        # 2 kw (20) + 1 phrase (15) = 35
        r = client.post("/analyze", json={"text": "fake hoax you won't believe"}).json()
        assert r["score"] == 35
        assert r["classification"] == "Suspicious"

    def test_boundary_score_60_is_suspicious(self, client):
        # 4 kw cap (30) + 2 phrase cap (30) = 60
        r = client.post(
            "/analyze",
            json={"text": "fake hoax scam you won't believe shocking truth"},
        ).json()
        assert r["score"] == 60
        assert r["classification"] == "Suspicious"

    def test_boundary_score_above_60_is_likely_fake(self, client):
        # all-caps adds +10 over the 60 above
        r = client.post(
            "/analyze",
            json={"text": "FAKE HOAX SCAM YOU WON'T BELIEVE SHOCKING TRUTH"},
        ).json()
        assert r["score"] == 70
        assert r["classification"] == "Likely Fake"

    def test_no_signals_gives_no_indicators_message(self, client):
        r = client.post("/analyze", json={"text": "Clear news report."}).json()
        assert any("No major" in ind for ind in r["indicators"])

    def test_word_count_via_http(self, client):
        r = client.post("/analyze", json={"text": "one two three"}).json()
        assert r["word_count"] == 3


# ============================================================
# Requirement 15: invalid/broken library -> safe 503, never misleading 200
# ============================================================

class TestBrokenLibraryHttp:
    """
    Req 15: when the keyword library cannot be loaded, the API must return
    HTTP 503 with a safe message -- never a misleading score=0 success.
    No filesystem paths or stack traces may appear in the response body.
    """

    @staticmethod
    def _broken_get_config():
        raise KeywordLibraryError("simulated library failure")

    @staticmethod
    def _broken_file_error():
        raise KeywordLibraryFileError("keywords.json not found")

    @staticmethod
    def _broken_parse_error():
        raise KeywordLibraryParseError("invalid JSON in library")

    @staticmethod
    def _broken_validation_error():
        raise KeywordLibraryValidationError("missing required field")

    # -- /analyze -> 503 --

    def test_analyze_503_on_library_error(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.post("/analyze", json={"text": "test"}).status_code == 503

    def test_analyze_503_on_file_error(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", self._broken_file_error)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.post("/analyze", json={"text": "test"}).status_code == 503

    def test_analyze_503_on_parse_error(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", self._broken_parse_error)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.post("/analyze", json={"text": "test"}).status_code == 503

    def test_analyze_503_on_validation_error(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", self._broken_validation_error)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.post("/analyze", json={"text": "test"}).status_code == 503

    def test_analyze_503_body_has_error_field(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        r = c.post("/analyze", json={"text": "test"}).json()
        assert r.get("error") == "service_unavailable"

    def test_analyze_503_body_has_message_field(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        r = c.post("/analyze", json={"text": "test"}).json()
        assert "message" in r
        assert len(r["message"]) > 0

    def test_analyze_503_body_has_no_score(self, monkeypatch):
        """Response must NOT include score=0, which would be a misleading success."""
        monkeypatch.setattr("analyzer.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        r = c.post("/analyze", json={"text": "test"}).json()
        assert "score" not in r

    def test_analyze_503_body_has_no_classification(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        r = c.post("/analyze", json={"text": "test"}).json()
        assert "classification" not in r

    def test_analyze_503_safe_message_no_filepath(self, monkeypatch):
        """Client-visible message must not expose filesystem paths."""
        monkeypatch.setattr("analyzer.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        body = c.post("/analyze", json={"text": "test"}).text.lower()
        assert "c:\\" not in body
        assert "c:/" not in body
        assert "users\\" not in body
        assert "users/" not in body
        assert "fakeguard" not in body

    def test_analyze_503_safe_message_no_traceback(self, monkeypatch):
        """Client-visible body must not contain Python traceback markers."""
        monkeypatch.setattr("analyzer.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        body = c.post("/analyze", json={"text": "test"}).text.lower()
        assert "traceback" not in body
        assert "most recent call" not in body
        assert "file \"" not in body

    # -- /keywords -> 503 --

    def test_keywords_503_on_library_error(self, monkeypatch):
        monkeypatch.setattr("main.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.get("/keywords").status_code == 503

    def test_keywords_503_safe_message_no_filepath(self, monkeypatch):
        monkeypatch.setattr("main.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        body = c.get("/keywords").text.lower()
        assert "c:\\" not in body
        assert "users\\" not in body
        assert "fakeguard" not in body

    def test_health_unaffected_by_broken_library(self, monkeypatch):
        """Broken library must never take down /health."""
        monkeypatch.setattr("analyzer.get_config", self._broken_get_config)
        monkeypatch.setattr("main.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.get("/health").status_code == 200

    def test_root_unaffected_by_broken_library(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", self._broken_get_config)
        c = TestClient(app, raise_server_exceptions=False)
        assert c.get("/").status_code == 200


# ============================================================
# Requirement 14: keyword added to JSON file detected via HTTP
#                 without restarting the in-process server
# ============================================================

class TestHotReloadViaApi:
    """
    Req 14: a keyword added to the JSON library is detected on the
    next /analyze request without any server restart.

    Uses a temp copy of the library so the real keywords.json is untouched.
    The module-level singleton is monkeypatched to point at the temp loader.
    """

    def test_new_keyword_detected_after_file_change(self, tmp_path, monkeypatch):
        p = tmp_path / "kw.json"
        lib = _minimal_lib()
        _write_lib(p, lib)

        loader = KeywordLoader(p)
        monkeypatch.setattr("keyword_loader._singleton", loader)
        c = TestClient(app, raise_server_exceptions=False)

        # Step 1: "newkeyword" not in library -> score 0
        r1 = c.post("/analyze", json={"text": "newkeyword"})
        assert r1.status_code == 200
        assert r1.json()["score"] == 0, (
            f"Expected 0 before hot-reload, got {r1.json()['score']}"
        )

        # Step 2: add "newkeyword" to the temp library file
        time.sleep(0.05)
        lib["suspicious_keywords"]["words"].append("newkeyword")
        lib["version"] = "test-2.0"
        _write_lib(p, lib)
        os.utime(p, None)

        # Step 3: next request triggers mtime-based reload -> score 10
        r2 = c.post("/analyze", json={"text": "newkeyword"})
        assert r2.status_code == 200
        assert r2.json()["score"] == 10, (
            f"Expected 10 after hot-reload, got {r2.json()['score']}"
        )

    def test_keyword_removed_no_longer_scores(self, tmp_path, monkeypatch):
        p = tmp_path / "kw.json"
        lib = _minimal_lib()
        _write_lib(p, lib)

        loader = KeywordLoader(p)
        monkeypatch.setattr("keyword_loader._singleton", loader)
        c = TestClient(app, raise_server_exceptions=False)

        # "fake" is in the initial library
        r1 = c.post("/analyze", json={"text": "fake"})
        assert r1.json()["score"] == 10

        # Remove "fake" from the library
        time.sleep(0.05)
        lib["suspicious_keywords"]["words"] = ["hoax"]
        _write_lib(p, lib)
        os.utime(p, None)

        r2 = c.post("/analyze", json={"text": "fake"})
        assert r2.json()["score"] == 0, (
            f"Expected 0 after removing 'fake', got {r2.json()['score']}"
        )

    def test_keywords_endpoint_reflects_reloaded_version(self, tmp_path, monkeypatch):
        """/keywords version field updates after hot-reload."""
        p = tmp_path / "kw.json"
        lib = _minimal_lib()
        _write_lib(p, lib)

        loader = KeywordLoader(p)
        monkeypatch.setattr("keyword_loader._singleton", loader)
        c = TestClient(app, raise_server_exceptions=False)

        assert c.get("/keywords").json()["version"] == "test-1.0"

        time.sleep(0.05)
        lib["version"] = "test-99.0"
        _write_lib(p, lib)
        os.utime(p, None)

        assert c.get("/keywords").json()["version"] == "test-99.0"

    def test_invalid_library_update_returns_503(self, tmp_path, monkeypatch):
        """
        If the file is updated to an invalid state, the next request must
        return 503, not a misleading 200 with the old cached config.
        """
        p = tmp_path / "kw.json"
        lib = _minimal_lib()
        _write_lib(p, lib)

        loader = KeywordLoader(p)
        monkeypatch.setattr("keyword_loader._singleton", loader)
        c = TestClient(app, raise_server_exceptions=False)

        # Confirm baseline works
        assert c.post("/analyze", json={"text": "test"}).status_code == 200

        # Corrupt the library file
        time.sleep(0.05)
        p.write_text("{ this is not valid json at all }", encoding="utf-8")
        os.utime(p, None)

        r = c.post("/analyze", json={"text": "test"})
        assert r.status_code == 503, (
            f"Expected 503 on invalid library, got {r.status_code}"
        )

    def test_invalid_library_never_returns_misleading_score(self, tmp_path, monkeypatch):
        """After a corrupt update, the response must NOT contain a score."""
        p = tmp_path / "kw.json"
        lib = _minimal_lib()
        _write_lib(p, lib)

        loader = KeywordLoader(p)
        monkeypatch.setattr("keyword_loader._singleton", loader)
        c = TestClient(app, raise_server_exceptions=False)

        time.sleep(0.05)
        p.write_text("CORRUPT", encoding="utf-8")
        os.utime(p, None)

        r = c.post("/analyze", json={"text": "test"}).json()
        assert "score" not in r


# ============================================================
# /keywords endpoint
# ============================================================

class TestKeywordsEndpoint:
    def test_keywords_returns_200(self, client):
        assert client.get("/keywords").status_code == 200

    def test_keywords_has_version(self, client):
        r = client.get("/keywords").json()
        assert "version" in r
        assert r["version"]

    def test_keywords_has_suspicious_keyword_count(self, client):
        r = client.get("/keywords").json()
        assert "suspicious_keyword_count" in r
        assert r["suspicious_keyword_count"] > 0

    def test_keywords_has_clickbait_phrase_count(self, client):
        r = client.get("/keywords").json()
        assert "clickbait_phrase_count" in r
        assert r["clickbait_phrase_count"] > 0

    def test_keywords_has_max_total_score(self, client):
        r = client.get("/keywords").json()
        assert r.get("max_total_score") == 100

    def test_keywords_scoring_block_complete(self, client):
        scoring = client.get("/keywords").json().get("scoring", {})
        for key in (
            "points_per_suspicious_keyword",
            "suspicious_keyword_cap",
            "points_per_clickbait_phrase",
            "clickbait_phrase_cap",
        ):
            assert key in scoring, f"Missing scoring key: {key!r}"

    def test_keywords_has_three_classification_bands(self, client):
        bands = client.get("/keywords").json().get("classification_bands", [])
        assert len(bands) == 3

    def test_keywords_classification_bands_have_label_min_max(self, client):
        for band in client.get("/keywords").json()["classification_bands"]:
            assert "label" in band
            assert "min" in band
            assert "max" in band

    def test_keywords_correct_band_labels(self, client):
        labels = [
            b["label"]
            for b in client.get("/keywords").json()["classification_bands"]
        ]
        assert set(labels) == {"Credible", "Suspicious", "Likely Fake"}

    def test_keywords_exposes_no_filepath(self, client):
        """The /keywords response must never leak filesystem paths."""
        body = client.get("/keywords").text.lower()
        assert "c:\\" not in body
        assert "c:/" not in body
        assert "users\\" not in body
        assert "users/" not in body
        assert "fakeguard" not in body
        assert "backend" not in body
        assert "app\\" not in body

    def test_keywords_does_not_expose_keyword_list(self, client):
        """
        /keywords returns metadata only, not the full keyword list itself.
        """
        r = client.get("/keywords").json()
        assert "words" not in r
        assert "phrases" not in r
