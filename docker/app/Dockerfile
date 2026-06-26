FROM node:24-bookworm-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build


FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg liquidsoap ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY manager ./manager
COPY scripts ./scripts
COPY --from=frontend-build /app/frontend/dist /opt/radio/www/html

RUN python -m pip install --no-cache-dir -U pip setuptools wheel \
    && python -m pip install --no-cache-dir . \
    && mkdir -p logs \
    && chown -R 10001:10001 logs

CMD ["python", "-m", "manager", "db-check"]
