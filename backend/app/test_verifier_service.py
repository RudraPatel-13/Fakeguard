"""Unit tests for verifier_service (claims, fact-check registry, domain trust, SSRF guard)."""

import pytest

import verifier_service as v


class TestExtractClaims:
    def test_prefers_assertive_numeric_sentences(self):
        text = ("Wow, amazing day. The ministry announced that 250 schools in Delhi will close on Monday. "
                "Do you agree?")
        claims = v.extract_claims(text)
        assert claims and "250 schools" in claims[0]["text"]
        assert "makes an assertion" in claims[0]["reasons"]

    def test_questions_never_claims(self):
        assert v.extract_claims("Is the earth flat? Who knows what happens next?") == []

    def test_respects_max_and_empty(self):
        assert v.extract_claims("") == [] and v.extract_claims("   ") == []
        text = " ".join(f"Officials said {i} people attended the meeting in Paris." for i in range(10))
        assert len(v.extract_claims(text, max_claims=2)) == 2


class TestCheckClaims:
    def test_known_debunked_claim_is_contradicted(self):
        r = v.check_claims(["5G towers are spreading the coronavirus to people"])
        assert r["overall"] == "contradicted"
        m = r["results"][0]["matches"][0]
        assert m["source"] == "offline_registry" and m["rating"] == "False"

    def test_unknown_claim_is_no_match_with_caveat(self):
        r = v.check_claims(["The council approved the budget on Tuesday"])
        assert r["overall"] == "no_match"
        assert any("does NOT mean" in n for n in r["notes"])

    def test_requires_all_groups(self):
        assert v.check_claims(["5G is a new mobile standard"])["overall"] == "no_match"

    def test_empty_input(self):
        assert v.check_claims([])["overall"] == "unavailable"

    def test_offline_mode_uses_no_network(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("network used in offline mode")
        monkeypatch.setattr(v, "_query_duckduckgo", boom)
        monkeypatch.setattr(v, "_query_google", boom)
        assert v.check_claims(["Moon landing was faked"])["mode"] == "offline"

    def test_online_failure_degrades_gracefully(self, monkeypatch):
        monkeypatch.setenv("FAKEGUARD_ONLINE", "1")

        def fail(_):
            raise RuntimeError("down")
        monkeypatch.setattr(v, "_query_google", fail)
        monkeypatch.setattr(v, "_query_duckduckgo", fail)
        r = v.check_claims(["Vaccines contain microchips for tracking"])
        assert r["mode"] == "online" and r["overall"] == "contradicted"
        assert any("unavailable" in n for n in r["notes"])

    def test_online_matches_are_merged(self, monkeypatch):
        monkeypatch.setenv("FAKEGUARD_ONLINE", "1")
        monkeypatch.setattr(v, "_query_google", lambda c: [
            {"source": "google_fact_check", "publisher": "X", "rating": "Pants on Fire", "url": "u", "claim": c}])
        monkeypatch.setattr(v, "_query_duckduckgo", lambda c: [])
        assert v.check_claims(["Some novel viral claim about a politician"])["overall"] == "contradicted"


class TestDomain:
    @pytest.mark.parametrize("raw,expected", [
        ("https://www.BBC.co.uk/news/x", "bbc.co.uk"), ("reuters.com", "reuters.com"),
        ("http://user@example.com:8080/p", "example.com"),
    ])
    def test_normalize(self, raw, expected):
        assert v.normalize_domain(raw) == expected

    def test_invalid(self):
        assert v.normalize_domain("") is None
        assert v.assess_domain("")["rating"] == "invalid"

    def test_known_high_and_subdomain(self):
        d = v.assess_domain("https://edition.reuters.com/world")
        assert d["known"] and d["trust_score"] >= 90 and d["whois_performed"] is False

    def test_known_unreliable_and_satire(self):
        assert v.assess_domain("infowars.com")["trust_score"] < 15
        assert v.assess_domain("theonion.com")["rating"] == "satire"

    def test_typosquat_flagged(self):
        d = v.assess_domain("https://reuter.com")
        assert not d["known"] and any("Resembles" in f for f in d["flags"])
        assert d["trust_score"] < 40

    def test_suspicious_tld_and_hyphens(self):
        d = v.assess_domain("breaking-news-truth-daily.xyz")
        assert d["trust_score"] < 40 and len(d["flags"]) >= 2

    def test_unknown_clean_domain_is_neutral_and_age_not_invented(self):
        d = v.assess_domain("example-bakery.com")
        assert d["trust_score"] == 50 and d["estimated_domain_age_years"] is None

    def test_gov_bonus(self):
        assert v.assess_domain("health.gov")["trust_score"] > 60


class TestUrlSafety:
    @pytest.mark.parametrize("url", [
        "ftp://example.com/x", "file:///etc/passwd", "javascript:alert(1)", "http://",
        "http://user:pw@example.com/", "not a url",
    ])
    def test_bad_urls_rejected(self, url):
        with pytest.raises(v.UnsafeUrlError):
            v.validate_fetch_url(url)

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/", "http://localhost:8000/", "http://10.0.0.5/", "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://0.0.0.0/",
    ])
    def test_private_targets_blocked(self, url):
        with pytest.raises(v.UnsafeUrlError):
            v.validate_fetch_url(url)

    def test_offline_verify_never_fetches(self, monkeypatch):
        def boom(u):
            raise AssertionError("fetched")
        monkeypatch.setattr(v, "fetch_page_metadata", boom)
        r = v.verify(url="http://127.0.0.1/admin")
        assert r["page"] is None and r["mode"] == "offline"

    def test_online_verify_reports_blocked_url(self, monkeypatch):
        monkeypatch.setenv("FAKEGUARD_ONLINE", "1")
        r = v.verify(url="http://127.0.0.1/admin")
        assert "blocked" in r["page"]["error"]


class TestVerify:
    def test_text_only(self):
        r = v.verify(text="NASA confirms six days of total darkness next week.")
        assert r["fact_check"]["overall"] == "contradicted" and r["domain"] is None

    def test_text_and_url(self):
        r = v.verify(text="The ministry said 40 schools will close.", url="https://bbc.com/x")
        assert r["domain"]["known"] and r["claims"]
