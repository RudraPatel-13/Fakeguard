"""
FakeGuard Phase 3 -- Keyword Library Loader
===========================================

Responsibilities (and only these):
  - Resolve the keyword JSON path relative to this module (never the CWD).
  - Load and strictly validate the JSON on first access and on every mtime change.
  - Cache the last successfully validated configuration as an immutable value.
  - Hot-reload when the file changes, without restarting FastAPI.
  - Raise a specific KeywordLibraryError subclass on every failure mode;
    never silently return empty lists, zero weights, or stale data.

Not a responsibility of this module:
  - Article text analysis  -> analyzer.py
  - HTTP routing           -> main.py
  - Exposing filesystem paths or Python tracebacks to the frontend
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Default library path -- resolved relative to *this file*, not the CWD.
# Works regardless of where uvicorn is launched from.
# ---------------------------------------------------------------------------
_DEFAULT_LIBRARY_PATH: Path = (
    Path(__file__).parent / "keyword_library" / "keywords.json"
)


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------

class KeywordLibraryError(Exception):
    """Base class for all keyword library problems."""


class KeywordLibraryFileError(KeywordLibraryError):
    """The library file could not be found or read from disk."""


class KeywordLibraryParseError(KeywordLibraryError):
    """The library file exists but contains invalid JSON."""


class KeywordLibraryValidationError(KeywordLibraryError):
    """The JSON parsed successfully but fails schema or value validation."""


# ---------------------------------------------------------------------------
# Immutable configuration dataclasses
# frozen=True makes every instance write-protected at the Python level.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SuspiciousKeywordConfig:
    """Suspicious-keyword scoring rules, loaded from the JSON library."""
    words: frozenset                   # normalised lowercase; frozenset is immutable
    points_per_distinct_keyword: int
    max_contribution: int


@dataclass(frozen=True)
class ClickbaitPhrasesConfig:
    """Clickbait-phrase scoring rules, loaded from the JSON library."""
    phrases: tuple                     # normalised lowercase; tuple is immutable
    points_per_phrase: int
    max_contribution: int


@dataclass(frozen=True)
class TextPatternConfig:
    """Text-pattern rule settings (caps ratio, punctuation counts)."""
    caps_ratio_threshold: float
    caps_points: int
    exclamation_min_count: int
    exclamation_points: int
    question_min_count: int
    question_points: int


@dataclass(frozen=True)
class ClassificationThreshold:
    """A single labelled score band (inclusive min, inclusive max)."""
    label: str
    min_score: int
    max_score: int


@dataclass(frozen=True)
class KeywordConfig:
    """
    Complete, validated, immutable snapshot of the keyword library.

    Returned by KeywordLoader.get_config().  Because every field uses
    immutable types (frozenset, tuple, frozen dataclass), callers cannot
    accidentally corrupt the cached copy held by the loader.
    """
    version: str
    suspicious_keywords: SuspiciousKeywordConfig
    clickbait_phrases: ClickbaitPhrasesConfig
    text_patterns: TextPatternConfig
    max_total_score: int
    thresholds: tuple                  # tuple[ClassificationThreshold, ...]


# ---------------------------------------------------------------------------
# Internal validation helpers (all raise KeywordLibraryValidationError)
# ---------------------------------------------------------------------------

def _require_key(obj: dict, key: str, context: str) -> object:
    """Return obj[key]; raise KeywordLibraryValidationError when absent."""
    if key not in obj:
        raise KeywordLibraryValidationError(
            f"Missing required field {key!r} in {context}."
        )
    return obj[key]


def _require_positive_int(value: object, field: str) -> int:
    """
    Require a genuine Python int that is strictly > 0.
    Explicitly rejects bool (bool is a subclass of int in Python).
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise KeywordLibraryValidationError(
            f"{field!r} must be a positive integer; got {value!r}."
        )
    return value


def _require_non_negative_int(value: object, field: str) -> int:
    """Require a genuine Python int >= 0."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise KeywordLibraryValidationError(
            f"{field!r} must be a non-negative integer; got {value!r}."
        )
    return value


def _require_float_between(
    value: object, field: str, lo: float, hi: float
) -> float:
    """Require a numeric value strictly between lo and hi (exclusive bounds)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise KeywordLibraryValidationError(
            f"{field!r} must be a number; got {value!r}."
        )
    fv = float(value)
    if not (lo < fv < hi):
        raise KeywordLibraryValidationError(
            f"{field!r} must be strictly between {lo} and {hi}; got {fv}."
        )
    return fv


