"""Password hashing (bcrypt) and JWT issue/verify (PyJWT, HS256, 7-day expiry)."""
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from auth_models import User
from database import DATA_DIR, get_db

TOKEN_TTL = timedelta(days=7)
ALGORITHM = "HS256"
MAX_PASSWORD_BYTES = 72  # bcrypt cannot use more than this, so longer passwords are refused explicitly
_BCRYPT_ROUNDS = int(os.environ.get("FAKEGUARD_BCRYPT_ROUNDS", "12"))
_bearer = HTTPBearer(auto_error=False)
_secret_cache: str | None = None


def _secret() -> str:
    """FAKEGUARD_JWT_SECRET, else a random secret generated once and kept in data/jwt_secret."""
    global _secret_cache
    if _secret_cache:
        return _secret_cache
    env = os.environ.get("FAKEGUARD_JWT_SECRET")
    if env:
        _secret_cache = env
        return env
    path = DATA_DIR / "jwt_secret"
    try:
        if path.exists():
            _secret_cache = path.read_text().strip()
        else:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _secret_cache = secrets.token_urlsafe(48)
            path.write_text(_secret_cache)
    except OSError:
        _secret_cache = secrets.token_urlsafe(48)  # read-only disk: tokens last until restart
    return _secret_cache


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(_BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:MAX_PASSWORD_BYTES], hashed.encode("ascii"))
    except ValueError:
        return False


# Checked against when the account does not exist, so response time does not reveal which emails are registered.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + TOKEN_TTL}, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=401, detail="Not authenticated. Please sign in.", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None:
        raise unauthorized
    uid = decode_token(creds.credentials)
    user = db.get(User, uid) if uid is not None else None
    if user is None:
        raise unauthorized
    return user
