"""
FakeGuard Phase 3 -- Live Acceptance Test
==========================================
Starts uvicorn in a subprocess, tests /analyze and /keywords,
demonstrates hot-reload by temporarily adding a keyword to keywords.json,
then restores the file.

Run from the FakeGuard project root:
  backend\\.venv\\Scripts\\python.exe acceptance_test.py
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VENV_PYTHON = Path("backend/.venv/Scripts/python.exe")
APP_DIR     = Path("backend/app")
KW_PATH     = APP_DIR / "keyword_library" / "keywords.json"
HOST        = "http://127.0.0.1:8001"
NEW_WORD    = "hotreloadtest"   # not in the real library

PASS = "[PASS]"
FAIL = "[FAIL]"


def _request(method, path, body=None):
    url  = HOST + path
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _wait_for_server(max_secs=15):
    for _ in range(max_secs * 2):
        try:
            _request("GET", "/health")
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _check(label, condition, detail=""):
    icon = PASS if condition else FAIL
    print(f"  {icon}  {label}")
    if detail:
        print(f"       {detail}")
    if not condition:
        raise AssertionError(f"FAILED: {label}")


def main():
    print("=" * 60)
    print("FakeGuard Phase 3 -- Live Acceptance Test")
    print("=" * 60)

    print("\n[1] Starting uvicorn on port 8001 ...")
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", "8001",
         "--app-dir", str(APP_DIR)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if not _wait_for_server():
        print("FAIL: server did not start in time")
        proc.kill()
        sys.exit(1)
    print("    Server ready.")

    kw_backup = KW_PATH.with_suffix(".json.bak")
    shutil.copy2(KW_PATH, kw_backup)
    passed = 0

    try:
        print("\n[2] GET /health")
        r = _request("GET", "/health")
        _check("status == healthy", r.get("status") == "healthy", str(r))
        passed += 1

        print("\n[3] GET /keywords -- library metadata")
        r = _request("GET", "/keywords")
        _check("version present",             bool(r.get("version")))
        _check("suspicious_keyword_count > 0", r.get("suspicious_keyword_count", 0) > 0)
        _check("clickbait_phrase_count > 0",   r.get("clickbait_phrase_count", 0) > 0)
        _check("max_total_score == 100",       r.get("max_total_score") == 100)
        _check("3 classification bands",       len(r.get("classification_bands", [])) == 3)
        print(f"       version={r['version']}  "
              f"keywords={r['suspicious_keyword_count']}  "
              f"phrases={r['clickbait_phrase_count']}")
        passed += 1

        print("\n[4] POST /analyze -- baseline with 'fake hoax scam'")
        r = _request("POST", "/analyze", {"text": "fake hoax scam"})
        _check("score == 30",              r.get("score") == 30,       f"score={r.get('score')}")
        _check("classification=Credible",  r.get("classification") == "Credible",
               f"classification={r.get('classification')}")
        _check("word_count == 3",          r.get("word_count") == 3,   f"word_count={r.get('word_count')}")
        passed += 1

        print(f"\n[5] POST /analyze -- '{NEW_WORD}' (not in library, expect 0)")
        r = _request("POST", "/analyze", {"text": NEW_WORD})
        score_before = r.get("score", -1)
        _check("score == 0 before change", score_before == 0, f"score={score_before}")
        passed += 1

        print(f"\n[6] Modifying keywords.json -- adding '{NEW_WORD}' ...")
        time.sleep(0.1)
        lib = json.loads(KW_PATH.read_text(encoding="utf-8"))
        orig_version = lib["version"]
        lib["suspicious_keywords"]["words"].append(NEW_WORD)
        lib["version"] = orig_version + "-test"
        KW_PATH.write_text(json.dumps(lib, indent=2), encoding="utf-8")
        os.utime(KW_PATH, None)
        print(f"    Saved.  New version: {lib['version']}")

        print(f"\n[7] POST /analyze -- '{NEW_WORD}' (expect 10 after hot-reload)")
        time.sleep(0.2)
        r = _request("POST", "/analyze", {"text": NEW_WORD})
        score_after = r.get("score", -1)
        _check("score == 10 after hot-reload",  score_after == 10, f"score={score_after}")
        _check("hot-reload changed the result",
               score_after != score_before,
               f"before={score_before}  after={score_after}")
        passed += 1

        print("\n[8] GET /keywords -- version reflects updated library")
        r = _request("GET", "/keywords")
        _check("version updated", "-test" in r.get("version", ""),
               f"version={r.get('version')}")
        passed += 1

        print("\n" + "=" * 60)
        print(f"ACCEPTANCE TEST PASSED  ({passed} groups, 0 failures)")
        print("Hot-reload confirmed: keyword changes applied without server restart.")
        print("=" * 60)

    except AssertionError:
        print("\nACCEPTANCE TEST FAILED")
        sys.exit(1)

    finally:
        shutil.copy2(kw_backup, KW_PATH)
        kw_backup.unlink(missing_ok=True)
        print("\n    keywords.json restored.")
        proc.terminate()
        proc.wait(timeout=5)
        print("    Server stopped.")


if __name__ == "__main__":
    main()
