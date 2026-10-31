"""Unit tests for fusion.fuse (ensemble score arithmetic)."""

import pytest

import fusion as f

RULE_CLEAN = {"score": 0, "max_score": 100, "breakdown": {}, "caps": {}}
RULE_BAD = {"score": 80, "max_score": 100,
            "breakdown": {"keywords": 30, "clickbait": 30, "caps": 10, "exclamation": 10, "question": 0},
            "caps": {"suspicious_max": 30, "clickbait_max": 30, "text_pattern_max": 25}}


def ML(s, lo=None, hi=None):
    return {"available": True, "ml_score": s,
            "interval": {"low": (s if lo is None else lo) / 100, "high": (s if hi is None else hi) / 100}}


def test_formula_exact():
    assert f.fuse(RULE_BAD, ML(30))["final_score"] == pytest.approx(0.6 * 20 + 0.4 * 30)


def test_weights_sum_to_one():
    assert f.W_RULES + f.W_ML == pytest.approx(1.0)


def test_ml_unavailable_falls_back_to_rules_only():
    r = f.fuse(RULE_BAD, {"available": False})
    assert r["final_score"] == 20 and r["components"]["w_ml"] == 0


def test_forensics_penalty_scaled_and_capped():
    assert f.fuse(RULE_CLEAN, ML(100))["final_score"] == 100
    r = f.fuse(RULE_CLEAN, ML(100), forensics_risk=100)
    assert r["penalties"]["forensics"] == f.FORENSICS_MAX_PENALTY
    assert r["final_score"] == 100 - f.FORENSICS_MAX_PENALTY
    assert f.fuse(RULE_CLEAN, ML(100), forensics_risk=500)["penalties"]["forensics"] == f.FORENSICS_MAX_PENALTY


def test_claim_and_source_penalties():
    r = f.fuse(RULE_CLEAN, ML(100), fact_check={"overall": "contradicted"}, domain={"trust_score": 0})
    assert r["penalties"]["claim_contradicted"] == f.CLAIM_CONTRADICTED_PENALTY
    assert r["penalties"]["low_trust_source"] == f.SOURCE_MAX_PENALTY
    assert f.fuse(RULE_CLEAN, ML(100), domain={"trust_score": 80})["penalties"]["low_trust_source"] == 0


def test_clamped_to_range():
    r = f.fuse(RULE_BAD, ML(0), forensics_risk=100, fact_check={"overall": "contradicted"},
               domain={"trust_score": 0})
    assert r["final_score"] == 0


def test_interval_contains_final_and_is_ordered():
    r = f.fuse(RULE_BAD, ML(40, 20, 60), forensics_risk=20)
    assert r["interval"]["low"] <= r["final_score"] <= r["interval"]["high"]
    assert r["interval"]["low"] < r["interval"]["high"]


def test_axes():
    ax = f.fuse(RULE_BAD, ML(25), domain={"trust_score": 10})["axes"]
    assert ax["sensationalism"] == 100 and ax["clickbait"] == 100
    assert ax["emotional_manipulation"] == 80 and ax["source_risk"] == 90 and ax["ml_risk"] == 75
    assert ax["forensic_risk"] is None


@pytest.mark.parametrize("score,band", [(100, "High trust"), (70, "High trust"), (69.9, "Mixed / verify"),
                                         (40, "Mixed / verify"), (39.9, "Low trust"), (0, "Low trust")])
def test_bands(score, band):
    assert f.trust_band(score) == band
