"""backend/main.py — FastAPI 앱 진입점"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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


def start():
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    start()
