# yt_trending

YouTube 인기 급상승 동영상 탐색 및 수집 도구.

## 목적

- YouTube 인기 급상승 동영상을 국가/카테고리별로 수집
- 제목, 채널, 조회수, 업로드 시간, 썸네일 등 메타데이터 저장
- 추후 concept_maker 리서치 단계에 피드 가능

## 데이터 소스 전략

| 방법 | 장점 | 단점 |
|------|------|------|
| YouTube Data API v3 | 공식, 안정적 | 일일 할당량 10,000 units |
| yt-dlp | 무료, 풍부한 메타데이터 | 비공식, 구조 변경 위험 |
| RSS Feed | 무료, 경량 | 메타데이터 제한적 |

→ **기본: yt-dlp** (할당량 없음), **옵션: YouTube Data API v3** (정확한 trending 순위)

## 프로젝트 구조

```
yt_trending/
├── src/
│   ├── fetcher/
│   │   ├── ytdlp.py        # yt-dlp 기반 trending 수집
│   │   └── yt_api.py       # YouTube Data API v3 (옵션)
│   ├── filter.py           # 카테고리/언어/조회수 필터
│   ├── exporter.py         # JSON/CSV 저장
│   └── cli.py              # 커맨드라인 인터페이스
├── config/
│   ├── settings.yaml       # 기본 설정 (국가코드, 카테고리 등)
│   └── .env.example
├── data/                   # 수집 결과 저장 (gitignore)
├── docs/
│   └── yt_api_categories.md  # YouTube 카테고리 ID 참조표
└── main.py                 # 진입점
```

## 빠른 시작

```bash
# 의존성 설치
pip install -r requirements.txt

# 인기 급상승 수집 (기본: 한국, 상위 50개)
python main.py fetch

# 국가/카테고리 지정
python main.py fetch --region KR --category 28 --limit 50

# 결과 저장
python main.py fetch --region KR --output data/trending_KR.json
```

## 카테고리 코드 (주요)

| ID | 카테고리 |
|----|---------|
| 0  | 전체 |
| 1  | 영화/애니메이션 |
| 10 | 음악 |
| 15 | 반려동물 |
| 17 | 스포츠 |
| 20 | 게임 |
| 22 | 인물/블로그 |
| 23 | 코미디 |
| 24 | 엔터테인먼트 |
| 25 | 뉴스/정치 |
| 26 | 노하우/스타일 |
| 27 | 교육 |
| 28 | 과학/기술 |
