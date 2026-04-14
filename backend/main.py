"""backend/main.py — FastAPI 앱 진입점"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).parent.parent / "config" / ".env")

from backend.auth import get_current_user
from backend.database import init_db
from backend.routers.auth_router import router as auth_router
from backend.routers.trending import router as trending_router
from backend.routers.brief import router as brief_router
from backend.routers.topic import router as topic_router
from backend.scheduler import start_scheduler

app = FastAPI(title="YT Trending Dashboard", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 인증 불필요 (공개)
app.include_router(auth_router)

# 인증 필요 — 모든 API 라우터에 get_current_user 의존성 주입
_auth = [Depends(get_current_user)]
app.include_router(trending_router, dependencies=_auth)
app.include_router(brief_router,    dependencies=_auth)
app.include_router(topic_router,    dependencies=_auth)

# 프론트엔드 정적 파일 서빙
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

    @app.get("/login", include_in_schema=False)
    def login_page():
        return FileResponse(str(FRONTEND_DIR / "login.html"))

    @app.get("/", include_in_schema=False)
    def root():
        return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.on_event("startup")
def on_startup():
    init_db()
    _ensure_admin()
    start_scheduler()
    print("[server] 시작됨 — http://localhost:8000")


def _ensure_admin():
    """최초 실행 시 관리자 계정이 없으면 자동 생성."""
    from datetime import datetime, timezone
    from backend.database import Session
    from backend.models import User
    from backend.auth import hash_password

    db = Session()
    try:
        if db.query(User).filter(User.role == "admin").first():
            return

        admin_user = os.environ.get("ADMIN_USERNAME", "admin")
        admin_pass = os.environ.get("ADMIN_PASSWORD", "admin1234")
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@yt-trending.local")

        user = User(
            username=admin_user,
            email=admin_email,
            password_hash=hash_password(admin_pass),
            role="admin",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        print(f"[server] 관리자 계정 생성 — username: {admin_user} / password: {admin_pass}")
        print("[server] ⚠️  운영 전 반드시 비밀번호를 변경하세요!")
    finally:
        db.close()


@app.post("/internal/collect", include_in_schema=False)
async def internal_collect(
    background_tasks: BackgroundTasks,
    x_scheduler_token: str | None = Header(None),
):
    """Cloud Scheduler 전용 수집 트리거. SCHEDULER_SECRET 헤더로 인증."""
    secret = os.environ.get("SCHEDULER_SECRET", "")
    if secret and x_scheduler_token != secret:
        raise HTTPException(status_code=403, detail="Forbidden")
    background_tasks.add_task(_run_collect_job)
    return JSONResponse({"status": "started"})


def _run_collect_job():
    from backend.scheduler import run_daily_job
    try:
        run_daily_job()
    except Exception as e:
        print(f"[collect_job] 실패: {e}")


def start():
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    start()
