# FakeGuard Phase 3 — Presentation Outline

## Evaluation breakdown
| Code | Criterion | Marks |
|---|---|---|
| P1 | Module-wise coding | 10 |
| P2 | Git repository setup | 5 |
| P3 | Git branching and commit conventions | 5 |
| P4 | Presentation | 5 |
| | **Total** | **25** |

---

## Slide 1 — Title and problem

**FakeGuard — Rule-Based News Credibility Analyzer**
Phase 3: Dynamic Keyword Library

**Problem (one sentence):**
> In Phase 2, every scoring rule was hardcoded in Python. Changing a single
> keyword meant editing source code and restarting the server.

**Phase 3 answer:**
> All rules live in a single JSON file. Edit the file. The next request picks
> it up — no server restart, no code change.

---

## Slide 2 — System architecture (P1)

Show the architecture diagram from `PHASE3_DOCUMENTATION.md §4`.

**Key point to say:**
- "There are three backend modules with strictly separated jobs.
  `keyword_loader.py` owns the config file. `analyzer.py` owns the scoring.
  `main.py` owns HTTP routing. None of them can do the other's job."

---

## Slide 3 — The three backend modules (P1)

Walk through each module's single responsibility:

| Module | One-line responsibility |
|---|---|
| `keyword_loader.py` | Read → validate → cache → hot-reload `keywords.json` |
| `analyzer.py` | Apply 5 scoring rules using whatever config `get_config()` returns |
| `main.py` | Route HTTP requests; convert `KeywordLibraryError` → HTTP 503 safely |

**Key point to say:**
- "If you delete `keywords.json` while the server is running, the next
  `/analyze` request returns HTTP 503 with a safe message. No crash.
  No Python traceback visible to the client. `/health` still returns 200."

---

## Slide 4 — keywords.json schema (P1)

Show the abbreviated JSON (from `PHASE3_DOCUMENTATION.md §7`).

**Key points to say:**
- "This is a plain text JSON file — not a compiled DLL, not a `.so` binary,
  not a database. Any text editor can open and change it."
- "Version 1.0.0 ships with 20 suspicious keywords and 15 clickbait phrases."
- "The scoring weights, category caps, and classification thresholds are all
  in here — none of them are in Python anymore."

---

## Slide 5 — Hot-reload flow (P1)

Draw or show the flow:

```
keywords.json saved
       ↓
Next POST /analyze
       ↓
analyzer.get_config()
       ↓
loader checks os.path.getmtime()
       ↓
mtime changed? → reload + validate → new frozen config
       ↓
analyzer scores with new rules
       ↓
result returned to client
```

**Key point to say:**
- "The check costs one `stat()` syscall per request — essentially free.
  A reload only happens when the file actually changed."

---

## Slide 6 — LIVE DEMO (P1 + P4)

### Step-by-step script (say each step aloud while doing it)

**Setup: two terminal windows open side by side.**

---

**Terminal 1 — Start backend:**
```bash
cd FakeGuard
backend/.venv/Scripts/python -m uvicorn main:app \
    --app-dir backend/app --port 8000
```
> "The server is running. I will not touch it again during the demo."

---

**Terminal 2 — Start frontend:**
```bash
npm run dev
```
> "Frontend is at localhost:5173."

---

**Step 1 — Baseline analysis in the browser:**

Open `http://localhost:5173`. Paste this text:
```
fake hoax scam
```
Expected result:
- Score: **30**
- Classification: **Credible**
- Indicators: "Suspicious keywords detected: fake, hoax, scam"

Say: *"Three keywords, 10 points each, 30 total — exactly at the cap.
Still Credible because Credible is 0–30."*

---

**Step 2 — Test a word NOT in the library:**

Paste into the UI:
```
demonstrationword
```
Expected: Score **0**, Classification **Credible**.

Say: *"This word is not in the library. Score is zero."*

---

**Step 3 — Edit `keywords.json`:**

Open `backend/app/keyword_library/keywords.json` in VS Code.
Add `"demonstrationword"` to the `"words"` array. Save (Ctrl+S).

Say: *"I just added 'demonstrationword' to the JSON file. I did not touch
`analyzer.py`. I did not restart the server. Terminal 1 is still running."*

---

**Step 4 — Analyze the same word again:**

Paste into the UI (same text as Step 2):
```
demonstrationword
```
Expected: Score **10**, Classification **Credible**.

Say: *"The score changed from 0 to 10. The server loaded the new rule from
the file on this request, with no restart."*

---

