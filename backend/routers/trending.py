"""backend/routers/trending.py — 트렌딩 데이터 API"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import TrendingSnapshot
from backend.collector import run_collection

router = APIRouter(prefix="/api", tags=["trending"])


# exclude_music=True 시 제외할 카테고리 (음악/게임/엔터/스포츠/브이로그/영화/코미디/자동차)
ENTERTAINMENT_CATEGORY_IDS = [10, 20, 24, 17, 1, 22, 2, 23]

# 하위 호환용 alias
MUSIC_CATEGORY_IDS = ENTERTAINMENT_CATEGORY_IDS

# 제목 키워드 추출용 한국어 불용어
_STOPWORDS = {
    "이", "그", "저", "것", "수", "등", "및", "또", "더", "가", "을", "를", "은", "는",
    "의", "에", "에서", "와", "과", "도", "만", "로", "으로", "한", "하는", "하고",
    "해서", "됩니다", "입니다", "합니다", "했다", "있다", "없다", "통해", "위해",
    "대해", "때문에", "부터", "까지", "이후", "이전", "현재", "최근", "새로운",
    "처음", "마지막", "모든", "그리고", "하지만", "따라서", "결국", "드디어",
    "또한", "아니라", "중", "후", "전", "때", "이번", "다음", "지금", "어떻게",
    "왜", "무엇", "어디", "누가", "the", "a", "an", "is", "in", "of", "to",
    "and", "for", "with", "on", "at", "by",
}


@router.get("/trending")
def get_trending(
    region:        str  = Query("KR"),
    category:      int  = Query(0),
    date_str:      str  = Query(None, alias="date"),
    period:        str  = Query("day", description="day | week | month"),
    exclude_music: bool = Query(True),
    video_type:    str  = Query("all", description="all | short | long"),
    db:            Session = Depends(get_db),
) -> dict:
    """trending 목록. period=day: 단일 날짜 / week·month: 기간 집계."""
    end = _parse_date(date_str) or date.today()
    delta = {"day": 1, "week": 7, "month": 30}.get(period, 1)
    start = end - timedelta(days=delta - 1)

    q = db.query(TrendingSnapshot).filter(
        TrendingSnapshot.captured_date >= start,
        TrendingSnapshot.captured_date <= end,
        TrendingSnapshot.region == region,
    )

    if category != 0:
        q = q.filter(TrendingSnapshot.category_id == category)

    if exclude_music:
        q = q.filter(TrendingSnapshot.category_id.notin_(MUSIC_CATEGORY_IDS))

    rows = q.order_by(TrendingSnapshot.spike_score.desc()).all()

    # 기간 집계: video_id별 최고 spike_score 스냅샷 선택 + 등장 횟수 추가
    seen: dict[str, Any] = {}
    appear_count: dict[str, int] = {}
    for r in rows:
        vid = r.video_id
        appear_count[vid] = appear_count.get(vid, 0) + 1
        if vid not in seen or (r.spike_score or 0) > (seen[vid].spike_score or 0):
            seen[vid] = r

    # 정렬 기준: 주/월은 (등장일수 × 스파이크) 복합, 일간은 spike_score 단독
    if period == "day":
        unique = sorted(seen.values(), key=lambda x: (x.spike_score or 0), reverse=True)
    else:
        unique = sorted(
            seen.values(),
            key=lambda x: appear_count[x.video_id] * (x.spike_score or 1),
            reverse=True,
        )

    all_videos = []
    for i, r in enumerate(unique, start=1):
        d = _to_dict(r)
        d["rank"] = i
        d["trending_days"] = appear_count[r.video_id]
        all_videos.append(d)

    # short/long 필터 후 순위 재부여
    videos = _filter_by_type(all_videos, video_type)
    for i, v in enumerate(videos, start=1):
        v["rank"] = i

    # 소규모 채널 돌파 수 (구독자 10만 이하 + 조회수 20만 이상)
    small_ch_breakout = sum(
        1 for v in videos
        if (v["subscriber_count"] or 0) < 100_000
        and (v["view_count"] or 0) >= 200_000
    )

    return {
        "date":                str(end),
        "start":               str(start),
        "period":              period,
        "region":              region,
        "count":               len(videos),
        "short_count":         sum(1 for v in all_videos if v["is_short"]),
        "long_count":          sum(1 for v in all_videos if not v["is_short"]),
        "small_ch_breakout":   small_ch_breakout,
        "videos":              videos,
    }


@router.get("/trending/compare")
def compare_trending(
    region:        str  = Query("KR"),
    category:      int  = Query(0),
    period:        str  = Query("week", description="day | week | month"),
    date_str:      str  = Query(None, alias="date"),
    exclude_music: bool = Query(True),
    db:            Session = Depends(get_db),
) -> dict:
    """기간별 trending 비교 (일간/주간/월간)."""
    end   = _parse_date(date_str) or date.today()
    delta = {"day": 1, "week": 7, "month": 30}.get(period, 7)
    start = end - timedelta(days=delta - 1)

    q = db.query(TrendingSnapshot).filter(
        TrendingSnapshot.captured_date >= start,
        TrendingSnapshot.captured_date <= end,
        TrendingSnapshot.region == region,
    )
    if category != 0:
        q = q.filter(TrendingSnapshot.category_id == category)
    if exclude_music:
        q = q.filter(TrendingSnapshot.category_id.notin_(MUSIC_CATEGORY_IDS))

    rows = q.order_by(TrendingSnapshot.captured_date, TrendingSnapshot.rank).all()

    by_date: dict[str, list] = {}
    for r in rows:
        key = str(r.captured_date)
        by_date.setdefault(key, []).append(_to_dict(r))

    freq: dict[str, dict] = {}
    for r in rows:
        vid = r.video_id
        if vid not in freq:
            freq[vid] = {"title": r.title, "channel": r.channel_name, "days": 0,
                         "max_rank": r.rank, "min_rank": r.rank,
                         "max_views": r.view_count, "thumbnail": r.thumbnail or ""}
        freq[vid]["days"] += 1
        freq[vid]["max_rank"] = min(freq[vid]["max_rank"], r.rank)
        freq[vid]["max_views"] = max(freq[vid]["max_views"], r.view_count)

    top_videos = sorted(freq.values(), key=lambda x: x["days"], reverse=True)[:20]

    return {
        "period":     period,
        "start":      str(start),
        "end":        str(end),
        "by_date":    by_date,
        "top_videos": top_videos,
    }


@router.get("/trending/categories")
def category_breakdown(
    region:        str  = Query("KR"),
    period:        str  = Query("week"),
    date_str:      str  = Query(None, alias="date"),
    exclude_music: bool = Query(True),
    db:            Session = Depends(get_db),
) -> dict:
    """카테고리별 분포."""
    end   = _parse_date(date_str) or date.today()
    delta = {"day": 1, "week": 7, "month": 30}.get(period, 7)
    start = end - timedelta(days=delta - 1)

    q = db.query(
        TrendingSnapshot.category_id,
        TrendingSnapshot.category_name,
        func.count(TrendingSnapshot.id).label("count"),
        func.avg(TrendingSnapshot.view_count).label("avg_views"),
        func.avg(TrendingSnapshot.spike_score).label("avg_spike"),
        func.avg(TrendingSnapshot.engagement_rate).label("avg_engagement"),
    ).filter(
        TrendingSnapshot.captured_date >= start,
        TrendingSnapshot.captured_date <= end,
        TrendingSnapshot.region == region,
    )
    if exclude_music:
        q = q.filter(TrendingSnapshot.category_id.notin_(MUSIC_CATEGORY_IDS))

    rows = (
        q.group_by(TrendingSnapshot.category_id, TrendingSnapshot.category_name)
        .order_by(func.count(TrendingSnapshot.id).desc())
        .all()
    )

    return {
        "period": period,
        "categories": [
            {
                "id":             r.category_id,
                "name":           r.category_name or "기타",
                "count":          r.count,
                "avg_views":      int(r.avg_views or 0),
                "avg_spike":      round(float(r.avg_spike or 0), 1),
                "avg_engagement": round(float(r.avg_engagement or 0), 2),
            }
            for r in rows
        ],
    }


@router.get("/trending/spikes")
def top_spikes(
    region:        str  = Query("KR"),
    date_str:      str  = Query(None, alias="date"),
    period:        str  = Query("day", description="day | week | month"),
    limit:         int  = Query(20),
    exclude_music: bool = Query(True),
    video_type:    str  = Query("all", description="all | short | long"),
    db:            Session = Depends(get_db),
) -> dict:
    """spike_score 상위 영상 (기간 집계 지원)."""
    end = _parse_date(date_str) or date.today()
    delta = {"day": 1, "week": 7, "month": 30}.get(period, 1)
    start = end - timedelta(days=delta - 1)

    q = db.query(TrendingSnapshot).filter(
        TrendingSnapshot.captured_date >= start,
        TrendingSnapshot.captured_date <= end,
        TrendingSnapshot.region == region,
        TrendingSnapshot.spike_score.isnot(None),
    )
    if exclude_music:
        q = q.filter(TrendingSnapshot.category_id.notin_(MUSIC_CATEGORY_IDS))

    rows = q.order_by(TrendingSnapshot.spike_score.desc()).all()

    # 중복 제거 — 기간 중 최고 spike_score 스냅샷 선택
    seen: dict[str, Any] = {}
    for r in rows:
        if r.video_id not in seen or (r.spike_score or 0) > (seen[r.video_id].spike_score or 0):
            seen[r.video_id] = r
    unique = sorted(seen.values(), key=lambda x: x.spike_score or 0, reverse=True)[:limit]

    spikes = _filter_by_type([_to_dict(r) for r in unique], video_type)
    return {"date": str(end), "period": period, "spikes": spikes}


@router.get("/trending/keywords")
def trending_keywords(
    region:        str  = Query("KR"),
    period:        str  = Query("week"),
    date_str:      str  = Query(None, alias="date"),
    category:      int  = Query(0),
    limit:         int  = Query(40),
    exclude_music: bool = Query(True),
    db:            Session = Depends(get_db),
) -> dict:
    """트렌딩 제목에서 키워드 빈도 추출."""
    end   = _parse_date(date_str) or date.today()
    delta = {"day": 1, "week": 7, "month": 30}.get(period, 7)
    start = end - timedelta(days=delta - 1)

    q = db.query(
        TrendingSnapshot.title,
        TrendingSnapshot.category_name,
        TrendingSnapshot.spike_score,
    ).filter(
        TrendingSnapshot.captured_date >= start,
        TrendingSnapshot.captured_date <= end,
        TrendingSnapshot.region == region,
    )
    if category != 0:
        q = q.filter(TrendingSnapshot.category_id == category)
    if exclude_music:
        q = q.filter(TrendingSnapshot.category_id.notin_(MUSIC_CATEGORY_IDS))

    rows = q.all()

    counter: Counter = Counter()
    spike_weight: dict[str, float] = {}

    for row in rows:
        words = re.split(r'[\s|\-\[\]\(\)\{\}「」【】《》〈〉,\.!?~…·/:;""\'%#@&\+]+', row.title)
        weight = 1 + (float(row.spike_score or 0) / 100)  # 스파이크 높은 영상 키워드 가중치
        for w in words:
            w = w.strip()
            if len(w) < 2 or w in _STOPWORDS or w.isdigit():
                continue
            counter[w] += 1
            spike_weight[w] = spike_weight.get(w, 0) + weight

    # 빈도 + 스파이크 가중 점수 합산
    scored = [
        {
            "keyword":     kw,
            "count":       cnt,
            "spike_weight": round(spike_weight.get(kw, 0), 1),
            "score":       round(cnt * 0.5 + spike_weight.get(kw, 0) * 0.5, 1),
        }
        for kw, cnt in counter.most_common(limit * 2)
        if cnt >= 2  # 1회만 등장은 제외
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)

    return {
        "period":   period,
        "start":    str(start),
        "end":      str(end),
        "total_videos": len(rows),
        "keywords": scored[:limit],
    }


@router.get("/trending/copyable")
def copyable_videos(
    region:          str  = Query("KR"),
    date_str:        str  = Query(None, alias="date"),
    max_subscribers: int  = Query(100000,  description="최대 구독자 수 (소규모 채널 기준)"),
    min_views:       int  = Query(200000,  description="최소 조회수"),
    limit:           int  = Query(30),
    exclude_music:   bool = Query(True),
    db:              Session = Depends(get_db),
) -> dict:
    """소규모 채널인데 조회수가 높은 영상 — 모방 가치 높음."""
    end   = _parse_date(date_str) or date.today()
    start = end - timedelta(days=6)  # 최근 7일

    q = db.query(TrendingSnapshot).filter(
        TrendingSnapshot.captured_date >= start,
        TrendingSnapshot.captured_date <= end,
        TrendingSnapshot.region == region,
        TrendingSnapshot.subscriber_count.isnot(None),
        TrendingSnapshot.subscriber_count > 0,
        TrendingSnapshot.subscriber_count <= max_subscribers,
        TrendingSnapshot.view_count >= min_views,
    )
    if exclude_music:
        q = q.filter(TrendingSnapshot.category_id.notin_(MUSIC_CATEGORY_IDS))

    rows = q.order_by(TrendingSnapshot.viral_coefficient.desc()).limit(limit).all()

    # 중복 video_id 제거 (여러 날 등장 시 최고 viral_coefficient만)
    seen: set[str] = set()
    unique = []
    for r in rows:
        if r.video_id not in seen:
            seen.add(r.video_id)
            unique.append(r)

    return {
        "date":            str(end),
        "max_subscribers": max_subscribers,
        "min_views":       min_views,
        "count":           len(unique),
        "videos":          [_to_dict(r) for r in unique],
    }


@router.get("/trending/early-signals")
def early_signals(
    base_region:    str  = Query("KR"),
    source_regions: str  = Query("US,JP", description="선행 트렌드 감지 지역 (콤마 구분)"),
    date_str:       str  = Query(None, alias="date"),
    period:         str  = Query("week"),
    exclude_music:  bool = Query(True),
    db:             Session = Depends(get_db),
) -> dict:
    """해외(US/JP)에서 급상승 중이지만 KR에는 아직 없는 영상."""
    end   = _parse_date(date_str) or date.today()
    delta = {"day": 1, "week": 7, "month": 30}.get(period, 7)
    start = end - timedelta(days=delta - 1)

    sources = [r.strip() for r in source_regions.split(",") if r.strip()]

    # KR 기준 지역에 있는 video_id 집합
    kr_q = db.query(TrendingSnapshot.video_id).filter(
        TrendingSnapshot.captured_date >= start,
        TrendingSnapshot.captured_date <= end,
        TrendingSnapshot.region == base_region,
    )
    if exclude_music:
        kr_q = kr_q.filter(TrendingSnapshot.category_id.notin_(MUSIC_CATEGORY_IDS))
    kr_ids = {r.video_id for r in kr_q.all()}

    result: dict[str, list] = {}
    available_regions: list[str] = []

    for src in sources:
        # 해당 지역 데이터 존재 여부 확인
        has_data = db.query(TrendingSnapshot.id).filter(
            TrendingSnapshot.region == src,
            TrendingSnapshot.captured_date >= start,
        ).first()

        if not has_data:
            result[src] = []
            continue

        available_regions.append(src)

        q = db.query(TrendingSnapshot).filter(
            TrendingSnapshot.captured_date >= start,
            TrendingSnapshot.captured_date <= end,
            TrendingSnapshot.region == src,
        )
        if exclude_music:
            q = q.filter(TrendingSnapshot.category_id.notin_(MUSIC_CATEGORY_IDS))
        if kr_ids:
            q = q.filter(TrendingSnapshot.video_id.notin_(kr_ids))

        rows = q.order_by(TrendingSnapshot.spike_score.desc()).limit(30).all()

        # 중복 video_id 제거
        seen: set[str] = set()
        unique = []
        for r in rows:
            if r.video_id not in seen:
                seen.add(r.video_id)
                unique.append(r)

        result[src] = [_to_dict(r) for r in unique[:20]]

    return {
        "base_region":       base_region,
        "period":            period,
        "start":             str(start),
        "end":               str(end),
        "available_regions": available_regions,
        "signals":           result,
    }


@router.post("/collect/overseas")
def collect_overseas(
    regions: str = Query("US,JP", description="수집할 해외 지역 (콤마 구분)"),
    db:      Session = Depends(get_db),
) -> dict:
    """선행 감지용 해외 키워드 수집 (US/JP 전용 키워드 + 한국어 번역)."""
    target_regions = [r.strip() for r in regions.split(",") if r.strip()]
    total = 0
    results = {}
    for reg in target_regions:
        try:
            # category=None → 해당 지역 전용 키워드 사용
            saved = run_collection(db, region=reg, category=None, include_keywords=True)
            results[reg] = saved
            total += saved
        except Exception as e:
            results[reg] = f"오류: {e}"
    return {"status": "ok", "total": total, "by_region": results}


@router.get("/analyze/{video_id}")
async def analyze_video(
    video_id: str,
    db:       Session = Depends(get_db),
) -> dict:
    """영상 AI 분석 — 왜 급상승했는지 + 모방 가이드."""
    # DB에서 최신 스냅샷 조회
    row = (
        db.query(TrendingSnapshot)
        .filter(TrendingSnapshot.video_id == video_id)
        .order_by(TrendingSnapshot.captured_date.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="영상을 찾을 수 없습니다.")

    from backend.services.video_analyzer import analyze_video as _analyze
    video_data = _to_dict(row)
    result = _analyze(video_data)
    return {"video_id": video_id, "title": row.title, **result}


@router.post("/collect")
def collect_now(
    region:   str        = Query("KR"),
    category: int | None = Query(None, description="None=settings.yaml 전체, 0=YouTube전체, N=특정카테고리"),
    limit:    int        = Query(50),
    db:       Session    = Depends(get_db),
) -> dict:
    """수동 데이터 수집 트리거. category 미지정 시 settings.yaml의 카테고리 전체 순회."""
    try:
        saved = run_collection(db, region=region, category=category, limit=limit)
        return {"status": "ok", "saved": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/available-dates")
def available_dates(
    region: str = Query("KR"),
    db:     Session = Depends(get_db),
) -> dict:
    """수집된 날짜 목록."""
    rows = (
        db.query(TrendingSnapshot.captured_date)
        .filter(TrendingSnapshot.region == region)
        .distinct()
        .order_by(TrendingSnapshot.captured_date.desc())
        .all()
    )
    return {"dates": [str(r.captured_date) for r in rows]}


# ─── 헬퍼 ────────────────────────────────────────────────────────────

def _parse_duration_seconds(duration: str | None) -> int:
    """ISO 8601 duration → 초 변환. 예: PT1M30S → 90"""
    if not duration:
        return 0
    import re as _re
    m = _re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s


def _is_short(duration: str | None) -> bool:
    """YouTube Shorts 판별 — 60초 이하."""
    secs = _parse_duration_seconds(duration)
    return 0 < secs <= 60


def _filter_by_type(videos: list[dict], video_type: str) -> list[dict]:
    """video_type: 'all' | 'short' | 'long'"""
    if video_type == "short":
        return [v for v in videos if v.get("is_short")]
    if video_type == "long":
        return [v for v in videos if not v.get("is_short")]
    return videos


def _to_dict(r: TrendingSnapshot) -> dict[str, Any]:
    reasons = []
    if r.spike_reasons:
        try:
            reasons = json.loads(r.spike_reasons)
        except Exception:
            pass
    short = _is_short(r.duration)
    return {
        "rank":             r.rank,
        "video_id":         r.video_id,
        "url":              f"https://www.youtube.com/shorts/{r.video_id}" if short else f"https://www.youtube.com/watch?v={r.video_id}",
        "title":            r.title,
        "channel":          r.channel_name,
        "channel_id":       r.channel_id,
        "thumbnail":        r.thumbnail or "",
        "title_ko":         r.title_ko or None,
        "subscriber_count": r.subscriber_count,
        "view_count":       r.view_count,
        "like_count":       r.like_count,
        "comment_count":    r.comment_count,
        "duration":         r.duration,
        "duration_seconds": _parse_duration_seconds(r.duration),
        "is_short":         short,
        "publish_date":     r.publish_date.isoformat() if r.publish_date else None,
        "category":         r.category_name,
        # 스파이크 지표
        "view_gain_1d":     r.view_gain_1d,
        "view_velocity":    r.view_velocity,
        "engagement_rate":  r.engagement_rate,
        "viral_coefficient":r.viral_coefficient,
        "trending_days":    r.trending_days,
        "spike_score":      r.spike_score,
        "spike_reasons":    reasons,
        # 신뢰도 지표
        "trust_score":      r.trust_score,
        "trust_flags":      json.loads(r.trust_flags) if r.trust_flags else [],
    }


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _get_videos_for_date(
    db: Session,
    target_date: date,
    region: str,
    exclude_entertainment: bool = False,
) -> list[dict[str, Any]]:
    """날짜+지역의 중복 제거된 영상 목록 반환 (brief 생성용)."""
    q = db.query(TrendingSnapshot).filter(
        TrendingSnapshot.captured_date == target_date,
        TrendingSnapshot.region == region,
    )
    if exclude_entertainment:
        q = q.filter(TrendingSnapshot.category_id.notin_(ENTERTAINMENT_CATEGORY_IDS))

    rows = q.order_by(TrendingSnapshot.spike_score.desc()).all()

    seen: dict[str, Any] = {}
    for r in rows:
        if r.video_id not in seen:
            seen[r.video_id] = _to_dict(r)

    return list(seen.values())


# ─── 카테고리별 큐레이션 (신뢰도 필터 적용, 20개/카테고리) ────────────────────

@router.get("/trending/curated")
def get_curated(
    region:        str = Query("KR"),
    date_str:      str = Query(None, alias="date"),
    period:        int = Query(3, ge=1, le=14, description="수집 기간(일)"),
    per_category:  int = Query(20, ge=5, le=50),
    min_trust:     int = Query(60, ge=0, le=100, description="최소 신뢰도 점수"),
    db:            Session = Depends(get_db),
) -> dict[str, Any]:
    """
    카테고리별 신뢰도 필터 후 상위 N개 영상 반환.
    - 뷰봇/사기 영상(trust_score < min_trust) 제거
    - spike_score 기준 상위 per_category개 선택
    """
    end   = _parse_date(date_str) or date.today()
    start = end - timedelta(days=period - 1)

    rows = (
        db.query(TrendingSnapshot)
        .filter(
            TrendingSnapshot.captured_date >= start,
            TrendingSnapshot.captured_date <= end,
            TrendingSnapshot.region == region,
            TrendingSnapshot.category_id.notin_(ENTERTAINMENT_CATEGORY_IDS),
        )
        .all()
    )

    # 영상 중복 제거 (video_id 기준 최고 spike_score 스냅샷 유지)
    best: dict[str, TrendingSnapshot] = {}
    for r in rows:
        vid = r.video_id
        if vid not in best or (r.spike_score or 0) > (best[vid].spike_score or 0):
            best[vid] = r

    # 신뢰도 필터
    trusted = [r for r in best.values() if (r.trust_score is None or r.trust_score >= min_trust)]
    filtered_out = len(best) - len(trusted)

    # 카테고리별 그룹핑 → 각 그룹 spike_score 내림차순 → 상위 per_category개
    from collections import defaultdict
    from backend.models import CATEGORY_NAMES

    cat_groups: dict[int, list[TrendingSnapshot]] = defaultdict(list)
    for r in trusted:
        cat_groups[r.category_id].append(r)

    categories_out = []
    for cat_id, cat_rows in cat_groups.items():
        sorted_rows = sorted(cat_rows, key=lambda r: r.spike_score or 0, reverse=True)
        top = sorted_rows[:per_category]
        categories_out.append({
            "category_id":   cat_id,
            "category_name": CATEGORY_NAMES.get(cat_id, str(cat_id)),
            "total_found":   len(cat_rows),
            "showing":       len(top),
            "videos":        [_to_dict(r) for r in top],
        })

    # 카테고리를 영상 수 내림차순 정렬
    categories_out.sort(key=lambda c: c["total_found"], reverse=True)

    return {
        "date":              end.isoformat(),
        "region":            region,
        "period_days":       period,
        "min_trust_score":   min_trust,
        "total_before_filter": len(best),
        "filtered_out":      filtered_out,
        "total_after_filter": len(trusted),
        "categories":        categories_out,
    }


# ─── 부업 적합도 분석 ─────────────────────────────────────────────────────────

# 카테고리별 추정 CPM (USD 기준, 한국 크리에이터 경험치 기반)
_CPM_TABLE: dict[int, float] = {
    28: 8.0,   # IT/테크
    27: 6.0,   # 교육
    25: 5.5,   # 뉴스/시사
    26: 5.0,   # 노하우/스킬
    15: 4.5,   # 반려동물
    0:  3.0,   # 기타
}

_CPM_TIER = {
    28: "high", 27: "high", 25: "mid", 26: "mid", 15: "mid", 0: "low",
}

_COLLECT_CATEGORY_IDS = [25, 27, 28, 26, 15]


@router.get("/trending/opportunity")
def get_opportunity(
    region:   str     = Query("KR"),
    date_str: str     = Query(None, alias="date"),
    days:     int     = Query(7, ge=1, le=30),
    db:       Session = Depends(get_db),
) -> dict[str, Any]:
    """
    카테고리별 부업 적합도 점수 분석.
    수집된 trending 데이터를 기반으로 CPM·성장성·진입난이도·참여율 복합 점수 산출.
    """
    end = _parse_date(date_str) or date.today()
    start = end - timedelta(days=days - 1)

    rows = (
        db.query(TrendingSnapshot)
        .filter(
            TrendingSnapshot.captured_date >= start,
            TrendingSnapshot.captured_date <= end,
            TrendingSnapshot.region == region,
            TrendingSnapshot.category_id.in_(_COLLECT_CATEGORY_IDS),
        )
        .all()
    )

    if not rows:
        return {"date": end.isoformat(), "region": region, "opportunities": []}

    # 카테고리별 집계
    from collections import defaultdict
    cat_groups: dict[int, list[TrendingSnapshot]] = defaultdict(list)
    seen_per_cat: dict[int, set[str]] = defaultdict(set)
    for r in rows:
        vid = r.video_id
        cid = r.category_id
        if vid not in seen_per_cat[cid]:
            seen_per_cat[cid].add(vid)
            cat_groups[cid].append(r)

    opportunities = []
    for cat_id, cat_rows in cat_groups.items():
        if not cat_rows:
            continue

        avg_views = sum(r.view_count or 0 for r in cat_rows) / len(cat_rows)
        avg_velocity = sum(r.view_velocity or 0 for r in cat_rows) / len(cat_rows)
        avg_spike = sum(r.spike_score or 0 for r in cat_rows) / len(cat_rows)
        avg_engagement = sum(r.engagement_rate or 0 for r in cat_rows) / len(cat_rows)

        # 소형 채널 비율 (구독자 10만 미만)
        has_sub = [r for r in cat_rows if r.subscriber_count is not None]
        small_ratio = (
            sum(1 for r in has_sub if (r.subscriber_count or 0) < 100_000) / len(has_sub)
            if has_sub else 0.5
        )

        # 점수 계산 (100점 만점)
        cpm = _CPM_TABLE.get(cat_id, _CPM_TABLE[0])
        cpm_score = min(cpm / 8.0 * 30, 30)                          # CPM 30점
        growth_score = min((avg_velocity / 5000 + avg_spike / 100) * 15, 30)  # 성장성 30점
        entry_score = small_ratio * 20                                # 진입 난이도 20점 (소형채널 많을수록 진입 쉬움)
        engagement_score = min(avg_engagement * 500, 20)              # 참여율 20점

        total_score = round(cpm_score + growth_score + entry_score + engagement_score)

        # 진입 난이도 레이블
        if small_ratio >= 0.6:
            entry_difficulty = "쉬움"
        elif small_ratio >= 0.3:
            entry_difficulty = "보통"
        else:
            entry_difficulty = "어려움"

        # 상위 영상 3개
        top_videos = sorted(cat_rows, key=lambda r: r.spike_score or 0, reverse=True)[:3]

        from backend.models import CATEGORY_NAMES
        opportunities.append({
            "category_id":       cat_id,
            "category_name":     CATEGORY_NAMES.get(cat_id, str(cat_id)),
            "opportunity_score": min(total_score, 100),
            "cpm_tier":          _CPM_TIER.get(cat_id, "low"),
            "estimated_cpm":     cpm,
            "avg_views":         round(avg_views),
            "entry_difficulty":  entry_difficulty,
            "small_channel_ratio": round(small_ratio * 100),
            "video_count":       len(cat_rows),
            "top_videos": [
                {
                    "video_id":    r.video_id,
                    "title":       r.title,
                    "channel":     r.channel_name,
                    "view_count":  r.view_count,
                    "spike_score": round(r.spike_score or 0, 1),
                    "thumbnail":   r.thumbnail,
                }
                for r in top_videos
            ],
        })

    # 점수 내림차순 정렬
    opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)

    return {
        "date":          end.isoformat(),
        "region":        region,
        "period_days":   days,
        "opportunities": opportunities,
    }
