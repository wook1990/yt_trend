"""backend/services/trend_clusterer.py — 영상 주제 클러스터링

수집된 영상을 키워드 기반으로 주제별 클러스터로 압축.
사전 정의 토픽 시드 + 동적 키워드 그룹 병행.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

# 주제 시드 — 각 토픽의 대표 키워드 목록
TOPIC_SEEDS: dict[str, list[str]] = {
    "🤖 AI · 테크": [
        "AI", "인공지능", "ChatGPT", "GPT", "클로드", "제미나이", "자동화",
        "노코드", "파이썬", "개발", "코딩", "IT", "디지털", "로봇", "데이터",
        "머신러닝", "딥러닝", "LLM", "프롬프트",
    ],
    "💰 재테크 · 투자": [
        "재테크", "투자", "주식", "ETF", "부동산", "금융", "달러", "환율",
        "경제", "돈", "수익", "자산", "금", "채권", "펀드", "배당", "코인",
        "비트코인", "절약", "저축", "경기",
    ],
    "🚀 창업 · 비즈니스": [
        "창업", "부업", "사업", "마케팅", "브랜딩", "광고", "온라인",
        "쇼핑몰", "프리랜서", "유튜브 수익", "수익화", "B2B", "스타트업",
        "퍼스널브랜딩", "콘텐츠", "플랫폼",
    ],
    "💪 건강 · 의학": [
        "건강", "다이어트", "운동", "헬스", "의학", "병원", "영양",
        "몸", "증상", "치료", "피부", "근육", "체중", "칼로리", "식단",
    ],
    "📚 자기계발 · 교육": [
        "자기계발", "공부", "습관", "생산성", "영어", "독서", "강의",
        "자격증", "취업", "학습", "집중", "목표", "성장", "멘탈",
    ],
    "📰 뉴스 · 시사": [
        "뉴스", "속보", "정치", "사건", "외교", "전쟁", "대통령",
        "정부", "사회", "이슈", "긴급", "선거", "국제",
    ],
    "⚖️ 법률 · 세금": [
        "세금", "법인", "절세", "법률", "계약", "세무", "회계",
        "규제", "소송", "변호사", "노동", "상속",
    ],
}


def cluster_videos(
    videos: list[dict[str, Any]],
    top_n: int = 20,
    min_cluster_size: int = 3,
) -> list[dict[str, Any]]:
    """
    영상 목록을 주제별 클러스터로 압축.

    Args:
        videos:           _to_dict() 형식의 영상 목록
        top_n:            클러스터당 상위 N개 영상 포함
        min_cluster_size: 이 수 미만 클러스터는 병합

    Returns:
        클러스터 목록 (score 내림차순 정렬)
    """
    buckets: dict[str, list[dict]] = defaultdict(list)

    for video in videos:
        topic = _assign_topic(video.get("title", ""))
        buckets[topic].append(video)

    # 작은 클러스터는 "기타"로 병합
    for topic, vids in list(buckets.items()):
        if len(vids) < min_cluster_size and topic != "기타":
            buckets["기타"].extend(vids)
            del buckets[topic]

    clusters = []
    for topic, vids in buckets.items():
        if not vids:
            continue

        # spike_score 내림차순 정렬
        vids.sort(key=lambda x: (x.get("spike_score") or 0), reverse=True)

        n = len(vids)
        avg_spike      = sum(v.get("spike_score") or 0 for v in vids) / n
        avg_views      = sum(v.get("view_count") or 0 for v in vids) / n
        avg_engagement = sum(v.get("engagement_rate") or 0 for v in vids) / n
        avg_viral      = sum(v.get("viral_coefficient") or 0 for v in vids) / n

        # 상위 키워드 추출
        top_kws = _top_keywords(vids[:20], top=5)

        clusters.append({
            "topic":          topic,
            "video_count":    n,
            "avg_spike":      round(avg_spike, 1),
            "avg_views":      int(avg_views),
            "avg_engagement": round(avg_engagement, 2),
            "avg_viral":      round(avg_viral, 1),
            "top_keywords":   top_kws,
            # Gemini 분석 (brief_generator에서 채움)
            "why_trending":       None,
            "title_pattern":      None,
            "creator_opportunity":None,
            "saturation":         None,
            # 대표 영상 top_n개
            "videos": vids[:top_n],
        })

    # 영상 수 × 평균 스파이크 복합 점수로 정렬
    clusters.sort(key=lambda x: x["video_count"] * (x["avg_spike"] + 1), reverse=True)
    return clusters


def _assign_topic(title: str) -> str:
    """제목에서 가장 높은 매칭 점수의 토픽 반환."""
    best_topic = "기타"
    best_score = 0

    for topic, seeds in TOPIC_SEEDS.items():
        score = sum(1 for seed in seeds if seed.lower() in title.lower())
        if score > best_score:
            best_score = score
            best_topic = topic

    return best_topic


def _top_keywords(videos: list[dict], top: int = 5) -> list[str]:
    """영상 제목에서 빈도 높은 키워드 추출."""
    STOPWORDS = {
        "이", "그", "저", "것", "수", "등", "및", "또", "더", "가", "을", "를",
        "은", "는", "의", "에", "와", "과", "도", "만", "로", "한", "하는",
        "있다", "없다", "통해", "위해", "때문", "이후", "이번", "지금", "방법",
        "진짜", "이유", "완전", "정말", "최고", "최초", "단독", "공개",
    }
    from collections import Counter
    counter: Counter = Counter()
    for v in videos:
        words = re.split(r'[\s|\-\[\]\(\)\/·,\.!?~…:;]+', v.get("title", ""))
        for w in words:
            w = w.strip()
            if len(w) >= 2 and w not in STOPWORDS and not w.isdigit():
                counter[w] += 1
    return [kw for kw, _ in counter.most_common(top)]
