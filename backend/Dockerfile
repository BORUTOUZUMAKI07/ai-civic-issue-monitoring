FROM python:3.12-slim AS builder

WORKDIR /app

COPY --from=ghcr.io/prefix-dev/pixi:latest /pixi /bin/pixi

COPY pixi.toml ./
COPY pyproject.toml ./

RUN pixi install

COPY src src
COPY tests tests
COPY alembic alembic
COPY alembic.ini ./

# ---------- RUNTIME STAGE ----------
FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system --gid 1001 app \
    && adduser --system --uid 1001 --gid 1001 app

COPY --from=builder --chown=app:app /app/.pixi /app/.pixi
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/alembic /app/alembic
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini

ENV PATH="/app/.pixi/envs/default/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, os, sys; port = os.environ.get('PORT', '8000'); sys.exit(0 if urllib.request.urlopen(f'http://0.0.0.0:{port}/health',timeout=3).status==200 else 1)" || exit 1
CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
