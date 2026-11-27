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

# Algorithms accepted for signing/verifying JWTs. The secret is a shared
# HMAC key, so only the HS family is ever correct here. Anything else
# (especially `none`) would turn every token check into a rubber stamp.
ALLOWED_JWT_ALGORITHMS: frozenset[str] = frozenset({"HS256", "HS384", "HS512"})


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

    # Auth-specific budgets (attempts per minute). These sit *on top of* the
    # generic buckets above and are deliberately tight: password guessing and
    # credential stuffing need far less headroom than normal API traffic.
    AUTH_LOGIN_RATE_LIMIT_IP: int = 10
    AUTH_LOGIN_RATE_LIMIT_ACCOUNT: int = 5
    AUTH_REFRESH_RATE_LIMIT_IP: int = 30
    AUTH_REFRESH_RATE_LIMIT_ACCOUNT: int = 20
    AUTH_FORGOT_RATE_LIMIT_IP: int = 5
    AUTH_FORGOT_RATE_LIMIT_ACCOUNT: int = 3

    # --- JWT ---
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # A refresh token may be presented once more within this window after it has
    # been rotated. That tolerates two browser tabs racing to refresh without
    # turning a harmless race into a full logout; beyond it the reuse is treated
    # as theft and the token family is revoked (see AuthService.refresh).
    REFRESH_REUSE_GRACE_SECONDS: int = 30
    REFRESH_REVOKE_ON_REUSE: bool = True
    # `iss`/`aud` are pinned into every token this service mints and verified on
    # decode. A shared HS256 key is symmetric, so the signature alone cannot say
    # *which* service issued a token: a token minted by any other system sharing
    # this key (a sibling deployment, a re-used secret) would verify here. These
    # claims scope a token to this issuer and this audience, and the defaults
    # match the project name so an unconfigured deployment still gets them.
    JWT_ISSUER: str = "civicpulse-api"
    JWT_AUDIENCE: str = "civicpulse-web"

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

    @field_validator("ALGORITHM", mode="after")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        # `decode_token` passes this straight into `algorithms=[...]`, so an
        # env var that reaches `none` (or an asymmetric name python-jose will
        # happily ignore the key for) would turn every token check into a
        # rubber stamp. The secret is a shared HMAC key, so only the HS
        # family can ever be correct here — reject anything else at startup
        # rather than discovering it in production.
        if v not in ALLOWED_JWT_ALGORITHMS:
            raise ValueError(f"ALGORITHM must be one of {', '.join(sorted(ALLOWED_JWT_ALGORITHMS))}; got '{v}'.")
        return v

    # --- Cookie settings ---
    COOKIE_SECURE: bool = False

    # --- Observability: OTLP logs, metrics and traces ---
    # The app exports all three signals over OTLP/HTTP to a Layer-2 collector.
    # Local Compose uses the container in docker/otel-collector-config.yaml;
    # production uses the same config in a dedicated free Render service whose
    # URL is supplied here. The vendor key stays on the collector, never in the
    # app or browser. Transport is vendor-neutral OTLP and export is fail-open:
    # no-op when disabled, the endpoint is unset, or extras are not installed.
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
    # (e.g. a bearer token); when a key collides, this wins. Production leaves
    # this empty: the collector holds the New Relic key. Empty by default.
    NEW_RELIC_OTLP_HEADERS: dict[str, str] = {}

    # --- OAuth (Google / GitHub) ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
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

    # --- Email verification ---
    # Off by default so existing deployments/users are not locked out on upgrade.
    # When enabled, newly registered accounts must verify before login succeeds.
    EMAIL_VERIFICATION_REQUIRED: bool = False
    EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES: int = 60
    EMAIL_VERIFY_EMAIL_SUBJECT: str = "Verify your CivicPulse account"

    # --- Audit / compliance ---
    # Durable audit documents older than this are archived (not deleted) by the
    # monthly Prefect flow so the hot collection stays bounded while evidence is
    # retained. Exposed in the compliance report rather than hardcoded there.
    AUDIT_LOG_RETENTION_DAYS: int = 90
    # Short-lived one-time code used by the OAuth callback -> frontend handoff.
    OAUTH_HANDOFF_TTL_SECONDS: int = 120

    # --- Encryption / TOTP ---
    # Used to encrypt sensitive values at rest (e.g. TOTP secrets). If left
    # unset, a stable key is derived from SECRET_KEY so existing deployments do
    # not need an extra env var; set explicitly in production for key separation.
    ENCRYPTION_KEY: str = ""
    TOTP_VALID_WINDOW: int = 1

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

    # --- Object storage (Neon Object Storage / S3-compatible) ---
    # "local" keeps bytes on the container filesystem (dev / single instance).
    # "s3" writes to NEON_STORAGE_BUCKET at AWS_ENDPOINT_URL_S3. Stored image
    # URLs keep their /uploads/... form in both modes so existing rows and the
    # frontend media helper do not need to change.
    STORAGE_BACKEND: str = "local"
    AWS_ENDPOINT_URL_S3: Optional[str] = None
    AWS_REGION: str = "us-east-2"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    NEON_STORAGE_BUCKET: str = "uploads"

    @field_validator("STORAGE_BACKEND")
    @classmethod
    def validate_storage_backend(cls, value: str) -> str:
        if value not in {"local", "s3"}:
            raise ValueError("STORAGE_BACKEND must be either 'local' or 's3'")
        return value

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

    # Trusted proxies for resolving client IP
    TRUSTED_PROXIES: list[str] = []


settings = Settings()
