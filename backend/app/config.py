# iCoDer Backend Configuration (Phase 1 cloud-flip 2026-06-27)
import os
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # ── Deployment Mode ───────────────────────────────────────────────────────
    # Phase 1 cloud-flip: iCoDer is a 托管云 SaaS (Corti-style). Default
    # `local` preserves existing single-developer workflow (sqlite + auto-seed).
    # Production deploys use ICODER_DEPLOYMENT_MODE=cloud + populate the
    # ICODER_* cloud-only vars below. See docs/cloud/CLOUD_DEPLOYMENT.md.
    ICODER_DEPLOYMENT_MODE: str = "local"  # local | cloud

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "iCoDer Clinical AI Platform"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "local"  # local | cloud (deprecated: was "production" pre-flip)
    DEBUG: bool = False
    SECRET_KEY: str = ""  # Set via ICODER_SECRET_KEY env var. Generate: python -c "import secrets; print(secrets.token_urlsafe(48))"
    # Default flipped: cloud production must NEVER auto-seed admin/admin123.
    # Local dev override via docker-compose.local-dev.yml or .env file.
    SEED_ON_STARTUP: bool = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.SECRET_KEY:
            import os, secrets as _secrets
            self.SECRET_KEY = os.environ.get("ICODER_SECRET_KEY", _secrets.token_urlsafe(48))

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # Cloud: must list every frontend domain explicitly. Local dev defaults
    # remain permissive (localhost variants).
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── Database ──────────────────────────────────────────────────────────────
    # Local default: sqlite for development. Cloud: managed Postgres (must be
    # supplied via DATABASE_URL env in production deploy).
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/icoder.db"

    # ── Auth ──────────────────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480  # 8 hours (human user sessions — login)
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # ── OAuth client_credentials ────────────────────────────────────────────────
    # Corti parity (2026-06-30, Phase 1.0): machine-to-machine tokens are
    # intentionally SHORT-lived (5 minutes) so a leaked credential has minimal
    # blast radius. See docs/corti-reverse-engineered/SUMMARY.md §13.2.
    # Override via OAUTH_CLIENT_EXPIRE_SECONDS env var.
    OAUTH_CLIENT_EXPIRE_SECONDS: int = 300  # 5 minutes
    # Whether the OAuth token endpoint MUST receive a Tenant-Name (or X-Tenant)
    # header. Local dev keeps this off (single-tenant convenience); cloud mode
    # enforces it (corti auth pattern: header is mandatory on every API call).
    OAUTH_REQUIRE_TENANT_HEADER: bool = False
    # Set of capability scopes recognised as Corti-style limited-scope
    # credentials. Tokens carrying only these scopes are restricted to the
    # corresponding endpoints (see app/api/oauth.py :: _check_scope_intersection).
    OAUTH_CAPABILITY_SCOPES: List[str] = ["transcribe", "streams", "textgen", "facts"]

    # ── LLM Configuration ─────────────────────────────────────────────────────
    LLM_PROVIDER: str = "deepseek"
    # LLM_API_KEY is now resolved from CredentialVault at runtime.
    # Set environment variable ICODER_CREDENTIAL_LLM before starting the server.
    # The hardcoded fallback below is for development only.
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT: int = 120

    # ── LLM Pricing (Phase 4-G #1 — live cost; Phase 5 A2 — currency unified to CNY) ───
    # Per-1M-token prices in CNY (yuan). Used by DeepSeekProvider/OpenAICompatibleProvider
    # to compute `cost_usd` (DB column name kept for backward compat; the value is CNY)
    # from `usage.input_tokens` + `usage.output_tokens`.
    # Defaults reflect DeepSeek V4 flash public pricing (2026-07, RMB). Override via env.
    LLM_PRICE_INPUT_PER_1M: float = 0.14
    LLM_PRICE_OUTPUT_PER_1M: float = 0.28

    # ── Agent Configuration ───────────────────────────────────────────────────
    AGENT_MAX_RETRIES: int = 2
    AGENT_CONFIDENCE_THRESHOLD: float = 0.6
    AGENT_FALLBACK_ENABLED: bool = True

    # ── RunTrace Persistence (Phase 3-D2 Task 1) ──────────────────────────────
    # memory = in-memory store (default, test/dev); db = persistent run_trace_events
    # table. When "db", emit_trace_event writes via a sync engine to work from
    # sync contexts (inbound_handler / _SimpleAgentDispatchHandler are sync).
    # See app/icoder/agent_runtime/orchestrator/run_trace.py.
    RUNTRACE_STORE: str = "memory"  # memory | db

    # ── Data Paths ────────────────────────────────────────────────────────────
    # Local dev uses ./data/ subtree. Cloud loads from region-scoped object
    # storage via ICODER_ASSET_BUCKET (S3-compatible). See docs/cloud/MULTI_REGION.md.
    DATA_DIR: str = str(Path(__file__).parent.parent / "data")
    CODE_DICTS_DIR: str = str(Path(__file__).parent.parent / "data" / "code_dicts")
    RULES_DIR: str = str(Path(__file__).parent.parent / "data" / "rules")
    REPORTS_DIR: str = str(Path(__file__).parent.parent / "data" / "reports")
    ICODER_ASSET_BUCKET: str = ""  # S3-compatible; empty = use local DATA_DIR

    # ── Cloud-Only Required Vars (ICODER_DEPLOYMENT_MODE=cloud) ───────────────
    # Phase 1: defaults empty. Phase 2: model_validator will require these
    # when ICODER_DEPLOYMENT_MODE=cloud. See docs/cloud/CLOUD_DEPLOYMENT.md §1.2.
    ICODER_HOSTED_URL: str = ""           # e.g. https://api.icoder.cloud
    ICODER_ENVIRONMENT: str = ""          # eu | us | cn
    ICODER_REGION: str = ""               # eu-frankfurt | us-virginia | cn-hangzhou | ...
    ICODER_TENANT_ID: str = ""            # issued at tenant provisioning
    ICODER_API_CLIENT_ID: str = ""        # backend-service flow
    ICODER_API_CLIENT_SECRET: str = ""    # backend-service flow

    # ── PHI & Audit ───────────────────────────────────────────────────────────
    # Cloud default is `edge` (强制 PHI 脱敏 before Agent processing). Local
    # dev override via docker-compose.local-dev.yml to `disabled`.
    ICODER_PHI_REDACTION_MODE: str = "edge"   # edge | disabled
    ICODER_AUDIT_SINK: str = "cloud_audit"   # cloud_audit | local

    # ── STT (Speech-to-Text) Configuration ────────────────────────────────────
    # Cloud uses server-side STT service, not bundled Whisper. Local dev can
    # opt into bundled Whisper by setting STT_WHISPER_MODEL explicitly.
    STT_WHISPER_MODEL: str = ""  # tiny | base | small | medium | large (empty = use managed STT)
    STT_DEVICE: str = "auto"  # auto/cuda/cpu
    STT_MEDICAL_TERMS_BOOST: bool = True  # Enable medical terminology enhancement

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 30

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    AUDIT_LOG_RETENTION_DAYS: int = 365

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()


def icoder_corti_capability_scopes() -> List[str]:
    """Backwards-compatible accessor (some tests import the function).

    Lives at module scope (not inside ``Settings``) so that callers reading
    the field at runtime get the current config — useful for tests that
    monkey-patch settings via env vars.
    """
    return list(settings.OAUTH_CAPABILITY_SCOPES or [])