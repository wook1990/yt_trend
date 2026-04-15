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


COMPARE_PROMPT = """당신은 YouTube 콘텐츠 전략 컨설턴트입니다.
두 주제를 비교 분석하고, 부업 크리에이터 관점에서 어느 쪽이 더 유리한지 판단해주세요.

## 주제 A: "{topic_a}" ({count_a}개 영상, 최근 {days}일)
{videos_a}

## 주제 B: "{topic_b}" ({count_b}개 영상, 최근 {days}일)
{videos_b}

---
아래 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):

{{
  "winner": "A | B | 동등",
  "winner_reason": "승자 판단 근거 (2문장)",
  "topic_a": {{
    "topic_overview": "주제 A 현황 (2문장)",
    "trend_direction": {{"status": "급상승 | 안정 | 하락", "reason": "근거 (1문장)"}},
    "competition_analysis": {{"level": "레드오션 | 블루오션 | 틈새시장", "detail": "분석 (1문장)"}},
    "cpm_potential": "높음 | 보통 | 낮음",
    "entry_difficulty": "쉬움 | 보통 | 어려움",
    "best_content_idea": {{"title": "추천 영상 제목", "why": "이유 (1문장)"}}
  }},
  "topic_b": {{
    "topic_overview": "주제 B 현황 (2문장)",
    "trend_direction": {{"status": "급상승 | 안정 | 하락", "reason": "근거 (1문장)"}},
    "competition_analysis": {{"level": "레드오션 | 블루오션 | 틈새시장", "detail": "분석 (1문장)"}},
    "cpm_potential": "높음 | 보통 | 낮음",
    "entry_difficulty": "쉬움 | 보통 | 어려움",
    "best_content_idea": {{"title": "추천 영상 제목", "why": "이유 (1문장)"}}
  }},
  "recommendation": "두 주제를 고려했을 때 크리에이터에게 구체적으로 권장하는 전략 (3문장)"
}}"""

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
}}

