# YT Trend — YouTube 트렌드 분석 대시보드

YouTube 급상승 영상을 수집·분석해 콘텐츠 제작자에게 인사이트를 제공하는 대시보드.

---

## 주요 기능

| 탭 | 설명 |
|---|---|
| 💡 브리프 | 오늘의 트렌드를 주제별로 클러스터링 + Gemini 인사이트 |
| 🎯 심층분석 | 특정 주제 입력 → YouTube 검색 + Gemini 전략 리포트 |
| 📊 급상승 | 날짜/지역/기간별 트렌딩 영상 목록 |
| 🚀 스파이크 | spike_score 상위 영상 |
| 📋 모방가능 | 소규모 채널인데 조회수 높은 영상 |
| 🔑 키워드 | 트렌딩 제목 빈도 키워드 |
| 🌍 선행감지 | US/JP에서 급상승 중이지만 KR 미진입 영상 |
| 📅 비교 | 기간별 트렌드 비교 |
| 📈 통계 | 카테고리 분포·채널 TOP10 |
| ⚙️ 관리 | 관리자 전용 — 가입 승인·유저 관리 |

### 분석 지표

- **spike_score** — 조회수 급등 종합 점수
- **viral_coefficient** — 좋아요+댓글 기반 바이럴 지수
- **view_gain_1d** — 전일 대비 조회수 증가량
- **engagement_rate** — (좋아요+댓글) / 조회수
- **숏폼/롱폼 분리** — 60초 기준 자동 분류

---

## 기술 스택

| 구분 | 기술 |
|---|---|
| 백엔드 | FastAPI, SQLAlchemy, APScheduler |
| DB | SQLite (로컬) / PostgreSQL (운영) |
| AI | Gemini 2.0 Flash, OpenAI GPT-4o-mini |
| 프론트엔드 | Alpine.js, Tailwind CSS, Chart.js |
| 인증 | JWT (python-jose), bcrypt |
| 패키지 관리 | uv |

---

## 프로젝트 구조

```
yt_trend/
├── backend/
│   ├── main.py              # FastAPI 진입점 + 내부 수집 트리거
│   ├── models.py            # DB 모델 (TrendingSnapshot, TrendBrief, User, SignupRequest)
│   ├── database.py          # DB 연결 (SQLite/PostgreSQL 자동 전환)
│   ├── collector.py         # YouTube 수집 로직
│   ├── analyzer.py          # 스파이크 지표 계산
│   ├── auth.py              # JWT 인증 유틸
│   ├── scheduler.py         # 자동 수집 스케줄러
│   ├── routers/
│   │   ├── trending.py      # 트렌딩 API
│   │   ├── brief.py         # 브리프 API
│   │   ├── topic.py         # 심층분석 API
│   │   └── auth_router.py   # 인증 API
│   └── services/
│       ├── brief_generator.py   # Gemini 브리프 생성
│       ├── topic_analyzer.py    # Gemini 주제 심층 분석
│       ├── trend_clusterer.py   # 토픽 클러스터링
│       ├── video_analyzer.py    # 영상 AI 분석
│       └── translator.py        # 제목 한국어 번역
├── src/
│   └── fetcher/
│       ├── yt_api.py        # YouTube mostPopular API
│       └── yt_search.py     # YouTube Search API
├── frontend/
│   ├── index.html           # 메인 대시보드 (SPA)
│   └── login.html           # 로그인 / 가입요청 페이지
├── config/
│   ├── settings.yaml        # 수집 설정 (카테고리, 키워드 등)
│   └── .env.example         # 환경변수 예시
├── Dockerfile
└── pyproject.toml
```

---

## 로컬 개발 환경 설정

### 1. 의존성 설치

```bash
# uv 설치 (없는 경우)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 의존성 설치
uv sync
```

### 2. 환경변수 설정

```bash
cp config/.env.example config/.env
# config/.env 파일 편집
```

필수 키:
```env
YOUTUBE_API_KEY=...   # Google Cloud Console에서 발급
GEMINI_API_KEY=...    # Google AI Studio에서 발급
JWT_SECRET=...        # 임의의 긴 문자열
ADMIN_PASSWORD=...    # 관리자 초기 비밀번호
```

### 3. 서버 실행

```bash
uv run yt-server
# http://localhost:8000
```

최초 실행 시 관리자 계정이 자동 생성됩니다 (`.env`의 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 사용).

---

## YouTube API 할당량

일일 한도: **10,000 units**

| 수집 항목 | 소비량 |
|---|---|
| KR 카테고리 4개 | ~4 units |
| KR 키워드 20개 | ~2,020 units |
| US 선행감지 (5키워드) | ~505 units |
| JP 선행감지 (5키워드) | ~505 units |
| **일일 합계** | **~3,034 units (30%)** |

---

## 인증 구조

- **폐쇄형 서비스** — 직접 가입 불가, 관리자 승인제
- 가입 요청 → 관리자가 승인 → 임시 비밀번호 발급
- JWT 토큰 7일 유효, localStorage 저장
- 관리자 탭(`⚙️ 관리`)은 admin 계정에만 표시

---

## 배포

자세한 내용은 [DEPLOY.md](./DEPLOY.md) 참고.

**권장 스택 (무료):**
- 백엔드: Google Cloud Run
- DB: Neon PostgreSQL (무료 500MB)
- 스케줄러: Google Cloud Scheduler (3개 무료)
- 도메인/CDN: Cloudflare
