# syntax=docker/dockerfile:1.7
# ANAMNESIS server — internal-only image. Do not publish.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.5.*

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY anamnesis-py/pyproject.toml ./anamnesis-py/pyproject.toml
COPY anamnesis-server/pyproject.toml ./anamnesis-server/pyproject.toml
COPY anamnesis-py/src ./anamnesis-py/src
COPY anamnesis-server/src ./anamnesis-server/src

RUN uv sync --all-packages --no-dev --frozen

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uv", "run", "--no-dev", "uvicorn", "anamnesis_server.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
