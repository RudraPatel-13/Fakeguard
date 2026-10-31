"""
FakeGuard Phase 4 -- Live Web Cross-Verification
==================================================
Searches the live news web (no API keys) to see whether a claim is covered by
reputable outlets or addressed by fact-checkers.

Providers (best effort, run concurrently):
  * Google News RSS search  -- general news coverage
  * Google News RSS search for "<claim> fact check" -- fact-checker coverage

Corroboration score (0-100):
  30 points per DISTINCT reputable outlet with a relevant story (max 90)
  + 4 points per other relevant story (max 10)
  A relevant story from a fact-checker whose headline says false/misleading/
  debunked caps the score at 15 and sets status 'debunked'.  A supportive
  fact-check adds 10.
  Levels: High >= 80, Medium 40-79, Low / Unverified < 40.

Offline fallback: when the network is unreachable the service returns
mode='offline' (simulation mode) using only the bundled debunked-claim registry;
corroboration score is None unless that registry contradicts the claim.

LIMITATIONS (shown to users): search results are matched by keyword overlap, so
a relevant-looking headline may not actually confirm the claim; absence of
coverage is not proof of falsehood (breaking or local news is often thinly
covered).  This is a triage signal, not a verdict.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree

import verifier_service as vs

logger = logging.getLogger("fakeguard.websearch")

HTTP_TIMEOUT = 6.0
MAX_RESULTS = 10
CACHE_TTL = 600
MAX_BYTES = 1_000_000

# Outlets treated as verified mainstream/wire sources (on top of the domain registry's 'high' ratings).
REPUTABLE_EXTRA = {
    "bloomberg.com", "afp.com", "france24.com", "dw.com", "cnn.com", "cbsnews.com", "nbcnews.com",
    "abcnews.go.com", "indianexpress.com", "hindustantimes.com", "ndtv.com", "thehindu.com",
    "timesofindia.indiatimes.com", "economist.com", "ft.com", "theguardian.com", "aljazeera.com",
    "pbs.org", "usatoday.com", "latimes.com", "cnbc.com", "scroll.in", "livemint.com", "thewire.in",
}
FACT_CHECKER_DOMAINS = {
    "snopes.com", "politifact.com", "factcheck.org", "altnews.in", "boomlive.in", "fullfact.org",
    "factly.in", "newschecker.in", "vishvasnews.com", "factcheck.afp.com", "leadstories.com",
    "checkyourfact.com", "africacheck.org", "logically.ai",
}
FACTCHECK_PUBLISHER_NAMES = {
    "snopes": "snopes.com", "politifact": "politifact.com", "factcheck.org": "factcheck.org",
    "alt news": "altnews.in", "boom": "boomlive.in", "full fact": "fullfact.org",
    "newschecker": "newschecker.in", "lead stories": "leadstories.com",
}

_DEBUNK = re.compile(
    r"\b(false|fake|misleading|debunk(?:ed|s)?|hoax|no evidence|baseless|untrue|fabricated|doctored|"
    r"not true|misattributed|satire|scam|unproven|incorrect|pants on fire|old video|edited|"
    r"not proof|not evidence|does not|doesn't|didn't|isn't|not show)\b", re.I)
_DISPUTE_NEWS = re.compile(r"\b(false|fake|bogus|hoax|debunk(?:ed|s)?|myth|conspiracy|baseless|misleading|"
                           r"disinformation|misinformation|no evidence|untrue|fabricated|not true)\b", re.I)
_SUPPORT = re.compile(r"\b(true|accurate|correct|confirmed|verified|legit(?:imate)?)\b", re.I)
_FILLER = set("""the a an of to in on for and or is are was were be been that this it with as by at from has have had
will would not no you your they them their we our i he she his her its who what when where why how can could should
share forward now urgent breaking shocking alert watch click please must before they delete says said say just very
all any more most some than then there these those into about over after also new""".split())

_cache: dict = {}
_cache_lock = threading.Lock()


def _http_get(url: str) -> str:
    """Single choke point for network access (monkeypatched in tests)."""
    import httpx
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (FakeGuard research; +local)"}) as c:
        with c.stream("GET", url) as r:
            r.raise_for_status()
            buf = b""
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > MAX_BYTES:
                    break
    return buf.decode("utf-8", errors="replace")


def web_enabled() -> bool:
    return os.environ.get("FAKEGUARD_OFFLINE", "").strip().lower() not in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# Query building
# ---------------------------------------------------------------------------

def keywords(text: str) -> list:
    out, seen = [], set()
    for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", text or ""):
        lw = w.lower().strip("'-")
        if lw.isdigit() and len(lw) < 4:
            continue
        if (len(lw) < 3 and not (len(lw) == 2 and any(ch.isdigit() for ch in lw))) or lw in _FILLER or lw in seen:
            continue
        seen.add(lw)
        out.append(lw)
    return out


def claim_text(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text or "")
    claims = vs.extract_claims(text, max_claims=3)
    if not claims:
        return text.strip()[:240]
    # Prefer the candidate with the most searchable keywords (avoids e.g. "Forward to 10 people").
    return max(claims, key=lambda c: len(keywords(c["text"])))["text"]


def build_query(text: str, max_terms: int = 6) -> str:
    """Pick the most checkable claim and reduce it to search keywords."""
    return " ".join(keywords(claim_text(text))[:max_terms])


def entities(claim: str) -> list:
    """Proper-noun-like tokens (capitalised, not sentence-initial, not SHOUTING) and numbers."""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", claim or "")
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in _FILLER or len(lw) < 3 or lw in out:
            continue
        if (i > 0 and w[0].isupper() and not (w.isupper() and len(w) > 4)) or w.isdigit():
            out.append(lw)
    return out[:5]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _strip_html(s: str) -> str:
    from bs4 import BeautifulSoup
    return BeautifulSoup(s or "", "html.parser").get_text(" ", strip=True)


def parse_rss(xml_text: str) -> list:
    """Parse Google-News-style RSS into raw result dicts. Rejects DTD/entity declarations."""
    if re.search(r"<!(DOCTYPE|ENTITY)", xml_text[:2000], re.I):
        raise ValueError("DTD not allowed in feed")
    root = ElementTree.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title or urlparse(link).scheme not in ("http", "https"):
            continue
        src = it.find("source")
        publisher = (src.text or "").strip() if src is not None and src.text else None
        src_url = src.get("url") if src is not None else None
        if publisher and title.endswith(" - " + publisher):
            title = title[: -len(publisher) - 3].strip()
        elif " - " in title and not publisher:
            title, publisher = title.rsplit(" - ", 1)
        date = None
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate") or "")
            date = dt.astimezone(timezone.utc).isoformat(timespec="minutes") if dt else None
        except (TypeError, ValueError):
            pass
        snippet = _strip_html(it.findtext("description") or "")
        if snippet.startswith(title):
            snippet = snippet[len(title):].strip(" - ")
        items.append({"title": title, "publisher": publisher, "source_url": src_url,
                      "url": link, "snippet": snippet[:280], "published": date})
    return items


def _search_news(query: str) -> list:
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    return parse_rss(_http_get(url))


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _domain_of(item: dict) -> Optional[str]:
    if item.get("source_url"):
        return vs.normalize_domain(item["source_url"])
    pub = (item.get("publisher") or "").lower()
    for name, dom in FACTCHECK_PUBLISHER_NAMES.items():
        if name in pub:
            return dom
    return None


def _relevance(q_terms: list, item: dict) -> float:
    if not q_terms:
        return 0.0
    hay = (item["title"] + " " + item.get("snippet", "")).lower()
    hits = sum(1 for t in q_terms if t in hay or (len(t) > 5 and t[:5] in hay))
    return hits / len(q_terms)


def classify(item: dict, q_terms: list) -> dict:
    """Tier an item and flag outlet stories that dispute the claim rather than support it."""
    dom = _domain_of(item)
    reg = vs._registry_lookup(dom)[1] if dom and vs._registry_lookup(dom) else None
    title_fc = bool(re.match(r"\s*(fact[ -]?check|fact check)\b", item["title"], re.I))
    is_fc = bool(dom and (dom in FACT_CHECKER_DOMAINS or (reg and reg.get("fact_checker")))) or title_fc
    reputable = bool(dom and (dom in REPUTABLE_EXTRA or (reg and reg["rating"] == "high")
                              or any(dom.endswith("." + d) for d in REPUTABLE_EXTRA)))
    if reg and reg["rating"] in ("unreliable", "satire", "low"):
        reputable = False
    tier = "fact_checker" if is_fc else "verified_outlet" if reputable else "unranked"
    verdict = None
    if is_fc:
        txt = item["title"]
        if _DEBUNK.search(txt):
            verdict = "debunked"
        elif _SUPPORT.search(txt):
            verdict = "supported"
        else:
            verdict = "unclear"
    flagged = bool(reg and reg["rating"] in ("unreliable", "satire"))
    disputes = tier != "fact_checker" and bool(_DISPUTE_NEWS.search(item["title"]))
    out = dict(item)
    out.pop("source_url", None)
    out.update({
        "domain": dom, "tier": tier, "fact_check_verdict": verdict,
        "trust_score": reg["trust"] if reg else (80 if reputable else None),
        "flagged_source": flagged, "disputes_claim": disputes, "relevance": round(_relevance(q_terms, item), 2),
    })
    return out


def score(results: list) -> dict:
    """Corroboration score/level/status from classified, relevance-filtered results."""
    outlets = {}
    disputing = {}
    for r in results:
        if r["tier"] == "verified_outlet":
            bucket = disputing if r.get("disputes_claim") else outlets
            bucket.setdefault(r["domain"], r["publisher"] or r["domain"])
    others = [r for r in results if r["tier"] == "unranked" and not r["flagged_source"]
              and not r.get("disputes_claim")]
    fcs = [r for r in results if r["tier"] == "fact_checker"]
    debunk = [r for r in fcs if r["fact_check_verdict"] == "debunked"]
    support = [r for r in fcs if r["fact_check_verdict"] == "supported"]

    s = min(90, 30 * len(outlets)) + min(10, 4 * len(others))
    status = "corroborated" if s >= 80 else "partial" if s >= 40 else "unverified"
    explanation = None
    if debunk:
        s = min(s, 15)
        status = "debunked"
        explanation = f"{len(debunk)} fact-checking article(s) describe this claim as false or misleading."
    elif len(disputing) >= 2:
        s = min(s, 15)
        status = "debunked"
        explanation = (f"{len(disputing)} verified outlets ({', '.join(sorted(disputing.values())[:3])}) "
                       "report this claim as false, misleading or a conspiracy theory.")
    elif len(disputing) == 1:
        s = min(s, 45)
        status = "partial"
        explanation = f"Coverage exists, but {next(iter(disputing.values()))} describes the claim as disputed."
    elif support:
        s = min(100, s + 10)
    if explanation is None:
        if status == "corroborated":
            explanation = f"Reported by {len(outlets)} verified outlets."
        elif status == "partial":
            explanation = "Limited or mixed coverage: few verified outlets found."
        else:
            explanation = "No credible news coverage found. This may be a fringe claim, or simply very recent or local news."
    level = "High" if s >= 80 else "Medium" if s >= 40 else "Low / Unverified"
    return {"score": int(s), "level": level, "status": status, "explanation": explanation,
            "verified_outlets": sorted(outlets.values()), "disputing_outlets": sorted(disputing.values())}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _offline_result(query: str, text: str, reason: str) -> dict:
    fc = vs.check_claims([text or query]) if (text or query) else {"overall": "unavailable"}
    contradicted = fc["overall"] == "contradicted"
    return {
        "mode": "offline", "simulation": True, "available": False, "query": query,
        "results": [], "fact_checks": [],
        "corroboration": {
            "score": 10 if contradicted else None, "level": "Low / Unverified" if contradicted else "Unavailable",
            "status": "debunked" if contradicted else "unavailable",
            "disputing_outlets": [],
            "explanation": ("Offline / simulation mode: the bundled registry matches a known debunked claim."
                            if contradicted else "Offline / simulation mode: live internet search was not possible."),
            "verified_outlets": [],
        },
        "notes": [reason, "Showing results from the bundled offline registry only."],
        "searched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def verify_web(text: str, query: Optional[str] = None) -> dict:
    """
    Search the live web for coverage of ``text`` (or an explicit ``query``).
    Never raises: network failures yield the offline fallback.
    """
    q = (query or "").strip() or build_query(text)
    if len(q.split()) < 2:
        return _offline_result(q, text, "Not enough searchable content to build a web query.")
    if not web_enabled():
        return _offline_result(q, text, "Live search disabled (FAKEGUARD_OFFLINE=1).")

    with _cache_lock:
        hit = _cache.get(q)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]

    queries = {"news": q, "factcheck": q + " fact check"}
    raw, errors = {}, []
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {k: ex.submit(_search_news, v) for k, v in queries.items()}
        for k, f in futs.items():
            try:
                raw[k] = f.result()
            except Exception as exc:
                logger.info("web search '%s' failed: %s", k, type(exc).__name__)
                errors.append(k)
    if len(errors) == 2:
        return _offline_result(q, text, "Could not reach the news search service (network unreachable or rate-limited).")

    q_terms = keywords(q)
    ents = entities(q if query else claim_text(text))
    seen, results = set(), []
    for k in ("factcheck", "news"):
        for item in raw.get(k, []):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            c = classify(item, q_terms)
            if ents:
                hay = (item["title"] + " " + item.get("snippet", "")).lower()
                if sum(e in hay for e in ents) / len(ents) < 0.5:
                    continue
            min_rel = 0.5 if c["tier"] == "fact_checker" else 0.4
            if len(q_terms) >= 3 and c["relevance"] < min_rel:
                continue
            results.append(c)
    order = {"fact_checker": 0, "verified_outlet": 1, "unranked": 2}
    results.sort(key=lambda r: (order[r["tier"]], -r["relevance"], r["published"] or ""), reverse=False)
    results = results[:MAX_RESULTS]

    notes = []
    if errors:
        notes.append("One search provider failed; results may be incomplete.")
    notes.append("Matching is by keyword overlap: a relevant headline does not by itself confirm the claim.")
    out = {
        "mode": "live", "simulation": False, "available": True, "query": q,
        "results": results,
        "fact_checks": [r for r in results if r["tier"] == "fact_checker"],
        "corroboration": score(results),
        "notes": notes,
        "searched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _cache_lock:
        _cache[q] = (time.time(), out)
        if len(_cache) > 200:
            _cache.pop(next(iter(_cache)))
    return out


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
