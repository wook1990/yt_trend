"""backend/routers/auth_router.py — 인증 API"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from backend.auth import (
    create_token, hash_password, verify_password,
    get_current_user, require_admin,
)
from backend.database import get_db
from backend.models import SignupRequest, User

router = APIRouter(prefix="/auth", tags=["auth"])


# ─── 스키마 ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class SignupRequestBody(BaseModel):
    username: str
    email: str
    reason: str | None = None


class RejectBody(BaseModel):
    reason: str | None = None


# ─── 로그인 ───────────────────────────────────────────────────────────────────

@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀렸습니다.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    token = create_token({"sub": user.username, "role": user.role})
    return {
        "access_token": token,
        "token_type":   "bearer",
        "username":     user.username,
        "role":         user.role,
    }


@router.get("/me")
def me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "username":   current_user.username,
        "email":      current_user.email,
        "role":       current_user.role,
        "created_at": current_user.created_at.isoformat(),
    }


# ─── 가입 요청 ────────────────────────────────────────────────────────────────

@router.post("/signup-request", status_code=201)
def signup_request(body: SignupRequestBody, db: Session = Depends(get_db)) -> dict:
    # 중복 확인
    if db.query(User).filter(
        (User.username == body.username) | (User.email == body.email)
    ).first():
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디 또는 이메일입니다.")

    if db.query(SignupRequest).filter(
        SignupRequest.status == "pending",
        (SignupRequest.username == body.username) | (SignupRequest.email == body.email),
    ).first():
        raise HTTPException(status_code=409, detail="이미 대기 중인 가입 요청이 있습니다.")

    req = SignupRequest(
        username=body.username,
        email=body.email,
        reason=body.reason,
        status="pending",
        requested_at=datetime.now(timezone.utc),
    )
    db.add(req)
    db.commit()
    return {"message": "가입 요청이 접수됐습니다. 관리자 승인 후 안내드립니다."}


# ─── 관리자 ───────────────────────────────────────────────────────────────────

@router.get("/admin/requests")
def list_requests(
    status_filter: str = "pending",
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    q = db.query(SignupRequest)
    if status_filter != "all":
        q = q.filter(SignupRequest.status == status_filter)
    rows = q.order_by(SignupRequest.requested_at.desc()).all()
    return {
        "requests": [
            {
                "id":           r.id,
                "username":     r.username,
                "email":        r.email,
                "reason":       r.reason,
                "status":       r.status,
                "requested_at": r.requested_at.isoformat(),
                "reviewed_at":  r.reviewed_at.isoformat() if r.reviewed_at else None,
                "reviewed_by":  r.reviewed_by,
            }
            for r in rows
        ]
    }


@router.post("/admin/requests/{req_id}/approve")
def approve_request(
    req_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    req = db.query(SignupRequest).filter(SignupRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없습니다.")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"이미 처리된 요청입니다: {req.status}")

    # 임시 비밀번호 = 이메일 앞부분 + 숫자
    import random, string
    temp_pw = req.username + "".join(random.choices(string.digits, k=4))

    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(temp_pw),
        role="user",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)

    req.status      = "approved"
    req.reviewed_at = datetime.now(timezone.utc)
    req.reviewed_by = admin.username
    db.commit()

    return {
        "message":       f"{req.username} 승인 완료",
        "temp_password": temp_pw,   # 관리자가 직접 전달해야 함
    }


@router.post("/admin/requests/{req_id}/reject")
def reject_request(
    req_id: int,
    body: RejectBody = RejectBody(),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    req = db.query(SignupRequest).filter(SignupRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없습니다.")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"이미 처리된 요청입니다: {req.status}")

    req.status      = "rejected"
    req.reviewed_at = datetime.now(timezone.utc)
    req.reviewed_by = admin.username
    db.commit()
    return {"message": f"{req.username} 거절 완료"}


@router.get("/admin/users")
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    users = db.query(User).order_by(User.created_at.desc()).all()
    return {
        "users": [
            {
                "id":         u.id,
                "username":   u.username,
                "email":      u.email,
                "role":       u.role,
                "is_active":  u.is_active,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ]
    }


@router.post("/admin/users/{user_id}/toggle-active")
def toggle_active(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="관리자 계정은 변경할 수 없습니다.")
    user.is_active = not user.is_active
    db.commit()
    return {"username": user.username, "is_active": user.is_active}


@router.post("/admin/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    import random, string
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    temp_pw = user.username + "".join(random.choices(string.digits, k=4))
    user.password_hash = hash_password(temp_pw)
    db.commit()
    return {"message": "비밀번호 초기화 완료", "temp_password": temp_pw}
