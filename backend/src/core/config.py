from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The backend's own env file, resolved relative to *this package* rather than the
# current working directory. The previous ``env_file=".env"`` silently loaded a
# different file depending on where the app was started from (repo root vs
# ``backend/``), so a config that worked via ``pixi run dev`` could vanish under a
# bare ``uvicorn``/pytest invocation and vice-versa. Anchoring to ``backend/.env``
# makes the source of truth deterministic. Real environment variables still take
# precedence (pydantic-settings resolves OS env before the dotenv file), so CI,
# Docker (compose injects vars) and the test suite are unaffected.
_BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# Placeholder / demo SECRET_KEY values that have appeared in example files,
# compose defaults, CI, or git history. They are trivially guessable —
# accepting any of them would let an attacker forge JWTs — so they are
# rejected in every environment, not just production.
WEAK_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "changeme",
        "civicpulse-prod-secret-key-change-me",
        "civicpulse-dev-secret-key-change-in-production",
        "dev-only-insecure-secret-change-me",
        "change-me-to-a-random-secret-key",
        "change-me-to-a-long-random-value",
        "change-me-generate-with-python-secrets-token-urlsafe-64",
        "test-secret-key-for-ci-only",
    }
)
SECRET_KEY_MIN_LENGTH: int = 32


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

    @field_validator("SECRET_KEY", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "SECRET_KEY must be set. Generate with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )
        if v in WEAK_SECRET_KEYS:
            raise ValueError(
                "SECRET_KEY is a known placeholder value and is trivially guessable. "
                "Generate a real key with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )
        if len(v) < SECRET_KEY_MIN_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {SECRET_KEY_MIN_LENGTH} characters to resist brute force. "
                "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )
        return v

    # --- Cookie settings ---
    COOKIE_SECURE: bool = False

    # --- Observability: 3-layer OTLP (Layer 1 -> 2 -> 3) ---
    # The app exports structured logs, spans AND metrics over OTLP/HTTP to the
    # Layer-2 OpenTelemetry collector (docker/otel-collector-config.yaml, compose
    # service ``otel-collector``), which owns NEW_RELIC_LICENSE_KEY and fans the
    # three signals out to New Relic (Layer 3, the sink). The app therefore never
    # holds the vendor credential, and every signal travels the same
    # vendor-neutral OTLP path -- swapping or adding a sink is a collector-config
    # change, not an app change. No-op when disabled, the endpoint is unset, or
    # the ``[observability]`` extras are not installed.
    NEW_RELIC_ENABLED: bool = False
    NEW_RELIC_OTLP_ENDPOINT: str = "http://localhost:4318"
    NEW_RELIC_EXPORT_INTERVAL_SECONDS: int = 30
    NEW_RELIC_APP_NAME: str = "CivicPulse-API"
    # HTTP basic auth for the collector's OTLP receiver. The receiver is a
    # public endpoint on a shared host, so when it is basicauth-gated the app
    # must send the matching pair or its telemetry is silently rejected.
    # Empty (the default) means "send no Authorization header" -- correct when
    # the collector runs unauthenticated on a network-isolated host. A pair is
    # used only when BOTH values are set: one without the other is treated as a
    # half-finished configuration and ignored rather than sent as a broken
    # credential. The collector reads the same names (docker-compose env).
    OTLP_AUTH_USER: str = ""
    OTLP_AUTH_PASSWORD: str = ""
    # Extra headers sent on every OTLP request, as a JSON object in the env. A
    # raw escape hatch for anything the derived Basic header does not cover
    # (e.g. a bearer token); when a key collides, this wins. Empty by default.
    NEW_RELIC_OTLP_HEADERS: dict[str, str] = {}

    # --- Error tracking (Sentry, opt-in) ---
    # Set SENTRY_DSN to group and alert on unhandled exceptions -- without it a
    # 500 is only a log line nobody reads. A strict no-op when unset, and
    # fail-open when sentry-sdk is absent (it ships in the optional
    # ``[observability]`` extra). Traces stay on the OTLP path, so Sentry's
    # performance sampling defaults to 0: this hook exists for *errors*, not a
    # second trace pipeline. Personal data is never attached (see setup_sentry).
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

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
    # NOTE: embeddings are produced by the HuggingFace Inference API with a fixed
    # model (see src/core/embeddings.py: ``sentence-transformers/all-MiniLM-L6-v2``,
    # 384-dim). There is deliberately no EMBEDDING_MODEL/EMBEDDING_DIMS setting:
    # the old, unused fields implied a configurable OpenAI embedding model the
    # code never read and a dimension (1536) that did not match the actual vectors.
    # Outbound LLM resilience: a shared client with a hard per-request timeout
    # and bounded retries, so one slow OpenAI call cannot pin a worker forever.
    OPENAI_TIMEOUT_SECONDS: float = 30.0
    OPENAI_MAX_RETRIES: int = 2

    # --- HuggingFace (embeddings) ---
    HF_TOKEN: Optional[str] = None

    # --- RAG ---
    RAG_SIMILARITY_THRESHOLD: float = 0.75
    RAG_TOP_K: int = 5
    # How many retrieved issues `build_rag_context` renders into the LLM prompt.
    RAG_MAX_CONTEXT_ISSUES: int = 5
    # Opt-in weighted re-ranking: order the candidates that already pass the
    # similarity threshold by a blend of vector similarity, recency, severity and
    # resolution status instead of raw cosine. Off by default so retrieval
    # behaviour is unchanged until `scripts/evaluate_ml.py --retrieval --weighted`
    # shows it helps. Weights are normalized by their sum at use, so they need not
    # add up to exactly 1.0 (a single non-zero weight is fine).
    RAG_WEIGHTED_RERANK: bool = False
    RAG_SIMILARITY_WEIGHT: float = 0.3
    RAG_RECENCY_WEIGHT: float = 0.2
    RAG_SEVERITY_WEIGHT: float = 0.25
    RAG_RESOLUTION_WEIGHT: float = 0.25
    # Recency half-life for the weighted re-ranker: a 30-day-old issue scores
    # half as high on the recency component as a brand-new one.
    RAG_RECENCY_HALF_LIFE_DAYS: float = 30.0
    # Opt-in: build retrieval context for an incoming report and feed it to the
    # LLM classifier, and consult that LLM (with the context) when the intake gate
    # is unsure (preclassified confidence below RAG_CLASSIFY_MIN_CONFIDENCE). Off
    # by default so classification is byte-for-byte unchanged unless enabled.
    RAG_CLASSIFY_ENABLED: bool = False
    RAG_CLASSIFY_MIN_CONFIDENCE: float = 0.60
    # Opt-in hybrid retrieval: fuse the dense vector ranking with BM25 lexical
    # ranking via Reciprocal Rank Fusion. Off by default so retrieval behaviour
    # is unchanged until `scripts/evaluate_ml.py --retrieval` shows it helps.
    RETRIEVAL_HYBRID: bool = False

    # --- Intake Gate ---
    REJECT_THRESHOLD: float = 0.85  # vision non_civic prob above this → hard reject
    REVIEW_THRESHOLD: float = 0.60  # vision confidence below this → accept with review

    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
