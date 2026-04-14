"""backend/scheduler.py — 매일 자정 자동 수집 스케줄러"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

_scheduler = BackgroundScheduler(timezone="Asia/Seoul")


def _daily_job():
    from datetime import date
    from backend.collector import run_collection
    from backend.database import Session
    from backend.routers.trending import _get_videos_for_date
    from backend.services.brief_generator import generate_and_save

    db = Session()
    try:
        for region in ["KR"]:
            run_collection(db, region=region, category=0, limit=50)

        # 수집 후 브리프 자동 생성
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
    _scheduler.add_job(_daily_job, CronTrigger(hour=0, minute=5), id="daily_collect", replace_existing=True)
    _scheduler.start()
    print("[scheduler] 매일 00:05 KST 자동 수집 등록")
