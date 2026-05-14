"""backend/routers/topic.py — 주제 심층 분석 API"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/topic", tags=["topic"])


class TopicRequest(BaseModel):
    topic: str
    region: str = "KR"
    days: int = 0           # 업로드일 기준: 0=오늘, 1=어제~오늘, 7=최근7일 (0이면 1로 처리)
    limit: int = 30
    # 필터
    max_subscriber: int = 0          # 최대 구독자수 (0=제한없음)
    min_duration_minutes: int = 0    # 최소 재생시간(분) (0=제한없음)
    sort_by: str = "view_count"       # "view_count" | "upload_date" | "engagement"
    compare_topic: str = ""           # 비교 주제


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
            max_subscriber=req.max_subscriber,
            min_duration_minutes=req.min_duration_minutes,
            sort_by=req.sort_by,
            compare_topic=req.compare_topic.strip(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return result
