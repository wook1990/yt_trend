"""backend/routers/brief.py — 트렌드 브리프 API"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.routers.trending import _get_videos_for_date
from backend.services.brief_generator import generate_and_save, get_brief_with_videos

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.get("", response_model=None)
def get_brief(
    region: str = Query("KR"),
    date_str: str | None = Query(None, alias="date"),
    top_n: int = Query(20),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    오늘(또는 지정 날짜)의 트렌드 브리프 반환.
    DB에 없으면 자동 생성.
    """
    target_date = date.fromisoformat(date_str) if date_str else date.today()

    # 해당 날짜 영상 조회
    videos = _get_videos_for_date(db, target_date, region)
    if not videos:
        raise HTTPException(status_code=404, detail="해당 날짜 영상 없음")

    # 저장된 브리프가 있으면 반환
    brief = get_brief_with_videos(db, videos, target_date, region, top_n=top_n)
    if brief:
        return brief

    # 없으면 자동 생성
    try:
        generate_and_save(db, videos, region=region, target_date=target_date, top_n=top_n)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    brief = get_brief_with_videos(db, videos, target_date, region, top_n=top_n)
    if not brief:
        raise HTTPException(status_code=500, detail="브리프 생성 실패")
    return brief


@router.post("/generate", response_model=None)
def force_generate_brief(
    region: str = Query("KR"),
    date_str: str | None = Query(None, alias="date"),
    top_n: int = Query(20),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """브리프 강제 재생성."""
    target_date = date.fromisoformat(date_str) if date_str else date.today()

    videos = _get_videos_for_date(db, target_date, region)
    if not videos:
        raise HTTPException(status_code=404, detail="해당 날짜 영상 없음")

    try:
        generate_and_save(db, videos, region=region, target_date=target_date, top_n=top_n)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    brief = get_brief_with_videos(db, videos, target_date, region, top_n=top_n)
    return brief