def _normalize_string(s: object, field: str) -> str:
    """
    Strip surrounding whitespace and lower-case a string entry.
    Raises KeywordLibraryValidationError if not a string or empty after normalization.
    """
    if not isinstance(s, str):
        raise KeywordLibraryValidationError(
            f"Every entry in {field!r} must be a string; "
            f"got {type(s).__name__!r}."
        )
    normalized = s.strip().lower()
    if not normalized:
        raise KeywordLibraryValidationError(
            f"An entry in {field!r} is empty or whitespace-only "
            f"after normalization."
        )
    return normalized


# ---------------------------------------------------------------------------
# Core parse-and-validate (pure: no file I/O, no state mutations)
# ---------------------------------------------------------------------------

def _parse_and_validate(raw: object) -> KeywordConfig:
    """
    Accept the Python value produced by json.load/loads and return a fully
    validated, immutable KeywordConfig.

    Pure function -- no side effects, safe to call from tests with dicts.
    Raises KeywordLibraryValidationError on any schema or value problem.
    """
    if not isinstance(raw, dict):
        raise KeywordLibraryValidationError(
            "Top-level JSON value must be an object (dict)."
        )

    # ---- version ----------------------------------------------------------
    version_raw = _require_key(raw, "version", "top level")
    if not isinstance(version_raw, str) or not version_raw.strip():
        raise KeywordLibraryValidationError(
            "'version' must be a non-empty string."
        )
    version = version_raw.strip()

    # ---- suspicious_keywords ----------------------------------------------
    sk_block = _require_key(raw, "suspicious_keywords", "top level")
    if not isinstance(sk_block, dict):
        raise KeywordLibraryValidationError(
            "'suspicious_keywords' must be an object."
        )
    sk_words_raw = _require_key(sk_block, "words", "suspicious_keywords")
    if not isinstance(sk_words_raw, list) or len(sk_words_raw) == 0:
        raise KeywordLibraryValidationError(
            "'suspicious_keywords.words' must be a non-empty array."
        )
    # frozenset deduplicates naturally (normalizer lower-cases first)
    sk_words: frozenset = frozenset(
        _normalize_string(w, "suspicious_keywords.words")
        for w in sk_words_raw
    )

    sk_scoring = _require_key(sk_block, "scoring", "suspicious_keywords")
    if not isinstance(sk_scoring, dict):
        raise KeywordLibraryValidationError(
            "'suspicious_keywords.scoring' must be an object."
        )
    sk_pdk = _require_positive_int(
        _require_key(
            sk_scoring,
            "points_per_distinct_keyword",
            "suspicious_keywords.scoring",
        ),
        "suspicious_keywords.scoring.points_per_distinct_keyword",
    )
    sk_cap = _require_positive_int(
        _require_key(sk_scoring, "max_contribution", "suspicious_keywords.scoring"),
        "suspicious_keywords.scoring.max_contribution",
    )
    if sk_cap < sk_pdk:
        raise KeywordLibraryValidationError(
            f"'suspicious_keywords.scoring.max_contribution' ({sk_cap}) must be "
            f">= points_per_distinct_keyword ({sk_pdk})."
        )

    # ---- clickbait_phrases ------------------------------------------------
    cb_block = _require_key(raw, "clickbait_phrases", "top level")
    if not isinstance(cb_block, dict):
        raise KeywordLibraryValidationError(
            "'clickbait_phrases' must be an object."
        )
    cb_phrases_raw = _require_key(cb_block, "phrases", "clickbait_phrases")
    if not isinstance(cb_phrases_raw, list) or len(cb_phrases_raw) == 0:
        raise KeywordLibraryValidationError(
            "'clickbait_phrases.phrases' must be a non-empty array."
        )
    # Deduplicate while preserving first-occurrence order (order matters
    # for phrase matching: more specific phrases may be listed first).
    _seen: set = set()
    cb_phrases: list = []
    for p in cb_phrases_raw:
        norm = _normalize_string(p, "clickbait_phrases.phrases")
        if norm not in _seen:
            _seen.add(norm)
            cb_phrases.append(norm)

    cb_scoring = _require_key(cb_block, "scoring", "clickbait_phrases")
    if not isinstance(cb_scoring, dict):
        raise KeywordLibraryValidationError(
            "'clickbait_phrases.scoring' must be an object."
        )
    cb_ppp = _require_positive_int(
        _require_key(cb_scoring, "points_per_phrase", "clickbait_phrases.scoring"),
        "clickbait_phrases.scoring.points_per_phrase",
    )
    cb_cap = _require_positive_int(
        _require_key(cb_scoring, "max_contribution", "clickbait_phrases.scoring"),
        "clickbait_phrases.scoring.max_contribution",
    )
    if cb_cap < cb_ppp:
        raise KeywordLibraryValidationError(
            f"'clickbait_phrases.scoring.max_contribution' ({cb_cap}) must be "
            f">= points_per_phrase ({cb_ppp})."
        )

    # ---- text_pattern_rules -----------------------------------------------
    tpr = _require_key(raw, "text_pattern_rules", "top level")
    if not isinstance(tpr, dict):
        raise KeywordLibraryValidationError(
            "'text_pattern_rules' must be an object."
        )

    ec = _require_key(tpr, "excessive_capitalization", "text_pattern_rules")
    if not isinstance(ec, dict):
        raise KeywordLibraryValidationError(
            "'text_pattern_rules.excessive_capitalization' must be an object."
        )
    caps_threshold = _require_float_between(
        _require_key(
            ec, "uppercase_ratio_threshold", "excessive_capitalization"
        ),
        "excessive_capitalization.uppercase_ratio_threshold",
        0.0,
        1.0,
    )
    caps_pts = _require_positive_int(
        _require_key(ec, "points", "excessive_capitalization"),
        "excessive_capitalization.points",
    )

    em = _require_key(tpr, "excessive_exclamation_marks", "text_pattern_rules")
    if not isinstance(em, dict):
        raise KeywordLibraryValidationError(
            "'text_pattern_rules.excessive_exclamation_marks' must be an object."
        )
    excl_min = _require_positive_int(
        _require_key(em, "min_count", "excessive_exclamation_marks"),
        "excessive_exclamation_marks.min_count",
    )
    excl_pts = _require_positive_int(
        _require_key(em, "points", "excessive_exclamation_marks"),
        "excessive_exclamation_marks.points",
    )

    qm = _require_key(tpr, "excessive_question_marks", "text_pattern_rules")
    if not isinstance(qm, dict):
        raise KeywordLibraryValidationError(
            "'text_pattern_rules.excessive_question_marks' must be an object."
        )
    quest_min = _require_positive_int(
        _require_key(qm, "min_count", "excessive_question_marks"),
        "excessive_question_marks.min_count",
    )
    quest_pts = _require_positive_int(
        _require_key(qm, "points", "excessive_question_marks"),
        "excessive_question_marks.points",
    )

    # ---- scoring ----------------------------------------------------------
    scoring_block = _require_key(raw, "scoring", "top level")
    if not isinstance(scoring_block, dict):
        raise KeywordLibraryValidationError("'scoring' must be an object.")
    max_total = _require_positive_int(
        _require_key(scoring_block, "max_total_score", "scoring"),
        "scoring.max_total_score",
    )

    # ---- classification thresholds ----------------------------------------
    cls_block = _require_key(raw, "classification", "top level")
    if not isinstance(cls_block, dict):
        raise KeywordLibraryValidationError("'classification' must be an object.")
    thresholds_raw = _require_key(cls_block, "thresholds", "classification")
    if not isinstance(thresholds_raw, list) or len(thresholds_raw) == 0:
        raise KeywordLibraryValidationError(
            "'classification.thresholds' must be a non-empty array."
        )

    thresholds: list = []
    for i, t in enumerate(thresholds_raw):
        ctx = f"classification.thresholds[{i}]"
        if not isinstance(t, dict):
            raise KeywordLibraryValidationError(f"{ctx!r} must be an object.")
        label_raw = _require_key(t, "label", ctx)
        if not isinstance(label_raw, str) or not label_raw.strip():
            raise KeywordLibraryValidationError(
                f"'{ctx}.label' must be a non-empty string."
            )
        mn = _require_non_negative_int(
            _require_key(t, "min", ctx), f"{ctx}.min"
        )
        mx = _require_non_negative_int(
            _require_key(t, "max", ctx), f"{ctx}.max"
        )
        if mn > mx:
            raise KeywordLibraryValidationError(
                f"{ctx!r} has min ({mn}) > max ({mx})."
            )
        thresholds.append(
            ClassificationThreshold(
                label=label_raw.strip(),
                min_score=mn,
                max_score=mx,
            )
        )

    # Verify contiguous, non-overlapping coverage of [0, max_total_score].
    # Expected: thresholds[0].min == 0; each next .min == prev .max + 1;
    # last .max == max_total_score.
    prev_max = -1
    for i, t in enumerate(thresholds):
        if t.min_score != prev_max + 1:
            raise KeywordLibraryValidationError(
                f"Classification thresholds are not contiguous: "
                f"thresholds[{i}].min={t.min_score} does not immediately "
                f"follow previous max={prev_max} (expected {prev_max + 1})."
            )
        prev_max = t.max_score

    if prev_max != max_total:
        raise KeywordLibraryValidationError(
            f"Classification thresholds must cover 0 to {max_total} exactly; "
            f"the last threshold ends at {prev_max}."
        )

    return KeywordConfig(
        version=version,
        suspicious_keywords=SuspiciousKeywordConfig(
            words=sk_words,
            points_per_distinct_keyword=sk_pdk,
            max_contribution=sk_cap,
        ),
        clickbait_phrases=ClickbaitPhrasesConfig(
            phrases=tuple(cb_phrases),
            points_per_phrase=cb_ppp,
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
        max_total_score=max_total,
        thresholds=tuple(thresholds),
    )


# ---------------------------------------------------------------------------
# KeywordLoader -- file I/O, mtime hot-reload, thread-safe caching
# ---------------------------------------------------------------------------

class KeywordLoader:
    """
    Thread-safe loader that owns the keyword library lifecycle:

    1. Resolves the file path relative to this module (not the CWD).
    2. Reads and validates the file eagerly at construction so any startup
       misconfiguration is caught immediately before FastAPI accepts requests.
    3. Checks the file's mtime on every get_config() call and reloads if it
       has changed -- no polling thread, no watchdog dependency.
    4. Caches the last successfully validated config in a frozen dataclass.
    5. On failure (missing file, bad JSON, failed validation), raises a
       KeywordLibraryError subclass.  Never silently returns empty lists,
       default weights, or data from a now-invalid file.
    """

    def __init__(self, library_path: Path | None = None) -> None:
        self._path: Path = (library_path or _DEFAULT_LIBRARY_PATH).resolve()
        self._config: KeywordConfig | None = None
        self._mtime: float | None = None
        self._lock = threading.Lock()
        # Eager load: surfaces problems immediately at startup.
        self._do_reload()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def get_config(self) -> KeywordConfig:
        """
        Return the current valid KeywordConfig, reloading if the file changed.

        Raises:
          KeywordLibraryFileError       -- file missing or unreadable
          KeywordLibraryParseError      -- invalid JSON
          KeywordLibraryValidationError -- schema / value problem
        """
        with self._lock:
            self._reload_if_changed()
            return self._config  # type: ignore[return-value]

    @property
    def library_path(self) -> Path:
        """
        Absolute resolved path of the library file.
        Available for server-side logging; never forwarded to the frontend.
        """
        return self._path

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _current_mtime(self) -> float:
        try:
            return os.path.getmtime(self._path)
        except OSError as exc:
            raise KeywordLibraryFileError(
                f"Keyword library file not accessible: {self._path.name}"
            ) from exc

    def _reload_if_changed(self) -> None:
        """Compare stored mtime to current; reload only on change."""
        current_mtime = self._current_mtime()
        if self._mtime is None or current_mtime != self._mtime:
            self._do_reload()

    def _do_reload(self) -> None:
        """
        Read -> parse -> validate; commit to cache only on full success.

        When the file changes to something invalid, this method raises and
        leaves self._config / self._mtime at their last-good values.
        However, because _reload_if_changed detected a mtime change, it
        will call _do_reload again on the next get_config() -- so callers
        always get either a fresh valid config or a clear exception.  They
        never silently receive the previous config after a detected change.
        """
        # Step 1: read raw bytes (avoids encoding ambiguity)
        try:
            raw_bytes = self._path.read_bytes()
        except FileNotFoundError:
            raise KeywordLibraryFileError(
                f"Keyword library file not found: {self._path.name}"
            )
        except OSError as exc:
            raise KeywordLibraryFileError(
                f"Cannot read keyword library ({self._path.name}): {exc}"
            ) from exc

        # Step 2: parse JSON
        try:
            raw = json.loads(raw_bytes)
        except json.JSONDecodeError as exc:
            raise KeywordLibraryParseError(
                f"Invalid JSON in keyword library "
                f"(line {exc.lineno}, col {exc.colno}): {exc.msg}"
            ) from exc

        # Step 3: validate schema and values
        config = _parse_and_validate(raw)  # raises KeywordLibraryValidationError

        # Step 4: atomic commit (only reached on full success)
        self._config = config
        self._mtime = os.path.getmtime(self._path)


# ---------------------------------------------------------------------------
# Module-level singleton -- primary entry point for analyzer.py
# ---------------------------------------------------------------------------

_singleton: "KeywordLoader | None" = None
_singleton_lock = threading.Lock()


def get_loader(library_path: Path | None = None) -> KeywordLoader:
    """
    Return the module-level singleton KeywordLoader.

    Initialised lazily on the first call.  Passing library_path on the first
    call overrides the default path (useful for integration tests or alternate
    deployments).  Subsequent calls ignore library_path.
    """
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = KeywordLoader(library_path)
    return _singleton


def get_config(library_path: Path | None = None) -> KeywordConfig:
    """
    Convenience shortcut: return the current valid config from the singleton.
    This is the primary call analyzer.py will make in the next phase.
    """
    return get_loader(library_path).get_config()
