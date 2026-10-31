"""
FakeGuard Phase 4 -- ML Credibility Classifier
================================================
TF-IDF + Logistic Regression text classifier with:

  * joblib persistence (``models/credibility_model.joblib``)
  * automatic fallback training from a bundled seed corpus when the artifact
    is missing or unreadable (so the service works offline, out of the box)
  * per-prediction feature attribution (coefficient x TF-IDF weight, which is
    exact for a linear model -- the same quantity SHAP reports for linear models
    under an independence assumption)
  * a bootstrap-ensemble uncertainty interval (5th-95th percentile of
    probabilities from models trained on resampled data)

HONESTY NOTE: the bundled model is trained on a small synthetic seed corpus
(see ml_seed_data.py), NOT on WELFake / ISOT.  It learns stylistic cues of
sensational writing; it cannot check facts.  Use ``train_from_csv`` with a real
dataset for production-grade quality.  ``model_info()`` reports the training
source so API consumers can see exactly what they are getting.

Scores: ``credible_probability`` is P(credible-style text) in [0, 1].
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("fakeguard.ml")

MODEL_DIR = Path(__file__).parent / "models"
MODEL_PATH = Path(os.environ.get("FAKEGUARD_MODEL_PATH", MODEL_DIR / "credibility_model.joblib"))
N_BOOTSTRAP = 15
MIN_TEXT_CHARS = 20

_lock = threading.Lock()
_bundle: Optional[dict] = None


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def _make_vectorizer():
    from sklearn.feature_extraction.text import TfidfVectorizer
    return TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
        max_features=50000,
        stop_words="english",
    )


def _make_classifier():
    from sklearn.linear_model import LogisticRegression
    return LogisticRegression(C=4.0, max_iter=1000, class_weight="balanced")


def train(texts: list, labels: list, source: str = "custom", seed: int = 42) -> dict:
    """Train vectorizer + classifier + bootstrap ensemble. Returns a model bundle."""
    from sklearn.model_selection import cross_val_score

    y = np.asarray(labels, dtype=int)
    if len(texts) != len(y) or len(set(y.tolist())) < 2:
        raise ValueError("Training needs matching texts/labels with both classes present.")

    vec = _make_vectorizer()
    X = vec.fit_transform(texts)
    clf = _make_classifier().fit(X, y)

    cv_acc = None
    try:
        folds = int(min(5, np.bincount(y).min()))
        if folds >= 2:
            cv_acc = float(cross_val_score(_make_classifier(), X, y, cv=folds).mean())
    except Exception as exc:  # pragma: no cover - diagnostic only
        logger.debug("CV skipped: %s", exc)

    rng = np.random.default_rng(seed)
    boots = []
    n = len(y)
    for _ in range(N_BOOTSTRAP):
        for _attempt in range(10):
            idx = rng.integers(0, n, n)
            if len(set(y[idx].tolist())) == 2:
                boots.append(_make_classifier().fit(X[idx], y[idx]))
                break

    return {
        "vectorizer": vec,
        "classifier": clf,
        "bootstrap": boots,
        "meta": {
            "algorithm": "TF-IDF (1-2 grams) + Logistic Regression + bootstrap ensemble",
            "training_source": source,
            "training_samples": int(n),
            "class_balance": {"credible": int((y == 1).sum()), "unreliable": int((y == 0).sum())},
            "cross_val_accuracy": cv_acc,
            "feature_count": int(X.shape[1]),
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }


def train_seed_model() -> dict:
    from ml_seed_data import CREDIBLE, UNRELIABLE
    texts = CREDIBLE + UNRELIABLE
    labels = [1] * len(CREDIBLE) + [0] * len(UNRELIABLE)
    return train(texts, labels, source="bundled synthetic seed corpus (NOT WELFake/ISOT)")


def train_from_csv(path: str, text_col: str = "text", label_col: str = "label",
                   credible_label: int = 0, save: bool = True) -> dict:
    """
    Train on a real dataset such as WELFake (columns: title,text,label where
    label 1 = FAKE, 0 = REAL -- hence credible_label=0 by default).
    """
    import csv
    texts, labels = [], []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            t = (row.get(text_col) or "").strip()
            if not t or row.get(label_col) in (None, ""):
                continue
            texts.append(t[:5000])
            labels.append(1 if int(float(row[label_col])) == credible_label else 0)
    bundle = train(texts, labels, source=f"csv:{Path(path).name}")
    if save:
        _save(bundle)
    set_bundle(bundle)
    return bundle


def _save(bundle: dict) -> None:
    import joblib
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = MODEL_PATH.with_suffix(".tmp")
    joblib.dump(bundle, tmp)
    os.replace(tmp, MODEL_PATH)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def set_bundle(bundle: Optional[dict]) -> None:
    global _bundle
    with _lock:
        _bundle = bundle


def get_bundle() -> dict:
    """Return the loaded model, loading from disk or regenerating if needed."""
    global _bundle
    with _lock:
        if _bundle is not None:
            return _bundle
        bundle = None
        if MODEL_PATH.is_file():
            try:
                import joblib
                # Trusted local artifact written by this module (joblib uses pickle).
                bundle = joblib.load(MODEL_PATH)
                if not {"vectorizer", "classifier", "meta"} <= set(bundle):
                    raise ValueError("malformed model bundle")
            except Exception as exc:
                logger.warning("Model artifact unreadable (%s); regenerating.", exc)
                bundle = None
        if bundle is None:
            logger.info("Training fallback seed model.")
            bundle = train_seed_model()
            try:
                _save(bundle)
            except Exception as exc:
                logger.warning("Could not persist model (%s); keeping in memory.", exc)
        _bundle = bundle
        return _bundle


# ---------------------------------------------------------------------------
# Inference + explainability
# ---------------------------------------------------------------------------

def predict(text: str, top_k: int = 8) -> dict:
    """
    Classify ``text``.  Never raises for ordinary input.

    Returns dict:
      available, credible_probability (0-1), ml_score (0-100), label,
      confidence (0-1, distance from the decision boundary),
      interval {low, high} (0-1), attributions {supports_credible[], supports_unreliable[]},
      warnings[]
    """
    warnings = []
    text = text or ""
    if len(text.strip()) < MIN_TEXT_CHARS:
        return {
            "available": False, "credible_probability": None, "ml_score": None,
            "label": None, "confidence": None, "interval": None,
            "attributions": {"supports_credible": [], "supports_unreliable": []},
            "warnings": [f"Text too short for ML classification (< {MIN_TEXT_CHARS} chars)."],
        }
    try:
        b = get_bundle()
    except Exception as exc:
        logger.error("ML model unavailable: %s", exc)
        return {
            "available": False, "credible_probability": None, "ml_score": None,
            "label": None, "confidence": None, "interval": None,
            "attributions": {"supports_credible": [], "supports_unreliable": []},
            "warnings": ["ML model is unavailable; rule-based score only."],
        }

    vec, clf = b["vectorizer"], b["classifier"]
    X = vec.transform([text])
    p = float(clf.predict_proba(X)[0][list(clf.classes_).index(1)])

    boot_ps = [float(m.predict_proba(X)[0][list(m.classes_).index(1)]) for m in b.get("bootstrap", [])]
    if boot_ps:
        lo, hi = float(np.percentile(boot_ps, 5)), float(np.percentile(boot_ps, 95))
        lo, hi = min(lo, p), max(hi, p)
    else:
        lo = hi = p

    # Attribution: contribution_i = coef_i * tfidf_i  (log-odds units)
    coefs = clf.coef_[0]
    row = X.tocoo()
    names = vec.get_feature_names_out()
    contribs = [(names[j], float(coefs[j] * v)) for j, v in zip(row.col, row.data)]
    pos = sorted([c for c in contribs if c[1] > 0], key=lambda c: -c[1])[:top_k]
    neg = sorted([c for c in contribs if c[1] < 0], key=lambda c: c[1])[:top_k]

    if X.nnz == 0:
        warnings.append("No vocabulary overlap with the model; prediction is the prior and uninformative.")
    if b["meta"].get("training_samples", 0) < 1000:
        warnings.append("Model trained on a small seed corpus; treat as a stylistic signal, not a fact check.")

    return {
        "available": True,
        "credible_probability": round(p, 4),
        "ml_score": round(p * 100, 1),
        "label": "credible-style" if p >= 0.5 else "unreliable-style",
        "confidence": round(abs(p - 0.5) * 2, 4),
        "interval": {"low": round(lo, 4), "high": round(hi, 4), "method": "bootstrap 5th-95th percentile"},
        "attributions": {
            "supports_credible": [{"token": t, "weight": round(w, 4)} for t, w in pos],
            "supports_unreliable": [{"token": t, "weight": round(w, 4)} for t, w in neg],
        },
        "warnings": warnings,
    }


def model_info() -> dict:
    try:
        b = get_bundle()
    except Exception as exc:
        return {"available": False, "error": "model unavailable"}
    meta = dict(b["meta"])
    meta.update({
        "available": True,
        "bootstrap_members": len(b.get("bootstrap", [])),
        "artifact_present": MODEL_PATH.is_file(),
        "limitations": [
            "Stylistic classifier: detects sensational/misinformation writing style, not factual accuracy.",
            "Bundled weights come from a small synthetic corpus; retrain on WELFake/ISOT for production.",
        ],
    })
    return meta
