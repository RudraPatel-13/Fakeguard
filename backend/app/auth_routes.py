"""/auth endpoints: register, login, me, history, stats, save-scan, demo login."""
import os
import re
import secrets
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import auth_service as svc
from auth_models import ScanHistory, User
from database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
DEMO_EMAIL = "demo.analyst@fakeguard.local"

# Brute-force throttle: 8 failed sign-ins per (email, client) per 10 minutes -> HTTP 429.
_FAIL_LIMIT, _FAIL_WINDOW = 8, 600
_failures: dict[str, deque] = defaultdict(deque)


def reset_throttle() -> None:
    _failures.clear()


def _throttle_key(email: str, request: Request) -> str:
    return f"{email}|{request.client.host if request.client else '?'}"


def _check_throttle(key: str) -> None:
    q = _failures[key]
    while q and time.monotonic() - q[0] > _FAIL_WINDOW:
        q.popleft()
    if len(q) >= _FAIL_LIMIT:
        raise HTTPException(status_code=429, detail="Too many failed sign-in attempts. Try again in a few minutes.")


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class SaveScanIn(BaseModel):
    input_type: str = Field(pattern="^(text|image)$")
    verdict: str = Field(min_length=1, max_length=60)
    credibility_score: float | None = Field(default=None, ge=0, le=100)
    summary: str = Field(default="", max_length=500)


def _user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "username": u.username, "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None}


def _scan_out(s: ScanHistory) -> dict:
    return {"id": s.id, "input_type": s.input_type, "verdict": s.verdict, "credibility_score": s.credibility_score,
            "summary": s.summary, "timestamp": s.timestamp.isoformat() if s.timestamp else None}


def _session(u: User) -> dict:
    return {"access_token": svc.create_access_token(u.id), "token_type": "bearer", "user": _user_out(u)}


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    username = body.username.strip()
    if not _EMAIL.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if not 2 <= len(username) <= 32:
        raise HTTPException(422, "Username must be 2-32 characters.")
    if len(body.password) < 6:
        raise HTTPException(422, "Password must be at least 6 characters.")
    if len(body.password.encode("utf-8")) > svc.MAX_PASSWORD_BYTES:
        raise HTTPException(422, f"Password must be at most {svc.MAX_PASSWORD_BYTES} bytes.")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=email, username=username, hashed_password=svc.hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # lost a race with a concurrent registration
        db.rollback()
        raise HTTPException(409, "An account with this email already exists.")
    return _session(user)


def _authenticate(db: Session, email: str, password: str, request: Request) -> User:
    email = email.strip().lower()
    key = _throttle_key(email, request)
    _check_throttle(key)
    user = db.scalar(select(User).where(User.email == email))
    ok = svc.verify_password(password, user.hashed_password if user else svc.DUMMY_HASH)
    if not user or not ok:
        _failures[key].append(time.monotonic())
        raise HTTPException(401, "Invalid email or password.", headers={"WWW-Authenticate": "Bearer"})
    _failures.pop(key, None)
    return user


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    return _session(_authenticate(db, body.email, body.password, request))


@router.post("/token")
def token_form(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password-form login (the username field is the email), mainly for the Swagger UI Authorize button."""
    return _session(_authenticate(db, form.username, form.password, request))


@router.post("/demo")
def demo_login(db: Session = Depends(get_db)):
    """One-click evaluator access to a shared demo account whose password is random and unknown.
    Disable with FAKEGUARD_DISABLE_DEMO=1."""
    if os.environ.get("FAKEGUARD_DISABLE_DEMO") == "1":
        raise HTTPException(404, "Demo login is disabled on this server.")
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if not user:
        user = User(email=DEMO_EMAIL, username="Demo Analyst",
                    hashed_password=svc.hash_password(secrets.token_urlsafe(24)))
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    return _session(user)


@router.get("/me")
def me(user: User = Depends(svc.get_current_user)):
    return _user_out(user)


@router.get("/history")
def history(limit: int = Query(50, ge=1, le=200), user: User = Depends(svc.get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ScanHistory).where(ScanHistory.user_id == user.id)
        .order_by(ScanHistory.timestamp.desc(), ScanHistory.id.desc()).limit(limit)
    ).all()
    return {"count": len(rows), "scans": [_scan_out(r) for r in rows]}


@router.get("/stats")
def stats(user: User = Depends(svc.get_current_user), db: Session = Depends(get_db)):
    total, avg = db.execute(
        select(func.count(ScanHistory.id), func.avg(ScanHistory.credibility_score)).where(ScanHistory.user_id == user.id)
    ).one()
    return {"total_scans": total, "average_score": round(avg, 1) if avg is not None else None}


@router.post("/save-scan", status_code=201)
def save_scan(body: SaveScanIn, user: User = Depends(svc.get_current_user), db: Session = Depends(get_db)):
    scan = ScanHistory(user_id=user.id, input_type=body.input_type, verdict=body.verdict.strip(),
                       credibility_score=body.credibility_score, summary=body.summary.strip())
    db.add(scan)
    db.commit()
    return _scan_out(scan)
