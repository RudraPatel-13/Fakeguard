"""
FakeGuard Phase 3 -- Article Analyzer
======================================
Applies the scoring rules from the external keyword library to a news article.

All keyword lists, scoring weights, category caps, and classification
thresholds are read from the KeywordConfig returned by
keyword_loader.get_config().  No scoring data is hardcoded here.

Phase 3 enhancement -- WordNet synonym detection:
  Before each analysis, analyzer.py asks wordnet_service to ensure its
  synonym-to-canonical mapping is up to date with the current keyword config.
  During Rule 1 (suspicious keyword detection), the analyzer performs two passes:
    Pass 1 -- direct matches: words that appear verbatim in keywords.json.
    Pass 2 -- WordNet matches: words absent from keywords.json but returned by
              WordNet as synonyms of a configured concept.
  Both passes contribute to the same per-canonical-concept count so that a
  configured term and its discovered synonym are never counted twice.

Changing keywords.json takes effect on the next request without restarting
the server -- the loader detects the file modification time change and
reloads transparently.  The WordNet synonym map is also rebuilt whenever the
canonical keyword set changes.

Raises keyword_loader.KeywordLibraryError (or a subclass) when the library
cannot be loaded or is currently invalid.  The API layer (main.py) catches
this and returns a safe HTTP 503 response.  Stack traces and filesystem paths
are never forwarded to the client.
"""

import logging
import re

import wordnet_service
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

    # Ensure the WordNet synonym map is consistent with the current keyword set.
    # This is a no-op when the keywords have not changed since the last call,
    # and a no-op when WordNet is unavailable.
    wordnet_service.update_synonym_map(cfg.suspicious_keywords.words)
    wn_enabled = wordnet_service.is_available()

    score = 0
    indicators: list = []
    breakdown = {"keywords": 0, "clickbait": 0, "caps": 0, "exclamation": 0, "question": 0}
    detected_phrases: list = []
    lowercase_text = text.lower()

    # ------------------------------------------------------------------ #
    # Rule 1: Suspicious keyword detection (direct + WordNet synonyms)    #
    # ------------------------------------------------------------------ #
    # Extract purely alphabetic tokens.  Hyphenated entries in the library
    # (e.g. "cover-up") will not match this pattern; they are kept for
    # potential future matcher improvements.
    words = re.findall(r"\b[a-zA-Z]+\b", lowercase_text)
    word_set = set(words)   # unique surface words for detection

    # detected_canonical_concepts: canonical_keyword -> surface_word that triggered it
    # Using an ordered dict-of-first-match to keep indicators deterministic.
    detected_canonical_concepts: dict = {}
    direct_match_surfaces: list = []    # surface words that are direct keyword matches
    wordnet_matches: list = []          # (surface_word, canonical_word) tuples

    # Pass 1 -- direct matches (highest priority; checked first so that a
    # configured keyword is never mistakenly treated as a synonym match even
    # if it also appears in another keyword's synset).
    for word in sorted(word_set):          # sorted for deterministic ordering
        if word in cfg.suspicious_keywords.words:
            if word not in detected_canonical_concepts:
                detected_canonical_concepts[word] = word
                direct_match_surfaces.append(word)

    # Pass 2 -- WordNet synonym matches (only for words not already matched
    # as direct keywords, and only when WordNet corpus is available).
    if wn_enabled:
        for word in sorted(word_set):
            if word in cfg.suspicious_keywords.words:
                continue                   # already handled in Pass 1
            canonical = wordnet_service.find_canonical(word)
            if canonical is not None and canonical not in detected_canonical_concepts:
                detected_canonical_concepts[canonical] = word
                wordnet_matches.append((word, canonical))

    # Score and build indicators for keyword / synonym findings.
    if detected_canonical_concepts:
        kw_points = min(
            len(detected_canonical_concepts) * cfg.suspicious_keywords.points_per_distinct_keyword,
            cfg.suspicious_keywords.max_contribution,
        )
        score += kw_points
        breakdown["keywords"] = kw_points

        # Indicator for direct keyword matches.
        if direct_match_surfaces:
            indicators.append(
                f"Suspicious keywords detected: {', '.join(sorted(direct_match_surfaces))}"
            )

        # Separate, clearly labelled indicator for each WordNet match.
        for surface_word, canonical in sorted(wordnet_matches):
            indicators.append(
                f'WordNet lexical match: "{surface_word}" is associated with '
                f'the configured concept "{canonical}".'
            )

        logger.debug(
            "Keyword / synonym detection: %d direct, %d WordNet  (+%d pts)",
            len(direct_match_surfaces),
            len(wordnet_matches),
            kw_points,
        )

    # ------------------------------------------------------------------ #
    # Rule 2: Clickbait phrase detection                                   #
    # ------------------------------------------------------------------ #
    for phrase in cfg.clickbait_phrases.phrases:
        if phrase in lowercase_text:
            detected_phrases.append(phrase)

    if detected_phrases:
        cb_points = min(
            len(detected_phrases) * cfg.clickbait_phrases.points_per_phrase,
            cfg.clickbait_phrases.max_contribution,
        )
        score += cb_points
        breakdown["clickbait"] = cb_points
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
            breakdown["caps"] = cfg.text_patterns.caps_points
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
        breakdown["exclamation"] = cfg.text_patterns.exclamation_points
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
        breakdown["question"] = cfg.text_patterns.question_points
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
        # Additive Phase 4 fields (legacy keys above are unchanged).
        "breakdown": breakdown,
        "max_score": cfg.max_total_score,
        "caps": {"suspicious_max": cfg.suspicious_keywords.max_contribution,
                 "clickbait_max": cfg.clickbait_phrases.max_contribution,
                 "text_pattern_max": cfg.text_patterns.caps_points + cfg.text_patterns.exclamation_points + cfg.text_patterns.question_points},
        "matched_terms": {
            "keywords": sorted(direct_match_surfaces),
            "wordnet": sorted(w for w, _ in wordnet_matches),
            "clickbait": list(detected_phrases),
        },
    }