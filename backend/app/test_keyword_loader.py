"""
Tests for keyword_loader.py
===========================
Uses pytest tmp_path fixture exclusively -- never touches the real keywords.json.
Covers: _parse_and_validate (pure), KeywordLoader (file I/O), hot-reload,
thread-safety, and immutability guarantees.
"""

import json
import os
import threading
import time
from pathlib import Path

import pytest

# keyword_loader lives in the same directory; pytest adds it to sys.path.
from keyword_loader import (
    KeywordLoader,
    KeywordConfig,
    SuspiciousKeywordConfig,
    ClickbaitPhrasesConfig,
    TextPatternConfig,
    ClassificationThreshold,
    KeywordLibraryError,
    KeywordLibraryFileError,
    KeywordLibraryParseError,
    KeywordLibraryValidationError,
    _parse_and_validate,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _minimal_valid() -> dict:
    """Return the smallest dict that passes _parse_and_validate."""
    return {
        "version": "1.0.0",
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


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests: _parse_and_validate  (pure -- no file I/O)
# ---------------------------------------------------------------------------

class TestParseAndValidate:

    # -- happy path --

    def test_valid_minimal(self):
        cfg = _parse_and_validate(_minimal_valid())
        assert isinstance(cfg, KeywordConfig)
        assert cfg.version == "1.0.0"

    def test_returns_correct_sub_types(self):
        cfg = _parse_and_validate(_minimal_valid())
        assert isinstance(cfg.suspicious_keywords, SuspiciousKeywordConfig)
        assert isinstance(cfg.clickbait_phrases, ClickbaitPhrasesConfig)
        assert isinstance(cfg.text_patterns, TextPatternConfig)

    def test_scoring_values_preserved(self):
        cfg = _parse_and_validate(_minimal_valid())
        assert cfg.suspicious_keywords.points_per_distinct_keyword == 10
        assert cfg.suspicious_keywords.max_contribution == 30
        assert cfg.clickbait_phrases.points_per_phrase == 15
        assert cfg.clickbait_phrases.max_contribution == 30
        assert cfg.text_patterns.caps_ratio_threshold == 0.50
        assert cfg.text_patterns.caps_points == 10
        assert cfg.text_patterns.exclamation_min_count == 3
        assert cfg.text_patterns.exclamation_points == 10
        assert cfg.text_patterns.question_min_count == 3
        assert cfg.text_patterns.question_points == 5
        assert cfg.max_total_score == 100

    def test_thresholds_parsed_correctly(self):
        cfg = _parse_and_validate(_minimal_valid())
        assert len(cfg.thresholds) == 3
        assert cfg.thresholds[0].label == "Credible"
        assert cfg.thresholds[0].min_score == 0
        assert cfg.thresholds[0].max_score == 30
        assert cfg.thresholds[2].label == "Likely Fake"
        assert cfg.thresholds[2].max_score == 100

    # -- top-level structure --

    def test_not_a_dict_raises(self):
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(["not", "a", "dict"])

    # -- version --

    def test_missing_version(self):
        d = _minimal_valid(); del d["version"]
        with pytest.raises(KeywordLibraryValidationError, match="version"):
            _parse_and_validate(d)

    def test_blank_version(self):
        d = _minimal_valid(); d["version"] = "   "
        with pytest.raises(KeywordLibraryValidationError, match="version"):
            _parse_and_validate(d)

    def test_numeric_version_rejected(self):
        d = _minimal_valid(); d["version"] = 1
        with pytest.raises(KeywordLibraryValidationError, match="version"):
            _parse_and_validate(d)

    def test_version_whitespace_stripped(self):
        d = _minimal_valid(); d["version"] = "  2.0.0  "
        cfg = _parse_and_validate(d)
        assert cfg.version == "2.0.0"

    # -- suspicious_keywords --

    def test_missing_suspicious_keywords(self):
        d = _minimal_valid(); del d["suspicious_keywords"]
        with pytest.raises(KeywordLibraryValidationError, match="suspicious_keywords"):
            _parse_and_validate(d)

    def test_empty_keyword_list_rejected(self):
        d = _minimal_valid(); d["suspicious_keywords"]["words"] = []
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_keyword_list_not_array_rejected(self):
        d = _minimal_valid(); d["suspicious_keywords"]["words"] = "fake"
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_non_string_keyword_rejected(self):
        d = _minimal_valid(); d["suspicious_keywords"]["words"] = ["fake", 42]
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_whitespace_only_keyword_rejected(self):
        d = _minimal_valid(); d["suspicious_keywords"]["words"] = ["fake", "   "]
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_keyword_normalization_lowercase(self):
        d = _minimal_valid(); d["suspicious_keywords"]["words"] = ["FAKE", "Hoax"]
        cfg = _parse_and_validate(d)
        assert "fake" in cfg.suspicious_keywords.words
        assert "hoax" in cfg.suspicious_keywords.words

    def test_keyword_normalization_strips_whitespace(self):
        d = _minimal_valid(); d["suspicious_keywords"]["words"] = ["  fake  "]
        cfg = _parse_and_validate(d)
        assert "fake" in cfg.suspicious_keywords.words

    def test_duplicate_keywords_deduplicated(self):
        d = _minimal_valid()
        d["suspicious_keywords"]["words"] = ["fake", "FAKE", "Fake", "hoax"]
        cfg = _parse_and_validate(d)
        assert len(cfg.suspicious_keywords.words) == 2  # fake + hoax

    def test_zero_keyword_points_rejected(self):
        d = _minimal_valid()
        d["suspicious_keywords"]["scoring"]["points_per_distinct_keyword"] = 0
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_negative_keyword_points_rejected(self):
        d = _minimal_valid()
        d["suspicious_keywords"]["scoring"]["points_per_distinct_keyword"] = -10
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_bool_keyword_points_rejected(self):
        # True == 1 in Python but must be rejected (bool subclasses int)
        d = _minimal_valid()
        d["suspicious_keywords"]["scoring"]["points_per_distinct_keyword"] = True
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_cap_less_than_per_keyword_rejected(self):
        d = _minimal_valid()
        d["suspicious_keywords"]["scoring"]["max_contribution"] = 5  # < 10
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_missing_scoring_block_rejected(self):
        d = _minimal_valid(); del d["suspicious_keywords"]["scoring"]
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    # -- clickbait_phrases --

    def test_missing_clickbait_phrases(self):
        d = _minimal_valid(); del d["clickbait_phrases"]
        with pytest.raises(KeywordLibraryValidationError, match="clickbait_phrases"):
            _parse_and_validate(d)

    def test_empty_phrases_list_rejected(self):
        d = _minimal_valid(); d["clickbait_phrases"]["phrases"] = []
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_phrase_normalization(self):
        d = _minimal_valid()
        d["clickbait_phrases"]["phrases"] = ["  YOU WILL NOT BELIEVE  "]
        cfg = _parse_and_validate(d)
        assert "you will not believe" in cfg.clickbait_phrases.phrases

    def test_phrase_deduplication_preserves_order(self):
        d = _minimal_valid()
        d["clickbait_phrases"]["phrases"] = ["must see", "click here", "MUST SEE"]
        cfg = _parse_and_validate(d)
        assert len(cfg.clickbait_phrases.phrases) == 2
        assert cfg.clickbait_phrases.phrases[0] == "must see"
        assert cfg.clickbait_phrases.phrases[1] == "click here"

    def test_negative_phrase_points_rejected(self):
        d = _minimal_valid()
        d["clickbait_phrases"]["scoring"]["points_per_phrase"] = -1
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_cb_cap_less_than_per_phrase_rejected(self):
        d = _minimal_valid()
        d["clickbait_phrases"]["scoring"]["max_contribution"] = 5  # < 15
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    # -- text_pattern_rules --

    def test_missing_text_pattern_rules(self):
        d = _minimal_valid(); del d["text_pattern_rules"]
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_caps_threshold_zero_rejected(self):
        d = _minimal_valid()
        d["text_pattern_rules"]["excessive_capitalization"]["uppercase_ratio_threshold"] = 0.0
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_caps_threshold_one_rejected(self):
        d = _minimal_valid()
        d["text_pattern_rules"]["excessive_capitalization"]["uppercase_ratio_threshold"] = 1.0
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_caps_threshold_negative_rejected(self):
        d = _minimal_valid()
        d["text_pattern_rules"]["excessive_capitalization"]["uppercase_ratio_threshold"] = -0.1
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_exclamation_zero_min_count_rejected(self):
        d = _minimal_valid()
        d["text_pattern_rules"]["excessive_exclamation_marks"]["min_count"] = 0
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_question_negative_points_rejected(self):
        d = _minimal_valid()
        d["text_pattern_rules"]["excessive_question_marks"]["points"] = -5
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_bool_min_count_rejected(self):
        d = _minimal_valid()
        d["text_pattern_rules"]["excessive_exclamation_marks"]["min_count"] = True
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    # -- scoring --

    def test_missing_scoring(self):
        d = _minimal_valid(); del d["scoring"]
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_zero_max_total_score_rejected(self):
        d = _minimal_valid(); d["scoring"]["max_total_score"] = 0
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_negative_max_total_score_rejected(self):
        d = _minimal_valid(); d["scoring"]["max_total_score"] = -100
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    # -- classification --

    def test_missing_classification(self):
        d = _minimal_valid(); del d["classification"]
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_empty_thresholds_rejected(self):
        d = _minimal_valid(); d["classification"]["thresholds"] = []
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_non_contiguous_thresholds_rejected(self):
        d = _minimal_valid()
        d["classification"]["thresholds"] = [
            {"label": "Credible",    "min": 0,  "max": 30},
            {"label": "Suspicious",  "min": 32, "max": 60},  # gap at 31
            {"label": "Likely Fake", "min": 61, "max": 100},
        ]
        with pytest.raises(KeywordLibraryValidationError, match="contiguous"):
            _parse_and_validate(d)

    def test_thresholds_not_covering_full_range_rejected(self):
        d = _minimal_valid()
        d["classification"]["thresholds"] = [
            {"label": "Credible",   "min": 0,  "max": 30},
            {"label": "Suspicious", "min": 31, "max": 99},  # misses 100
        ]
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_threshold_min_gt_max_rejected(self):
        d = _minimal_valid()
        d["classification"]["thresholds"][0]["min"] = 30
        d["classification"]["thresholds"][0]["max"] = 0
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    def test_blank_threshold_label_rejected(self):
        d = _minimal_valid()
        d["classification"]["thresholds"][0]["label"] = "   "
        with pytest.raises(KeywordLibraryValidationError):
            _parse_and_validate(d)

    # -- immutability --

    def test_keyword_config_is_frozen(self):
        cfg = _parse_and_validate(_minimal_valid())
        with pytest.raises((AttributeError, TypeError)):
            cfg.version = "hacked"  # type: ignore

    def test_suspicious_words_is_frozenset(self):
        cfg = _parse_and_validate(_minimal_valid())
        assert isinstance(cfg.suspicious_keywords.words, frozenset)

    def test_clickbait_phrases_is_tuple(self):
        cfg = _parse_and_validate(_minimal_valid())
        assert isinstance(cfg.clickbait_phrases.phrases, tuple)

    def test_thresholds_is_tuple(self):
        cfg = _parse_and_validate(_minimal_valid())
        assert isinstance(cfg.thresholds, tuple)

    def test_threshold_items_are_frozen(self):
        cfg = _parse_and_validate(_minimal_valid())
        with pytest.raises((AttributeError, TypeError)):
            cfg.thresholds[0].label = "hacked"  # type: ignore


# ---------------------------------------------------------------------------
# Tests: KeywordLoader  (file I/O via tmp_path)
# ---------------------------------------------------------------------------

class TestKeywordLoader:

    def test_loads_valid_file(self, tmp_path):
        p = tmp_path / "kw.json"
        _write(p, _minimal_valid())
        loader = KeywordLoader(p)
        cfg = loader.get_config()
        assert cfg.version == "1.0.0"
        assert "fake" in cfg.suspicious_keywords.words

    def test_missing_file_raises_file_error(self, tmp_path):
        p = tmp_path / "nonexistent.json"
        with pytest.raises(KeywordLibraryFileError):
            KeywordLoader(p)

    def test_invalid_json_raises_parse_error(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ this is not valid json }", encoding="utf-8")
        with pytest.raises(KeywordLibraryParseError):
            KeywordLoader(p)

    def test_invalid_schema_raises_validation_error(self, tmp_path):
        p = tmp_path / "bad_schema.json"
        d = _minimal_valid(); del d["suspicious_keywords"]
        _write(p, d)
        with pytest.raises(KeywordLibraryValidationError):
            KeywordLoader(p)

    def test_library_path_property(self, tmp_path):
        p = tmp_path / "kw.json"
        _write(p, _minimal_valid())
        loader = KeywordLoader(p)
        assert loader.library_path == p.resolve()

    def test_no_reload_when_mtime_unchanged(self, tmp_path):
        p = tmp_path / "kw.json"
        _write(p, _minimal_valid())
        loader = KeywordLoader(p)
        cfg1 = loader.get_config()
        cfg2 = loader.get_config()
        # Same frozen object returned when file has not changed
        assert cfg1 is cfg2

    def test_hot_reload_on_file_change(self, tmp_path):
        p = tmp_path / "kw.json"
        _write(p, _minimal_valid())
        loader = KeywordLoader(p)
        assert loader.get_config().version == "1.0.0"

        time.sleep(0.05)
        d2 = _minimal_valid()
        d2["version"] = "2.0.0"
        d2["suspicious_keywords"]["words"] = ["scam", "fraud"]
        _write(p, d2)
        os.utime(p, None)  # guarantee mtime advances

        cfg2 = loader.get_config()
        assert cfg2.version == "2.0.0"
        assert "scam" in cfg2.suspicious_keywords.words
        assert "fake" not in cfg2.suspicious_keywords.words

    def test_invalid_reload_raises_library_error(self, tmp_path):
        p = tmp_path / "kw.json"
        _write(p, _minimal_valid())
        loader = KeywordLoader(p)

        time.sleep(0.05)
        p.write_text("INVALID JSON {{{{", encoding="utf-8")
        os.utime(p, None)

        with pytest.raises(KeywordLibraryError):
            loader.get_config()

    def test_invalid_reload_raises_parse_error_specifically(self, tmp_path):
        p = tmp_path / "kw.json"
        _write(p, _minimal_valid())
        loader = KeywordLoader(p)

        time.sleep(0.05)
        p.write_text("not json at all", encoding="utf-8")
        os.utime(p, None)

        with pytest.raises(KeywordLibraryParseError):
            loader.get_config()

    def test_invalid_reload_raises_validation_error_specifically(self, tmp_path):
        p = tmp_path / "kw.json"
        _write(p, _minimal_valid())
        loader = KeywordLoader(p)

        time.sleep(0.05)
        d_bad = _minimal_valid(); del d_bad["classification"]
        _write(p, d_bad)
        os.utime(p, None)

        with pytest.raises(KeywordLibraryValidationError):
            loader.get_config()

    def test_all_errors_are_subclasses_of_base(self):
        for err_type in (
            KeywordLibraryFileError,
            KeywordLibraryParseError,
            KeywordLibraryValidationError,
        ):
            assert issubclass(err_type, KeywordLibraryError)

    def test_thread_safety_concurrent_reads(self, tmp_path):
        """Many threads calling get_config() concurrently must not crash."""
        p = tmp_path / "kw.json"
        _write(p, _minimal_valid())
        loader = KeywordLoader(p)
        errors = []

        def reader():
            try:
                for _ in range(100):
                    cfg = loader.get_config()
                    assert cfg.version == "1.0.0"
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(12)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors, f"Thread errors: {errors}"

    def test_thread_safety_concurrent_read_write(self, tmp_path):
        """
        Writer updating the file while readers call get_config must not crash
        with any *unexpected* exception.  KeywordLibraryError is expected
        (the writer may leave the file empty or partial mid-write) and is
        therefore tolerated.  Only non-library exceptions are failures.
        """
        p = tmp_path / "kw.json"
        _write(p, _minimal_valid())
        loader = KeywordLoader(p)
        unexpected_errors = []
        stop = threading.Event()

        def writer():
            ver = 1
            while not stop.is_set():
                time.sleep(0.02)
                d = _minimal_valid(); d["version"] = str(ver)
                _write(p, d); os.utime(p, None); ver += 1

        def reader():
            while not stop.is_set():
                try:
                    loader.get_config()
                except KeywordLibraryError:
                    # Expected: file may be empty/partial during the write.
                    pass
                except Exception as exc:
                    unexpected_errors.append(exc)
                    break

        wt = threading.Thread(target=writer)
        readers = [threading.Thread(target=reader) for _ in range(6)]
        wt.start()
        for t in readers: t.start()
        time.sleep(0.3)
        stop.set(); wt.join()
        for t in readers: t.join()
        assert not unexpected_errors, f"Unexpected errors: {unexpected_errors}"


# ---------------------------------------------------------------------------
# Tests: real keywords.json (read-only sanity check)
# ---------------------------------------------------------------------------

class TestRealLibraryFile:
    """
    Confirm that the project real keywords.json loads correctly and
    preserves the original analyzer.py scoring values.
    These tests are read-only and do not modify the file.
    """

    @pytest.fixture(scope="class")
    @classmethod
    def real_cfg(cls):
        real_path = Path(__file__).parent / "keyword_library" / "keywords.json"
        return KeywordLoader(real_path).get_config()

    def test_real_library_loads(self, real_cfg):
        assert isinstance(real_cfg, KeywordConfig)

    def test_real_library_has_non_empty_version(self, real_cfg):
        assert real_cfg.version

    def test_real_library_has_original_10_keywords(self, real_cfg):
        original = {
            "fake", "hoax", "scam", "shocking", "fraud",
            "secret", "exposed", "urgent", "banned", "conspiracy",
        }
        assert original.issubset(real_cfg.suspicious_keywords.words)

    def test_real_library_has_original_7_phrases(self, real_cfg):
        # The apostrophe variant is in the file; normalised to lowercase here
        original = {
            "you won't believe", "you will not believe", "shocking truth",
            "what happens next", "must see", "click here", "you need to know",
        }
        assert original.issubset(set(real_cfg.clickbait_phrases.phrases))

    def test_real_library_scoring_matches_analyzer(self, real_cfg):
        sk = real_cfg.suspicious_keywords
        cb = real_cfg.clickbait_phrases
        tp = real_cfg.text_patterns
        assert sk.points_per_distinct_keyword == 10
        assert sk.max_contribution == 30
        assert cb.points_per_phrase == 15
        assert cb.max_contribution == 30
        assert tp.caps_ratio_threshold == 0.50
        assert tp.caps_points == 10
        assert tp.exclamation_min_count == 3
        assert tp.exclamation_points == 10
        assert tp.question_min_count == 3
        assert tp.question_points == 5
        assert real_cfg.max_total_score == 100

    def test_real_library_thresholds_cover_0_to_100(self, real_cfg):
        mins = [t.min_score for t in real_cfg.thresholds]
        maxs = [t.max_score for t in real_cfg.thresholds]
        assert mins[0] == 0
        assert maxs[-1] == 100

    def test_real_library_classification_labels(self, real_cfg):
        labels = [t.label for t in real_cfg.thresholds]
        assert "Credible" in labels
        assert "Suspicious" in labels
        assert "Likely Fake" in labels
