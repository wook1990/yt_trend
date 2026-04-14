"""src/filter.py — 수집 결과 필터링

수집한 영상 목록에서 조건에 맞는 영상만 추려냄.
"""

from __future__ import annotations

from typing import Any


def apply(
    videos: list[dict[str, Any]],
    *,
    min_views: int | None = None,
    max_duration: int | None = None,   # 초
    min_duration: int | None = None,   # 초
    keyword: str | None = None,        # 제목/설명 포함 여부
    exclude_keyword: str | None = None,
) -> list[dict[str, Any]]:
    """
    필터 조건을 순차 적용해 영상 목록 반환.

    Args:
        videos:          fetcher가 반환한 영상 목록
        min_views:       최소 조회수
        max_duration:    최대 길이 (초)
        min_duration:    최소 길이 (초)
        keyword:         제목 또는 설명에 포함되어야 할 키워드
        exclude_keyword: 제목 또는 설명에 없어야 할 키워드
    """
    result = videos

    if min_views is not None:
        result = [v for v in result if (v.get("view_count") or 0) >= min_views]

    if min_duration is not None:
        result = [v for v in result if _duration_sec(v) >= min_duration]

    if max_duration is not None:
        result = [v for v in result if _duration_sec(v) <= max_duration]

    if keyword:
        kw = keyword.lower()
        result = [
            v for v in result
            if kw in (v.get("title") or "").lower()
            or kw in (v.get("description") or "").lower()
        ]

    if exclude_keyword:
        ekw = exclude_keyword.lower()
        result = [
            v for v in result
            if ekw not in (v.get("title") or "").lower()
            and ekw not in (v.get("description") or "").lower()
        ]

    return result


def _duration_sec(video: dict) -> int:
    """duration 값을 초로 변환. ytdlp는 int, yt_api는 ISO 8601 문자열."""
    dur = video.get("duration")
    if isinstance(dur, int):
        return dur
    if isinstance(dur, str) and dur.startswith("PT"):
        return _parse_iso_duration(dur)
    return 0


def _parse_iso_duration(s: str) -> int:
    """PT4M13S → 253초"""
    import re
    h = int(m.group(1)) if (m := re.search(r"(\d+)H", s)) else 0
    m_ = int(m.group(1)) if (m := re.search(r"(\d+)M", s)) else 0
    sec = int(m.group(1)) if (m := re.search(r"(\d+)S", s)) else 0
    return h * 3600 + m_ * 60 + sec
