# Windows-optimized backend Dockerfile
FROM python:3.11-slim

# Install system dependencies and uv in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user early
RUN useradd -m -u 1000 appuser

WORKDIR /app
RUN chown appuser:appuser /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency files (Now perfectly synced for CPU)
COPY --chown=appuser:appuser pyproject.toml uv.lock ./

# Switch to non-root user
USER appuser

# Environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

# Install dependencies using the optimized lockfile
RUN uv sync --frozen --no-install-project --no-dev

# Copy source code with correct ownership
COPY --chown=appuser:appuser src ./src

EXPOSE 8000

# Optimized uvicorn command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
