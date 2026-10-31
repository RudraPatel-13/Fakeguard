"""
FakeGuard Phase 4 -- Ensemble Score Fusion
===========================================
Final Trust Score (0-100, higher = more trustworthy):

    Index = clamp( w_rules*Rule_Trust + w_ml*ML_Trust + w_web*Web_Corroboration - Penalties , 0, 100 )

  Rule_Trust = 100 - 100 * rule_suspicion_score / max_total_score
  ML_Trust   = 100 * P(credible-style)           (omitted -> its weight moves to rules)
  Penalties  = forensics (<= 25) + contradicted claim (20) + low-trust source (<= 12)

The weights and penalty ceilings are constants below so they are auditable.
The legacy ``score`` (rule suspicion, higher = worse) is untouched elsewhere.
"""

from __future__ import annotations

from typing import Optional

W_RULES = 0.6
W_ML = 0.4
# With live web corroboration available the three signals are fused:
W3_RULES, W3_ML, W3_WEB = 0.40, 0.25, 0.35
FORENSICS_MAX_PENALTY = 25.0
CLAIM_CONTRADICTED_PENALTY = 20.0
SOURCE_MAX_PENALTY = 12.0
SOURCE_TRUST_FLOOR = 40


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def trust_band(score: float) -> str:
    if score >= 70:
        return "High trust"
    if score >= 40:
        return "Mixed / verify"
    return "Low trust"


def _pct(points: float, cap: float) -> float:
    return _clamp(100.0 * points / cap) if cap else 0.0


def fuse(rule: dict, ml: Optional[dict] = None, forensics_risk: Optional[float] = None,
         fact_check: Optional[dict] = None, domain: Optional[dict] = None,
         web: Optional[dict] = None) -> dict:
    max_score = rule.get("max_score") or 100
    rule_trust = 100.0 - 100.0 * rule["score"] / max_score

    ml_ok = bool(ml and ml.get("available"))
    web_score = None
    if web and web.get("available") and (web.get("corroboration") or {}).get("score") is not None:
        web_score = float(web["corroboration"]["score"])
    web_ok = web_score is not None
    if web_ok:
        w_rules, w_ml, w_web = (W3_RULES, W3_ML, W3_WEB) if ml_ok else (
            W3_RULES / (W3_RULES + W3_WEB), 0.0, W3_WEB / (W3_RULES + W3_WEB))
    else:
        w_rules, w_ml = (W_RULES, W_ML) if ml_ok else (1.0, 0.0)
        w_web = 0.0

    penalties = {"forensics": 0.0, "claim_contradicted": 0.0, "low_trust_source": 0.0}
    if forensics_risk is not None:
        penalties["forensics"] = round(FORENSICS_MAX_PENALTY * _clamp(forensics_risk) / 100.0, 2)
    web_debunked = bool(web and (web.get("corroboration") or {}).get("status") == "debunked")
    if (fact_check and fact_check.get("overall") == "contradicted") or web_debunked:
        penalties["claim_contradicted"] = CLAIM_CONTRADICTED_PENALTY
    if domain and domain.get("trust_score") is not None and domain["trust_score"] < SOURCE_TRUST_FLOOR:
        frac = (SOURCE_TRUST_FLOOR - domain["trust_score"]) / SOURCE_TRUST_FLOOR
        penalties["low_trust_source"] = round(SOURCE_MAX_PENALTY * frac, 2)
    total_pen = sum(penalties.values())

    ml_trust = ml["ml_score"] if ml_ok else 0.0
    base = w_rules * rule_trust + w_ml * ml_trust + w_web * (web_score or 0.0)
    final = _clamp(base - total_pen)

    interval = None
    if ml_ok and ml.get("interval"):
        fixed = w_rules * rule_trust + w_web * (web_score or 0.0) - total_pen
        lo = _clamp(fixed + w_ml * 100 * ml["interval"]["low"])
        hi = _clamp(fixed + w_ml * 100 * ml["interval"]["high"])
        interval = {"low": round(min(lo, final), 1), "high": round(max(hi, final), 1)}

    b = rule.get("breakdown", {})
    caps = rule.get("caps", {})
    axes = {
        "sensationalism": round(_pct(b.get("keywords", 0), caps.get("suspicious_max", 0)), 1),
        "clickbait": round(_pct(b.get("clickbait", 0), caps.get("clickbait_max", 0)), 1),
        "emotional_manipulation": round(_pct(
            b.get("caps", 0) + b.get("exclamation", 0) + b.get("question", 0),
            caps.get("text_pattern_max", 0)), 1),
        "source_risk": (round(100 - domain["trust_score"], 1)
                        if domain and domain.get("trust_score") is not None else None),
        "ml_risk": round(100 - ml["ml_score"], 1) if ml_ok else None,
        "forensic_risk": round(_clamp(forensics_risk), 1) if forensics_risk is not None else None,
        "corroboration_risk": round(100 - web_score, 1) if web_ok else None,
    }

    return {
        "final_score": round(final, 1),
        "band": trust_band(final),
        "interval": interval,
        "components": {
            "rule_trust": round(rule_trust, 1), "ml_trust": round(ml_trust, 1) if ml_ok else None,
            "w_rules": round(w_rules, 3), "w_ml": round(w_ml, 3), "w_web": round(w_web, 3),
            "web_trust": round(web_score, 1) if web_ok else None,
        },
        "penalties": penalties,
        "axes": axes,
        "formula": "Index = w_rules*Rule_Trust + w_ml*ML_Trust + w_web*Web_Corroboration - Penalties",
    }
