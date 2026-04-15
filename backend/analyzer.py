"""backend/analyzer.py — 스파이크 지표 계산 및 급등 원인 분석"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any


# ─── 급등 판단 임계값 ───────────────────────────────────────────────
THRESHOLDS = {
    "fresh_hours":          48,      # 업로드 후 N시간 이내 = 신규 급등
    "resurgence_days":      30,      # N일 이상 된 영상이 trending = 재급등
    "small_channel_views":  5.0,     # 구독자 대비 조회수 5배 이상 = 소채널 돌파
    "high_engagement":      0.05,    # 조회수 대비 좋아요 5% 이상 = 고반응
    "viral_view_gain_1d":   500_000, # 하루 조회수 증가 50만 이상 = 급격한 바이럴
    "sustained_trending":   3,       # N일 연속 trending = 지속 인기
}


def compute(
    video: dict[str, Any],
    prev_view_count: int | None,
    trending_days: int,
) -> dict[str, Any]:
    """
    단일 영상의 스파이크 지표 계산.

    Args:
        video:           yt_api.fetch()가 반환한 영상 딕셔너리
        prev_view_count: 어제 저장된 조회수 (없으면 None)
        trending_days:   연속 trending 일수

    Returns:
        지표 딕셔너리 (model 필드에 직접 저장 가능)
    """
    view_count       = video.get("view_count") or 0
    like_count       = video.get("like_count") or 0
    subscriber_count = video.get("subscriber_count") or 0
    publish_date     = _parse_publish(video.get("publish_date", ""))

    # 1. 하루 조회수 증가
    view_gain_1d = (view_count - prev_view_count) if prev_view_count is not None else None

    # 2. 업로드 후 경과 시간 (시간 단위)
    hours_since_upload = _hours_since(publish_date) if publish_date else None

    # 3. 조회수 속도 (시간당 조회수)
    view_velocity = (view_count / hours_since_upload) if hours_since_upload and hours_since_upload > 0 else None

    # 4. 참여율 (좋아요 / 조회수)
    engagement_rate = (like_count / view_count) if view_count > 0 else None

    # 5. 바이럴 계수 (조회수 / 구독자)
    viral_coefficient = (view_count / subscriber_count) if subscriber_count > 0 else None

    # 6. 급등 원인 분류
    reasons = _detect_reasons(
        hours_since_upload=hours_since_upload,
        view_gain_1d=view_gain_1d,
        view_velocity=view_velocity,
        engagement_rate=engagement_rate,
        viral_coefficient=viral_coefficient,
        trending_days=trending_days,
    )

    # 7. 종합 스파이크 점수 (0~100)
    spike_score = _score(
        view_gain_1d=view_gain_1d,
        view_velocity=view_velocity,
        engagement_rate=engagement_rate,
        viral_coefficient=viral_coefficient,
        trending_days=trending_days,
        reasons=reasons,
    )

    return {
        "view_gain_1d":      view_gain_1d,
        "view_velocity":     round(view_velocity, 2) if view_velocity else None,
        "engagement_rate":   round(engagement_rate * 100, 2) if engagement_rate else None,
        "viral_coefficient": round(viral_coefficient, 2) if viral_coefficient else None,
        "trending_days":     trending_days,
        "spike_score":       round(spike_score, 1),
        "spike_reasons":     json.dumps(reasons, ensure_ascii=False),
    }


def _detect_reasons(
    *,
    hours_since_upload: float | None,
    view_gain_1d: int | None,
    view_velocity: float | None,
    engagement_rate: float | None,
    viral_coefficient: float | None,
    trending_days: int,
) -> list[dict]:
    """급등 원인을 라벨 + 설명으로 반환."""
    reasons = []
    t = THRESHOLDS

    if hours_since_upload is not None:
        if hours_since_upload <= t["fresh_hours"]:
            reasons.append({
                "label": "🚀 신규 급등",
                "key":   "FRESH_VIRAL",
                "desc":  f"업로드 {int(hours_since_upload)}시간만에 급상승",
            })
        elif hours_since_upload > t["resurgence_days"] * 24:
            reasons.append({
                "label": "🔄 재급등",
                "key":   "RESURGENCE",
                "desc":  f"{int(hours_since_upload/24)}일 전 업로드 영상이 재조명",
            })

    if view_gain_1d is not None and view_gain_1d >= t["viral_view_gain_1d"]:
        reasons.append({
            "label": "📈 폭발적 증가",
            "key":   "VIRAL_SPIKE",
            "desc":  f"1일 조회수 +{view_gain_1d:,}회",
        })

    if viral_coefficient is not None and viral_coefficient >= t["small_channel_views"]:
        reasons.append({
            "label": "💥 소채널 돌파",
            "key":   "SMALL_CHANNEL_BREAKOUT",
            "desc":  f"구독자 대비 {viral_coefficient:.1f}배 조회수",
        })

    if engagement_rate is not None and engagement_rate >= t["high_engagement"] * 100:
        reasons.append({
            "label": "❤️ 높은 반응",
            "key":   "HIGH_ENGAGEMENT",
            "desc":  f"좋아요율 {engagement_rate:.1f}%",
        })

    if trending_days >= t["sustained_trending"]:
        reasons.append({
            "label": "🏆 지속 인기",
            "key":   "SUSTAINED_TRENDING",
            "desc":  f"{trending_days}일 연속 급상승",
        })

    if not reasons:
        reasons.append({
            "label": "📊 일반 급등",
            "key":   "GENERAL",
            "desc":  "급상승 차트 진입",
        })

    return reasons


def _score(
    *,
    view_gain_1d: int | None,
    view_velocity: float | None,
    engagement_rate: float | None,
    viral_coefficient: float | None,
    trending_days: int,
    reasons: list[dict],
) -> float:
    score = 0.0

    # 조회수 증가 (최대 40점)
    if view_gain_1d:
        score += min(40, math.log10(max(view_gain_1d, 1)) * 5)

    # 조회수 속도 (최대 20점)
    if view_velocity:
        score += min(20, math.log10(max(view_velocity, 1)) * 4)

    # 참여율 (최대 20점)
    if engagement_rate:
        score += min(20, engagement_rate * 2)

    # 바이럴 계수 (최대 10점)
    if viral_coefficient:
        score += min(10, viral_coefficient * 1.5)

    # 지속 인기 보너스 (최대 10점)
    score += min(10, trending_days * 2)

    return min(100, score)


# ─── 신뢰도 (뷰봇/사기 영상 감지) ───────────────────────────────────────────

def compute_trust(
    view_count: int,
    like_count: int | None,
    comment_count: int | None,
    subscriber_count: int | None,
    view_velocity: float | None,
) -> tuple[int, list[str]]:
    """
    뷰봇/사기 영상 신뢰도 점수 계산.

    Returns:
        (trust_score 0~100, 의심 신호 목록)
        trust_score 60 미만 → 의심 영상으로 분류
    """
    flags: list[str] = []
    deduct = 0

    if view_count < 1000:
        # 조회수가 너무 낮으면 판단 보류 (신뢰도 영향 없음)
        return 80, []

    likes = like_count or 0
    comments = comment_count or 0
    subs = subscriber_count or 0

    like_rate = likes / view_count if view_count else 0
    comment_rate = comments / view_count if view_count else 0

    # ── 신호 1: 좋아요율 극단 저하 ─────────────────────────────────────────
    # YouTube 평균 좋아요율 0.5~3%. 0.03% 미만 = 심각한 참여 공백
    if view_count >= 50_000 and like_rate < 0.0003:
        deduct += 35
        flags.append(f"좋아요율 {like_rate*100:.3f}% (정상 0.5%↑)")

    elif view_count >= 10_000 and like_rate < 0.001:
        deduct += 20
        flags.append(f"좋아요율 낮음 {like_rate*100:.2f}%")

    # ── 신호 2: 댓글+좋아요 동시 0 (참여 완전 공백) ──────────────────────
    if view_count >= 100_000 and likes == 0 and comments == 0:
        deduct += 40
        flags.append("조회수 10만+ 인데 좋아요·댓글 0")

    elif view_count >= 30_000 and likes == 0:
        deduct += 25
        flags.append("조회수 3만+ 인데 좋아요 0")

    # ── 신호 3: 신생 채널 이상 급등 ──────────────────────────────────────
    # 구독자 500 미만인데 조회수 100만+
    if subs > 0 and subs < 500 and view_count >= 1_000_000:
        deduct += 40
        flags.append(f"구독자 {subs:,}명 채널 조회수 {view_count:,}회")

    elif subs > 0 and subs < 1_000 and view_count >= 500_000:
        deduct += 30
        flags.append(f"구독자 {subs:,}명 채널 조회수 {view_count:,}회")

    elif subs > 0 and subs < 5_000 and view_count >= 2_000_000:
        deduct += 20
        flags.append(f"구독자 대비 조회수 극단적 불균형")

    # ── 신호 4: 조회 속도 + 참여율 역전 ─────────────────────────────────
    # 시간당 1만뷰 이상인데 좋아요율 0.05% 미만
    if view_velocity and view_velocity > 10_000 and like_rate < 0.0005:
        deduct += 25
        flags.append(f"초고속 유입({view_velocity:.0f}/h)에 참여율 극히 낮음")

    # ── 신호 5: 댓글 완전 없음 (조회수 대비) ─────────────────────────────
    if view_count >= 200_000 and comment_rate < 0.00005:
        deduct += 15
        flags.append(f"댓글 거의 없음 ({comments}개/{view_count:,}뷰)")

    trust_score = max(0, 100 - deduct)
    return trust_score, flags


def _parse_publish(date_str: str) -> datetime | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _hours_since(dt: datetime) -> float:
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 3600
