# iCoDer Backend Configuration
import os
from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "iCoDer Clinical AI Platform"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "production"
    DEBUG: bool = False
    SECRET_KEY: str = ""  # Set via ICODER_SECRET_KEY env var. Generate: python -c "import secrets; print(secrets.token_urlsafe(48))"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.SECRET_KEY:
            import os, secrets as _secrets
            self.SECRET_KEY = os.environ.get("ICODER_SECRET_KEY", _secrets.token_urlsafe(48))

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/icoder.db"

    # Auth
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480  # 8 hours
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # LLM Configuration
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

    # Agent Configuration
    AGENT_MAX_RETRIES: int = 2
    AGENT_CONFIDENCE_THRESHOLD: float = 0.6
    AGENT_FALLBACK_ENABLED: bool = True

    # Data Paths
    DATA_DIR: str = str(Path(__file__).parent.parent / "data")
    CODE_DICTS_DIR: str = str(Path(__file__).parent.parent / "data" / "code_dicts")
    RULES_DIR: str = str(Path(__file__).parent.parent / "data" / "rules")
    REPORTS_DIR: str = str(Path(__file__).parent.parent / "data" / "reports")

    # STT (Speech-to-Text) Configuration
    STT_WHISPER_MODEL: str = "medium"  # tiny/base/small/medium/large
    STT_DEVICE: str = "auto"  # auto/cuda/cpu
    STT_MEDICAL_TERMS_BOOST: bool = True  # Enable medical terminology enhancement

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 30

    # Logging
    LOG_LEVEL: str = "INFO"
    AUDIT_LOG_RETENTION_DAYS: int = 365

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
