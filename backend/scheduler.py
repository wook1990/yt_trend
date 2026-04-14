"""backend/scheduler.py — 스케줄 수집 처리

로컬: APScheduler (백그라운드 크론)
Cloud Run: Cloud Scheduler → POST /internal/collect HTTP 트리거
"""

from __future__ import annotations

import os


def run_daily_job():
    """수집 + 브리프 생성. 로컬 APScheduler / Cloud Scheduler 둘 다 이 함수 호출."""
    from datetime import date
    from backend.collector import run_collection
    from backend.database import Session
    from backend.routers.trending import _get_videos_for_date
    from backend.services.brief_generator import generate_and_save

    db = Session()
    try:
        for region in ["KR"]:
            run_collection(db, region=region, category=None, limit=50)

        today = date.today()
        for region in ["KR"]:
            try:
                videos = _get_videos_for_date(db, today, region)
                if videos:
                    generate_and_save(db, videos, region=region, target_date=today)
                    print(f"[scheduler] {region} 브리프 생성 완료")
            except Exception as e:
                print(f"[scheduler] {region} 브리프 생성 실패: {e}")
    finally:
        db.close()


def start_scheduler():
    """로컬 개발 전용: APScheduler 백그라운드 크론 등록."""
    if os.environ.get("DATABASE_URL"):
        # Cloud Run 환경 — Cloud Scheduler가 HTTP 트리거하므로 APScheduler 불필요
        print("[scheduler] Cloud Run 환경 — Cloud Scheduler HTTP 트리거 사용")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        scheduler.add_job(run_daily_job, CronTrigger(hour=0, minute=5),
                          id="daily_collect", replace_existing=True)
        scheduler.start()
        print("[scheduler] 매일 00:05 KST 자동 수집 등록 (로컬)")
    except ImportError:
        print("[scheduler] APScheduler 없음 — 수동 수집 모드")
