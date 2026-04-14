"""backend/database.py — DB 연결 (SQLite 로컬 / PostgreSQL 운영)"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# DATABASE_URL 환경변수 우선, 없으면 로컬 SQLite
_DATABASE_URL = os.environ.get("DATABASE_URL", "")

if _DATABASE_URL:
    # Neon/Supabase 등에서 "postgres://" prefix 사용 시 수정
    if _DATABASE_URL.startswith("postgres://"):
        _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)
    engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
else:
    DATA_DIR = Path(__file__).parent.parent / "data"
    DATA_DIR.mkdir(exist_ok=True)
    DB_PATH = DATA_DIR / "trending.db"
    engine  = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )

Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    if not _DATABASE_URL:
        _migrate_sqlite()


def _migrate_sqlite():
    """SQLite 전용: 기존 DB에 새 컬럼 추가."""
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE trending_snapshots ADD COLUMN title_ko VARCHAR(500)"))
            conn.commit()
        except Exception:
            pass
