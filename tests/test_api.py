"""tests/test_api.py — 전체 API 기능 검증 (외부 API 호출 없음)

실행 방법:
  uv run python tests/test_api.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("YOUTUBE_API_KEY", "dummy")
os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("DATABASE_URL", "")  # SQLite 사용

from fastapi.testclient import TestClient

from backend.main import app
from backend.database import Session, engine
from backend.models import Base, TrendingSnapshot

# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

def _create_tables():
    Base.metadata.create_all(bind=engine)

def _seed_video(session, suffix="", date_=None):
    """테스트용 영상 데이터 삽입 (이미 있으면 무시)."""
    today = date_ or date.today()
    video_id = f"testvid{suffix}"
    existing = session.query(TrendingSnapshot).filter(
        TrendingSnapshot.video_id == video_id,
        TrendingSnapshot.captured_date == today,
        TrendingSnapshot.region == "KR",
    ).first()
    if existing:
        return existing
    v = TrendingSnapshot(
        captured_date=today,
        rank=1,
        region="KR",
        category_id=28,
        video_id=video_id,
        title=f"테스트 영상 {suffix}",
        channel_id=f"channel{suffix}",
        channel_name=f"테스트채널 {suffix}",
        view_count=100000,
        like_count=5000,
        comment_count=300,
        subscriber_count=80000,
        category_name="과학/기술",
        trust_score=80,
        trust_flags=json.dumps([]),
        tags=json.dumps([]),
        trending_days=1,
        spike_score=75.0,
        spike_reasons=json.dumps([{"label": "급등", "score": 75}]),
        engagement_rate=5.3,
        view_velocity=1200.0,
        viral_coefficient=0.8,
    )
    session.add(v)
    session.commit()
    return v

# ── 테스트 실행 ────────────────────────────────────────────────────────────────

PASS = []
FAIL = []

def check(name: str, cond: bool, detail: str = ""):
    if cond:
        print(f"  ✅ {name}")
        PASS.append(name)
    else:
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
        FAIL.append(name)

admin_pass = os.environ.get("ADMIN_PASSWORD", "admin1234")

def run_tests():
    _create_tables()

    with TestClient(app) as client:
        token = ""
        today_str = str(date.today())

        # ① 인증 ─────────────────────────────────────────────────────────────
        print("\n[1] 인증")
        r = client.post("/auth/login", json={"username": "admin", "password": admin_pass})
        check("관리자 로그인", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            token = r.json().get("access_token", "")
        check("토큰 발급", bool(token))

        auth = {"Authorization": f"Bearer {token}"}

        # ② 기본 트렌딩 ───────────────────────────────────────────────────────
        print("\n[2] 기본 트렌딩")
        db = Session()
        _seed_video(db, suffix="_t1")
        _seed_video(db, suffix="_t2")
        db.close()

        r = client.get(f"/api/trending?region=KR&date={today_str}", headers=auth)
        check("GET /api/trending", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            check("videos 필드 존재", "videos" in data)
            check("videos 2개 이상", len(data.get("videos", [])) >= 2)

        # ③ 스파이크 ──────────────────────────────────────────────────────────
        print("\n[3] 스파이크")
        r = client.get(f"/api/trending/spikes?region=KR&date={today_str}&limit=10", headers=auth)
        check("GET /api/trending/spikes", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            check("spikes 필드 존재", "spikes" in r.json())

        # ④ 카테고리 통계 ─────────────────────────────────────────────────────
        print("\n[4] 카테고리 통계")
        r = client.get(f"/api/trending/categories?region=KR&date={today_str}", headers=auth)
        check("GET /api/trending/categories", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            check("categories 필드 존재", "categories" in r.json())

        # ⑤ 수집된 날짜 목록 (stats) ──────────────────────────────────────────
        print("\n[5] 수집 날짜 목록")
        r = client.get("/api/stats/available-dates?region=KR", headers=auth)
        check("GET /api/stats/available-dates", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            check("dates 필드 존재", "dates" in data)
            check("오늘 날짜 포함", today_str in data.get("dates", []))

        # ⑥ 키워드 분석 ───────────────────────────────────────────────────────
        print("\n[6] 키워드 분석")
        r = client.get(f"/api/trending/keywords?region=KR&date={today_str}&limit=20", headers=auth)
        check("GET /api/trending/keywords", r.status_code == 200, f"status={r.status_code}")

        # ⑦ 비교 분석 ─────────────────────────────────────────────────────────
        print("\n[7] 비교 분석")
        r = client.get(f"/api/trending/compare?region=KR&date={today_str}", headers=auth)
        check("GET /api/trending/compare", r.status_code == 200, f"status={r.status_code}")

        # ⑧ 복사가능 영상 ─────────────────────────────────────────────────────
        print("\n[8] 복사가능 영상")
        r = client.get(f"/api/trending/copyable?region=KR&date={today_str}", headers=auth)
        check("GET /api/trending/copyable", r.status_code == 200, f"status={r.status_code}")

        # ⑨ 큐레이션 ─────────────────────────────────────────────────────────
        print("\n[9] 큐레이션 (신뢰도 필터)")
        r = client.get("/api/trending/curated?region=KR&period=7&min_trust=60", headers=auth)
        check("GET /api/trending/curated", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            check("categories 필드 존재", "categories" in data)

        # ⑩ 부업 기회 분석 ────────────────────────────────────────────────────
        print("\n[10] 부업 기회 분석")
        r = client.get(f"/api/trending/opportunity?region=KR&date={today_str}", headers=auth)
        check("GET /api/trending/opportunity", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            check("opportunities 필드 존재", "opportunities" in data)

        # ⑪ 브리프 ────────────────────────────────────────────────────────────
        print("\n[11] 브리프")
        r = client.get(f"/api/brief?region=KR&date={today_str}", headers=auth)
        check("GET /api/brief (없어도 200)", r.status_code == 200, f"status={r.status_code}")

        # ⑫ 내 키워드 CRUD ────────────────────────────────────────────────────
        print("\n[12] 키워드 관리")
        import random as _rand, string as _str
        rand_kw = "qa_" + "".join(_rand.choices(_str.ascii_lowercase, k=6))

        r = client.get("/api/keywords/my", headers=auth)
        check("GET /api/keywords/my", r.status_code == 200, f"status={r.status_code}")

        r = client.post("/api/keywords/my",
            json={"keyword": rand_kw, "region": "KR"}, headers=auth)
        check("POST /api/keywords/my (추가)", r.status_code in (200, 201), f"status={r.status_code}")
        kw_id = r.json().get("id") if r.status_code in (200, 201) else None

        if kw_id:
            r = client.delete(f"/api/keywords/my/{kw_id}", headers=auth)
            check("DELETE /api/keywords/my/{id}", r.status_code in (200, 204), f"status={r.status_code}")

        # ⑬ 가입 요청 ─────────────────────────────────────────────────────────
        print("\n[13] 가입 요청")
        import random, string
        rand_user = "qa_" + "".join(random.choices(string.ascii_lowercase, k=6))
        r = client.post("/auth/signup-request", json={
            "username": rand_user,
            "email": f"{rand_user}@test.com",
            "reason": "QA 테스트",
        })
        check("POST /auth/signup-request", r.status_code in (200, 201), f"status={r.status_code}")

        # ⑭ 관리자 — 가입 요청 목록 ──────────────────────────────────────────
        print("\n[14] 관리자 패널")
        r = client.get("/auth/admin/requests", headers=auth)
        check("GET /auth/admin/requests", r.status_code == 200, f"status={r.status_code}")

        r = client.get("/auth/admin/users", headers=auth)
        check("GET /auth/admin/users", r.status_code == 200, f"status={r.status_code}")

    # ── 결과 요약 ──────────────────────────────────────────────────────────────
    total = len(PASS) + len(FAIL)
    print(f"\n{'='*50}")
    print(f"결과: {len(PASS)}/{total} 통과" + (" 🎉" if not FAIL else ""))
    if FAIL:
        print(f"실패 항목:")
        for f in FAIL:
            print(f"  - {f}")
    print(f"{'='*50}")

    return len(FAIL) == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
