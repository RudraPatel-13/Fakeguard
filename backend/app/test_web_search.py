"""Tests for web_search_service (all HTTP mocked via the _http_get choke point), fusion with web, and endpoints."""

import io

import pytest
from PIL import Image
from starlette.testclient import TestClient

import fusion
import web_search_service as w
from main import app


def item(title, pub, src, date="Mon, 03 Mar 2025 10:00:00 GMT"):
    return (f"<item><title>{title} - {pub}</title><link>https://news.google.com/rss/articles/{abs(hash(title))}</link>"
            f"<pubDate>{date}</pubDate><description>&lt;a href=\"x\"&gt;{title}&lt;/a&gt; {pub}</description>"
            f"<source url=\"{src}\">{pub}</source></item>")


def feed(*items):
    return f"<?xml version='1.0'?><rss><channel>{''.join(items)}</channel></rss>"


def serve(monkeypatch, news="", factcheck=None):
    """Route feed requests: queries ending in 'fact check' get ``factcheck``."""
    factcheck = news if factcheck is None else factcheck

    def fake(url):
        return factcheck if "fact+check" in url else news
    monkeypatch.setattr(w, "_http_get", fake)


BOE = "Bank of England holds interest rates steady citing stable inflation"
CLAIM = "The Bank of England held interest rates steady on Thursday citing stable inflation"


class TestParsing:
    def test_rss_fields(self):
        r = w.parse_rss(feed(item(BOE, "Reuters", "https://www.reuters.com")))[0]
        assert r["title"] == BOE and r["publisher"] == "Reuters"
        assert r["published"].startswith("2025-03-03T10:00")
        assert r["source_url"] == "https://www.reuters.com" and r["url"].startswith("https://")

    def test_rejects_dtd_and_non_http_links(self):
        with pytest.raises(ValueError):
            w.parse_rss('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><rss/>')
        bad = "<rss><channel><item><title>x - Y</title><link>javascript:alert(1)</link></item></channel></rss>"
        assert w.parse_rss(bad) == []

    def test_query_building_drops_filler_and_keeps_5g(self):
        q = w.build_query("URGENT!!! Share now: 5G towers spread the coronavirus, officials say.")
        assert "5g" in q and "urgent" not in q and "share" not in q


class TestCorroboration:
    def test_high_when_multiple_verified_outlets(self, monkeypatch):
        serve(monkeypatch, feed(
            item(BOE, "Reuters", "https://www.reuters.com"),
            item("Interest rates held by Bank of England as inflation stable", "BBC", "https://www.bbc.com"),
            item("Bank of England keeps interest rates steady, inflation stable", "The Guardian", "https://www.theguardian.com"),
        ))
        r = w.verify_web(CLAIM)
        c = r["corroboration"]
        assert r["mode"] == "live" and r["available"] and c["level"] == "High" and c["score"] >= 80
        assert set(c["verified_outlets"]) == {"Reuters", "BBC", "The Guardian"}
        assert all(x["tier"] == "verified_outlet" for x in r["results"])

    def test_single_outlet_is_low(self, monkeypatch):
        serve(monkeypatch, feed(item(BOE, "Reuters", "https://www.reuters.com")))
        c = w.verify_web(CLAIM)["corroboration"]
        assert c["level"] == "Low / Unverified"
        assert c["score"] == 30 and c["status"] == "unverified"

    def test_two_outlets_is_medium(self, monkeypatch):
        serve(monkeypatch, feed(item(BOE, "Reuters", "https://www.reuters.com"),
                                item(BOE + " today", "BBC", "https://www.bbc.com")))
        c = w.verify_web(CLAIM)["corroboration"]
        assert c["level"] == "Medium" and c["status"] == "partial"

    def test_same_outlet_counted_once(self, monkeypatch):
        serve(monkeypatch, feed(item(BOE, "Reuters", "https://www.reuters.com"),
                                item(BOE + " again", "Reuters", "https://www.reuters.com")))
        assert w.verify_web(CLAIM)["corroboration"]["score"] == 30

    def test_irrelevant_results_ignored(self, monkeypatch):
        serve(monkeypatch, feed(item("Local team wins cricket final", "BBC", "https://www.bbc.com")))
        r = w.verify_web(CLAIM)
        assert r["results"] == [] and r["corroboration"]["status"] == "unverified"

    def test_wrong_entity_filtered(self, monkeypatch):
        serve(monkeypatch, feed(item("US Fed holds interest rates steady, citing inflation", "Al Jazeera",
                                     "https://www.aljazeera.com")))
        assert w.verify_web(CLAIM)["results"] == []

    def test_unranked_blog_and_unreliable_do_not_corroborate(self, monkeypatch):
        serve(monkeypatch, feed(item(BOE, "Random Blog", "https://randomblog.example"),
                                item(BOE, "Infowars", "https://www.infowars.com")))
        r = w.verify_web(CLAIM)
        assert r["corroboration"]["score"] <= 4
        tiers = {x["publisher"]: x["tier"] for x in r["results"]}
        assert tiers["Random Blog"] == "unranked"


