"""backend/services/topic_analyzer.py — 특정 주제 심층 전략 분석

사용자가 입력한 주제로 YouTube를 검색 → 상위 영상 분석 → Gemini가
콘텐츠 제작자 관점의 심층 전략 리포트 생성.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any


ANALYSIS_PROMPT = """당신은 YouTube 콘텐츠 전략 컨설턴트입니다.
주제 "{topic}" 에 대한 YouTube 시장을 분석하고, 이 주제로 채널을 만들거나 영상을 제작하려는 크리에이터에게
최대한 구체적이고 실행 가능한 전략을 제시해주세요.

## 분석 대상 영상 데이터 ({video_count}개, 최근 {days}일)
{videos_json}

---
아래 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):

{{
  "topic_overview": "이 주제의 YouTube 생태계 현황 — 누가 장악하고 있는지, 어떤 채널이 강세인지, 시청자 규모는 어느 정도인지 (3문장)",

  "trend_direction": {{
    "status": "급상승 | 안정 | 하락",
    "reason": "트렌드 방향 판단 근거 (2문장)"
  }},

  "audience_persona": "이 주제를 보는 시청자는 누구인가 — 연령대, 주요 고민/목표, 어떤 정보를 원하는지 (3문장)",

  "competition_analysis": {{
    "level": "레드오션 | 블루오션 | 틈새시장",
    "detail": "경쟁 강도와 진입 난이도 분석 (2문장)",
    "dominant_channels": ["강세 채널명 또는 채널 유형 1", "채널 유형 2", "채널 유형 3"]
  }},

  "winning_formats": [
    {{
      "format": "포맷명 (예: 단계별 튜토리얼, 실패 사례 고백, 비교 리뷰)",
      "why_works": "이 포맷이 이 주제에서 통하는 이유 (1문장)",
      "example_title": "예시 제목"
    }}
  ],

  "title_formulas": [
    {{
      "formula": "제목 공식 (예: [숫자]가지 [주제] [결과/효과] 실제로 해봤더니)",
      "explanation": "이 공식이 클릭을 유도하는 심리적 이유 (1문장)",
      "sample": "실제 적용 예시 제목"
    }}
  ],

  "content_gaps": [
    {{
      "gap": "아직 잘 다루지 않는 각도/포맷/관점",
      "opportunity": "왜 이게 기회인지 (1문장)"
    }}
  ],

  "content_ideas": [
    {{
      "title": "구체적인 영상 제목 (올릴 수 있을 만큼 구체적으로)",
      "hook": "첫 30초 오프닝 훅 아이디어",
      "why_will_work": "이 영상이 뜰 것 같은 이유 (1문장)",
      "difficulty": "쉬움 | 보통 | 어려움"
    }}
  ],

  "seo_keywords": ["이 주제 영상에 반드시 넣어야 할 검색 키워드 5~8개"],

  "creator_strategy": "이 주제로 성공하려면 어떤 포지셔닝과 전략이 필요한지 — 차별화 포인트, 업로드 빈도, 초기 전략 등 (4~5문장 실행 가이드)"
}}"""


def analyze_topic(
    topic: str,
    region: str = "KR",
    days: int = 30,
    search_limit: int = 30,
) -> dict[str, Any]:
    """
    주제를 YouTube에서 검색하고 Gemini로 심층 분석.

    Returns:
        {
            "topic": str,
            "region": str,
            "analyzed_at": str,
            "video_count": int,
            "videos": list[dict],   # 검색된 영상 목록
            "analysis": dict,       # Gemini 분석 결과
        }
    """
    from src.fetcher.yt_search import search_by_keyword

    # 1. YouTube 검색
    videos = search_by_keyword(
        keyword=topic,
        region=region,
        limit=search_limit,
        published_within_days=days,
    )

    # 2. Gemini 심층 분석
    analysis = _call_gemini(topic, videos, days)

    return {
        "topic":       topic,
        "region":      region,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "video_count": len(videos),
        "videos":      _slim_videos(videos),
        "analysis":    analysis,
    }


# ─── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _slim_videos(videos: list[dict]) -> list[dict]:
    """프론트엔드 표시에 필요한 필드만 추출."""
    result = []
    for v in videos:
        duration = v.get("duration", "")
        secs = _duration_seconds(duration)
        result.append({
            "video_id":    v.get("id", ""),
            "url":         f"https://www.youtube.com/shorts/{v.get('id','')}" if 0 < secs <= 60 else f"https://www.youtube.com/watch?v={v.get('id','')}",
            "title":       v.get("title", ""),
            "channel":     v.get("channel", ""),
            "view_count":  v.get("view_count") or 0,
            "like_count":  v.get("like_count"),
            "comment_count": v.get("comment_count"),
            "duration":    duration,
            "duration_seconds": secs,
            "is_short":    0 < secs <= 60,
            "upload_date": v.get("upload_date", ""),
            "thumbnail":   v.get("thumbnail", ""),
        })
    return result


def _duration_seconds(duration: str | None) -> int:
    if not duration:
        return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _call_gemini(topic: str, videos: list[dict], days: int) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY 미설정"}

    # 분석용 영상 요약 (Gemini에 전달할 핵심 정보)
    video_summaries = []
    for v in videos[:30]:
        secs = _duration_seconds(v.get("duration", ""))
        video_summaries.append({
            "title":       v.get("title", ""),
            "channel":     v.get("channel", ""),
            "view_count":  v.get("view_count") or 0,
            "like_count":  v.get("like_count") or 0,
            "comment_count": v.get("comment_count") or 0,
            "upload_date": v.get("upload_date", ""),
            "duration_sec": secs,
            "is_short":    0 < secs <= 60,
            "description": (v.get("description") or "")[:200],
        })

    prompt = ANALYSIS_PROMPT.format(
        topic=topic,
        video_count=len(video_summaries),
        days=days,
        videos_json=json.dumps(video_summaries, ensure_ascii=False, indent=2),
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
        return result if isinstance(result, dict) else {"error": "파싱 실패", "raw": text[:500]}
    except json.JSONDecodeError as e:
        return {"error": f"JSON 파싱 실패: {e}"}
    except Exception as e:
        print(f"[topic_analyzer] Gemini 실패: {e}")
        return {"error": str(e)}
