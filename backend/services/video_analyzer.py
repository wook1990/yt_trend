"""backend/services/video_analyzer.py — 영상 분석 서비스

curator의 분석 기능을 yt_trending 목적에 맞게 재구성.
콘텐츠 제작자 관점: 왜 급상승했는지 + 어떻게 모방할 수 있는지.

AI 우선순위: Gemini → OpenAI → 실패
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

ANALYSIS_PROMPT = """당신은 유튜브 콘텐츠 전략 전문가입니다.
아래 영상 데이터를 분석해 콘텐츠 제작자가 **비슷한 영상을 만들어 성공할 수 있도록** 구체적인 인사이트를 제공하세요.

## 영상 정보
- 제목: {title}
- 채널: {channel} (구독자: {subscribers}명)
- 카테고리: {category}
- 조회수: {views}회
- 좋아요: {likes}개
- 댓글: {comments}개
- 업로드일: {publish_date}
- 영상 길이: {duration}
- 반응률(좋아요/조회수): {engagement_rate}%
- 바이럴 계수(조회수/구독자): {viral_coefficient}x
- 스파이크 점수: {spike_score}/100
- 급등 원인 태그: {spike_reasons}

## 영상 설명
{description}

## 자막/내용 (있는 경우)
{transcript}

---

아래 JSON 형식으로 분석 결과를 반환하세요. 마크다운 코드블록 없이 JSON만 반환:

{{
  "hook": "이 영상의 핵심 가치를 한 줄로 (30자 이내, 임팩트 있게)",
  "why_viral": "왜 급상승했는지 구체적 이유 3가지를 2-3문장으로 설명",
  "summary": "영상 핵심 내용 요약 (3-4문장, 시청 안 해도 내용 파악 가능하게)",
  "copy_guide": {{
    "title_pattern": "이 영상 제목의 성공 패턴 분석 (키워드 배치, 숫자 활용, 감정 자극 방식 등)",
    "content_structure": "영상 구성 방식 (인트로→본론→결론 패턴, 핵심 포맷)",
    "target_audience": "핵심 타겟 시청자 (구체적으로)",
    "optimal_timing": "이런 영상의 최적 업로드 시기/상황",
    "similar_topics": ["비슷한 성공 가능성 높은 주제 1", "주제 2", "주제 3"]
  }},
  "key_insights": [
    "콘텐츠 제작자가 배울 수 있는 핵심 인사이트 1",
    "핵심 인사이트 2",
    "핵심 인사이트 3"
  ],
  "creator_tips": [
    "이 영상을 모방해 만들 때 반드시 포함해야 할 요소 1",
    "반드시 포함해야 할 요소 2"
  ],
  "caution": "이 영상 모방 시 주의할 점 (저작권, 포화된 주제 여부 등)"
}}"""


def analyze_video(video_data: dict) -> dict[str, Any]:
    """
    영상 데이터를 받아 AI 분석 결과 반환.

    video_data: _to_dict() 형식의 영상 메타데이터
    """
    prompt = _build_prompt(video_data)
    result = _call_ai(prompt)
    return result


def _build_prompt(v: dict) -> str:
    # 자막 시도 (yt-dlp)
    transcript = _get_transcript(v.get("video_id", ""))

    spike_reasons = ", ".join(
        r.get("label", "") for r in (v.get("spike_reasons") or [])
    ) or "없음"

    return ANALYSIS_PROMPT.format(
        title=v.get("title", ""),
        channel=v.get("channel", ""),
        subscribers=_fmt(v.get("subscriber_count")),
        category=v.get("category") or "기타",
        views=_fmt(v.get("view_count")),
        likes=_fmt(v.get("like_count")),
        comments=_fmt(v.get("comment_count")),
        publish_date=v.get("publish_date", "")[:10] if v.get("publish_date") else "불명",
        duration=_fmt_duration(v.get("duration", "")),
        engagement_rate=round(float(v.get("engagement_rate") or 0), 2),
        viral_coefficient=round(float(v.get("viral_coefficient") or 0), 1),
        spike_score=round(float(v.get("spike_score") or 0), 0),
        spike_reasons=spike_reasons,
        description="(설명 없음)",
        transcript=transcript or "(자막 없음 — 메타데이터 기반 분석)",
    )


def _get_transcript(video_id: str, max_chars: int = 3000) -> str | None:
    """yt-dlp로 자막 추출 시도."""
    if not video_id:
        return None
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": False,
            "writeautomaticsub": False,
            "skip_download": True,
            "subtitleslangs": ["ko", "en"],
        }
        url = f"https://www.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            desc = (info.get("description") or "")[:max_chars]
            return desc if desc.strip() else None
    except Exception:
        return None


def _call_ai(prompt: str) -> dict[str, Any]:
    """Gemini → OpenAI 순으로 시도."""

    # 1. Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            return _parse_json(response.text)
        except Exception as e:
            print(f"[analyzer] Gemini 실패: {e}")

    # 2. OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            return _parse_json(resp.choices[0].message.content)
        except Exception as e:
            print(f"[analyzer] OpenAI 실패: {e}")

    return {"error": "AI API를 사용할 수 없습니다. GEMINI_API_KEY 또는 OPENAI_API_KEY를 설정해주세요."}


def _parse_json(text: str) -> dict:
    """AI 응답에서 JSON 파싱."""
    # 코드블록 제거
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # JSON 부분만 추출
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {"error": "분석 결과 파싱 실패", "raw": text[:500]}


def _fmt(n: Any) -> str:
    if n is None:
        return "불명"
    n = int(n)
    if n >= 100_000_000:
        return f"{n/100_000_000:.1f}억"
    if n >= 10_000:
        return f"{n//10_000}만"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def _fmt_duration(iso: str) -> str:
    if not iso:
        return "불명"
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return iso
    h, mi, s = int(m.group(1) or 0), int(m.group(2) or 0), int(m.group(3) or 0)
    if h:
        return f"{h}시간 {mi}분"
    return f"{mi}분 {s}초"
