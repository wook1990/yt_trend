"""src/fetcher/yt_api.py — YouTube Data API v3 기반 trending 수집

공식 API 사용. YOUTUBE_API_KEY 환경 변수 필요.
일일 할당량: 10,000 units (videos.list = 1 unit per call)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

import requests

API_BASE = "https://www.googleapis.com/youtube/v3"


def fetch(region: str = "KR", category: int = 0, limit: int = 50) -> list[dict[str, Any]]:
    """
    YouTube Data API v3로 mostPopular 영상 수집.

    Args:
        region:   ISO 3166-1 alpha-2 국가 코드
        category: YouTube 카테고리 ID (0 = 전체)
        limit:    최대 수집 수 (API 최대 50)

    Returns:
        영상 메타데이터 딕셔너리 리스트
    """
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("[yt_api] YOUTUBE_API_KEY가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    params: dict[str, Any] = {
        "part":        "snippet,statistics,contentDetails",
        "chart":       "mostPopular",
        "regionCode":  region,
        "maxResults":  min(limit, 50),
        "key":         api_key,
    }
    if category != 0:
        params["videoCategoryId"] = str(category)

    all_videos = []
    page_token = None

    while len(all_videos) < limit:
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(f"{API_BASE}/videos", params=params, timeout=10)
        if not resp.ok:
            print(f"[yt_api] API 오류 {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            break

        data = resp.json()
        for item in data.get("items", []):
            all_videos.append(_normalize(item, region))

        page_token = data.get("nextPageToken")
        if not page_token or len(all_videos) >= limit:
            break

    return all_videos[:limit]


def _normalize(item: dict, region: str) -> dict:
    """API 응답을 통일된 포맷으로 변환."""
    snippet = item.get("snippet", {})
    stats   = item.get("statistics", {})
    content = item.get("contentDetails", {})

    thumbnails = snippet.get("thumbnails", {})
    thumb = (thumbnails.get("maxres") or thumbnails.get("high") or {}).get("url", "")

    return {
        "id":           item.get("id", ""),
        "url":          f"https://www.youtube.com/watch?v={item.get('id', '')}",
        "title":        snippet.get("title", ""),
        "channel":      snippet.get("channelTitle", ""),
        "channel_id":   snippet.get("channelId", ""),
        "view_count":   _int(stats.get("viewCount")),
        "like_count":   _int(stats.get("likeCount")),
        "duration":     content.get("duration", ""),   # ISO 8601 (PT4M13S)
        "upload_date":  snippet.get("publishedAt", "")[:10],
        "description":  (snippet.get("description") or "")[:300],
        "thumbnail":    thumb,
        "tags":            snippet.get("tags") or [],
        "category_id":     _int(snippet.get("categoryId")),   # 영상 자체의 카테고리
        "comment_count":   _int(stats.get("commentCount")),
        "region":          region,
        "fetched_at":      datetime.now(timezone.utc).isoformat(),
        "provider":        "yt_api",
    }


def _int(val: Any) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
