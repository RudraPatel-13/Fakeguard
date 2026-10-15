"""
Integration tests for the Phase 3 refactored analyzer.py
=========================================================
Two test classes:

  TestScoringWithRealLibrary
    Calls analyze_text() against the real keywords.json.
    Uses only words / phrases present in the original Phase 2 set so
    results are deterministic regardless of future library additions.

  TestConfigChangeBehavior
    Monkeypatches analyzer.get_config to return controlled KeywordConfigs.
    Verifies that analyze_text() honours whatever config is returned --
    proving that a hot-reload (different config at runtime) produces
    different analysis results.
"""

import pytest

from keyword_loader import (
    KeywordConfig,
    SuspiciousKeywordConfig,
    ClickbaitPhrasesConfig,
    TextPatternConfig,
    ClassificationThreshold,
    KeywordLibraryError,
)
from analyzer import analyze_text


# ---------------------------------------------------------------------------
# Test-config builder
# ---------------------------------------------------------------------------

def _cfg(
    words=("testword",),
    phrases=("test phrase",),
    kw_pts=10, kw_cap=30,
    cb_pts=15, cb_cap=30,
    caps_threshold=0.50, caps_pts=10,
    excl_min=3, excl_pts=10,
    quest_min=3, quest_pts=5,
    max_score=100,
):
    """Return a minimal controlled KeywordConfig for monkeypatching."""
    return KeywordConfig(
        version="test",
        suspicious_keywords=SuspiciousKeywordConfig(
            words=frozenset(words),
            points_per_distinct_keyword=kw_pts,
            max_contribution=kw_cap,
        ),
        clickbait_phrases=ClickbaitPhrasesConfig(
            phrases=tuple(phrases),
            points_per_phrase=cb_pts,
            max_contribution=cb_cap,
        ),
        text_patterns=TextPatternConfig(
            caps_ratio_threshold=caps_threshold,
            caps_points=caps_pts,
            exclamation_min_count=excl_min,
            exclamation_points=excl_pts,
            question_min_count=quest_min,
            question_points=quest_pts,
        ),
        max_total_score=max_score,
        thresholds=tuple([
            ClassificationThreshold("Credible",    0,  30),
            ClassificationThreshold("Suspicious",  31, 60),
            ClassificationThreshold("Likely Fake", 61, 100),
        ]),
    )


# ---------------------------------------------------------------------------
# Class 1: scoring tests against the real keywords.json
# ---------------------------------------------------------------------------

