# FakeGuard Phase 4 — Hybrid ML, Unified OCR Pipeline, Fact Verification & Dashboard

## 1. What changed

| Area | Files | Summary |
|---|---|---|
| ML classifier | `backend/app/ml_service.py`, `ml_seed_data.py` | TF-IDF + Logistic Regression, bootstrap uncertainty interval, per-token attribution, `.joblib` persistence with automatic fallback training |
| Live web search | `backend/app/web_search_service.py` | Real-time Google News RSS search (no API key): reputable-outlet matching, fact-checker detection, 0–100 corroboration score, offline simulation fallback |
| Verification | `backend/app/verifier_service.py` | Claim extraction, fact-check lookup (offline registry; optional Google Fact Check + DuckDuckGo), source reputation, SSRF-guarded page fetch |
| Fusion | `backend/app/fusion.py` | Auditable composite trust score + six risk axes |
| Image pipeline | `backend/app/image_analyzer.py` | OCR preprocessing, word boxes + confidence, keyword overlays, forensics risk, dual verdict |
| API | `backend/app/main.py` | `/analyze` and `/analyze-image` enriched; new `/verify-claim`, `/model-info`, `/keywords/rules`, `/keywords/reload` |
| Frontend | `src/components/*`, `src/*.js(x)` | Five-tab light-theme workspace (Stripe/Linear style) with live scanner, web feed and ELA slider |

Legacy endpoints and payload keys are unchanged; all new fields are additive. The pre-existing 279 tests still pass.

> **Revision:** the dashboard was first built in a dark theme and then redesigned as a light theme per the updated brief; live web verification was added in the same phase.

## 2. ML methodology (honest scope)

* **Model**: `TfidfVectorizer(1–2-grams, sublinear tf, English stop words)` → `LogisticRegression(C=4, class_weight=balanced)`.
* **Training data shipped**: a small hand-written *synthetic* seed corpus (79 sentences) in `ml_seed_data.py`. It is **not** WELFake or ISOT, and the 96% cross-validation accuracy it reports is on that tiny stylistic corpus — do not read it as real-world accuracy. `GET /model-info` states the training source and limitations.
* **What it detects**: sensational / misinformation *writing style*. It cannot verify facts.
* **Production training**: `ml_service.train_from_csv("WELFake_Dataset.csv")` (WELFake layout: `label` 1 = fake, 0 = real; handled by `credible_label=0`). It saves the artifact and hot-swaps the model.
* **Artifact**: `backend/app/models/credibility_model.joblib` (git-ignored). Missing or corrupt → regenerated automatically. Override path with `FAKEGUARD_MODEL_PATH`. joblib uses pickle: only load artifacts you created.
* **Explainability**: for a linear model the log-odds is exactly `Σ coefᵢ·tfidfᵢ + intercept` (verified by a unit test), so each token's contribution is reported directly (negative → unreliable-style).
* **Confidence interval**: 5th–95th percentile of P(credible) across 15 bootstrap-resampled models. It measures model variance, not factual correctness.

## 3. Score fusion: the FakeGuard Credibility Index

```
Rule_Trust = 100 - 100 * rule_score / max_total_score
ML_Trust   = 100 * P(credible)
Web_Trust  = live corroboration score (0-100)
Index      = clamp( w_rules*Rule_Trust + w_ml*ML_Trust + w_web*Web_Trust - Penalties , 0, 100 )
```

| Signals available | w_rules | w_ml | w_web |
|---|---|---|---|
| rules + ML + web | 0.40 | 0.25 | 0.35 |
| rules + ML (no web / offline) | 0.60 | 0.40 | - |
| rules + web (ML unavailable) | 0.53 | - | 0.47 |
| rules only | 1.0 | - | - |

```
Penalties = 0.25 * forensics_risk         (max 25, image scans)
          + 20 if a claim matches the offline debunked registry OR live web status = 'debunked'  (applied once)
          + 12 * (40 - source_trust) / 40  when source_trust < 40
```

