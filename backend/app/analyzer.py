"""
FakeGuard Phase 3 -- Article Analyzer
======================================
Applies the scoring rules from the external keyword library to a news article.

All keyword lists, scoring weights, category caps, and classification
thresholds are read from the KeywordConfig returned by
keyword_loader.get_config().  No scoring data is hardcoded here.

Changing keywords.json takes effect on the next request without restarting
the server -- the loader detects the file modification time change and
reloads transparently.

Raises keyword_loader.KeywordLibraryError (or a subclass) when the library
cannot be loaded or is currently invalid.  The API layer (main.py) catches
this and returns a safe HTTP 503 response.  Stack traces and filesystem paths
are never forwarded to the client.
"""

import logging
import re

from keyword_loader import KeywordConfig, get_config

logger = logging.getLogger("fakeguard.analyzer")


def analyze_text(text: str) -> dict:
    """
    Analyze a news article and return a credibility assessment.

    Parameters
    ----------
    text : str
        Raw article text provided by the client.

    Returns
    -------
    dict with keys:
        score          int   credibility indicator score (0 to max_total_score)
        classification str   label from the matching threshold band
        indicators     list  human-readable descriptions of detected signals
        word_count     int   count of alphabetic word tokens found

    Raises
    ------
    keyword_loader.KeywordLibraryError
        Propagated when the keyword library is missing, invalid, or otherwise
        unavailable.  The caller (main.py) is responsible for catching this
        and generating a safe error response.
    """
    # Fetch the current validated configuration.
    # Hot-reload happens transparently here: get_config() checks the file's
    # mtime on every call and reloads if it has changed.
    # Raises KeywordLibraryError on any failure -- never silently falls back.
    cfg: KeywordConfig = get_config()

    score = 0
    indicators: list = []
    lowercase_text = text.lower()

    # ------------------------------------------------------------------ #
    # Rule 1: Suspicious keyword detection                                 #
    # ------------------------------------------------------------------ #
    # Extract purely alphabetic tokens.  Hyphenated entries in the library
    # (e.g. "cover-up") will not match this pattern; they are kept for
    # potential future matcher improvements.
    words = re.findall(r"\b[a-zA-Z]+\b", lowercase_text)

    detected_keywords = []
    for word in words:
        if word in cfg.suspicious_keywords.words:
            if word not in detected_keywords:          # count each distinct keyword once
                detected_keywords.append(word)

    if detected_keywords:
        kw_points = min(
            len(detected_keywords) * cfg.suspicious_keywords.points_per_distinct_keyword,
            cfg.suspicious_keywords.max_contribution,
        )
        score += kw_points
        indicators.append(
            f"Suspicious keywords detected: {', '.join(detected_keywords)}"
        )
        logger.debug(
            "Suspicious keywords: %s  (+%d pts)", detected_keywords, kw_points
        )

    # ------------------------------------------------------------------ #
    # Rule 2: Clickbait phrase detection                                   #
    # ------------------------------------------------------------------ #
    detected_phrases = []
    for phrase in cfg.clickbait_phrases.phrases:
        if phrase in lowercase_text:
            detected_phrases.append(phrase)

    if detected_phrases:
        cb_points = min(
            len(detected_phrases) * cfg.clickbait_phrases.points_per_phrase,
            cfg.clickbait_phrases.max_contribution,
        )
        score += cb_points
        indicators.append(
            f"Clickbait phrases detected: {', '.join(detected_phrases)}"
        )
        logger.debug(
            "Clickbait phrases: %s  (+%d pts)", detected_phrases, cb_points
        )

    # ------------------------------------------------------------------ #
    # Rule 3: Excessive capitalisation                                     #
    # ------------------------------------------------------------------ #
    letters = [ch for ch in text if ch.isalpha()]
    uppercase_letters = [ch for ch in letters if ch.isupper()]

    if letters:
        uppercase_ratio = len(uppercase_letters) / len(letters)
        if uppercase_ratio > cfg.text_patterns.caps_ratio_threshold:
            score += cfg.text_patterns.caps_points
            indicators.append("Excessive capitalization detected.")
            logger.debug(
                "Caps ratio %.2f > %.2f  (+%d pts)",
                uppercase_ratio,
                cfg.text_patterns.caps_ratio_threshold,
                cfg.text_patterns.caps_points,
            )

    # ------------------------------------------------------------------ #
    # Rule 4: Excessive exclamation marks                                  #
    # ------------------------------------------------------------------ #
    exclamation_count = text.count("!")
    if exclamation_count >= cfg.text_patterns.exclamation_min_count:
        score += cfg.text_patterns.exclamation_points
        indicators.append("Excessive exclamation marks detected.")
        logger.debug(
            "Exclamation count %d >= %d  (+%d pts)",
            exclamation_count,
            cfg.text_patterns.exclamation_min_count,
            cfg.text_patterns.exclamation_points,
        )

    # ------------------------------------------------------------------ #
    # Rule 5: Excessive question marks                                     #
    # ------------------------------------------------------------------ #
    question_count = text.count("?")
    if question_count >= cfg.text_patterns.question_min_count:
        score += cfg.text_patterns.question_points
        indicators.append("Excessive question marks detected.")
        logger.debug(
            "Question count %d >= %d  (+%d pts)",
            question_count,
            cfg.text_patterns.question_min_count,
            cfg.text_patterns.question_points,
        )

    # ------------------------------------------------------------------ #
    # Cap total score at the configured maximum                            #
    # ------------------------------------------------------------------ #
    score = min(score, cfg.max_total_score)

    # ------------------------------------------------------------------ #
    # Classify using thresholds from the keyword config                   #
    # ------------------------------------------------------------------ #
    # The loader guarantees thresholds are contiguous and cover
    # [0, max_total_score] exactly, so exactly one band will always match.
    classification = cfg.thresholds[-1].label      # safe fallback: last band
    for threshold in cfg.thresholds:
        if threshold.min_score <= score <= threshold.max_score:
            classification = threshold.label
            break

    # ------------------------------------------------------------------ #
    # No signals detected                                                  #
    # ------------------------------------------------------------------ #
    if not indicators:
        indicators.append("No major suspicious indicators detected.")

    logger.debug(
        "Result: score=%d  classification=%r  word_count=%d",
        score, classification, len(words),
    )

    return {
        "score": score,
        "classification": classification,
        "indicators": indicators,
        "word_count": len(words),
    }