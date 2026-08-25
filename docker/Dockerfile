FROM python:3.12-slim AS builder

WORKDIR /app

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend backend

RUN cd backend && pip install --no-cache-dir . && \
    pip install --no-cache-dir "aiosqlite>=0.20.0"

# ---------- RUNTIME STAGE ----------
FROM python:3.12-slim

RUN useradd -m -u 1000 appuser
WORKDIR /app

COPY --from=builder --chown=appuser:appuser /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder --chown=appuser:appuser /usr/local/bin /usr/local/bin
COPY --from=builder --chown=appuser:appuser /app/backend/src ./backend/src
COPY --from=builder --chown=appuser:appuser /app/backend/configs ./backend/configs
COPY --from=builder --chown=appuser:appuser /app/backend/alembic ./backend/alembic
COPY --from=builder --chown=appuser:appuser /app/backend/alembic.ini ./backend/alembic.ini

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

USER appuser
EXPOSE 8000

CMD ["uvicorn", "backend.src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