Bands: >=70 High trust, 40-69 Mixed / verify, <40 Low trust. The legacy `score` (rule *suspicion*, higher = worse) is unchanged. Constants live at the top of `fusion.py`. Risk axes (0-100, higher = worse): sensationalism, clickbait, emotional manipulation, source risk, ML risk, forensic risk, corroboration risk; unavailable axes are `null`.

## 4. Image pipeline

1. Decode/validate (unchanged) → 2. OCR: `image_to_string` on the original, plus `image_to_data` word boxes. A Pillow/NumPy-preprocessed variant (grayscale, upscale, median denoise — a stand-in for bilateral filtering, autocontrast, local-mean adaptive threshold) is OCR'd too and **kept only if mean confidence is >3 points higher**. OpenCV is intentionally not required. → 3. OCR text goes through rules + ML. → 4. EXIF + ELA, with numeric stats (`max_diff`, `mean_diff`, `hot_fraction`). → 5. `forensics.risk_score` (heuristic 0–100) and `dual_verdict`:

* **visual_integrity** — risk from ELA discrepancy (halved for non-JPEG), editing software in EXIF, modified-after-capture timestamps, missing EXIF (weak). Never proof of tampering.
* **content_credibility** — fused trust score of the OCR text, forensics-penalised.

`keyword_overlays` maps detected keywords, WordNet synonyms and clickbait phrases onto OCR word boxes as 0–1 normalised coordinates.

Tesseract must be installed for OCR; without it `ocr.status = "ocr_unavailable"` and the visual verdict still works.

## 5. Verification service

* **Claims**: sentences scored for figures/dates, named entities and assertion verbs; questions are excluded; top 3 returned.
* **Fact-check**: bundled registry of 10 widely debunked claim patterns (token-group matching). `no_match` explicitly does **not** mean true.
* **Online mode** (`FAKEGUARD_ONLINE=1`): adds Google Fact Check Tools (needs `GOOGLE_FACTCHECK_API_KEY`) and DuckDuckGo Instant Answer; each failure degrades to offline results with a note. Snopes/PolitiFact scraping and RSS cross-referencing were **not** implemented.
* **Domain trust**: small bundled registry (~24 domains with project-assigned scores — *not* the MBFC database) plus heuristics (risky TLDs, hyphens/digits, raw IPs, typosquats of registry domains, gov/edu namespaces). **No WHOIS is performed**; `estimated_domain_age_years` is a coarse figure for registry domains only, otherwise `null`.
* **URL fetch** (online only): http(s) only, no credentials, every resolved IP must be public (blocks loopback/private/link-local/metadata), redirects re-validated per hop (max 3), 512 KB cap, 6 s timeout. DNS-rebinding between check and connect is not fully eliminated; run online mode only in trusted deployments.

## 5a. Live web verification (`web_search_service.py`)

* **Search**: two concurrent Google News RSS queries (the claim keywords, and the same plus "fact check"). No API key. The query is built from the most searchable extracted claim (at most 6 keywords; filler/shouting words and small bare numbers dropped). Results are cached for 10 minutes.
* **Relevance**: a result must contain at least 40% of the query terms (50% for fact-checkers) and at least 50% of the claim's proper-noun "entities", which stops e.g. a US Fed story counting for a Bank of England claim.
* **Tiers**: *Verified Outlet* (domain rated "high" in the registry or in the extra reputable list: Reuters, AP, BBC, Bloomberg, AFP, The Hindu, NYT ...), *Fact-Checker* (Snopes, PolitiFact, Alt News, BOOM, FactCheck.org, Full Fact ...; verdict read from the headline: debunked / supported / unclear), *Unranked* (everything else; flagged if the registry marks it unreliable or satire).
* **Outlets that dispute the claim**: a verified-outlet headline containing words like false/bogus/hoax/conspiracy is treated as *disputing*, not corroborating (otherwise coverage of a debunked rumour would look like support). Two disputing outlets give status `debunked`; one caps the score at 45.
* **Corroboration score**: 30 per distinct supporting outlet (max 90) + 4 per other relevant story (max 10); a debunking fact-check caps it at 15, a supportive one adds 10. High >=80, Medium 40-79, Low / Unverified <40.
* **Fallback**: network failure, malformed feed or `FAKEGUARD_OFFLINE=1` gives `mode: "offline"`, `simulation: true`, score `null` (fusion then ignores the web signal), except that the bundled debunked-claim registry can still return status `debunked`.
* **Safety**: feeds containing DTD/entity declarations are rejected; only http(s) result links are kept; the UI opens them with `rel="noopener"`.
* **Known limits**: keyword-overlap matching can mis-judge relevance; fact-check verdicts come from headline wording; brand-new or local stories are thinly covered, so "Low" means *unverified*, not *false*.

