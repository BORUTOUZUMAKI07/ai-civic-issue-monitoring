FROM python:3.12-slim AS builder

WORKDIR /app

# Build context is the repository ROOT (Render, GHCR and Docker Compose all use
# it) so this Dockerfile can include the trained ONNX model from ../models.
COPY backend/pyproject.toml ./

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.5.0,<3" "torchvision>=0.20.0,<1" && \
    pip install --no-cache-dir ".[ml,observability]" && \
    pip install --no-cache-dir "aiosqlite>=0.20.0"

COPY backend/src src
COPY backend/tests tests
COPY backend/configs configs
COPY backend/alembic alembic
COPY backend/alembic.ini ./
# The .dvc file is only a pointer. Bake the real weights into the image so the
# container has /app/models/model.onnx and ONNX inference is used in production.
COPY models/model.onnx models/model.onnx

# ---------- RUNTIME STAGE ----------
FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system --gid 1001 app \
    && adduser --system --uid 1001 --gid 1001 app \
    && mkdir -p /app/logs /app/uploads /app/models && chown -R app:app /app/logs /app/uploads /app/models

COPY --from=builder --chown=app:app /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder --chown=app:app /usr/local/bin /usr/local/bin
COPY --from=builder --chown=app:app /app/src /app/src
COPY --from=builder --chown=app:app /app/configs /app/configs
COPY --from=builder --chown=app:app /app/alembic /app/alembic
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=app:app /app/models /app/models

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, os, sys; port = os.environ.get('PORT', '8000'); sys.exit(0 if urllib.request.urlopen(f'http://0.0.0.0:{port}/health',timeout=3).status==200 else 1)" || exit 1
# Render injects PORT (typically 10000). Respect it instead of hardcoding 8000.
CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
