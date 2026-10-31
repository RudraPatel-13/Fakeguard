"""
FakeGuard Phase 4 -- Claim Extraction, Fact-Check Lookup & Source Trust
=========================================================================
Three independent capabilities:

  extract_claims(text)         -- pick the most verifiable sentences
  check_claims(claims)         -- cross-reference against fact-check sources
  assess_domain(url_or_domain) -- source reputation from a bundled registry
  fetch_page_metadata(url)     -- (online only) SSRF-guarded title/site lookup

Modes
-----
Offline (default): claims are matched against a small bundled registry of
widely debunked claims; domains against a small bundled reputation registry.
Online (FAKEGUARD_ONLINE=1): additionally queries the Google Fact Check Tools
API (requires GOOGLE_FACTCHECK_API_KEY) and DuckDuckGo Instant Answer, and
allows fetching a user-supplied URL.  Every network failure degrades silently
to offline results and is reported in ``notes``.

HONESTY NOTES
-------------
* The bundled registries are SMALL SAMPLES curated for this project, not the
  Media Bias/Fact Check database and not a live fact-check feed.
* No WHOIS lookup is performed.  ``estimated_domain_age_years`` is only given
  for registry domains (approximate founding era) and is None otherwise.
* Absence of a match is NOT evidence that a claim is true.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("fakeguard.verifier")

HTTP_TIMEOUT = 6.0
MAX_FETCH_BYTES = 512 * 1024
MAX_REDIRECTS = 3


def online_enabled() -> bool:
    return os.environ.get("FAKEGUARD_ONLINE", "").strip().lower() in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Registries (bundled samples)
# ---------------------------------------------------------------------------

# rating: high | mixed | low | satire | unreliable ; trust 0-100 (project-assigned)
DOMAIN_REGISTRY = {
    "reuters.com":        {"name": "Reuters", "rating": "high", "trust": 94, "bias": "center", "age": "25+"},
    "apnews.com":         {"name": "Associated Press", "rating": "high", "trust": 94, "bias": "center", "age": "20+"},
    "bbc.com":            {"name": "BBC News", "rating": "high", "trust": 90, "bias": "center", "age": "25+"},
    "bbc.co.uk":          {"name": "BBC News", "rating": "high", "trust": 90, "bias": "center", "age": "25+"},
    "npr.org":            {"name": "NPR", "rating": "high", "trust": 88, "bias": "center-left", "age": "25+"},
    "theguardian.com":    {"name": "The Guardian", "rating": "high", "trust": 84, "bias": "center-left", "age": "25+"},
    "nytimes.com":        {"name": "The New York Times", "rating": "high", "trust": 85, "bias": "center-left", "age": "25+"},
    "washingtonpost.com": {"name": "The Washington Post", "rating": "high", "trust": 84, "bias": "center-left", "age": "25+"},
    "wsj.com":            {"name": "The Wall Street Journal", "rating": "high", "trust": 85, "bias": "center-right", "age": "25+"},
    "thehindu.com":       {"name": "The Hindu", "rating": "high", "trust": 82, "bias": "center-left", "age": "20+"},
    "aljazeera.com":      {"name": "Al Jazeera", "rating": "high", "trust": 74, "bias": "center-left", "age": "25+"},
    "snopes.com":         {"name": "Snopes", "rating": "high", "trust": 86, "bias": "center", "age": "25+", "fact_checker": True},
    "politifact.com":     {"name": "PolitiFact", "rating": "high", "trust": 86, "bias": "center-left", "age": "15+", "fact_checker": True},
    "factcheck.org":      {"name": "FactCheck.org", "rating": "high", "trust": 90, "bias": "center", "age": "20+", "fact_checker": True},
    "who.int":            {"name": "World Health Organization", "rating": "high", "trust": 90, "bias": "center", "age": "25+"},
    "nasa.gov":           {"name": "NASA", "rating": "high", "trust": 92, "bias": "center", "age": "25+"},
    "foxnews.com":        {"name": "Fox News", "rating": "mixed", "trust": 58, "bias": "right", "age": "25+"},
    "dailymail.co.uk":    {"name": "Daily Mail", "rating": "low", "trust": 40, "bias": "right", "age": "20+"},
    "breitbart.com":      {"name": "Breitbart", "rating": "low", "trust": 32, "bias": "far-right", "age": "15+"},
    "theonion.com":       {"name": "The Onion", "rating": "satire", "trust": 20, "bias": "satire", "age": "25+"},
    "infowars.com":       {"name": "Infowars", "rating": "unreliable", "trust": 6, "bias": "conspiracy", "age": "20+"},
    "naturalnews.com":    {"name": "Natural News", "rating": "unreliable", "trust": 8, "bias": "pseudoscience", "age": "20+"},
    "beforeitsnews.com":  {"name": "Before It's News", "rating": "unreliable", "trust": 8, "bias": "conspiracy", "age": "10+"},
    "worldnewsdailyreport.com": {"name": "World News Daily Report", "rating": "unreliable", "trust": 4, "bias": "fabricated", "age": "10+"},
}

SUSPICIOUS_TLDS = {"xyz", "top", "click", "buzz", "gq", "tk", "ml", "cf", "ga", "work", "loan", "icu", "rest"}
NEWSY_WORDS = ("news", "daily", "times", "post", "herald", "report", "today", "truth", "patriot", "alert")

# Widely debunked claims.  match = token groups; every group needs >=1 hit.
CLAIM_REGISTRY = [
    {"id": "5g-covid", "claim": "5G networks cause or spread COVID-19", "rating": "False",
     "groups": [["5g"], ["covid", "coronavirus", "virus", "pandemic"]],
     "explanation": "Radio waves do not carry viruses; COVID-19 spreads between people and has spread in places without 5G."},
    {"id": "vaccine-microchip", "claim": "Vaccines contain tracking microchips", "rating": "False",
     "groups": [["vaccine", "vaccines", "vaccination", "jab"], ["microchip", "microchips", "chip", "chips", "tracking"]],
     "explanation": "No vaccine ingredient list includes microchips; syringe needles are too small to inject such devices."},
    {"id": "vaccine-autism", "claim": "Vaccines cause autism", "rating": "False",
     "groups": [["vaccine", "vaccines", "mmr"], ["autism", "autistic"]],
     "explanation": "Large studies covering millions of children found no link between vaccines and autism."},
    {"id": "bleach-cure", "claim": "Drinking bleach or disinfectant cures disease", "rating": "False and dangerous",
     "groups": [["bleach", "disinfectant", "chlorine", "mms"], ["cure", "cures", "drink", "drinking", "treat"]],
     "explanation": "Ingesting bleach is poisonous and has caused serious harm."},
    {"id": "moon-hoax", "claim": "The Moon landings were faked", "rating": "False",
     "groups": [["moon"], ["hoax", "faked", "fake", "staged"]],
     "explanation": "Independent evidence (retroreflectors, returned samples, third-party tracking) confirms the landings."},
    {"id": "flat-earth", "claim": "The Earth is flat", "rating": "False",
     "groups": [["flat"], ["earth"]],
     "explanation": "Observations from ships, aircraft, satellites and eclipses show the Earth is an oblate spheroid."},
    {"id": "nasa-darkness", "claim": "NASA confirms days of total darkness", "rating": "False",
     "groups": [["nasa"], ["darkness", "dark"], ["days", "six", "15", "fifteen", "week"]],
     "explanation": "A recurring hoax; no such solar event has been predicted by any space agency."},
    {"id": "forward-cash", "claim": "Forwarding a message earns free money, data or phones", "rating": "False",
     "groups": [["forward", "share", "send"], ["free", "win", "reward", "cash", "recharge", "phone", "data"]],
     "explanation": "Chain-message giveaways are a staple of scams and engagement bait."},
    {"id": "miracle-cure", "claim": "A single miracle remedy cures cancer or diabetes", "rating": "Unproven / misleading",
     "groups": [["miracle", "cure", "cures", "cured"], ["cancer", "diabetes", "disease", "tumor"]],
     "explanation": "No single natural remedy has been shown to cure cancer or diabetes; claims of suppressed cures are a common marketing trick."},
    {"id": "elections-rigged-generic", "claim": "Election results were rigged without evidence", "rating": "Unsupported",
     "groups": [["election", "elections", "vote", "votes"], ["rigged", "stolen", "fraud"]],
     "explanation": "Blanket fraud claims are unsupported unless backed by evidence upheld by courts or audits; check official results."},
]

_STOP = set("the a an of to in on for and or is are was were be been that this it with as by at from has have had will would not no".split())

_ASSERT_VERBS = re.compile(
    r"\b(says?|said|claims?|claimed|confirms?|confirmed|announced?|reports?|reported|"
    r"proves?|proved|reveals?|revealed|found|died|killed|banned|approved|declared|"
    r"will|cause[sd]?|cures?|increase[sd]?|decrease[sd]?|according to)\b", re.I)


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

def extract_claims(text: str, max_claims: int = 3) -> list:
    """
    Heuristically choose the sentences most likely to carry checkable assertions.

    Score = digits + named-entity-like capitals + assertion verbs - question/
    exclamatory-opinion penalties.  Returns [{"text", "score", "reasons"}].
    """
    if not text or not text.strip():
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    scored = []
    for i, s in enumerate(sentences):
        words = s.split()
        if len(words) < 4 or len(words) > 60:
            continue
        reasons, score = [], 0.0
        if s.endswith("?"):
            continue
        if re.search(r"\d", s):
            score += 1.5; reasons.append("contains figures/dates")
        caps = [w for w in words[1:] if w[:1].isupper() and not w.isupper() and w.lower() not in _STOP]
        if caps:
            score += min(len(caps), 3) * 0.7; reasons.append("names entities")
        if _ASSERT_VERBS.search(s):
            score += 1.5; reasons.append("makes an assertion")
        if s.count("!") >= 2:
            score -= 1.0
        if i == 0:
            score += 0.5
        if score > 0:
            scored.append({"text": s[:400], "score": round(score, 2), "reasons": reasons, "_i": i})
    scored.sort(key=lambda c: (-c["score"], c["_i"]))
    out = scored[:max_claims]
    for c in out:
        c.pop("_i")
    return out


# ---------------------------------------------------------------------------
# Fact-check lookup
# ---------------------------------------------------------------------------

def _match_registry(claim_text: str) -> Optional[dict]:
    toks = _tokens(claim_text)
    best = None
    for entry in CLAIM_REGISTRY:
        if all(toks & set(g) for g in entry["groups"]):
            best = entry
            break
    return best


def _query_google(claim: str) -> list:
    key = os.environ.get("GOOGLE_FACTCHECK_API_KEY")
    if not key:
        return []
    import httpx
    r = httpx.get(
        "https://factchecktools.googleapis.com/v1alpha1/claims:search",
        params={"query": claim[:200], "key": key, "pageSize": 3},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for c in r.json().get("claims", [])[:3]:
        for rev in c.get("claimReview", [])[:1]:
            out.append({
                "source": "google_fact_check",
                "publisher": (rev.get("publisher") or {}).get("name"),
                "rating": rev.get("textualRating"),
                "url": rev.get("url"),
                "claim": c.get("text"),
            })
    return out


def _query_duckduckgo(claim: str) -> list:
    import httpx
    r = httpx.get(
        "https://api.duckduckgo.com/",
        params={"q": claim[:200], "format": "json", "no_html": 1, "skip_disambig": 1},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    d = r.json()
    if d.get("AbstractText"):
        return [{"source": "duckduckgo_instant_answer", "publisher": d.get("AbstractSource"),
                 "rating": None, "url": d.get("AbstractURL"), "claim": d["AbstractText"][:300]}]
    return []


def check_claims(claims: list) -> dict:
    """
    Cross-reference claim dicts (from extract_claims) or plain strings.

    Returns:
      mode, results[{claim, status, matches[]}], overall ('contradicted'|'no_match'|'unavailable'),
      notes[]
    status: 'contradicted' (matches a debunked-claim record) | 'no_match' (NOT evidence of truth)
    """
    online = online_enabled()
    notes = []
    results = []
    for c in claims:
        text = c["text"] if isinstance(c, dict) else str(c)
        matches = []
        hit = _match_registry(text)
        if hit:
            matches.append({
                "source": "offline_registry", "publisher": "FakeGuard offline registry",
                "rating": hit["rating"], "url": None, "claim": hit["claim"],
                "explanation": hit["explanation"],
            })
        if online:
            for fn in (_query_google, _query_duckduckgo):
                try:
                    matches.extend(fn(text))
                except Exception as exc:
                    logger.info("%s failed: %s", fn.__name__, exc)
                    note = f"{fn.__name__.lstrip('_')} unavailable; used remaining sources."
                    if note not in notes:
                        notes.append(note)
        contradicted = any(
            m["rating"] and re.search(r"false|fake|misleading|unsupported|unproven|incorrect|pants",
                                      str(m["rating"]), re.I)
            for m in matches
        )
        results.append({"claim": text, "status": "contradicted" if contradicted else "no_match",
                        "matches": matches})
    if not results:
        overall = "unavailable"
    elif any(r["status"] == "contradicted" for r in results):
        overall = "contradicted"
    else:
        overall = "no_match"
    if overall == "no_match":
        notes.append("No match found. This does NOT mean the claims are true; it means no known fact-check was found.")
    if not online:
        notes.append("Offline mode: only the bundled sample registry was consulted (set FAKEGUARD_ONLINE=1 for live sources).")
    return {"mode": "online" if online else "offline", "results": results,
            "overall": overall, "notes": notes}


# ---------------------------------------------------------------------------
# Domain reputation
# ---------------------------------------------------------------------------

def normalize_domain(url_or_domain: str) -> Optional[str]:
    s = (url_or_domain or "").strip()
    if not s:
        return None
    if "://" not in s:
        s = "http://" + s
    try:
        host = urlparse(s).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _registry_lookup(host: str) -> Optional[tuple]:
    parts = host.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        if cand in DOMAIN_REGISTRY:
            return cand, DOMAIN_REGISTRY[cand]
    return None


def _lookalike_of(host: str) -> Optional[str]:
    """Detect simple typosquats of registry domains (edit distance 1-2, or brand as subdomain label)."""
    base = host.split(".")
    label = base[-2] if len(base) >= 2 else host
    for dom in DOMAIN_REGISTRY:
        dlabel = dom.split(".")[0]
        if host == dom or host.endswith("." + dom) or len(dlabel) < 5:
            continue
        if label == dlabel:      # same label on a different TLD
            return dom
        if _edit_distance(label, dlabel) <= 1:
            return dom
        if dlabel in label and label != dlabel and re.search(r"[-\d]", label):
            return dom
    return None


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def assess_domain(url_or_domain: str) -> dict:
    """Source reputation for a URL/domain.  Never performs network I/O."""
    host = normalize_domain(url_or_domain)
    if not host:
        return {"domain": None, "known": False, "trust_score": None, "rating": "invalid",
                "flags": ["Could not parse a domain from the input."], "estimated_domain_age_years": None,
                "whois_performed": False}
    flags = []
    hit = _registry_lookup(host)
    if hit:
        dom, e = hit
        age = e.get("age")
        return {"domain": host, "registry_domain": dom, "known": True, "name": e["name"],
                "rating": e["rating"], "trust_score": e["trust"], "bias": e["bias"],
                "fact_checker": bool(e.get("fact_checker")),
                "estimated_domain_age_years": age, "whois_performed": False,
                "flags": (["Satire publication: content is not intended as factual news."] if e["rating"] == "satire"
                          else ["Listed as repeatedly publishing false or misleading content."]
                          if e["rating"] == "unreliable" else []),
                "source": "bundled sample registry (not the MBFC database)"}

    score = 50
    tld = host.rsplit(".", 1)[-1]
    if tld in SUSPICIOUS_TLDS:
        score -= 18; flags.append(f"Low-cost TLD '.{tld}' is disproportionately used for throwaway sites.")
    label = host.split(".")[-2] if host.count(".") >= 1 else host
    if label.count("-") >= 2:
        score -= 10; flags.append("Multiple hyphens in the domain name.")
    if sum(ch.isdigit() for ch in label) >= 3:
        score -= 8; flags.append("Many digits in the domain name.")
    if len(label) > 24:
        score -= 6; flags.append("Unusually long domain name.")
    if any(w in label for w in NEWSY_WORDS) and tld not in {"com", "org", "net", "co", "in", "uk"}:
        score -= 6; flags.append("News-sounding name on an uncommon TLD.")
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        score -= 25; flags.append("Raw IP address instead of a domain name.")
    if host.count(".") >= 4:
        score -= 6; flags.append("Deeply nested subdomains.")
    look = _lookalike_of(host)
    if look:
        score -= 30; flags.append(f"Resembles the established domain '{look}' (possible impersonation).")
    if tld in {"gov", "edu"} or host.endswith((".gov.in", ".gov.uk", ".ac.uk", ".edu.au")):
        score += 25; flags.append("Government/education namespace (restricted registration).")
    if not flags:
        flags.append("Domain not in the bundled registry; no heuristic red flags. Reputation unknown.")
    return {"domain": host, "known": False, "rating": "unknown", "trust_score": max(0, min(100, score)),
            "bias": None, "fact_checker": False, "estimated_domain_age_years": None,
            "whois_performed": False, "flags": flags,
            "source": "heuristics only (no WHOIS, no registry entry)"}


# ---------------------------------------------------------------------------
# Safe page fetch (online only)
# ---------------------------------------------------------------------------

class UnsafeUrlError(ValueError):
    pass


def _check_public_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise UnsafeUrlError("Host could not be resolved.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise UnsafeUrlError("URL resolves to a non-public address and was blocked.")


def validate_fetch_url(url: str) -> str:
    p = urlparse((url or "").strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise UnsafeUrlError("Only absolute http(s) URLs are allowed.")
    if p.username or p.password:
        raise UnsafeUrlError("URLs with embedded credentials are not allowed.")
    _check_public_host(p.hostname)
    return p.geturl()


def fetch_page_metadata(url: str) -> dict:
    """
    Fetch title / description / site name / article text of a public URL.
    Raises UnsafeUrlError for blocked targets; returns {"error": ...} on network failure.
    Redirects are followed manually so every hop is re-validated.
    """
    import httpx
    from bs4 import BeautifulSoup

    current = validate_fetch_url(url)
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=False,
                      headers={"User-Agent": "FakeGuardBot/4.0 (+credibility research)"}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                with client.stream("GET", current) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            return {"error": "Redirect without location."}
                        current = validate_fetch_url(str(httpx.URL(current).join(loc)))
                        continue
                    ctype = r.headers.get("content-type", "")
                    if "html" not in ctype and "xml" not in ctype:
                        return {"error": f"Unsupported content type: {ctype or 'unknown'}."}
                    buf = b""
                    for chunk in r.iter_bytes():
                        buf += chunk
                        if len(buf) >= MAX_FETCH_BYTES:
                            break
                    status = r.status_code
            except httpx.HTTPError as exc:
                return {"error": f"Fetch failed: {type(exc).__name__}"}
            soup = BeautifulSoup(buf, "html.parser")

            def meta(*names):
                for n in names:
                    tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
                    if tag and tag.get("content"):
                        return tag["content"].strip()[:300]
                return None

            paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            body = " ".join(p for p in paragraphs if len(p) > 40)[:6000]
            return {
                "final_url": current, "status_code": status,
                "title": (meta("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else None)),
                "description": meta("og:description", "description"),
                "site_name": meta("og:site_name"),
                "author": meta("author", "article:author"),
                "published": meta("article:published_time", "date"),
                "text": body,
            }
    return {"error": "Too many redirects."}


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def verify(text: Optional[str] = None, url: Optional[str] = None) -> dict:
    """
    Full verification: claims + fact-check + domain trust (+ page metadata when online).
    Never raises for ordinary input (UnsafeUrlError is converted into a ``page.error``).
    """
    page = None
    notes = []
    if url:
        if online_enabled():
            try:
                page = fetch_page_metadata(url)
            except UnsafeUrlError as exc:
                page = {"error": str(exc)}
            except Exception as exc:  # pragma: no cover
                logger.warning("fetch error: %s", exc)
                page = {"error": "Page could not be fetched."}
            if page and not text and page.get("text"):
                text = page["text"]
            if page and not text and page.get("title"):
                text = page["title"]
        else:
            notes.append("Live page fetch disabled (offline mode); domain assessed from URL only.")
    claims = extract_claims(text or "")
    fact = check_claims(claims)
    domain = assess_domain(url) if url else None
    return {
        "mode": "online" if online_enabled() else "offline",
        "claims": claims, "fact_check": fact, "domain": domain, "page": page,
        "notes": notes + fact["notes"],
    }
