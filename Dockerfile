# syntax=docker/dockerfile:1
# Base pinned by digest (python:3.13-slim, 2026-11-19). Update deliberately: see README.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.txt .
# Every package (and its dependencies) must match a SHA-256 hash in requirements.txt.
RUN pip install --require-hashes --no-deps -r requirements.txt
COPY src/ src/

# Test stage: `docker build --target test .` fails the build if any test fails. Never shipped.
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --require-hashes --no-deps -r requirements-dev.txt
COPY tests/ tests/
RUN python -m pytest -q -p no:cacheprovider tests

FROM base AS runtime
RUN groupadd --gid 10001 mcp && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin mcp
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), 2).close()"]
CMD ["python", "-m", "homelab_mcp"]