class TestFactCheckers:
    def test_debunked_factcheck_caps_score_and_marks_status(self, monkeypatch):
        news = feed(item("5G towers spread the coronavirus, viral post says", "BBC", "https://www.bbc.com"),
                    item("5G towers spread the coronavirus claim spreads online", "CNN", "https://www.cnn.com"),
                    item("5G towers spread the coronavirus: shock", "Reuters", "https://www.reuters.com"))
        fc = feed(item("Fact Check: False claim that 5G towers spread the coronavirus", "Snopes", "https://www.snopes.com"))
        serve(monkeypatch, news, fc)
        r = w.verify_web("Officials say 5G towers spread the coronavirus.")
        c = r["corroboration"]
        assert c["status"] == "debunked" and c["score"] <= 15
        assert r["fact_checks"][0]["fact_check_verdict"] == "debunked"
        assert r["fact_checks"][0]["tier"] == "fact_checker"

    def test_outlets_disputing_claim_are_not_counted_as_support(self, monkeypatch):
        serve(monkeypatch, feed(
            item("Bogus conspiracy theories link 5G towers to coronavirus", "CNBC", "https://www.cnbc.com"),
            item("YouTube limits false claims that 5G towers spread coronavirus", "CNN", "https://www.cnn.com")))
        r = w.verify_web("5G towers spread the coronavirus")
        c = r["corroboration"]
        assert c["status"] == "debunked" and not c["verified_outlets"] and len(c["disputing_outlets"]) == 2

    def test_supportive_factcheck_adds_points(self, monkeypatch):
        fc = feed(item("Fact Check: True, Bank of England held interest rates steady citing stable inflation",
                       "PolitiFact", "https://www.politifact.com"))
        serve(monkeypatch, feed(item(BOE, "Reuters", "https://www.reuters.com")), fc)
        r = w.verify_web(CLAIM)
        assert r["corroboration"]["score"] == 40
        assert r["fact_checks"][0]["fact_check_verdict"] == "supported"

    @pytest.mark.parametrize("title,verdict", [
        ("Misleading: video does not show the event", "debunked"),
        ("Fact check: Is this photo real?", "unclear"),
    ])
    def test_verdict_keywords(self, title, verdict):
        c = w.classify({"title": title, "publisher": "Alt News", "source_url": "https://www.altnews.in",
                        "url": "https://x.y", "snippet": "", "published": None}, ["photo"])
        assert c["tier"] == "fact_checker" and c["fact_check_verdict"] == verdict


class TestFallbackAndCache:
    def test_network_down_gives_offline_simulation(self):
        r = w.verify_web(CLAIM)      # conftest blocks network
        assert r["mode"] == "offline" and r["simulation"] and r["available"] is False
        assert r["corroboration"]["score"] is None and "Offline" in r["corroboration"]["explanation"]

    def test_offline_registry_still_flags_known_hoax(self):
        r = w.verify_web("NASA confirms six days of total darkness next week")
        assert r["corroboration"]["status"] == "debunked" and r["corroboration"]["score"] == 10

    def test_one_provider_failing_degrades_gracefully(self, monkeypatch):
        good = feed(item(BOE, "Reuters", "https://www.reuters.com"))

        def flaky(url):
            if "fact+check" in url:
                raise TimeoutError("slow")
            return good
        monkeypatch.setattr(w, "_http_get", flaky)
        r = w.verify_web(CLAIM)
        assert r["mode"] == "live" and any("provider failed" in n for n in r["notes"])

    def test_malformed_feed_is_handled(self, monkeypatch):
        serve(monkeypatch, "<<not xml")
        assert w.verify_web(CLAIM)["mode"] == "offline"

    def test_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("FAKEGUARD_OFFLINE", "1")
        monkeypatch.setattr(w, "_http_get", lambda u: (_ for _ in ()).throw(AssertionError("called")))
        assert w.verify_web(CLAIM)["mode"] == "offline"

    def test_too_little_text_is_offline_not_error(self):
        assert w.verify_web("ok")["available"] is False

    def test_cache_avoids_second_request(self, monkeypatch):
        calls = []

        def counting(url):
            calls.append(url)
            return feed(item(BOE, "Reuters", "https://www.reuters.com"))
        monkeypatch.setattr(w, "_http_get", counting)
        w.verify_web(CLAIM)
        n = len(calls)
        w.verify_web(CLAIM)
        assert len(calls) == n


