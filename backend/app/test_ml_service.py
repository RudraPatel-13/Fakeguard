"""Unit tests for ml_service (TF-IDF + LogisticRegression credibility model)."""

import csv

import pytest

import ml_service

SENSATIONAL = ("SHOCKING!!! Secret miracle cure EXPOSED, doctors hate it, "
               "share now before they delete this bombshell!!!")
SOBER = ("The central bank held interest rates steady on Wednesday, officials said "
         "in a statement released after the meeting.")


@pytest.fixture(autouse=True)
def fresh_model(tmp_path, monkeypatch):
    monkeypatch.setattr(ml_service, "MODEL_PATH", tmp_path / "m.joblib")
    ml_service.set_bundle(None)
    yield
    ml_service.set_bundle(None)


class TestFallbackGeneration:
    def test_missing_artifact_triggers_training_and_persists(self):
        assert not ml_service.MODEL_PATH.exists()
        ml_service.predict(SOBER)
        assert ml_service.MODEL_PATH.is_file()

    def test_artifact_roundtrip_is_reused(self):
        ml_service.predict(SOBER)
        first = ml_service.get_bundle()["meta"]["trained_at"]
        ml_service.set_bundle(None)
        assert ml_service.get_bundle()["meta"]["trained_at"] == first

    def test_corrupt_artifact_regenerates(self):
        ml_service.MODEL_PATH.write_bytes(b"not a joblib file")
        assert ml_service.predict(SOBER)["available"] is True


class TestPredict:
    def test_sensational_scores_lower_than_sober(self):
        assert ml_service.predict(SENSATIONAL)["ml_score"] < ml_service.predict(SOBER)["ml_score"]

    def test_labels(self):
        assert ml_service.predict(SENSATIONAL)["label"] == "unreliable-style"
        assert ml_service.predict(SOBER)["label"] == "credible-style"

    def test_probability_and_score_ranges(self):
        r = ml_service.predict(SOBER)
        assert 0 <= r["credible_probability"] <= 1
        assert r["ml_score"] == pytest.approx(r["credible_probability"] * 100, abs=0.1)
        assert 0 <= r["confidence"] <= 1

    def test_interval_brackets_point_estimate(self):
        r = ml_service.predict(SENSATIONAL)
        assert r["interval"]["low"] <= r["credible_probability"] <= r["interval"]["high"]

    def test_deterministic(self):
        assert ml_service.predict(SOBER) == ml_service.predict(SOBER)

    @pytest.mark.parametrize("text", ["", "   ", "hi", None])
    def test_short_or_empty_is_unavailable_not_error(self, text):
        r = ml_service.predict(text)
        assert r["available"] is False and r["ml_score"] is None and r["warnings"]

    def test_no_vocabulary_overlap_warns(self):
        r = ml_service.predict("zzzzqx qqqwwweee rrrttyyy uuuiiiooo ppp")
        assert r["available"] is True
        assert any("vocabulary" in w for w in r["warnings"])


class TestExplainability:
    def test_attributions_have_expected_signs_and_tokens(self):
        a = ml_service.predict(SENSATIONAL)["attributions"]
        assert a["supports_unreliable"]
        assert all(x["weight"] < 0 for x in a["supports_unreliable"])
        assert all(x["weight"] > 0 for x in a["supports_credible"])
        tokens = {x["token"] for x in a["supports_unreliable"]}
        assert tokens & {"secret", "shocking", "exposed", "miracle", "bombshell", "delete"}

    def test_top_k_limit(self):
        a = ml_service.predict(SENSATIONAL, top_k=2)["attributions"]
        assert len(a["supports_unreliable"]) <= 2 and len(a["supports_credible"]) <= 2

    def test_contributions_reconstruct_logit(self):
        """sum(coef*tfidf) + intercept must equal the model decision function."""
        b = ml_service.get_bundle()
        X = b["vectorizer"].transform([SENSATIONAL])
        logit = float(X.dot(b["classifier"].coef_[0])[0] + b["classifier"].intercept_[0])
        assert logit == pytest.approx(float(b["classifier"].decision_function(X)[0]), abs=1e-9)


class TestTraining:
    def test_train_requires_both_classes(self):
        with pytest.raises(ValueError):
            ml_service.train(["aaa bbb ccc", "ddd eee fff"], [1, 1])

    def test_train_from_csv_welfake_layout(self, tmp_path):
        rows = ([("good", "Officials said the budget was approved on Monday.", 0)] * 6
                + [("bad", "SHOCKING secret hoax exposed share now!!!", 1)] * 6)
        p = tmp_path / "d.csv"
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["title", "text", "label"])
            w.writerows(rows)
        b = ml_service.train_from_csv(str(p), save=False)
        assert b["meta"]["training_samples"] == 12
        assert ml_service.predict("SHOCKING secret hoax exposed share now!!!")["label"] == "unreliable-style"


class TestModelInfo:
    def test_fields(self):
        i = ml_service.model_info()
        assert i["available"] and i["training_samples"] > 0
        assert "NOT WELFake" in i["training_source"]
        assert i["limitations"]
