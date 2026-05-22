# syntax=docker/dockerfile:1.7
#
# ANAMNESIS server — internal-only image. Do not publish.
#
# Hardening references (mirrors VERIDEX backend Dockerfile):
#   - OWASP Docker Security Cheat Sheet — rules 3/4/5/7/8
#     https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html
#   - CIS Docker Benchmark v1.7 — 4.1 (USER), 4.6 (HEALTHCHECK), 4.9 (COPY-not-ADD)
#     https://www.cisecurity.org/benchmark/docker
#
# Why a pinned digest on the base image:
#   `python:3.12-slim` is a moving tag. Pinning the multi-arch manifest digest
#   means rebuilds are reproducible and verifiable — and any intentional bump
#   shows up as a one-line diff in code review.
#
# python:3.12-slim — multi-arch manifest digest captured 2026-05-22 from Docker Hub.
# To rotate: `docker pull python:3.12-slim && docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim`
# Reference: https://hub.docker.com/_/python (3.12-slim tag)
ARG PYTHON_BASE=python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

# ---- builder ----
FROM ${PYTHON_BASE} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

RUN pip install --no-cache-dir uv==0.5.*

WORKDIR /build

COPY pyproject.toml uv.lock README.md ./
COPY anamnesis-py/pyproject.toml ./anamnesis-py/pyproject.toml
COPY anamnesis-server/pyproject.toml ./anamnesis-server/pyproject.toml
COPY anamnesis-py/src ./anamnesis-py/src
COPY anamnesis-server/src ./anamnesis-server/src

RUN uv sync --all-packages --no-dev --frozen

# ---- runtime ----
FROM ${PYTHON_BASE} AS runtime

LABEL org.opencontainers.image.title="anamnesis-server" \
      org.opencontainers.image.description="ANAMNESIS EU-AI-Act Art-15 audit + reasoning-trace-reuse server" \
      org.opencontainers.image.vendor="ANAMNESIS" \
      org.opencontainers.image.licenses="Proprietary" \
      org.opencontainers.image.source="https://github.com/ozan/anamnesis"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# curl required for HEALTHCHECK in runtime layer (no build-essential).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Non-root user. UID 1000 lines up with the typical pod-securityContext default
# so PVC mounts do not need fsGroup remapping.
RUN groupadd --system --gid 1000 anamnesis && \
    useradd  --system --uid 1000 --gid 1000 --create-home --home-dir /home/anamnesis \
             --shell /usr/sbin/nologin anamnesis

WORKDIR /app

# Carry the .venv from the builder, then re-own to the non-root user so it can
# import (read-only is fine; we do not write here at runtime).
COPY --from=builder --chown=anamnesis:anamnesis /build/.venv /app/.venv
COPY --from=builder --chown=anamnesis:anamnesis /build/anamnesis-py /app/anamnesis-py
COPY --from=builder --chown=anamnesis:anamnesis /build/anamnesis-server /app/anamnesis-server

ENV PATH="/app/.venv/bin:${PATH}"

USER anamnesis

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "anamnesis_server.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
