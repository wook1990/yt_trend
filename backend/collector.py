"""backend/collector.py — 데이터 수집 및 DB 저장

수집 방식 2가지:
  1. 카테고리 trending  : YouTube mostPopular API (생산성 카테고리만)
  2. 키워드 검색        : YouTube Search API (재테크/AI/창업 등 고CPM 주제)

settings.yaml 에서 두 방식의 설정을 모두 읽어 실행.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from sqlalchemy.orm import Session

from backend.analyzer import compute
from backend.models import TrendingSnapshot, CATEGORY_NAMES

API_BASE = "https://www.googleapis.com/youtube/v3"

_SETTINGS_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"


def _load_settings() -> dict:
    with open(_SETTINGS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── 메인 진입점 ─────────────────────────────────────────────────────────────

def run_collection(
    db: Session,
    region: str = "KR",
    category: int | None = None,
    limit: int = 50,
    target_date: date | None = None,
    include_keywords: bool = True,  # category=None일 때 키워드 수집 포함 여부
) -> int:
    """
    전체 수집 실행. 저장된 건수 반환.

    category=None  → settings.yaml의 collect_categories 전체 순회 + 키워드 수집
    category=0     → YouTube 전체 trending 50개
    category=N     → 특정 카테고리 N만
    include_keywords: category=None 일 때 키워드 수집도 함께 실행
    """
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        raise RuntimeError("YOUTUBE_API_KEY가 설정되지 않았습니다.")

    target_date = target_date or date.today()
    settings    = _load_settings()
    seen_ids: set[str] = set()
    total = 0

    fetch_cfg = settings.get("fetch", {})
    kw_limit_kr = fetch_cfg.get("limit_per_keyword", 50)
    kw_limit_os = fetch_cfg.get("limit_per_keyword_overseas", 15)

    if category is None:
        # 1. 카테고리 trending 수집 (KR 전용)
        if region == "KR":
            cat_ids = [c["id"] for c in fetch_cfg.get("collect_categories", [])]
            for cat_id in cat_ids:
                total += _collect_category(db, api_key, region, cat_id, limit, target_date, seen_ids)

        # 2. 키워드 검색 수집
        if include_keywords:
            if region == "KR":
                keywords  = fetch_cfg.get("search_keywords", [])
                kw_limit  = kw_limit_kr
            elif region == "US":
                keywords  = fetch_cfg.get("us_search_keywords", [])
                kw_limit  = kw_limit_os
            elif region == "JP":
                keywords  = fetch_cfg.get("jp_search_keywords", [])
                kw_limit  = kw_limit_os
            else:
                keywords  = fetch_cfg.get("search_keywords", [])
                kw_limit  = kw_limit_kr

            for kw in keywords:
                total += _collect_keyword(db, api_key, region, kw, kw_limit, target_date, seen_ids)
    else:
        total += _collect_category(db, api_key, region, category, limit, target_date, seen_ids)

    print(f"[collector] {target_date} {region} 총 {total}개 저장")
    return total


# ─── 카테고리 trending 수집 ───────────────────────────────────────────────────

def _collect_category(
    db: Session,
    api_key: str,
    region: str,
    category: int,
    limit: int,
    target_date: date,
    seen_ids: set[str],
) -> int:
    exists = db.query(TrendingSnapshot).filter(
        TrendingSnapshot.captured_date == target_date,
        TrendingSnapshot.region == region,
        TrendingSnapshot.category_id == category,
    ).first()
    if exists:
        print(f"[collector] {target_date} {region} cat={category} 이미 수집됨 — 스킵")
        return 0

    videos = _fetch_trending(api_key, region, category, limit)
    return _save_videos(db, api_key, videos, region, category, target_date, seen_ids)


# ─── 키워드 검색 수집 ─────────────────────────────────────────────────────────

def _collect_keyword(
    db: Session,
    api_key: str,
    region: str,
    keyword: str,
    limit: int,
    target_date: date,
    seen_ids: set[str],
) -> int:
    from src.fetcher.yt_search import search_by_keyword

    videos = search_by_keyword(keyword=keyword, region=region, limit=limit, api_key=api_key)
    if not videos:
        return 0

    saved = _save_videos(db, api_key, videos, region, 0, target_date, seen_ids)
    print(f"[collector] keyword='{keyword}' → {saved}개 저장")
    return saved


# ─── 공통 저장 로직 ───────────────────────────────────────────────────────────

def _save_videos(
    db: Session,
    api_key: str,
    videos: list[dict],
    region: str,
    fallback_category: int,
    target_date: date,
    seen_ids: set[str],
) -> int:
    """videos 목록을 받아 중복 제거 후 DB 저장."""
    new_videos = [v for v in videos if v["id"] not in seen_ids]
    if not new_videos:
        return 0

    # 비한국 지역: 제목 한국어 번역 (Gemini)
    title_ko_map: dict[str, str] = {}
    if region != "KR":
        from backend.services.translator import translate_titles
        titles = [v.get("title", "") for v in new_videos]
        title_ko_map = translate_titles(titles)

    # 구독자 수 일괄 조회
    channel_ids = list({v["channel_id"] for v in new_videos if v.get("channel_id")})
    subs_map = _fetch_subscribers(api_key, channel_ids)

    # 어제 조회수
    yesterday  = _yesterday(target_date)
    prev_views = _get_prev_views(db, [v["id"] for v in new_videos], yesterday, region)

    # 연속 trending 일수
    trending_days_map = _get_trending_days(db, [v["id"] for v in new_videos], target_date, region)

    saved = 0
    for rank, video in enumerate(new_videos, start=1):
        video["subscriber_count"] = subs_map.get(video.get("channel_id", ""))
        prev  = prev_views.get(video["id"])
        t_days = trending_days_map.get(video["id"], 1)
        metrics = compute(video, prev, t_days)

        vid_category_id   = video.get("category_id") or fallback_category
        vid_category_name = CATEGORY_NAMES.get(vid_category_id, "기타")

        # 키워드 검색 출처 표기 (tags 앞에 붙이기)
        search_kw = video.get("search_keyword")
        raw_tags  = video.get("tags", [])[:10]
        if search_kw:
            raw_tags = [f"검색:{search_kw}"] + raw_tags[:9]

        original_title = video.get("title", "")
        row = TrendingSnapshot(
            captured_date=target_date,
            rank=rank,
            region=region,
            category_id=vid_category_id,
            video_id=video["id"],
            title=original_title,
            title_ko=title_ko_map.get(original_title) or None,
            channel_id=video.get("channel_id", ""),
            channel_name=video.get("channel", ""),
            subscriber_count=video.get("subscriber_count"),
            view_count=video.get("view_count") or 0,
            like_count=video.get("like_count"),
            comment_count=video.get("comment_count"),
            duration=video.get("duration", ""),
            publish_date=_parse_dt(video.get("upload_date", "")),
            thumbnail=video.get("thumbnail", ""),
            category_name=vid_category_name,
            tags=json.dumps(raw_tags, ensure_ascii=False),
            **metrics,
        )
        db.add(row)
        seen_ids.add(video["id"])
        saved += 1

    db.commit()
    return saved


# ─── API 호출 헬퍼 ────────────────────────────────────────────────────────────

def _fetch_trending(api_key: str, region: str, category: int, limit: int) -> list[dict]:
    from src.fetcher.yt_api import fetch
    return fetch(region=region, category=category, limit=limit)


def _fetch_subscribers(api_key: str, channel_ids: list[str]) -> dict[str, int]:
    if not channel_ids:
        return {}
    result = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        resp = requests.get(
            f"{API_BASE}/channels",
            params={"part": "statistics", "id": ",".join(batch), "key": api_key},
            timeout=10,
        )
        if not resp.ok:
            continue
        for item in resp.json().get("items", []):
            subs = item.get("statistics", {}).get("subscriberCount")
            if subs:
                result[item["id"]] = int(subs)
    return result


def _get_prev_views(db: Session, video_ids: list[str], prev_date: date, region: str) -> dict[str, int]:
    rows = db.query(TrendingSnapshot.video_id, TrendingSnapshot.view_count).filter(
        TrendingSnapshot.video_id.in_(video_ids),
        TrendingSnapshot.captured_date == prev_date,
        TrendingSnapshot.region == region,
    ).all()
    return {r.video_id: r.view_count for r in rows}


def _get_trending_days(db: Session, video_ids: list[str], today: date, region: str) -> dict[str, int]:
    from sqlalchemy import func
    rows = db.query(
        TrendingSnapshot.video_id,
        func.count(TrendingSnapshot.id).label("cnt"),
    ).filter(
        TrendingSnapshot.video_id.in_(video_ids),
        TrendingSnapshot.region == region,
    ).group_by(TrendingSnapshot.video_id).all()
    return {r.video_id: r.cnt + 1 for r in rows}


def _yesterday(d: date) -> date:
    from datetime import timedelta
    return d - timedelta(days=1)


def _parse_dt(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None