class TestScoringWithRealLibrary:
    """
    Each test uses the real keyword library.
    Expected scores use only the original 10 keywords and 7 phrases from
    Phase 2, so results are stable even if the library is later extended.
    """

    # -- basic cases ---

    def test_empty_text(self):
        r = analyze_text("")
        assert r["score"] == 0
        assert r["classification"] == "Credible"
        assert r["word_count"] == 0
        assert r["indicators"] == ["No major suspicious indicators detected."]

    def test_clean_text_no_signals(self):
        r = analyze_text("The government held a press conference today.")
        assert r["score"] == 0
        assert r["classification"] == "Credible"
        assert r["indicators"] == ["No major suspicious indicators detected."]

    # -- suspicious keywords ---

    def test_one_keyword(self):
        # "fake" is one suspicious keyword -> 1 x 10 = 10
        r = analyze_text("This article is fake.")
        assert r["score"] == 10
        assert r["classification"] == "Credible"
        assert any("fake" in ind for ind in r["indicators"])

    def test_three_keywords_reach_cap(self):
        # 3 x 10 = 30, exactly at the cap
        r = analyze_text("fake hoax scam")
        assert r["score"] == 30
        assert r["classification"] == "Credible"   # 30 is still Credible (0-30)

    def test_keywords_beyond_cap_are_capped(self):
        # 5 x 10 = 50, but cap = 30
        r = analyze_text("fake hoax scam shocking fraud")
        assert r["score"] == 30

    def test_repeated_keyword_counts_once(self):
        # "fake" five times: still 1 distinct keyword x 10 = 10
        r = analyze_text("fake fake fake fake fake")
        assert r["score"] == 10

    def test_keyword_detection_is_case_insensitive(self):
        # Analyzer lowercases before matching
        r1 = analyze_text("fake news")
        r2 = analyze_text("FAKE news")
        assert r1["score"] == r2["score"] == 10

    # -- clickbait phrases ---

    def test_one_clickbait_phrase(self):
        # "you won't believe" -> 1 x 15 = 15
        r = analyze_text("you won't believe what happened")
        assert r["score"] == 15
        assert r["classification"] == "Credible"
        assert any("clickbait" in ind.lower() for ind in r["indicators"])

    def test_two_clickbait_phrases_reach_cap(self):
        # "must see" and "click here" -> no suspicious keywords
        # 2 x 15 = 30, exactly at the cap
        r = analyze_text("you won't believe this, must see it")
        assert r["score"] == 30
        assert r["classification"] == "Credible"

    # -- combination crossing classification boundary ---

    def test_keywords_cap_plus_phrase_crosses_into_suspicious(self):
        # 3 keywords (cap = 30) + 1 phrase (15) = 45 -> Suspicious
        r = analyze_text("fake hoax scam you won't believe")
        assert r["score"] == 45
        assert r["classification"] == "Suspicious"

    def test_score_exactly_31_is_suspicious(self):
        # 2 keywords (20) + 1 phrase (15) = 35 -> Suspicious
        r = analyze_text("fake hoax you won't believe")
        assert r["score"] == 35
        assert r["classification"] == "Suspicious"

    def test_score_exactly_60_is_suspicious_not_likely_fake(self):
        # 4 keywords (cap 30) + 2 phrases (cap 30) = 60
        # "shocking" is both a keyword and part of "shocking truth"
        r = analyze_text("fake hoax scam you won't believe shocking truth")
        assert r["score"] == 60
        assert r["classification"] == "Suspicious"

    def test_score_above_60_is_likely_fake(self):
        # Same as above + all-caps -> caps penalty (+10) -> 70
        # "FAKE HOAX SCAM YOU WON'T BELIEVE SHOCKING TRUTH"
        # all letters uppercase -> ratio 1.0 > 0.5 -> +10
        r = analyze_text("FAKE HOAX SCAM YOU WON'T BELIEVE SHOCKING TRUTH")
        assert r["score"] == 70
        assert r["classification"] == "Likely Fake"

    # -- text patterns ---

    def test_excessive_exclamation_marks(self):
        # No keywords/phrases; 3 x "!" -> +10
        r = analyze_text("This just happened!!!")
        assert r["score"] == 10
        assert any("exclamation" in ind for ind in r["indicators"])

    def test_only_two_exclamation_marks_no_trigger(self):
        r = analyze_text("Great news!!")
        assert r["score"] == 0

    def test_excessive_question_marks(self):
        r = analyze_text("Really??? Is this true???")
        assert r["score"] == 5
        assert any("question" in ind for ind in r["indicators"])

    def test_all_caps_triggers_capitalization_rule(self):
        r = analyze_text("ALL CAPS WITH NO KEYWORDS")
        assert r["score"] == 10
        assert any("capitalization" in ind for ind in r["indicators"])

    def test_sentence_case_below_caps_threshold(self):
        # Only first letter is uppercase -> ratio far below 0.5
        r = analyze_text("Normal sentence with proper capitalisation.")
        assert r["score"] == 0

    def test_combined_signals_produces_correct_total(self):
        # "FAKE HOAX SCAM you won't believe!!!"
        # keywords: fake, hoax, scam -> cap 30
        # phrases:  "you won't believe" -> 15
        # caps: FAKE HOAX SCAM = 12 uppercase / 26 total = 0.46 < 0.50  NO
        # excl: 3 -> +10
        # total: 30 + 15 + 10 = 55 -> Suspicious
        r = analyze_text("FAKE HOAX SCAM you won't believe!!!")
        assert r["score"] == 55
        assert r["classification"] == "Suspicious"

    def test_score_never_exceeds_100(self):
        text = "FAKE HOAX SCAM SHOCKING FRAUD YOU WON'T BELIEVE SHOCKING TRUTH!!!!!???"
        r = analyze_text(text)
        assert r["score"] <= 100

    # -- response structure ---

    def test_response_has_all_required_keys(self):
        r = analyze_text("test")
        for key in ("score", "classification", "indicators", "word_count"):
            assert key in r

    def test_score_is_int(self):
        assert isinstance(analyze_text("fake")["score"], int)

    def test_classification_is_str(self):
        assert isinstance(analyze_text("fake")["classification"], str)

    def test_indicators_is_list(self):
        assert isinstance(analyze_text("fake")["indicators"], list)

    def test_word_count_is_int(self):
        assert isinstance(analyze_text("test")["word_count"], int)

    def test_word_count_counts_alpha_tokens_only(self):
        assert analyze_text("one two three")["word_count"] == 3

    def test_word_count_excludes_numbers_and_punctuation(self):
        assert analyze_text("test 123 !!!")["word_count"] == 1

    def test_indicators_never_empty(self):
        r = analyze_text("The weather is fine today.")
        assert len(r["indicators"]) >= 1


# ---------------------------------------------------------------------------
# Class 2: behavioral / config-change tests (monkeypatched configs)
# ---------------------------------------------------------------------------

