"""backend/services/translator.py — Gemini 기반 영상 제목 한국어 번역

여러 제목을 한 번에 배치 번역해 API 호출 수를 최소화.
"""

from __future__ import annotations

import json
import os
import re


def translate_titles(titles: list[str]) -> dict[str, str]:
    """
    제목 목록을 Gemini로 한국어 번역.

    Returns:
        {원본제목: 한국어번역} 딕셔너리
    """
    if not titles:
        return {}

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[translator] GEMINI_API_KEY 없음 — 번역 스킵")
        return {}

    # 50개씩 배치 처리
    result: dict[str, str] = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i+50]
        result.update(_translate_batch(batch, api_key))
    return result


def _translate_batch(titles: list[str], api_key: str) -> dict[str, str]:
    prompt = (
        "다음 YouTube 영상 제목들을 자연스러운 한국어로 번역해주세요.\n"
        "- 고유명사(인물명, 브랜드명)는 그대로 유지\n"
        "- 제목의 임팩트와 톤을 살려서 번역\n"
        "- JSON 형식으로만 응답: {\"원본\": \"번역\", ...}\n\n"
        "제목 목록:\n"
        + json.dumps(titles, ensure_ascii=False)
    )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()
        # 코드블록 제거
        text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except Exception as e:
        print(f"[translator] Gemini 번역 실패: {e}")

    return {}
