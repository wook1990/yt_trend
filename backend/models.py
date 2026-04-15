"""backend/models.py — DB 테이블 정의"""

from datetime import date, datetime
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


class TrendingSnapshot(Base):
    """매일 수집한 trending 순위 스냅샷."""
    __tablename__ = "trending_snapshots"
    __table_args__ = (
        UniqueConstraint("captured_date", "region", "category_id", "video_id"),
    )

    id:               Mapped[int]   = mapped_column(Integer, primary_key=True)
    captured_date:    Mapped[date]  = mapped_column(Date, index=True)
    rank:             Mapped[int]   = mapped_column(Integer)
    region:           Mapped[str]   = mapped_column(String(2), index=True)
    category_id:      Mapped[int]   = mapped_column(Integer, default=0)

    video_id:         Mapped[str]   = mapped_column(String(20), index=True)
    title:            Mapped[str]   = mapped_column(String(500))
    channel_id:       Mapped[str]   = mapped_column(String(60))
    channel_name:     Mapped[str]   = mapped_column(String(200))
    subscriber_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    view_count:       Mapped[int]   = mapped_column(BigInteger, default=0)
    like_count:       Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_count:    Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration:         Mapped[str | None] = mapped_column(String(20), nullable=True)
    publish_date:     Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    thumbnail:        Mapped[str | None] = mapped_column(String(500), nullable=True)
    category_name:    Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags:             Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    title_ko:         Mapped[str | None] = mapped_column(String(500), nullable=True)  # 한국어 번역

    # 계산된 스파이크 지표 (수집 시 저장)
    view_gain_1d:       Mapped[int | None]   = mapped_column(BigInteger, nullable=True)
    view_velocity:      Mapped[float | None] = mapped_column(Float, nullable=True)
    engagement_rate:    Mapped[float | None] = mapped_column(Float, nullable=True)
    viral_coefficient:  Mapped[float | None] = mapped_column(Float, nullable=True)
    trending_days:      Mapped[int]          = mapped_column(Integer, default=1)
    spike_score:        Mapped[float | None] = mapped_column(Float, nullable=True)
    spike_reasons:      Mapped[str | None]   = mapped_column(Text, nullable=True)  # JSON

    # 신뢰도 지표 (뷰봇/사기 영상 필터링)
    trust_score:        Mapped[int | None]   = mapped_column(Integer, nullable=True)
    trust_flags:        Mapped[str | None]   = mapped_column(Text, nullable=True)   # JSON


class TrendBrief(Base):
    """일별 트렌드 클러스터 브리프 (압축 인사이트)."""
    __tablename__ = "trend_briefs"
    __table_args__ = (
        UniqueConstraint("generated_date", "region"),
    )

    id:             Mapped[int]      = mapped_column(Integer, primary_key=True)
    generated_date: Mapped[date]     = mapped_column(Date, index=True)
    region:         Mapped[str]      = mapped_column(String(2))
    clusters:       Mapped[str]      = mapped_column(Text)   # JSON
    meta_insight:   Mapped[str|None] = mapped_column(Text, nullable=True)
    generated_at:   Mapped[datetime] = mapped_column(DateTime)


class User(Base):
    """서비스 사용자."""
    __tablename__ = "users"

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True)
    username:      Mapped[str]      = mapped_column(String(50), unique=True, index=True)
    email:         Mapped[str]      = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str]      = mapped_column(String(200))
    role:          Mapped[str]      = mapped_column(String(20), default="user")  # admin | user
    is_active:     Mapped[bool]     = mapped_column(default=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime)


class SignupRequest(Base):
    """가입 요청 (관리자 승인 대기)."""
    __tablename__ = "signup_requests"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    username:     Mapped[str]           = mapped_column(String(50))
    email:        Mapped[str]           = mapped_column(String(200))
    reason:       Mapped[str | None]    = mapped_column(Text, nullable=True)
    status:       Mapped[str]           = mapped_column(String(20), default="pending")  # pending | approved | rejected
    requested_at: Mapped[datetime]      = mapped_column(DateTime)
    reviewed_at:  Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    reviewed_by:  Mapped[str|None]      = mapped_column(String(50), nullable=True)


class UserKeyword(Base):
    """사용자 정의 수집 키워드."""
    __tablename__ = "user_keywords"
    __table_args__ = (UniqueConstraint("user_id", "keyword"),)

    id:                Mapped[int]           = mapped_column(Integer, primary_key=True)
    user_id:           Mapped[int]           = mapped_column(Integer, index=True)
    keyword:           Mapped[str]           = mapped_column(String(100))
    region:            Mapped[str]           = mapped_column(String(2), default="KR")
    is_active:         Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at:        Mapped[datetime]      = mapped_column(DateTime)
    last_collected_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)


CATEGORY_NAMES = {
    # YouTube 기본 카테고리
    0: "전체", 1: "영화/애니", 2: "자동차", 10: "음악",
    15: "반려동물", 17: "스포츠", 20: "게임", 22: "인물/블로그",
    23: "코미디", 24: "엔터테인먼트", 25: "뉴스/정치",
    26: "노하우/스타일", 27: "교육", 28: "과학/기술",
    # 가상 카테고리 (키워드 기반 강제 분류)
    101: "요리/레시피",
    102: "뷰티/패션",
    103: "부동산",
    104: "법률/세금",
}