class TestFusionWithWeb:
    RULE = {"score": 0, "max_score": 100, "breakdown": {}, "caps": {}}
    ML = {"available": True, "ml_score": 100, "interval": {"low": 1.0, "high": 1.0}}

    @staticmethod
    def web(score, status="corroborated"):
        return {"available": True, "corroboration": {"score": score, "status": status}}

    def test_three_way_weights(self):
        r = fusion.fuse(self.RULE, self.ML, web=self.web(0, "unverified"))
        assert r["final_score"] == pytest.approx(100 * (0.40 + 0.25))
        assert r["components"]["w_web"] == 0.35

    def test_web_unavailable_keeps_two_way(self):
        r = fusion.fuse(self.RULE, self.ML, web={"available": False, "corroboration": {"score": None}})
        assert r["final_score"] == 100 and r["components"]["w_web"] == 0
        assert r["axes"]["corroboration_risk"] is None

    def test_debunked_web_applies_claim_penalty_once(self):
        r = fusion.fuse(self.RULE, self.ML, fact_check={"overall": "contradicted"}, web=self.web(10, "debunked"))
        assert r["penalties"]["claim_contradicted"] == fusion.CLAIM_CONTRADICTED_PENALTY

    def test_weights_renormalised_without_ml(self):
        r = fusion.fuse(self.RULE, {"available": False}, web=self.web(100))
        assert r["final_score"] == 100 and r["components"]["w_ml"] == 0
        assert r["components"]["w_rules"] + r["components"]["w_web"] == pytest.approx(1.0, abs=0.01)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestEndpoints:
    def test_verify_web_endpoint_live(self, client, monkeypatch):
        serve(monkeypatch, feed(item(BOE, "Reuters", "https://www.reuters.com")))
        j = client.post("/verify-web", json={"text": CLAIM, "url": "https://www.bbc.com/x"}).json()
        assert j["web"]["mode"] == "live" and j["domain"]["known"]

    def test_verify_web_offline_fallback_and_validation(self, client):
        assert client.post("/verify-web", json={"text": CLAIM}).json()["web"]["mode"] == "offline"
        assert client.post("/verify-web", json={"text": "  "}).status_code == 422

    def test_analyze_default_has_no_web(self, client):
        assert client.post("/analyze", json={"text": CLAIM}).json()["web"] is None

    def test_analyze_verify_web_true_fuses_corroboration(self, client, monkeypatch):
        serve(monkeypatch, feed(item(BOE, "Reuters", "https://www.reuters.com"),
                                item(BOE + " now", "BBC", "https://www.bbc.com"),
                                item(BOE + " again", "The Guardian", "https://www.theguardian.com")))
        j = client.post("/analyze?verify_web=true", json={"text": CLAIM}).json()
        assert j["web"]["corroboration"]["level"] == "High"
        assert j["fusion"]["components"]["w_web"] == 0.35 and j["fusion"]["axes"]["corroboration_risk"] < 20
        assert {"score", "classification", "indicators", "word_count"} <= set(j)

    def test_analyze_verify_web_offline_still_200(self, client):
        j = client.post("/analyze?verify_web=true", json={"text": CLAIM}).json()
        assert j["web"]["mode"] == "offline" and j["fusion"]["components"]["w_web"] == 0

    def test_image_pipeline_pipes_ocr_text_to_web(self, client, monkeypatch):
        import pytesseract
        monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.0")
        monkeypatch.setattr(pytesseract, "image_to_string", lambda img, config="": CLAIM)
        serve(monkeypatch, feed(item(BOE, "Reuters", "https://www.reuters.com")))
        buf = io.BytesIO()
        Image.new("RGB", (300, 200), (240, 240, 240)).save(buf, format="PNG")
        files = {"file": ("a.png", buf.getvalue(), "image/png")}
        j = client.post("/analyze-image", files=files).json()
        assert j["web"]["mode"] == "live" and j["web"]["corroboration"]["score"] == 30
        assert j["fusion"]["components"]["w_web"] == 0.35
        j2 = client.post("/analyze-image?verify_web=false", files=files).json()
        assert j2["web"] is None
