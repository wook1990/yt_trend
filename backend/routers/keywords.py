"""backend/routers/keywords.py — 사용자 커스텀 키워드 관리 API"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from backend.auth import get_current_user
from backend.database import Session
from backend.models import User, UserKeyword

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


def _get_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


class KeywordCreate(BaseModel):
    keyword: str
    region: str = "KR"


# ─── GET /api/keywords/my ─────────────────────────────────────────────────────

@router.get("/my")
def list_my_keywords(
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
) -> list[dict[str, Any]]:
    rows = (
        db.query(UserKeyword)
        .filter(UserKeyword.user_id == current_user.id, UserKeyword.is_active == True)
        .order_by(UserKeyword.created_at.desc())
        .all()
    )
    return [
        {
            "id":                r.id,
            "keyword":           r.keyword,
            "region":            r.region,
            "created_at":        r.created_at.isoformat(),
            "last_collected_at": r.last_collected_at.isoformat() if r.last_collected_at else None,
        }
        for r in rows
    ]


# ─── POST /api/keywords/my ───────────────────────────────────────────────────

@router.post("/my", status_code=201)
def add_keyword(
    body: KeywordCreate,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
) -> dict[str, Any]:
    keyword = body.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="키워드를 입력해주세요.")
    if len(keyword) > 100:
        raise HTTPException(status_code=400, detail="키워드는 100자 이하여야 합니다.")

    existing = (
        db.query(UserKeyword)
        .filter(
            UserKeyword.user_id == current_user.id,
            UserKeyword.keyword == keyword,
        )
        .first()
    )
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
            return {"id": existing.id, "keyword": existing.keyword, "region": existing.region}
        raise HTTPException(status_code=409, detail="이미 등록된 키워드입니다.")

    kw = UserKeyword(
        user_id=current_user.id,
        keyword=keyword,
        region=body.region,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return {"id": kw.id, "keyword": kw.keyword, "region": kw.region}


# ─── DELETE /api/keywords/my/{id} ────────────────────────────────────────────

@router.delete("/my/{keyword_id}", status_code=204)
def delete_keyword(
    keyword_id: int,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
) -> None:
    kw = (
        db.query(UserKeyword)
        .filter(UserKeyword.id == keyword_id, UserKeyword.user_id == current_user.id)
        .first()
    )
    if not kw:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다.")
    kw.is_active = False
    db.commit()


# ─── POST /api/keywords/collect ──────────────────────────────────────────────

@router.post("/collect")
def trigger_collect(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(_get_db),
) -> dict[str, str]:
    keywords = (
        db.query(UserKeyword)
        .filter(UserKeyword.user_id == current_user.id, UserKeyword.is_active == True)
        .all()
    )
    if not keywords:
        raise HTTPException(status_code=400, detail="등록된 키워드가 없습니다.")

    kw_data = [{"id": k.id, "keyword": k.keyword, "region": k.region} for k in keywords]
    background_tasks.add_task(_run_keyword_collect, current_user.id, kw_data)
    return {"status": "started", "count": str(len(kw_data))}


def _run_keyword_collect(user_id: int, kw_data: list[dict]) -> None:
    from datetime import datetime, timezone
    from src.fetcher.yt_search import search_by_keyword
    from backend.collector import _save_videos
    from backend.database import Session as DBSession2

    db = DBSession2()
    try:
        for item in kw_data:
            try:
                videos = search_by_keyword(
                    keyword=item["keyword"],
                    region=item["region"],
                    limit=20,
                    published_within_days=7,
                )
                if videos:
                    _save_videos(db, videos, region=item["region"])
                # 수집 시각 업데이트
                kw = db.query(UserKeyword).filter(UserKeyword.id == item["id"]).first()
                if kw:
                    kw.last_collected_at = datetime.now(timezone.utc)
                    db.commit()
                print(f"[keywords] '{item['keyword']}' — {len(videos)}개 수집")
            except Exception as e:
                print(f"[keywords] '{item['keyword']}' 수집 실패: {e}")
    finally:
        db.close()
