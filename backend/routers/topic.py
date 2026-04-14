"""backend/routers/topic.py — 주제 심층 분석 API"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/topic", tags=["topic"])


class TopicRequest(BaseModel):
    topic: str
    region: str = "KR"
    days: int = 30
    limit: int = 30


@router.post("/analyze", response_model=None)
def analyze_topic(req: TopicRequest) -> dict[str, Any]:
    """
    특정 주제를 YouTube에서 검색 후 Gemini 심층 전략 분석.
    - topic: 분석할 주제 (예: '파이썬 자동화 부업', '간헐적 단식', '스마트스토어 창업')
    - region: KR | US | JP
    - days: 최근 N일 내 영상 대상
    - limit: 검색할 영상 수 (최대 50)
    """
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic은 필수입니다.")
    if len(topic) > 100:
        raise HTTPException(status_code=400, detail="topic은 100자 이하여야 합니다.")

    from backend.services.topic_analyzer import analyze_topic as _analyze
    try:
        result = _analyze(
            topic=topic,
            region=req.region,
            days=req.days,
            search_limit=min(req.limit, 50),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result
