# ═══════════════════════════════════════════════════════════════════════════════
# PDS-Ultimate — Production Dockerfile
# ═══════════════════════════════════════════════════════════════════════════════
# Multi-stage build: slim Python + Playwright + system deps
#
# Build:   docker build -t pds-ultimate .
# Run:     docker run --env-file pds_ultimate/.env pds-ultimate
# Compose: docker compose up -d
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Stage 1: Builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Системные зависимости для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем и ставим зависимости (кэш Docker layer)
COPY pds_ultimate/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 2: Runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="PDS-Ultimate <qwert2009>"
LABEL description="PDS-Ultimate AI Enterprise Personal Assistant"
LABEL version="1.0.0"

# Переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    TZ=Asia/Ashgabat \
    # Playwright
    PLAYWRIGHT_BROWSERS_PATH=/app/browsers \
    # Whisper — CPU по умолчанию в Docker
    WHISPER_DEVICE=cpu

WORKDIR /app

# Системные зависимости для runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright / Chromium deps
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxshmfence1 \
    # OCR deps
    libgl1-mesa-glx \
    libglib2.0-0 \
    # General
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Копируем установленные пакеты из builder
COPY --from=builder /install /usr/local

# Устанавливаем Playwright Chromium
RUN playwright install chromium 2>/dev/null || true

# Копируем приложение
COPY pds_ultimate/ /app/pds_ultimate/

# Создаём директории данных
RUN mkdir -p \
    /app/pds_ultimate/data \
    /app/pds_ultimate/data/backups \
    /app/pds_ultimate/data/documents \
    /app/pds_ultimate/data/user_files \
    /app/pds_ultimate/data/screenshots \
    /app/pds_ultimate/data/downloads \
    /app/pds_ultimate/data/active_orders \
    /app/pds_ultimate/logs \
    /app/pds_ultimate/credentials

# Не-root пользователь
RUN groupadd -r pds && useradd -r -g pds -d /app pds \
    && chown -R pds:pds /app
USER pds

# Healthcheck
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import pds_ultimate; print('OK')" || exit 1

# Порт (если нужен webhook вместо polling)
EXPOSE 8443

# Точка входа
CMD ["python", "-m", "pds_ultimate.main"]
