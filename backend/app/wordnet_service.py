"""
FakeGuard -- WordNet Synonym Service
=====================================
Discovers lexical synonyms for configured suspicious concepts using
NLTK's WordNet interface.

Design principles:
  - Only direct co-lemmas within the same WordNet synsets are used.
    No hyponym / hypernym traversal -- avoids unbounded or unrelated matches.
  - Queries all parts of speech (ADJ, NOUN, VERB, ADV) and merges results.
  - Caches per-word synonym lookups so the corpus is not re-queried repeatedly.
  - Maintains a synonym-to-canonical mapping for all configured keywords;
    rebuilds only when the canonical word set changes (tracks mtime-analogue).
  - Thread-safe: all mutable state is guarded by a single threading.Lock.
  - Degrades gracefully when the WordNet corpus or NLTK is not installed:
    all public functions return empty / None rather than raising.

Limitations (document these honestly):
  - WordNet provides lexical, not contextual, relationships.
    "The claim was not fabricated" matches as readily as "The claim was fabricated."
    Synonym detection flags suspicious vocabulary; it does not verify factual truth.
  - Multiword lemmas with underscores are normalised to space-separated phrases.
    The analyzer uses whole-word regex matching so single-word lemmas match correctly;
    multiword phrases fall through to substring detection (same as clickbait phrases).
  - WordNet version differences may cause synonym sets to vary across installations.
    Tests that rely on specific synonym words should use mocks or inspect the corpus
    at test time and skip if the expected word is absent.

Not a responsibility of this module:
  - Article scoring or classification  -> analyzer.py
  - HTTP routing or request handling   -> main.py
  - Keyword configuration management  -> keyword_loader.py
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger("fakeguard.wordnet")

# ---------------------------------------------------------------------------
# Corpus availability
# ---------------------------------------------------------------------------

def _check_corpus_available() -> bool:
    """
    Return True iff NLTK is installed AND the WordNet corpus data is present.

    Performs a real corpus access (wn.synsets) so that a partial or
    corrupt install is caught here rather than at analysis time.
    """
    try:
        import nltk  # noqa: F401
        from nltk.corpus import wordnet as wn
        wn.synsets("test")          # force actual data access
        return True
    except LookupError:
        logger.warning(
            "WordNet corpus not found. "
            "Download it with: python -m nltk.downloader wordnet omw-1.4"
        )
        return False
    except ImportError:
        logger.warning(
            "NLTK is not installed. Install it with: pip install nltk"
        )
        return False
    except Exception as exc:  # pragma: no cover
        logger.warning("WordNet availability check failed unexpectedly: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Core (uncached) synonym lookup
# ---------------------------------------------------------------------------

def _get_wordnet_synonyms(word: str) -> frozenset:
    """
    Return direct co-lemmas for *word* from all of its WordNet synsets.

    Rules:
      - All parts of speech are queried (no POS restriction applied here;
        suspicious news keywords span ADJ, NOUN, VERB).
      - Only lemmas within the *same synsets* as the input word are returned
        (no hypernym / hyponym traversal).
      - Underscores in multiword lemma names are replaced with spaces.
      - Results are lowercased and deduplicated.
      - The input word itself is excluded from the results.

    Returns an empty frozenset if WordNet is unavailable or the word has
    no synsets.
    """
    try:
        from nltk.corpus import wordnet as wn
    except (ImportError, LookupError):
        return frozenset()

    normalized = word.strip().lower()
    synonyms: set = set()

    try:
        for synset in wn.synsets(normalized):
            for lemma in synset.lemmas():
                name = lemma.name().lower().replace("_", " ")
                if name != normalized:
                    synonyms.add(name)
    except Exception as exc:  # pragma: no cover
        logger.debug("WordNet lookup error for %r: %s", word, exc)

    return frozenset(synonyms)


# ---------------------------------------------------------------------------
# WordNetService: stateful, caching, thread-safe singleton
# ---------------------------------------------------------------------------

class WordNetService:
    """
    Stateful, thread-safe service that:
      1. Checks WordNet corpus availability once at construction.
      2. Caches per-word synonym lookups (word -> frozenset[str]).
      3. Maintains a synonym-to-canonical mapping for all configured keywords.
      4. Rebuilds the mapping only when the canonical word set changes.
    """

    def __init__(self) -> None:
        self._available: bool = _check_corpus_available()
        self._lock = threading.Lock()

        # Per-word synonym cache: normalized_word -> frozenset of synonyms
        self._synonym_cache: dict = {}

        # Mapping from discovered synonym -> canonical suspicious concept
        self._synonym_to_canonical: dict = {}

        # Track the keyword set used to build the current map
        self._last_canonical_words: frozenset = frozenset()

        if self._available:
            logger.info("WordNet synonym service initialized (corpus available).")
        else:
            logger.warning(
                "WordNet synonym service initialized WITHOUT corpus. "
                "Synonym detection is disabled. "
                "To enable: python -m nltk.downloader wordnet omw-1.4"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if the WordNet corpus is usable."""
        return self._available

    def get_synonyms(self, word: str) -> frozenset:
        """
        Return cached WordNet synonyms for *word*.

        Returns an empty frozenset if WordNet is unavailable.
        The result is cached permanently for the lifetime of this service
        instance (the corpus does not change at runtime).
        """
        if not self._available:
            return frozenset()

        normalized = word.strip().lower()
        with self._lock:
            if normalized not in self._synonym_cache:
                self._synonym_cache[normalized] = _get_wordnet_synonyms(normalized)
            return self._synonym_cache[normalized]

    def update_synonym_map(self, canonical_words: frozenset) -> None:
        """
        Rebuild the synonym-to-canonical mapping if *canonical_words* has
        changed since the last call.

        Called by the analyzer before each analysis request so that the
        mapping stays consistent with the current keyword configuration
        (which may have been hot-reloaded from keywords.json).

        This method is a no-op when WordNet is unavailable.
        """
        if not self._available:
            return

        with self._lock:
            if canonical_words == self._last_canonical_words:
                return  # fast path -- nothing changed

            logger.info(
                "Rebuilding WordNet synonym map for %d canonical concept(s).",
                len(canonical_words),
            )

            new_map: dict = {}
            for canonical in canonical_words:
                # Use the internal lookup directly (no double-locking needed
                # because we already hold self._lock here).
                if canonical not in self._synonym_cache:
                    self._synonym_cache[canonical] = _get_wordnet_synonyms(canonical)
                synonyms = self._synonym_cache[canonical]

                for syn in synonyms:
                    # A synonym that IS itself a canonical concept must not be
                    # added to the map (avoids mapping "fake" -> "hoax" if they
                    # happen to share a synset, which is unlikely but possible).
                    if syn not in canonical_words:
                        # First canonical concept wins when synonyms overlap.
                        if syn not in new_map:
                            new_map[syn] = canonical

            self._synonym_to_canonical = new_map
            self._last_canonical_words = canonical_words

            logger.debug(
                "Synonym map built: %d synonym entry/entries for %d concept(s).",
                len(new_map),
                len(canonical_words),
            )

    def find_canonical(self, word: str) -> Optional[str]:
        """
        Given a surface word found in article text, return the canonical
        suspicious concept it maps to via WordNet, or None if no mapping
        exists.

        Returns None immediately when WordNet is unavailable.
        """
        if not self._available:
            return None

        normalized = word.strip().lower()
        with self._lock:
            return self._synonym_to_canonical.get(normalized)

    def cache_stats(self) -> dict:
        """Return diagnostic information about the current cache state."""
        with self._lock:
            return {
                "wordnet_available": self._available,
                "cached_word_lookups": len(self._synonym_cache),
                "synonym_map_entries": len(self._synonym_to_canonical),
                "canonical_concepts_tracked": len(self._last_canonical_words),
            }


# ---------------------------------------------------------------------------
# Module-level singleton (lazy; thread-safe)
# ---------------------------------------------------------------------------

_service: Optional[WordNetService] = None
_service_lock = threading.Lock()


def get_service() -> WordNetService:
    """Return the module-level WordNetService singleton (lazy initialization)."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = WordNetService()
    return _service


# ---------------------------------------------------------------------------
# Module-level convenience wrappers
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Return True if the WordNet corpus is usable."""
    return get_service().is_available()


def get_synonyms(word: str) -> frozenset:
    """Return cached WordNet synonyms for *word* (empty frozenset if unavailable)."""
    return get_service().get_synonyms(word)


def update_synonym_map(canonical_words: frozenset) -> None:
    """Rebuild the synonym map if *canonical_words* changed (no-op if unchanged)."""
    get_service().update_synonym_map(canonical_words)


def find_canonical(word: str) -> Optional[str]:
    """Return the canonical concept for *word* via WordNet, or None."""
    return get_service().find_canonical(word)


def cache_stats() -> dict:
    """Return WordNet service diagnostic statistics."""
    return get_service().cache_stats()