**Step 5 — Revert the file (optional, for tidiness):**

Remove `"demonstrationword"` from `keywords.json`. Save.

---

**Step 6 — Show the test suite:**

Switch to Terminal 2 (or open a third):
```bash
backend/.venv/Scripts/python -m pytest \
  backend/app/test_keyword_loader.py \
  backend/app/test_analyzer_integration.py \
  backend/app/test_api.py
```
Show output:
```
177 passed in 2.10s
```

Say: *"177 automated tests: unit tests for the loader, integration tests for
the scorer, and HTTP API tests using a real TestClient. None of them
require a running server."*

---

**Step 7 — Show Git history:**

```bash
git log --oneline --graph --all --decorate
```

Show output:
```
*   8ef8d75 (HEAD -> master) feat: merge Phase 3 dynamic keyword library ...
|\
| * 79c6fe7 docs: document Phase 3 implementation
| * 620f37e test(phase3): add HTTP API test suite (69 tests)
| * 89f1da9 feat(phase3): integrate keyword_loader into analyzer + main
| * 486ab31 feat(phase3): add keyword_loader module
| * 01e6739 feat(phase3): add external keyword library JSON
|/
* 2f5b2f5 chore: initial Phase 2 baseline
```

Say: *"All Phase 3 work happened on a feature branch. It was merged into
master only after all 177 tests passed. Every commit has a Conventional
Commit message: chore, feat, test, docs."*

---

## Slide 7 — Git repository setup (P2)

Show `git status` → `nothing to commit, working tree clean`

Show `.gitignore` highlights:
```gitignore
.venv/          ← Python virtual environment excluded
__pycache__/    ← bytecode excluded
.env            ← secrets excluded
node_modules    ← frontend packages excluded
```

**Key point to say:**
- "`keywords.json`, all test files, `README.md`, and all source code ARE
  tracked. Nothing important is excluded."

---

## Slide 8 — Git branching and commit conventions (P3)

Show the graph again. Explain:

| Element | What it shows |
|---|---|
| Two branches | Feature development separated from stable `master` |
| `--no-ff` merge | Branch topology preserved in graph; not a fast-forward |
| Conventional Commits | `chore:`, `feat:`, `test:`, `docs:` — evaluator can read what each commit changed without opening the diff |
| Gate before merge | 177 tests must pass before the feature branch is allowed into `master` |

---

## Slide 9 — Test summary (P1)

| Suite | Tests | Covers |
|---|---|---|
| `test_keyword_loader.py` | 69 | Validation, hot-reload, thread-safety |
| `test_analyzer_integration.py` | 39 | Scoring correctness, config-change behavior |
| `test_api.py` | 69 | HTTP endpoints, 503 safety, frontend compat |
| **Total** | **177** | **All 18 validation requirements** |

---

## Slide 10 — Limitations and future scope (P4)

**Be honest about what the system does and does not do:**

| What it does | What it does NOT do |
|---|---|
| Scores stylistic signals in text | Verify factual claims |
| Detects suspicious vocabulary patterns | Identify disinformation definitively |
| Detects clickbait writing style | Perform deepfake or image forgery detection |
| Flags excessive punctuation / ALL CAPS | Cross-check sources |

**One natural next step:**
> "Add a weighted domain credibility list to the JSON library — same
> hot-reload mechanism, no new architecture needed."

---

## Quick reference — expected demo output

| Input | Expected score | Expected classification |
|---|---|---|
| `"The government held a press conference"` | 0 | Credible |
| `"fake"` | 10 | Credible |
| `"fake hoax scam"` | 30 | Credible |
| `"fake hoax scam you won't believe"` | 45 | Suspicious |
| `"FAKE HOAX SCAM YOU WON'T BELIEVE SHOCKING TRUTH"` | 70 | Likely Fake |
| `"Alert!!!"` | 10 (exclamation rule) | Credible |
| `"Really??? Is this true???"` | 5 (question rule) | Credible |

---

## Commands cheat sheet (for during the demo)

```bash
# Start backend
backend/.venv/Scripts/python -m uvicorn main:app --app-dir backend/app --port 8000

# Start frontend
npm run dev

# Run all tests
backend/.venv/Scripts/python -m pytest backend/app/test_keyword_loader.py backend/app/test_analyzer_integration.py backend/app/test_api.py

# Git history
git log --oneline --graph --all --decorate

# Git status
git status

# Show tracked files
git ls-files

# Show .gitignore is working
git check-ignore -v backend/.venv
```