## 적용된 필터 조건
{filter_context}"""


def analyze_topic(
    topic: str,
    region: str = "KR",
    days: int = 30,
    search_limit: int = 30,
    video_type: str = "all",
    min_views: int = 0,
    max_subscriber_tier: str = "all",
    sort_by: str = "view_count",
    compare_topic: str = "",
) -> dict[str, Any]:
    """
    주제를 YouTube에서 검색하고 Gemini로 심층 분석.

    Returns:
        {
            "topic": str,
            "region": str,
            "analyzed_at": str,
            "video_count": int,
            "videos": list[dict],
            "analysis": dict,
            "filters": dict,        # 적용된 필터 조건
            "compare": dict | None, # 비교 분석 결과 (compare_topic 있을 때)
        }
    """
    from src.fetcher.yt_search import search_by_keyword

    filters = {
        "video_type": video_type,
        "min_views": min_views,
        "max_subscriber_tier": max_subscriber_tier,
        "sort_by": sort_by,
    }

    # 1. YouTube 검색
    videos = search_by_keyword(
        keyword=topic,
        region=region,
        limit=search_limit,
        published_within_days=days,
    )

    # 2. 필터 적용
    videos = _apply_filters(videos, video_type, min_views, max_subscriber_tier)
    videos = _sort_videos(videos, sort_by)

    # 3. Gemini 심층 분석
    filter_context = _build_filter_context(filters)
    analysis = _call_gemini(topic, videos, days, filter_context=filter_context)

    result: dict[str, Any] = {
        "topic":       topic,
        "region":      region,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "video_count": len(videos),
        "videos":      _slim_videos(videos),
        "analysis":    analysis,
        "filters":     filters,
        "compare":     None,
    }

    # 4. 비교 분석 (선택)
    if compare_topic:
        compare_videos = search_by_keyword(
            keyword=compare_topic,
            region=region,
            limit=search_limit,
            published_within_days=days,
        )
        compare_videos = _apply_filters(compare_videos, video_type, min_views, max_subscriber_tier)
        compare_videos = _sort_videos(compare_videos, sort_by)
        result["compare"] = {
            "topic":       compare_topic,
            "video_count": len(compare_videos),
            "videos":      _slim_videos(compare_videos),
            "analysis":    _call_gemini_compare(
                topic, videos, compare_topic, compare_videos, days
            ),
        }

    return result


# ─── 필터 / 정렬 헬퍼 ────────────────────────────────────────────────────────

def _apply_filters(
    videos: list[dict],
    video_type: str,
    min_views: int,
    max_subscriber_tier: str,
) -> list[dict]:
    result = []
    for v in videos:
        # 영상 타입 필터
        if video_type != "all":
            secs = _duration_seconds(v.get("duration", ""))
            is_short = 0 < secs <= 60
            if video_type == "short" and not is_short:
                continue
            if video_type == "long" and is_short:
                continue

        # 최소 조회수 필터
        if min_views > 0 and (v.get("view_count") or 0) < min_views:
            continue

        # 채널 구독자 규모 필터
        if max_subscriber_tier != "all":
            subs = v.get("subscriber_count") or v.get("channel_subscriber_count") or 0
            if max_subscriber_tier == "small" and subs >= 100_000:
                continue
            elif max_subscriber_tier == "mid" and subs >= 1_000_000:
                continue
            # "large" = 100만 이상만 포함
            elif max_subscriber_tier == "large" and subs < 1_000_000:
                continue

        result.append(v)
    return result


def _sort_videos(videos: list[dict], sort_by: str) -> list[dict]:
    if sort_by == "upload_date":
        return sorted(videos, key=lambda v: v.get("upload_date", ""), reverse=True)
    elif sort_by == "engagement":
        def engagement(v: dict) -> float:
            views = v.get("view_count") or 1
            likes = v.get("like_count") or 0
            comments = v.get("comment_count") or 0
            return (likes + comments * 2) / views
        return sorted(videos, key=engagement, reverse=True)
    else:  # view_count (default)
        return sorted(videos, key=lambda v: v.get("view_count") or 0, reverse=True)


def _build_filter_context(filters: dict) -> str:
    parts = []
    vt = filters.get("video_type", "all")
    if vt == "short":
        parts.append("쇼츠(60초 이하)만 포함")
    elif vt == "long":
        parts.append("롱폼(60초 초과)만 포함")

    mv = filters.get("min_views", 0)
    if mv > 0:
        parts.append(f"최소 조회수 {mv:,}회 이상")

    tier = filters.get("max_subscriber_tier", "all")
    tier_labels = {"small": "소형 채널(10만 미만)", "mid": "중형 채널(100만 미만)", "large": "대형 채널(100만 이상)"}
    if tier in tier_labels:
        parts.append(tier_labels[tier])

    sb = filters.get("sort_by", "view_count")
    sort_labels = {"view_count": "조회수 높은 순", "upload_date": "최신 업로드 순", "engagement": "참여율 높은 순"}
    parts.append(f"정렬: {sort_labels.get(sb, sb)}")

    return " / ".join(parts) if parts else "필터 없음 (전체)"


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


def _call_gemini(topic: str, videos: list[dict], days: int, filter_context: str = "필터 없음") -> dict:
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
        filter_context=filter_context,
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


def _call_gemini_compare(
    topic_a: str,
    videos_a: list[dict],
    topic_b: str,
    videos_b: list[dict],
    days: int,
) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "GEMINI_API_KEY 미설정"}

    def _summarize(videos: list[dict]) -> list[dict]:
        result = []
        for v in videos[:20]:
            secs = _duration_seconds(v.get("duration", ""))
            result.append({
                "title":        v.get("title", ""),
                "channel":      v.get("channel", ""),
                "view_count":   v.get("view_count") or 0,
                "like_count":   v.get("like_count") or 0,
                "comment_count": v.get("comment_count") or 0,
                "upload_date":  v.get("upload_date", ""),
                "duration_sec": secs,
                "is_short":     0 < secs <= 60,
            })
        return result

    prompt = COMPARE_PROMPT.format(
        topic_a=topic_a,
        count_a=len(videos_a),
        topic_b=topic_b,
        count_b=len(videos_b),
        days=days,
        videos_a=json.dumps(_summarize(videos_a), ensure_ascii=False, indent=2),
        videos_b=json.dumps(_summarize(videos_b), ensure_ascii=False, indent=2),
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
        print(f"[topic_analyzer] Gemini 비교 분석 실패: {e}")
        return {"error": str(e)}