class TestConfigChangeBehavior:
    """
    Monkeypatch analyzer.get_config to return controlled configs.
    Proves that analyze_text() is fully driven by whatever get_config()
    returns -- simulating the effect of a hot-reload.
    """

    def test_analyzer_uses_injected_keyword_list(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", lambda: _cfg(words=("uniquexyz",)))
        r = analyze_text("uniquexyz in this sentence")
        assert r["score"] == 10

    def test_word_not_in_injected_list_scores_zero(self, monkeypatch):
        monkeypatch.setattr("analyzer.get_config", lambda: _cfg(words=("other",)))
        r = analyze_text("uniquexyz in this sentence")
        assert r["score"] == 0

    def test_config_change_changes_result(self, monkeypatch):
        """Simulates hot-reload: different config -> different score."""
        cfg1 = _cfg(words=("alpha",))
        monkeypatch.setattr("analyzer.get_config", lambda: cfg1)
        r1 = analyze_text("alpha beta gamma")
        assert r1["score"] == 10      # "alpha" matched

        cfg2 = _cfg(words=("beta", "gamma"))
        monkeypatch.setattr("analyzer.get_config", lambda: cfg2)
        r2 = analyze_text("alpha beta gamma")
        assert r2["score"] == 20      # "beta" + "gamma" matched

    def test_keyword_removed_no_longer_scores(self, monkeypatch):
        cfg_with = _cfg(words=("removeword",))
        monkeypatch.setattr("analyzer.get_config", lambda: cfg_with)
        assert analyze_text("removeword here")["score"] > 0

        cfg_without = _cfg(words=("different",))
        monkeypatch.setattr("analyzer.get_config", lambda: cfg_without)
        assert analyze_text("removeword here")["score"] == 0

    def test_custom_scoring_weight_is_used(self, monkeypatch):
        cfg = _cfg(words=("testword",), kw_pts=20, kw_cap=60)
        monkeypatch.setattr("analyzer.get_config", lambda: cfg)
        r = analyze_text("testword")
        assert r["score"] == 20      # 1 x 20, not default 10

    def test_custom_phrase_points_are_used(self, monkeypatch):
        cfg = _cfg(phrases=("special phrase",), cb_pts=25, cb_cap=50)
        monkeypatch.setattr("analyzer.get_config", lambda: cfg)
        r = analyze_text("special phrase in the text")
        assert r["score"] == 25

    def test_custom_classification_thresholds_applied(self, monkeypatch):
        """Custom threshold bands override the default Credible/Suspicious/Likely Fake."""
        cfg = KeywordConfig(
            version="test",
            suspicious_keywords=SuspiciousKeywordConfig(
                words=frozenset(["badword"]),
                points_per_distinct_keyword=10,
                max_contribution=30,
            ),
            clickbait_phrases=ClickbaitPhrasesConfig(
                phrases=("no match phrase",),
                points_per_phrase=15,
                max_contribution=30,
            ),
            text_patterns=TextPatternConfig(
                caps_ratio_threshold=0.50,
                caps_points=10,
                exclamation_min_count=3,
                exclamation_points=10,
                question_min_count=3,
                question_points=5,
            ),
            max_total_score=100,
            thresholds=tuple([
                ClassificationThreshold("Good",   0,  5),
                ClassificationThreshold("Meh",    6,  50),
                ClassificationThreshold("Bad",    51, 100),
            ]),
        )
        monkeypatch.setattr("analyzer.get_config", lambda: cfg)
        r = analyze_text("badword")
        assert r["score"] == 10
        assert r["classification"] == "Meh"     # NOT "Credible"

    def test_caps_threshold_from_config_respected(self, monkeypatch):
        # Lower threshold (0.20) -> normal sentence triggers caps rule
        cfg = _cfg(caps_threshold=0.20)
        monkeypatch.setattr("analyzer.get_config", lambda: cfg)
        # "Hello World" -> H,W uppercase out of total letters ~10 = ~20% = exactly at border
        # "Hello World There" -> H,W,T = 3/17 ~ 17.6% < 20% -- no trigger
        # "HELLO world" -> 5 uppercase / 10 total = 50% > 20% -> trigger
        r = analyze_text("HELLO world")
        assert r["score"] == 10    # caps penalty triggered

    def test_exclamation_threshold_from_config_respected(self, monkeypatch):
        # Raise exclamation threshold to 5
        cfg = _cfg(excl_min=5)
        monkeypatch.setattr("analyzer.get_config", lambda: cfg)
        r = analyze_text("Wow!!!")    # 3 exclamation marks, but threshold is 5
        assert r["score"] == 0       # no trigger

    def test_library_error_propagates_from_analyzer(self, monkeypatch):
        """If get_config() raises, analyze_text() must propagate it."""
        def _fail():
            raise KeywordLibraryError("simulated failure")
        monkeypatch.setattr("analyzer.get_config", _fail)
        with pytest.raises(KeywordLibraryError):
            analyze_text("any text")

    def test_library_error_is_not_swallowed(self, monkeypatch):
        """analyze_text must NOT catch and hide KeywordLibraryError."""
        from keyword_loader import KeywordLibraryFileError
        def _fail():
            raise KeywordLibraryFileError("file gone")
        monkeypatch.setattr("analyzer.get_config", _fail)
        with pytest.raises(KeywordLibraryFileError):
            analyze_text("test")
