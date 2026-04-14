FROM python:3.11-slim

WORKDIR /app

# uv 설치
RUN pip install uv --no-cache-dir

# 의존성 먼저 복사 (캐시 활용)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

# 소스 복사
COPY . .

# 포트 (Cloud Run은 PORT 환경변수 사용, 기본 8080)
ENV PORT=8080

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
