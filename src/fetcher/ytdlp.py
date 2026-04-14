"""src/fetcher/innertube.py (파일명: ytdlp.py) — YouTube Innertube API 기반 trending 수집

YouTube 내부 API를 직접 호출. API 키 불필요, 할당량 없음.
비공식 API이므로 YouTube 업데이트 시 파싱 구조가 변경될 수 있음.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from typing import Any

import requests

YOUTUBE_URL = "https://www.youtube.com"
BROWSE_URL  = f"{YOUTUBE_URL}/youtubei/v1/browse"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 카테고리별 탭 params (YouTube 내부 protobuf 인코딩)
CATEGORY_PARAMS: dict[int, str] = {
    0:  "",
    10: "4gINGgt5dG1hX2NoYXJ0cw==",                         # 음악
    20: "4gIcGhpnYW1pbmdfY29ycHVzX21vc3RfcG9wdWxhcg==",    # 게임
    25: "4gIJGgdyZWxhdGVk",                                  # 뉴스
}


def fetch(region: str = "KR", category: int = 0, limit: int = 50) -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    # 1) 홈페이지 방문으로 innertube key + visitor data 획득
    try:
        home = session.get(YOUTUBE_URL, timeout=10)
        home.raise_for_status()
    except requests.RequestException as e:
        print(f"[innertube] 홈페이지 요청 실패: {e}", file=sys.stderr)
        return []

    api_key  = _extract(home.text, r'"INNERTUBE_API_KEY":"([^"]+)"')
    visitor  = _extract(home.text, r'"visitorData":"([^"]+)"')
    client_v = _extract(home.text, r'"INNERTUBE_CLIENT_VERSION":"([^"]+)"') or "2.20250101"

    if not api_key:
        print("[innertube] API 키 추출 실패.", file=sys.stderr)
        return []

    # 2) trending 브라우즈 요청
    body: dict[str, Any] = {
        "browseId": "FEtrending",
        "context": {
            "client": {
                "clientName":    "WEB",
                "clientVersion": client_v,
                "hl":            "ko" if region == "KR" else "en",
                "gl":            region,
                "visitorData":   visitor,
            }
        },
    }
    cat_param = CATEGORY_PARAMS.get(category, "")
    if cat_param:
        body["params"] = cat_param

    try:
        resp = session.post(
            f"{BROWSE_URL}?key={api_key}&prettyPrint=false",
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[innertube] browse 요청 실패: {e}", file=sys.stderr)
        return []

    return _parse(resp.json(), region, limit)


def _extract(text: str, pattern: str) -> str:
    m = re.search(pattern, text)
    return m.group(1) if m else ""


def _parse(data: dict, region: str, limit: int) -> list[dict]:
    videos: list[dict] = []

    try:
        tabs = (
            data
            .get("contents", {})
            .get("twoColumnBrowseResultsRenderer", {})
            .get("tabs", [])
        )
        for tab in tabs:
            sections = (
                tab
                .get("tabRenderer", {})
                .get("content", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            for section in sections:
                for item in section.get("itemSectionRenderer", {}).get("contents", []):
                    # 직접 videoRenderer
                    if "videoRenderer" in item:
                        v = _norm(item["videoRenderer"], region)
                        if v:
                            videos.append(v)
                    # shelfRenderer 안의 영상들
                    shelf_items = (
                        item
                        .get("shelfRenderer", {})
                        .get("content", {})
                        .get("expandedShelfContentsRenderer", {})
                        .get("items", [])
                    )
                    for si in shelf_items:
                        if "videoRenderer" in si:
                            v = _norm(si["videoRenderer"], region)
                            if v:
                                videos.append(v)
                    if len(videos) >= limit:
                        return videos[:limit]
    except (KeyError, TypeError):
        pass

    return videos[:limit]


def _norm(r: dict, region: str) -> dict | None:
    vid_id = r.get("videoId", "")
    if not vid_id:
        return None
    return {
        "id":          vid_id,
        "url":         f"https://www.youtube.com/watch?v={vid_id}",
        "title":       _text(r.get("title", {})),
        "channel":     _text(r.get("longBylineText") or r.get("shortBylineText") or {}),
        "channel_id":  _browse_id(r.get("longBylineText") or r.get("shortBylineText") or {}),
        "view_count":  _views(_text(r.get("viewCountText", {}))),
        "like_count":  None,
        "duration":    _text(r.get("lengthText", {})),
        "upload_date": _text(r.get("publishedTimeText", {})),
        "description": _text(r.get("descriptionSnippet", {}))[:300],
        "thumbnail":   _thumb(r.get("thumbnail", {})),
        "tags":        [],
        "region":      region,
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "provider":    "innertube",
    }


def _text(obj: dict) -> str:
    if not obj:
        return ""
    if "simpleText" in obj:
        return obj["simpleText"]
    return "".join(r.get("text", "") for r in obj.get("runs", []))


def _browse_id(obj: dict) -> str:
    for run in obj.get("runs", []):
        bid = run.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("browseId", "")
        if bid:
            return bid
    return ""


def _thumb(obj: dict) -> str:
    thumbs = obj.get("thumbnails", [])
    return thumbs[-1]["url"] if thumbs else ""


def _views(s: str) -> int | None:
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else None
