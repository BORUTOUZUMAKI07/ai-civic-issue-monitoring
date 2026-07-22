FROM python:3.12-slim AS builder

COPY --from=ghcr.io/prefix-dev/pixi:latest /pixi /bin/pixi

WORKDIR /app

COPY pixi.toml ./
COPY pyproject.toml ./
COPY backend/pyproject.toml backend/pyproject.toml

ENV PIXI_HOME=/app/.pixi

RUN pixi install

# ---------- RUNTIME STAGE ----------
FROM python:3.12-slim

RUN useradd -m -u 1000 appuser
WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.pixi /app/.pixi
COPY --from=builder --chown=appuser:appuser /app/backend/src ./backend/src

ENV PATH="/app/.pixi/envs/default/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

USER appuser
EXPOSE 8000

CMD ["uvicorn", "backend.src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
