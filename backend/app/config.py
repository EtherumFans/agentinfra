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
    JWT_EXPIRE_MINUTES: int = 480  # 8 hours
    JWT_REFRESH_EXPIRE_DAYS: int = 7

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

    # ── Agent Configuration ───────────────────────────────────────────────────
    AGENT_MAX_RETRIES: int = 2
    AGENT_CONFIDENCE_THRESHOLD: float = 0.6
    AGENT_FALLBACK_ENABLED: bool = True

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