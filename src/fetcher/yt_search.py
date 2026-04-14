"""src/fetcher/yt_search.py — YouTube Search API 기반 키워드 수집

search.list (100 units/call) → video_ids 추출 → videos.list (1 unit/call) 상세 조회.
카테고리 시스템에 없는 고CPM 주제(재테크/창업/AI 등)를 직접 검색으로 수집.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

API_BASE = "https://www.googleapis.com/youtube/v3"


def search_by_keyword(
    keyword: str,
    region: str = "KR",
    limit: int = 15,
    published_within_days: int = 30,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """
    키워드로 최근 인기 영상을 검색해 반환.

    Args:
        keyword:              검색어
        region:               ISO 3166-1 alpha-2 국가 코드
        limit:                최대 결과 수 (search.list 최대 50)
        published_within_days: 최근 N일 내 업로드된 영상만
        api_key:              YouTube Data API key (없으면 환경변수 사용)

    Returns:
        영상 메타데이터 딕셔너리 리스트 (yt_api._normalize 동일 포맷 + search_keyword 필드)
    """
    key = api_key or os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        print("[yt_search] YOUTUBE_API_KEY가 설정되지 않았습니다.", file=sys.stderr)
        return []

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=published_within_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Step 1 — 검색으로 video_id 목록 획득 (100 units)
    search_params: dict[str, Any] = {
        "part":          "id",
        "q":             keyword,
        "regionCode":    region,
        "type":          "video",
        "order":         "viewCount",        # 조회수 높은 순
        "publishedAfter": published_after,
        "maxResults":    min(limit, 50),
        "key":           key,
    }
    if region == "KR":
        search_params["relevanceLanguage"] = "ko"

    resp = requests.get(f"{API_BASE}/search", params=search_params, timeout=10)
    if not resp.ok:
        print(f"[yt_search] search.list 오류 ({keyword}): {resp.status_code} {resp.text[:150]}", file=sys.stderr)
        return []

    video_ids = [
        item["id"]["videoId"]
        for item in resp.json().get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    if not video_ids:
        return []

    # Step 2 — 상세 정보 조회 (1 unit)
    detail_resp = requests.get(
        f"{API_BASE}/videos",
        params={
            "part":   "snippet,statistics,contentDetails",
            "id":     ",".join(video_ids),
            "key":    key,
        },
        timeout=10,
    )
    if not detail_resp.ok:
        return []

    results = []
    for item in detail_resp.json().get("items", []):
        normalized = _normalize(item, region)
        normalized["search_keyword"] = keyword  # 어떤 키워드로 발견됐는지 기록
        results.append(normalized)

    # 조회수 내림차순 정렬
    results.sort(key=lambda x: x.get("view_count") or 0, reverse=True)
    return results


def _normalize(item: dict, region: str) -> dict:
    snippet = item.get("snippet", {})
    stats   = item.get("statistics", {})
    content = item.get("contentDetails", {})

    thumbnails = snippet.get("thumbnails", {})
    thumb = (thumbnails.get("maxres") or thumbnails.get("high") or {}).get("url", "")

    return {
        "id":            item.get("id", ""),
        "url":           f"https://www.youtube.com/watch?v={item.get('id', '')}",
        "title":         snippet.get("title", ""),
        "channel":       snippet.get("channelTitle", ""),
        "channel_id":    snippet.get("channelId", ""),
        "view_count":    _int(stats.get("viewCount")),
        "like_count":    _int(stats.get("likeCount")),
        "comment_count": _int(stats.get("commentCount")),
        "duration":      content.get("duration", ""),
        "upload_date":   snippet.get("publishedAt", "")[:10],
        "description":   (snippet.get("description") or "")[:300],
        "thumbnail":     thumb,
        "tags":          snippet.get("tags") or [],
        "category_id":   _int(snippet.get("categoryId")),
        "region":        region,
        "fetched_at":    datetime.now(timezone.utc).isoformat(),
        "provider":      "yt_search",
    }


def _int(val: Any) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
