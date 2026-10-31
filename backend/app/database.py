"""SQLite persistence for accounts and saved scans (SQLAlchemy 2.0)."""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Runtime state (database, JWT secret) lives in backend/app/data/, which is git-ignored.
DATA_DIR = Path(os.environ.get("FAKEGUARD_DATA_DIR") or Path(__file__).resolve().parent / "data")
DB_URL = os.environ.get("FAKEGUARD_DB_URL")
if not DB_URL:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_URL = f"sqlite:///{(DATA_DIR / 'fakeguard.db').as_posix()}"

_connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    import auth_models  # noqa: F401  (registers the tables on Base.metadata)
    Base.metadata.create_all(engine)


def get_db():
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
