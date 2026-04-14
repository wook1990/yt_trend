"""backend/services/brief_generator.py — Gemini 트렌드 브리프 생성

클러스터 요약 데이터를 Gemini에 전달해 인사이트 생성.
하루 1회 호출 → 전체를 하나의 프롬프트로 처리.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models import TrendBrief
from backend.services.trend_clusterer import cluster_videos


BRIEF_PROMPT = """당신은 유튜브 콘텐츠 트렌드 분석 전문가입니다.
오늘({date}, {region}) 수집된 트렌딩 영상 데이터를 주제별로 클러스터링한 결과입니다.
각 클러스터에 대해 콘텐츠 제작자 관점의 인사이트를 제공하세요.

## 클러스터 데이터
{clusters_summary}

---
아래 JSON 형식으로만 응답하세요 (마크다운 없이):

{{
  "clusters": [
    {{
      "topic": "클러스터명 (입력 그대로)",
      "why_trending": "지금 이 주제가 뜨는 구체적 이유 (2문장)",
      "title_pattern": "성공 제목 패턴 (예: '숫자+주제+결과' 형식)",
      "creator_opportunity": "제작 기회 — 어떤 각도로 만들면 뜰지 (2문장)",
      "saturation": "낮음|보통|높음"
    }}
  ],
  "meta_insight": "오늘 전체 트렌드를 관통하는 핵심 인사이트 3-4문장. 어떤 주제가 왜 강세인지, 콘텐츠 제작자에게 가장 중요한 포인트는 무엇인지."
}}"""


def generate_and_save(
    db: Session,
    videos: list[dict[str, Any]],
    region: str = "KR",
    target_date: date | None = None,
    top_n: int = 20,
) -> TrendBrief:
    """
    영상 목록을 클러스터링하고 Gemini 브리프를 생성해 DB에 저장.
    이미 오늘 생성된 브리프가 있으면 덮어씀.
    """
    target_date = target_date or date.today()

    # 클러스터링
    clusters = cluster_videos(videos, top_n=top_n)
    if not clusters:
        raise ValueError("클러스터링 결과 없음")

    # Gemini 인사이트 생성
    insights = _call_gemini(clusters, region, str(target_date))
    if "clusters" in insights:
        _merge_insights(clusters, insights["clusters"])
    meta = insights.get("meta_insight", "")

    # DB 저장 (upsert)
    existing = db.query(TrendBrief).filter(
        TrendBrief.generated_date == target_date,
        TrendBrief.region == region,
    ).first()

    # videos 필드는 DB에 저장하지 않음 (API 응답 시 별도 조회)
    clusters_for_db = [
        {k: v for k, v in c.items() if k != "videos"}
        for c in clusters
    ]

    if existing:
        existing.clusters    = json.dumps(clusters_for_db, ensure_ascii=False)
        existing.meta_insight = meta
        existing.generated_at = datetime.now(timezone.utc)
        brief = existing
    else:
        brief = TrendBrief(
            generated_date=target_date,
            region=region,
            clusters=json.dumps(clusters_for_db, ensure_ascii=False),
            meta_insight=meta,
            generated_at=datetime.now(timezone.utc),
        )
        db.add(brief)

    db.commit()
    db.refresh(brief)
    return brief


def get_brief_with_videos(
    db: Session,
    videos: list[dict[str, Any]],
    target_date: date,
    region: str,
    top_n: int = 20,
) -> dict[str, Any] | None:
    """
    저장된 브리프를 조회하고 각 클러스터에 영상 데이터를 채워서 반환.
    """
    brief = db.query(TrendBrief).filter(
        TrendBrief.generated_date == target_date,
        TrendBrief.region == region,
    ).first()

    if not brief:
        return None

    clusters_meta = json.loads(brief.clusters)

    # 영상을 클러스터별로 재매핑 (같은 클러스터링 함수 재사용)
    clustered = cluster_videos(videos, top_n=top_n)
    video_map = {c["topic"]: c["videos"] for c in clustered}

    for c in clusters_meta:
        c["videos"] = video_map.get(c["topic"], [])

    return {
        "date":         str(target_date),
        "region":       region,
        "generated_at": brief.generated_at.isoformat(),
        "clusters":     clusters_meta,
        "meta_insight": brief.meta_insight,
    }


# ─── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _call_gemini(clusters: list[dict], region: str, date_str: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {}

    # 클러스터 요약 (제목 최대 10개만 전달해 토큰 절약)
    summaries = []
    for c in clusters:
        top_titles = [v.get("title", "") for v in c.get("videos", [])[:10]]
        summaries.append({
            "topic":          c["topic"],
            "video_count":    c["video_count"],
            "avg_spike":      c["avg_spike"],
            "avg_views":      c["avg_views"],
            "avg_engagement": c["avg_engagement"],
            "top_keywords":   c["top_keywords"],
            "sample_titles":  top_titles,
        })

    prompt = BRIEF_PROMPT.format(
        date=date_str,
        region=region,
        clusters_summary=json.dumps(summaries, ensure_ascii=False, indent=2),
    )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = re.sub(r"```(?:json)?\s*|\s*```", "", response.text).strip()
        result = json.loads(text)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        print(f"[brief_generator] Gemini 실패: {e}")
        return {}


def _merge_insights(clusters: list[dict], insights: list[dict]) -> None:
    """Gemini 인사이트를 클러스터에 병합."""
    insight_map = {i.get("topic", ""): i for i in insights}
    for c in clusters:
        ins = insight_map.get(c["topic"], {})
        c["why_trending"]        = ins.get("why_trending")
        c["title_pattern"]       = ins.get("title_pattern")
        c["creator_opportunity"] = ins.get("creator_opportunity")
        c["saturation"]          = ins.get("saturation")
