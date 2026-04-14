# 배포 가이드

## 아키텍처

```
사용자 브라우저
      │
      ▼
Cloudflare (DNS + SSL + CDN)
      │
      ▼
Google Cloud Run  ←──(HTTP 트리거)── Google Cloud Scheduler (매일 00:05 KST)
      │
      ▼
Neon PostgreSQL (무료 500MB)
```

---

## 사전 준비

| 서비스 | 용도 | 비용 |
|---|---|---|
| [Google Cloud](https://console.cloud.google.com) | Cloud Run + Cloud Scheduler | 무료 (크레딧 $300) |
| [Neon](https://neon.tech) | PostgreSQL DB | 무료 (500MB) |
| [Google AI Studio](https://aistudio.google.com) | Gemini API Key | 무료 |
| [Google Cloud Console](https://console.cloud.google.com/apis) | YouTube Data API Key | 무료 (10,000 units/일) |
| Cloudflare | 도메인 DNS | 무료 (도메인 별도 구매) |

---

## 1단계 — Neon PostgreSQL 설정

1. [neon.tech](https://neon.tech) 회원가입
2. **New Project** → Project name: `yt-trend`, Region: `Asia Pacific (Singapore)`
3. 생성 후 Dashboard → **Connection string** 복사

```
postgresql://username:password@host.neon.tech/dbname?sslmode=require
```

> ⚠️ 이 문자열은 `DATABASE_URL` 환경변수로 사용

---

## 2단계 — Google Cloud 프로젝트 설정

```bash
# gcloud CLI 설치 (없는 경우)
# macOS
brew install google-cloud-sdk

# gcloud 로그인
gcloud auth login

# 프로젝트 생성
gcloud projects create yt-trend-app --name="YT Trend"
gcloud config set project yt-trend-app

# 결제 계정 연결 (콘솔에서: Billing → 계정 연결)
# https://console.cloud.google.com/billing

# 필요한 API 활성화
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com
```

---

## 3단계 — Cloud Run 배포

```bash
# 프로젝트 루트에서 실행
gcloud run deploy yt-trend \
  --source . \
  --region asia-northeast3 \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 2 \
  --set-env-vars "\
DATABASE_URL=postgresql://...(Neon 연결 문자열),\
YOUTUBE_API_KEY=발급받은키,\
GEMINI_API_KEY=발급받은키,\
JWT_SECRET=랜덤문자열최소32자,\
ADMIN_USERNAME=admin,\
ADMIN_PASSWORD=설정할비밀번호,\
ADMIN_EMAIL=관리자이메일,\
SCHEDULER_SECRET=랜덤문자열"
```

배포 완료 시 Service URL 확인:
```
Service URL: https://yt-trend-xxxxxxxx-an3.a.run.app
```

> ℹ️ 환경변수가 많으면 Cloud Console → Cloud Run → 서비스 선택 → **편집** → 환경변수 탭에서 GUI로 입력 가능

---

## 4단계 — Cloud Scheduler 등록 (자동 수집)

```bash
# 위에서 받은 Service URL로 교체
SERVICE_URL="https://yt-trend-xxxxxxxx-an3.a.run.app"
SCHEDULER_SECRET="위에서_설정한_SCHEDULER_SECRET"

gcloud scheduler jobs create http yt-trend-daily-collect \
  --schedule="5 0 * * *" \
  --time-zone="Asia/Seoul" \
  --uri="${SERVICE_URL}/internal/collect" \
  --message-body="{}" \
  --headers="Content-Type=application/json,X-Scheduler-Token=${SCHEDULER_SECRET}" \
  --http-method=POST \
  --location=asia-northeast3
```

수동 즉시 실행 테스트:
```bash
gcloud scheduler jobs run yt-trend-daily-collect --location=asia-northeast3
```

---

## 5단계 — Cloudflare 도메인 연결

### 방법 A — 서브도메인 연결 (권장)

1. Cloudflare 대시보드 → 도메인 선택 → **DNS** → **Records**
2. **Add record** 클릭
   - Type: `CNAME`
   - Name: `trend` (→ `trend.yourdomain.com`)
   - Target: `yt-trend-xxxxxxxx-an3.a.run.app`
   - Proxy status: **Proxied** (주황 구름 아이콘) ✅
3. 저장 후 `https://trend.yourdomain.com` 으로 접속 확인

### 방법 B — 루트 도메인 연결

- Type: `CNAME`, Name: `@`, Target: Cloud Run URL
- Cloudflare는 루트 도메인 CNAME(CNAME Flattening)을 지원하므로 동작함

> ℹ️ Cloudflare Proxy를 켜면 SSL 자동 처리, DDoS 방어, 캐싱이 적용됩니다.

---

## 환경변수 전체 목록

| 변수명 | 필수 | 설명 |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL 연결 문자열 (없으면 SQLite) |
| `YOUTUBE_API_KEY` | ✅ | YouTube Data API v3 키 |
| `GEMINI_API_KEY` | ✅ | Gemini API 키 |
| `OPENAI_API_KEY` | ❌ | OpenAI 키 (Gemini fallback용) |
| `JWT_SECRET` | ✅ | JWT 서명 키 (32자 이상 랜덤 문자열) |
| `ADMIN_USERNAME` | ✅ | 최초 관리자 아이디 |
| `ADMIN_PASSWORD` | ✅ | 최초 관리자 비밀번호 |
| `ADMIN_EMAIL` | ❌ | 관리자 이메일 |
| `SCHEDULER_SECRET` | ✅ | 내부 수집 트리거 보안 토큰 |

---

## 로컬 개발 → 운영 배포 워크플로

```bash
# 로컬에서 개발 (SQLite 자동 사용)
uv run yt-server

# 변경사항 git push
git add -A && git commit -m "feat: ..."
git push origin main

# Cloud Run 재배포 (코드 변경 시)
gcloud run deploy yt-trend --source . --region asia-northeast3
```

---

## 비용 추정 (월간)

| 서비스 | 무료 한도 | 예상 사용량 | 비용 |
|---|---|---|---|
| Cloud Run | 2M req, 360K GB-s | ~900 req/월 | **$0** |
| Cloud Scheduler | 3 jobs 무료 | 1 job | **$0** |
| Cloud Build | 120분/일 무료 | ~2분/배포 | **$0** |
| Neon PostgreSQL | 0.5GB | ~50MB/월 | **$0** |
| Cloudflare | 무제한 | - | **$0** |
| **합계** | | | **$0** |

> ⚠️ Google Cloud 신규 가입 시 $300 크레딧 제공. 이후 Cloud Run은 위 무료 한도 내에서 계속 무료.

---

## 트러블슈팅

### 컨테이너 로그 확인
```bash
gcloud run services logs read yt-trend --region asia-northeast3 --limit 50
```

### DB 마이그레이션 이슈
첫 배포 후 `init_db()`가 자동으로 테이블을 생성합니다. 이후 스키마 변경 시 Alembic 또는 수동 ALTER TABLE 필요.

### Cloud Run 콜드 스타트
`min-instances=0` 설정 시 요청이 없으면 컨테이너가 종료됩니다. 응답이 느리면 `--min-instances 1` 로 변경 (소량 비용 발생).

### Scheduler 수동 테스트
```bash
# Cloud Scheduler 없이 직접 테스트
curl -X POST https://yt-trend-xxx.a.run.app/internal/collect \
  -H "X-Scheduler-Token: 설정한토큰" \
  -H "Content-Type: application/json"
```
