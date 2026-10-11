from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "CivicPulse"
    VERSION: str = "0.1.0"

    # --- PostgreSQL (Aiven / local Docker) ---
    DATABASE_URL: Optional[str] = None
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "civicpulse_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    ASYNC_DATABASE_URI: str = ""

    @field_validator("ASYNC_DATABASE_URI", mode="before")
    @classmethod
    def build_async_uri(cls, v, info):
        if v:
            return v
        base_url = info.data.get("DATABASE_URL")
        user = info.data.get("POSTGRES_USER", "")
        password = info.data.get("POSTGRES_PASSWORD", "")
        host = info.data.get("POSTGRES_HOST", "localhost")
        port = info.data.get("POSTGRES_PORT", 5432)
        db = info.data.get("POSTGRES_DB", "civicpulse_db")

        if base_url:
            base = base_url.replace("postgresql://", "postgresql+asyncpg://")
            q = ""
            if "?" in base:
                base, q = base.split("?", 1)
                params = q.split("&")
                ssl_params = [p for p in params if p.startswith("sslmode=")]
                other_params = [
                    p for p in params if not p.startswith("sslmode=") and not p.startswith("channel_binding=")
                ]
                if ssl_params and "require" in ssl_params[0]:
                    other_params.append("ssl=require")
                q = ("?" + "&".join(other_params)) if other_params else ""
            return f"{base}{q}"
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

    # --- MongoDB (Atlas / local Docker) ---
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "civicpulse_analytics"

    # --- Redis (Upstash / local Docker) ---
    REDIS_URL: str = "redis://localhost:6379"
    UPSTASH_REDIS_REST_URL: Optional[str] = None
    UPSTASH_REDIS_REST_TOKEN: Optional[str] = None

    # --- Rate Limiting ---
    RATE_LIMIT_IP_CAPACITY: int = 60
    RATE_LIMIT_IP_REFILL: float = 1.0
    RATE_LIMIT_USER_CAPACITY: int = 200
    RATE_LIMIT_USER_REFILL: float = 3.33

    # --- JWT ---
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Cookie settings ---
    COOKIE_SECURE: bool = False

    @model_validator(mode="after")
    def validate_secret_key(self):
        if not self.SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set. Generate with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )
        return self

    # --- Observability: 3-layer New Relic via OTLP (Layer 1 -> 2 -> 3) ---
    # The app exports structured logs over OTLP/HTTP to the Layer-2
    # OpenTelemetry collector (docker/otel-collector-config.yaml, compose
    # service ``otel-collector``), which owns NEW_RELIC_LICENSE_KEY and
    # forwards everything to New Relic (Layer 3). The app therefore never
    # holds the vendor credential. ``/metrics`` stays the in-process metric
    # source of truth (the collector scrapes it). No-op when disabled, the
    # endpoint is unset, or the ``[observability]`` extras are not installed.
    NEW_RELIC_ENABLED: bool = False
    NEW_RELIC_OTLP_ENDPOINT: str = "http://localhost:4318"
    NEW_RELIC_EXPORT_INTERVAL_SECONDS: int = 30
    NEW_RELIC_APP_NAME: str = "CivicPulse-API"
    # Bearer token the Layer-2 collector must present to scrape /metrics.
    # Unset (None/"") leaves /metrics open (local dev, tests).
    METRICS_TOKEN: Optional[str] = None

    # --- OAuth (Google / GitHub) ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    # Base URL the browser can reach this backend at (used to build OAuth redirect URIs).
    # e.g. http://localhost:8000 in dev. In production behind the Next.js proxy this is the
    # public API origin.
    BACKEND_URL: str = "http://localhost:8000"

    # --- SMTP (outbound email) ---
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = "CivicPulse <no-reply@civicpulse.local>"
    ALERT_EMAIL_TO: str = ""

    # --- Password reset ---
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 60
    PASSWORD_RESET_EMAIL_SUBJECT: str = "CivicPulse password reset"

    # --- Frontend ---
    FRONTEND_URL: str = "http://localhost:3000"

    # --- CORS ---
    CORS_ORIGINS: str = ""

    # --- ML Model ---
    MODEL_PATH: str = "models/model.pth"
    DRIFT_WINDOW_SIZE: int = 10
    DRIFT_ALERT_THRESHOLD: float = 0.05

    # --- A/B Testing ---
    AB_TEST_ENABLED: bool = False
    AB_TEST_MODE: str = "shadow"  # "shadow" or "traffic_split"
    AB_TEST_TRAFFIC_PCT: float = 0.1  # 10% to challenger

    # --- DagsHub / MLflow ---
    DAGSHUB_USERNAME: str = ""
    DAGSHUB_REPO: str = "ai-civic-issue-monitoring"
    MLFLOW_TRACKING_URI: str = ""
    MLFLOW_TRACKING_USERNAME: Optional[str] = None
    MLFLOW_TRACKING_PASSWORD: Optional[str] = None

    # --- LLM Provider (OpenAI / Groq) ---
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "llama-3.1-8b-instant"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMS: int = 1536
    # Outbound LLM resilience: a shared client with a hard per-request timeout
    # and bounded retries, so one slow OpenAI call cannot pin a worker forever.
    OPENAI_TIMEOUT_SECONDS: float = 30.0
    OPENAI_MAX_RETRIES: int = 2

    # --- Prometheus /metrics (RED); additive to New Relic, not a replacement ---
    ENABLE_PROMETHEUS: bool = True

    # --- HuggingFace (embeddings) ---
    HF_TOKEN: Optional[str] = None

    # --- RAG ---
    RAG_SIMILARITY_THRESHOLD: float = 0.75
    RAG_TOP_K: int = 5
    # Opt-in hybrid retrieval: fuse the dense vector ranking with BM25 lexical
    # ranking via Reciprocal Rank Fusion. Off by default so retrieval behaviour
    # is unchanged until `scripts/evaluate_ml.py --retrieval` shows it helps.
    RETRIEVAL_HYBRID: bool = False

    # --- Intake Gate ---
    REJECT_THRESHOLD: float = 0.85  # vision non_civic prob above this → hard reject
    REVIEW_THRESHOLD: float = 0.60  # vision confidence below this → accept with review

    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