## 6. API additions

`POST /analyze?verify_web=true|false` — body `{text, url?}` (web search is opt-in, default false). Adds `web`, `breakdown`, `matched_terms`, `ml`, `claims`, `fact_check`, `domain`, `fusion`.

`POST /analyze-image?verify_web=true|false` (default true; OCR text is piped to the web verifier) — adds `web`, `ocr.{mean_confidence,words,preprocessing}`, `ela.{max_diff,mean_diff,hot_fraction}`, `forensics`, `keyword_overlays`, `ml`, `fusion`, `dual_verdict`.

`POST /verify-web` — body `{text, url?}` returns `{web, domain}`; 422 if `text` is empty. Always degrades to offline mode instead of failing.

`POST /verify-claim` — body `{text?, url?}` (422 if both empty) → `{mode, claims, fact_check, domain, page, notes}`.

`GET /model-info` — classifier metadata, fusion constants, `verification_mode`.

`GET /keywords/rules` — loaded rule lists (read-only; `/keywords` still hides them). `POST /keywords/reload` — forces an mtime check.

## 7. Frontend (light theme)

Design system: snow-white cards on a slate canvas, navy text, indigo primary, emerald = credible, rose = flagged, 16px radius, dual-layer soft shadows, `cubic-bezier(.2,.8,.2,1)` transitions, hover lift and press states; `prefers-reduced-motion` is respected.

Tabs: **Article & Text** (preset pills, live counter, "Search live internet" toggle) | **Image Forensics** (drag-drop, ELA/original slider with keyboard support, keyword boxes, OCR inspector, dual verdict) | **URL Verifier** | **Rule Studio** | **Audit History** (LocalStorage, last 50, JSON export, print/PDF).

Components: `LiveScanner` (5-step progress: OCR, rules, ML, live internet, synthesis; progress is timer-indicative since the backend runs the stages in one request), `ScoreGauge` (radial gauge animating 0 to score, hue shifts red to yellow to green), `WebVerificationList` (corroboration meter, live/offline banner, source cards with badges "Verified Outlet", "Fact-Check: Debunked", "Unranked Blog", links), `ImageComparisonSlider`, `PresetBar` ("Try Verified News (BBC/AP)", "Try Viral Clickbait Scam", "Try Sensational Social Media Rumor", "Try Uploading Newspaper Clip", which draws a sample clipping on a canvas and runs it through the image pipeline), `AxisChart`, `CredibilityReport`, `Header` (backend / live-web status).

Export: **JSON** and **Print / PDF** (browser print dialog with a print stylesheet; there is no server-side PDF generator).

Not built: a synonym-threshold control (WordNet matching has no tunable threshold; Rule Studio has a live rule tester instead). UI screenshots are not included: no browser was available to capture them.

## 8. Tests

`pytest` from the repository root: 412 passed, 1 skipped (the real-Tesseract integration test, skipped when the binary is absent). New: `test_ml_service.py`, `test_verifier_service.py`, `test_fusion.py`, `test_phase4.py`, `test_web_search.py` (canned RSS feeds: corroboration, debunks, disputing outlets, fallback, cache, fusion, endpoints, OCR to web). `conftest.py` isolates the model artifact and blocks real network access in every test. `npm run lint` and `npm run build` pass. The UI was not exercised in a browser during development (no browser available), so a manual smoke test is recommended.
