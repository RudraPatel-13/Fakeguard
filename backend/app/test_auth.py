"""Authentication, JWT and saved-scan tests. Existing endpoints must stay open to guests."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from starlette.testclient import TestClient

import auth_routes
import auth_service as svc
from database import Base, engine
from main import app

CREDS = {"email": "Rudra@Example.com", "username": "Rudra", "password": "s3cret-pass"}


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    auth_routes.reset_throttle()
    yield


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def _register(client, **over):
    return client.post("/auth/register", json={**CREDS, **over})


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _token(client):
    return _register(client).json()["access_token"]


# ---------- registration ----------
def test_register_success_returns_token_and_profile(client):
    r = _register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["email"] == "rudra@example.com"  # normalised
    assert body["user"]["username"] == "Rudra"
    assert body["user"]["role"] == "analyst"
    assert "password" not in str(body).lower().replace("access_token", "")
    assert "hashed_password" not in body["user"]


def test_register_duplicate_email_rejected_case_insensitively(client):
    assert _register(client).status_code == 201
    r = _register(client, email="RUDRA@example.COM", username="Other")
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


@pytest.mark.parametrize("over,fragment", [
    ({"password": "12345"}, "at least 6"),
    ({"password": "x" * 80}, "at most"),
    ({"email": "not-an-email"}, "valid email"),
    ({"email": "a@b"}, "valid email"),
    ({"username": "x"}, "Username"),
    ({"username": "   "}, "Username"),
])
def test_register_validation(client, over, fragment):
    r = _register(client, **over)
    assert r.status_code == 422
    assert fragment in r.json()["detail"]


def test_register_missing_fields_is_422(client):
    assert client.post("/auth/register", json={"email": "a@b.co"}).status_code == 422


def test_password_is_stored_hashed(client):
    from sqlalchemy import select
    from auth_models import User
    from database import SessionLocal
    _register(client)
    with SessionLocal() as db:
        u = db.scalar(select(User))
        assert u.hashed_password != CREDS["password"]
        assert u.hashed_password.startswith("$2")
        assert svc.verify_password(CREDS["password"], u.hashed_password)
        assert not svc.verify_password("wrong", u.hashed_password)


# ---------- login ----------
def test_login_valid(client):
    _register(client)
    r = client.post("/auth/login", json={"email": "rudra@example.com", "password": CREDS["password"]})
    assert r.status_code == 200
    assert r.json()["user"]["username"] == "Rudra"


def test_login_wrong_password_and_unknown_user_look_identical(client):
    _register(client)
    bad = client.post("/auth/login", json={"email": CREDS["email"], "password": "nope-nope"})
    ghost = client.post("/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"})
    assert bad.status_code == ghost.status_code == 401
    assert bad.json() == ghost.json()


def test_login_is_throttled_after_repeated_failures(client):
    _register(client)
    for _ in range(8):
        assert client.post("/auth/login", json={"email": CREDS["email"], "password": "bad-pass"}).status_code == 401
    r = client.post("/auth/login", json={"email": CREDS["email"], "password": CREDS["password"]})
    assert r.status_code == 429


def test_oauth_form_login(client):
    _register(client)
    r = client.post("/auth/token", data={"username": CREDS["email"], "password": CREDS["password"]})
    assert r.status_code == 200 and r.json()["access_token"]


# ---------- JWT ----------
def test_me_with_valid_token(client):
    r = client.get("/auth/me", headers=_auth(_token(client)))
    assert r.status_code == 200
    assert r.json()["email"] == "rudra@example.com"


def test_token_expiry_is_seven_days(client):
    payload = jwt.decode(_token(client), options={"verify_signature": False})
    assert timedelta(days=6, hours=23) < timedelta(seconds=payload["exp"] - payload["iat"]) <= timedelta(days=7, seconds=5)


def test_expired_token_rejected(client):
    _register(client)
    old = datetime.now(timezone.utc) - timedelta(days=8)
    token = jwt.encode({"sub": "1", "iat": old, "exp": old + timedelta(days=7)}, svc._secret(), algorithm="HS256")
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401


def test_tampered_or_foreign_tokens_rejected(client):
    good = _token(client)
    assert client.get("/auth/me", headers=_auth(good + "x")).status_code == 401
    forged = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(days=1)}, "other-secret-that-is-long-enough-for-hs256-0123", algorithm="HS256")
    assert client.get("/auth/me", headers=_auth(forged)).status_code == 401
    none_alg = jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(days=1)}, None, algorithm="none")
    assert client.get("/auth/me", headers=_auth(none_alg)).status_code == 401


def test_token_for_deleted_user_rejected(client):
    from auth_models import User
    from database import SessionLocal
    token = _token(client)
    with SessionLocal() as db:
        db.delete(db.get(User, 1))
        db.commit()
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401


# ---------- protection ----------
@pytest.mark.parametrize("method,path", [
    ("get", "/auth/me"), ("get", "/auth/history"), ("get", "/auth/stats"), ("post", "/auth/save-scan"),
])
def test_protected_routes_require_auth(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


# ---------- saved scans ----------
def test_save_scan_and_history_roundtrip(client):
    h = _auth(_token(client))
    r = client.post("/auth/save-scan", headers=h, json={
        "input_type": "text", "verdict": "High trust", "credibility_score": 82.5, "summary": "Bank rates"})
    assert r.status_code == 201
    client.post("/auth/save-scan", headers=h, json={"input_type": "image", "verdict": "Low trust", "credibility_score": 20})
    hist = client.get("/auth/history", headers=h).json()
    assert hist["count"] == 2
    assert hist["scans"][0]["input_type"] == "image"  # newest first
    assert hist["scans"][1]["summary"] == "Bank rates"
    stats = client.get("/auth/stats", headers=h).json()
    assert stats == {"total_scans": 2, "average_score": 51.2}


def test_stats_empty(client):
    assert client.get("/auth/stats", headers=_auth(_token(client))).json() == {"total_scans": 0, "average_score": None}


@pytest.mark.parametrize("payload", [
    {"input_type": "video", "verdict": "x"},
    {"input_type": "text", "verdict": ""},
    {"input_type": "text", "verdict": "x", "credibility_score": 101},
    {"input_type": "text", "verdict": "x", "credibility_score": -1},
    {"input_type": "text", "verdict": "x", "summary": "y" * 501},
])
def test_save_scan_validation(client, payload):
    assert client.post("/auth/save-scan", headers=_auth(_token(client)), json=payload).status_code == 422


def test_history_is_private_per_user(client):
    a = _auth(_token(client))
    b = _auth(_register(client, email="b@example.com", username="Bee").json()["access_token"])
    client.post("/auth/save-scan", headers=a, json={"input_type": "text", "verdict": "Mine", "credibility_score": 50})
    assert client.get("/auth/history", headers=b).json()["count"] == 0
    assert client.get("/auth/history", headers=a).json()["count"] == 1


# ---------- demo ----------
def test_demo_login_is_stable_account(client):
    first = client.post("/auth/demo").json()
    second = client.post("/auth/demo").json()
    assert first["user"]["id"] == second["user"]["id"]
    assert first["user"]["username"] == "Demo Analyst"
    # its password is random: it can't be signed into with a guessed one
    assert client.post("/auth/login", json={"email": auth_routes.DEMO_EMAIL, "password": "demo123"}).status_code == 401


def test_demo_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("FAKEGUARD_DISABLE_DEMO", "1")
    assert client.post("/auth/demo").status_code == 404


# ---------- guests keep working ----------
def test_existing_endpoints_still_open_to_guests(client):
    assert client.get("/health").status_code == 200
    assert client.get("/keywords").status_code == 200
    r = client.post("/analyze", json={"text": "The central bank held rates steady on Wednesday, officials said."})
    assert r.status_code == 200 and "score" in r.json()
