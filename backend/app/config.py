# iCoDer Backend Configuration (Phase 1 cloud-flip 2026-06-27)
import os
import ipaddress
import re
from pathlib import Path
from typing import ClassVar, Optional, List
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict

# A1A Gate 1 Step 4 — known-weak SECRET_KEY literals that must NEVER boot
# in cloud mode. Matched case-insensitively after strip(). Kept at module
# level so it is accessible without pydantic's private-attr handling.
_WEAK_SECRET_KEY_LITERALS: frozenset[str] = frozenset({
    "", "change-me", "change-me-in-production", "changeme",
    "secret", "test", "dev", "development",
})


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
    # SQL statements are diagnostically useful, but bound parameters may hold
    # complete clinical notes.  Keep statement echo independent from DEBUG and
    # opt-in even for local development; database.py always hides parameters.
    ICODER_DATABASE_SQL_ECHO: bool = False
    SECRET_KEY: str = ""  # Set via ICODER_SECRET_KEY env var. Generate: python -c "import secrets; print(secrets.token_urlsafe(48))"
    # Default flipped: cloud production must NEVER auto-seed admin/admin123.
    # Local dev override via docker-compose.local-dev.yml or .env file.
    SEED_ON_STARTUP: bool = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # A1A Gate 1 Step 4 — env var takes precedence over .env file value
        # so cloud KMS injection (ICODER_SECRET_KEY env) always wins.
        env_sk = os.environ.get("ICODER_SECRET_KEY")
        # An explicitly empty cloud injection must override any local .env
        # value and fail closed; treating it as "unset" can accidentally boot
        # production with a developer secret.
        if env_sk is not None:
            self.SECRET_KEY = env_sk
        if not self.SECRET_KEY and self.ICODER_DEPLOYMENT_MODE != "cloud":
            import secrets as _secrets
            self.SECRET_KEY = _secrets.token_urlsafe(48)
        # A1A Gate 1 Step 4 — fail-closed env policy (2026-07-17).
        # Cloud mode MUST refuse to boot if any required secret is missing or
        # carries a known-weak default. Local mode auto-generates a random
        # SECRET_KEY (preserves single-developer workflow).
        self._validate_fail_closed_policy()

    def _validate_fail_closed_policy(self) -> None:
        """Refuse to boot if cloud mode + weak/missing required secrets.

        Raises RuntimeError at startup so uvicorn exits non-zero before
        binding the socket. Local mode is permissive.
        """
        if self.ICODER_DEPLOYMENT_MODE != "cloud":
            return
        failures: list[str] = []
        sk = (self.SECRET_KEY or "").strip()
        if sk.lower() in _WEAK_SECRET_KEY_LITERALS:
            failures.append(
                "SECRET_KEY is empty or a known-weak literal "
                f"({sk!r}); set ICODER_SECRET_KEY env var to a strong value "
                "(generate: python -c \"import secrets; print(secrets.token_urlsafe(48))\")"
            )
        if not self.ICODER_HOSTED_URL:
            failures.append("ICODER_HOSTED_URL is empty; required in cloud mode")
        elif not self.ICODER_HOSTED_URL.lower().startswith("https://"):
            failures.append("ICODER_HOSTED_URL must use https:// in cloud mode")
        if self.ICODER_ENVIRONMENT not in {"eu", "us", "cn"}:
            failures.append(
                f"ICODER_ENVIRONMENT={self.ICODER_ENVIRONMENT!r}; must be one of eu/us/cn"
            )
        if not self.ICODER_REGION:
            failures.append("ICODER_REGION is empty; required in cloud mode")
        elif not self.ICODER_REGION.startswith(f"{self.ICODER_ENVIRONMENT}-"):
            failures.append(
                f"ICODER_REGION={self.ICODER_REGION!r} does not belong to "
                f"ICODER_ENVIRONMENT={self.ICODER_ENVIRONMENT!r}"
            )
        if not self.ICODER_TENANT_ID:
            failures.append("ICODER_TENANT_ID is empty; required in cloud mode")
        if not self.ICODER_API_CLIENT_ID:
            failures.append("ICODER_API_CLIENT_ID is empty; required in cloud mode")
        if not self.ICODER_API_CLIENT_SECRET:
            failures.append("ICODER_API_CLIENT_SECRET is empty; required in cloud mode")
        metrics_token = (self.ICODER_METRICS_BEARER_TOKEN or "").strip()
        if not 32 <= len(metrics_token) <= 512:
            failures.append(
                "ICODER_METRICS_BEARER_TOKEN must contain 32 to 512 "
                "characters in cloud mode"
            )
        if self.SEED_ON_STARTUP:
            failures.append(
                "SEED_ON_STARTUP=true is forbidden in cloud mode "
                "(would auto-create admin/admin123)"
            )
        if self.DEBUG:
            failures.append("DEBUG=true is forbidden in cloud mode")
        if self.ICODER_DATABASE_SQL_ECHO:
            failures.append(
                "ICODER_DATABASE_SQL_ECHO=true is forbidden in cloud mode"
            )
        if self.APP_ENV != "cloud":
            failures.append("APP_ENV=cloud is required when ICODER_DEPLOYMENT_MODE=cloud")
        if self.ICODER_STREAM_MEDIA_VALIDATION_MODE != "decoder":
            failures.append(
                "ICODER_STREAM_MEDIA_VALIDATION_MODE=decoder is required in cloud mode"
            )
        decoder_path = (self.ICODER_STREAM_MEDIA_DECODER_PATH or "").strip()
        if (
            not decoder_path
            or len(decoder_path) > 512
            or any(character in decoder_path for character in ("\x00", "\r", "\n"))
        ):
            failures.append(
                "ICODER_STREAM_MEDIA_DECODER_PATH must identify the isolated "
                "decoder executable in cloud mode"
            )
        if not 0.25 <= self.ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS <= 10:
            failures.append(
                "ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS must be between "
                "0.25 and 10 in cloud mode"
            )
        if not 1 <= self.ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY <= 16:
            failures.append(
                "ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY must be between "
                "1 and 16 in cloud mode"
            )
        if not 0.05 <= self.ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS <= 5:
            failures.append(
                "ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS must be "
                "between 0.05 and 5 in cloud mode"
            )
        for setting_name, executable_path in (
            (
                "ICODER_TRANSCRIPTS_MEDIA_DECODER_PATH",
                self.ICODER_TRANSCRIPTS_MEDIA_DECODER_PATH,
            ),
            (
                "ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH",
                self.ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH,
            ),
        ):
            normalized_path = (executable_path or "").strip()
            if (
                not normalized_path
                or len(normalized_path) > 512
                or any(
                    character in normalized_path
                    for character in ("\x00", "\r", "\n")
                )
            ):
                failures.append(
                    f"{setting_name} must identify an isolated media executable "
                    "in cloud mode"
                )
        if not 5 <= self.ICODER_TRANSCRIPTS_MEDIA_DECODER_TIMEOUT_SECONDS <= 600:
            failures.append(
                "ICODER_TRANSCRIPTS_MEDIA_DECODER_TIMEOUT_SECONDS must be between "
                "5 and 600 in cloud mode"
            )
        if not 1 <= self.ICODER_TRANSCRIPTS_MEDIA_PROBE_TIMEOUT_SECONDS <= 60:
            failures.append(
                "ICODER_TRANSCRIPTS_MEDIA_PROBE_TIMEOUT_SECONDS must be between "
                "1 and 60 in cloud mode"
            )
        if not 1 <= self.ICODER_TRANSCRIPTS_MEDIA_DECODER_MAX_CONCURRENCY <= 8:
            failures.append(
                "ICODER_TRANSCRIPTS_MEDIA_DECODER_MAX_CONCURRENCY must be between "
                "1 and 8 in cloud mode"
            )
        if not 0.05 <= self.ICODER_TRANSCRIPTS_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS <= 10:
            failures.append(
                "ICODER_TRANSCRIPTS_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS must be "
                "between 0.05 and 10 in cloud mode"
            )
        if not 1 <= self.ICODER_TRANSCRIPTS_MAX_DURATION_SECONDS <= 7200:
            failures.append(
                "ICODER_TRANSCRIPTS_MAX_DURATION_SECONDS must be between 1 and "
                "7200 in cloud mode"
            )
        if not self.DATABASE_URL.lower().startswith(("postgresql://", "postgresql+")):
            failures.append(
                "DATABASE_URL must use managed PostgreSQL in cloud mode; "
                "SQLite/local files are forbidden"
            )
        cors_origins = [str(origin).strip().lower() for origin in self.CORS_ORIGINS]
        if not cors_origins or any(
            not origin.startswith("https://")
            or "localhost" in origin
            or "127.0.0.1" in origin
            for origin in cors_origins
        ):
            failures.append(
                "CORS_ORIGINS must be a non-empty HTTPS-only allowlist without "
                "localhost/127.0.0.1 in cloud mode"
            )
        if self.ICODER_PHI_REDACTION_MODE != "edge":
            failures.append("ICODER_PHI_REDACTION_MODE=edge is required in cloud mode")
        connector_hosts = {
            item.strip().rstrip(".").casefold()
            for item in os.environ.get(
                "ICODER_CONNECTOR_EGRESS_ALLOWLIST", ""
            ).split(",")
            if item.strip()
        }
        connector_phi_hosts = {
            item.strip().rstrip(".").casefold()
            for item in os.environ.get(
                "ICODER_CONNECTOR_PHI_EGRESS_ALLOWLIST", ""
            ).split(",")
            if item.strip()
        }
        connector_phi_enabled = os.environ.get(
            "ICODER_CONNECTOR_ALLOW_PHI", "0"
        ).strip().casefold() in {"1", "true", "yes"}
        invalid_connector_hosts = {
            host for host in connector_hosts | connector_phi_hosts
            if (
                "*" in host
                or "://" in host
                or "/" in host
                or not re.fullmatch(
                    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
                    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                    host,
                )
            )
        }
        if invalid_connector_hosts:
            failures.append(
                "ICODER_CONNECTOR_*_EGRESS_ALLOWLIST entries must be exact "
                "ASCII hostnames without schemes, paths, ports, or wildcards"
            )
        if connector_phi_enabled and not connector_phi_hosts:
            failures.append(
                "ICODER_CONNECTOR_ALLOW_PHI=true requires a non-empty "
                "ICODER_CONNECTOR_PHI_EGRESS_ALLOWLIST"
            )
        if not connector_phi_hosts.issubset(connector_hosts):
            failures.append(
                "ICODER_CONNECTOR_PHI_EGRESS_ALLOWLIST must be a subset of "
                "ICODER_CONNECTOR_EGRESS_ALLOWLIST"
            )
        ncbi_contact = (self.ICODER_NCBI_CONTACT_EMAIL or "").strip()
        if ncbi_contact and (
            len(ncbi_contact) > 254
            or re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", ncbi_contact) is None
        ):
            failures.append(
                "ICODER_NCBI_CONTACT_EMAIL must be a valid operational email "
                "address when configured"
            )
        if self.ICODER_AUDIT_SINK != "cloud_audit":
            failures.append("ICODER_AUDIT_SINK=cloud_audit is required in cloud mode")
        if (self.ICODER_SINGLE_TENANT_ORG_ID or "").strip():
            failures.append(
                "ICODER_SINGLE_TENANT_ORG_ID must be empty in cloud mode; "
                "tenant identity must come from the authenticated request"
            )
        if not (self.ICODER_ASSET_BUCKET or "").strip():
            failures.append("ICODER_ASSET_BUCKET is empty; region-scoped assets are required")
        if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
            failures.append("ICODER_CREDENTIAL_LLM is empty; KMS credential ingress is required")
        if (self.LLM_PROVIDER or "").strip().lower() == "mock":
            failures.append("LLM_PROVIDER=mock is forbidden in cloud mode")
        retriever_url = (self.MEDCODER_RETRIEVER_URL or "").strip()
        retriever_token = os.environ.get("MEDCODER_RETRIEVER_TOKEN", "").strip()
        if not retriever_url:
            failures.append(
                "MEDCODER_RETRIEVER_URL is empty; isolated semantic retrieval "
                "is required in cloud mode"
            )
        else:
            parsed_retriever = urlparse(retriever_url)
            if (
                parsed_retriever.scheme != "https"
                or not parsed_retriever.netloc
                or parsed_retriever.username
                or parsed_retriever.password
                or parsed_retriever.query
                or parsed_retriever.fragment
            ):
                failures.append(
                    "MEDCODER_RETRIEVER_URL must be an absolute HTTPS URL "
                    "without credentials, query, or fragment in cloud mode"
                )
        if not 32 <= len(retriever_token) <= 512:
            failures.append(
                "MEDCODER_RETRIEVER_TOKEN must contain 32 to 512 characters "
                "in cloud mode"
            )
        if self.MEDCODER_RETRIEVER_ALLOW_HTTP:
            failures.append(
                "MEDCODER_RETRIEVER_ALLOW_HTTP=true is forbidden in cloud mode"
            )
        if not 0.1 <= self.MEDCODER_RETRIEVER_TIMEOUT_SECONDS <= 120.0:
            failures.append(
                "MEDCODER_RETRIEVER_TIMEOUT_SECONDS must be between 0.1 and 120"
            )
        memory_semantic_url = (self.ICODER_MEMORY_SEMANTIC_URL or "").strip()
        memory_semantic_token = os.environ.get(
            "ICODER_CREDENTIAL_MEMORY_SEMANTIC", ""
        ).strip()
        if not self.ICODER_MEMORY_SEMANTIC_REQUIRED:
            failures.append(
                "ICODER_MEMORY_SEMANTIC_REQUIRED=true is required in cloud mode"
            )
        if not memory_semantic_url:
            failures.append(
                "ICODER_MEMORY_SEMANTIC_URL is empty; governed semantic Memory "
                "retrieval is required in cloud mode"
            )
        else:
            parsed_memory_semantic = urlparse(memory_semantic_url)
            try:
                memory_semantic_port = parsed_memory_semantic.port
            except ValueError:
                memory_semantic_port = -1
            memory_semantic_host = (
                parsed_memory_semantic.hostname or ""
            ).rstrip(".").casefold()
            if (
                parsed_memory_semantic.scheme != "https"
                or not parsed_memory_semantic.netloc
                or parsed_memory_semantic.username
                or parsed_memory_semantic.password
                or parsed_memory_semantic.query
                or parsed_memory_semantic.fragment
                or memory_semantic_port not in (None, 443)
            ):
                failures.append(
                    "ICODER_MEMORY_SEMANTIC_URL must be an absolute HTTPS URL "
                    "on port 443 without credentials, query, or fragment in cloud mode"
                )
            elif memory_semantic_host not in connector_hosts:
                failures.append(
                    "ICODER_MEMORY_SEMANTIC_URL host must be present in "
                    "ICODER_CONNECTOR_EGRESS_ALLOWLIST in cloud mode"
                )
        if not 32 <= len(memory_semantic_token) <= 512:
            failures.append(
                "ICODER_CREDENTIAL_MEMORY_SEMANTIC must contain 32 to 512 "
                "characters in cloud mode"
            )
        if not self.OAUTH_REQUIRE_TENANT_HEADER:
            failures.append("OAUTH_REQUIRE_TENANT_HEADER=true is required in cloud mode")
        # Phase A1A Gate 4.4 — cloud mode requires at-rest PHI encryption.
        # Without it, a stolen DB file (backup mishandling, snapshot leak,
        # dev-laptop theft) yields all PHI columns in plaintext.
        from app.services.phi_encryption import is_encryption_enabled
        if not is_encryption_enabled():
            failures.append(
                "ICODER_PHI_ENCRYPTION_KEY is empty; required in cloud mode "
                "(generate: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\")"
            )
        if self.ICODER_INVITE_DELIVERY_MODE != "webhook":
            failures.append(
                "ICODER_INVITE_DELIVERY_MODE=webhook is required in cloud mode; "
                "manual invitation credentials are forbidden"
            )
        invite_url = urlparse(self.ICODER_INVITE_WEBHOOK_URL or "")
        invite_host = (invite_url.hostname or "").casefold()
        if (
            invite_url.scheme != "https"
            or not invite_url.netloc
            or invite_url.username
            or invite_url.password
            or invite_url.query
            or invite_url.fragment
            or invite_host in {"localhost", "localhost.localdomain"}
        ):
            failures.append(
                "ICODER_INVITE_WEBHOOK_URL must be an absolute HTTPS URL "
                "without credentials, query, fragment, or localhost in cloud mode"
            )
        elif invite_host:
            try:
                invite_ip = ipaddress.ip_address(invite_host)
            except ValueError:
                invite_ip = None
            if invite_ip is not None and (
                invite_ip.is_private
                or invite_ip.is_loopback
                or invite_ip.is_link_local
                or invite_ip.is_reserved
                or invite_ip.is_multicast
            ):
                failures.append(
                    "ICODER_INVITE_WEBHOOK_URL cannot target a private or reserved IP"
                )
        if not 32 <= len(self.ICODER_INVITE_WEBHOOK_BEARER_TOKEN.strip()) <= 512:
            failures.append(
                "ICODER_INVITE_WEBHOOK_BEARER_TOKEN must contain 32 to 512 "
                "characters in cloud mode"
            )
        invite_domains = [domain.strip().casefold() for domain in self.ICODER_INVITE_ALLOWED_EMAIL_DOMAINS]
        if not invite_domains or any(
            not re.fullmatch(
                r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
                r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                domain,
            )
            for domain in invite_domains
        ):
            failures.append(
                "ICODER_INVITE_ALLOWED_EMAIL_DOMAINS must be a non-empty "
                "exact-domain allowlist in cloud mode"
            )
        if not 1 <= self.ICODER_INVITE_MAX_ATTEMPTS <= 20:
            failures.append("ICODER_INVITE_MAX_ATTEMPTS must be between 1 and 20")
        if not 1 <= self.ICODER_INVITE_RETRY_BASE_SECONDS <= 3600:
            failures.append("ICODER_INVITE_RETRY_BASE_SECONDS must be between 1 and 3600")
        if not 10 <= self.ICODER_INVITE_CLAIM_TIMEOUT_SECONDS <= 3600:
            failures.append("ICODER_INVITE_CLAIM_TIMEOUT_SECONDS must be between 10 and 3600")
        if not 0.1 <= self.ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS <= 60.0:
            failures.append("ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS must be between 0.1 and 60")
        # Phase A1A Gate 4.3 escape hatch must NOT be set in cloud mode.
        if os.environ.get("ICODER_PHI_REDACTION_BYPASS", "0") in ("1", "true", "True"):
            failures.append(
                "ICODER_PHI_REDACTION_BYPASS is set; forbidden in cloud mode "
                "(would disable fail-closed PHI redaction)"
            )
        # Phase A1A Gate 3.3 §3 — trace persistence must be DB-backed in
        # cloud mode. Memory store loses all events on process restart,
        # which violates the "trace survives the run" guarantee the
        # Console RunTrace page relies on for audit.
        #
        # Phase A1A Gate 3R.3 — verify via the deployment profile. The
        # profile is resolved by app.services.deployment_profile and
        # MUST be one of {BEST_EFFORT_DB, REQUIRED_DB} in cloud mode.
        # MEMORY_DEV is refused because it routes through the in-memory
        # store.
        try:
            from app.services.deployment_profile import (
                DeploymentProfile,
                resolve_profile,
            )
            profile = resolve_profile(
                deployment_mode=self.ICODER_DEPLOYMENT_MODE,
                runtrace_store=self.RUNTRACE_STORE,
                runtrace_fail_closed=self.RUNTRACE_FAIL_CLOSED,
                explicit_profile=self.RUNTRACE_DEPLOYMENT_PROFILE or None,
            )
            self._resolved_runtrace_profile = profile
            if not DeploymentProfile.is_cloud_allowed(profile):
                failures.append(
                    f"RUNTRACE_DEPLOYMENT_PROFILE resolved to {profile!r}; "
                    "cloud mode requires BEST_EFFORT_DB or REQUIRED_DB "
                    "(memory store loses trace events on restart)"
                )
        except ValueError as ve:
            failures.append(
                f"RUNTRACE_DEPLOYMENT_PROFILE invalid: {ve}"
            )
        if self.ICODER_RUN_HISTORY_TTL_DAYS <= 0:
            failures.append(
                "ICODER_RUN_HISTORY_TTL_DAYS must be a positive integer"
            )
        if self.ICODER_RUN_TRACE_EVENTS_TTL_DAYS <= 0:
            failures.append(
                "ICODER_RUN_TRACE_EVENTS_TTL_DAYS must be a positive integer"
            )
        if (
            self.ICODER_RUN_TRACE_EVENTS_TTL_DAYS
            > self.ICODER_RUN_HISTORY_TTL_DAYS
        ):
            failures.append(
                "ICODER_RUN_TRACE_EVENTS_TTL_DAYS must not exceed "
                "ICODER_RUN_HISTORY_TTL_DAYS"
            )
        if failures:
            joined = "\n  - ".join(failures)
            raise RuntimeError(
                f"[A1A Gate 1 fail-closed] ICODER_DEPLOYMENT_MODE=cloud but:\n  - {joined}\n"
                "Refusing to boot. Fix the above env vars and restart."
            )

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
    OAUTH_CAPABILITY_SCOPES: List[str] = [
        "transcribe", "streams", "textgen", "facts",
        "feedback:read", "feedback:write", "feedback:evaluate", "traces:read",
        "coding:validate", "compliance:evaluate", "documentation:check",
    ]
    # Feedback is soft-deleted for caller semantics, retained only for the
    # bounded quality/audit window, and physically removed with its Context.
    AGENTIC_FEEDBACK_RETENTION_DAYS: int = 90

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
    # Development performance budget for one complete CDI orchestration. This
    # is an observable warning gate, not a provider timeout or a Corti SLA.
    ICODER_CDI_LATENCY_BUDGET_MS: int = 30_000
    # Independent per-query calls inside one required CDI safety gate may use
    # small bounded concurrency. Main clinical stages and the gates themselves
    # remain causally ordered. Three covers the common three-query CDI case in
    # one provider round while the orchestrator still hard-caps malformed or
    # excessive configuration at four.
    ICODER_CDI_GATE_MAX_CONCURRENCY: int = 3

    # Owner/admin-triggered external connectivity canary. Disabled by default;
    # it sends only a fixed repository-owned synthetic token and never accepts
    # request text. Per-request limits may only tighten these server caps.
    ICODER_MODEL_LIVE_CANARY_ENABLED: bool = False
    ICODER_MODEL_LIVE_CANARY_MAX_COST_CNY: float = 0.05
    ICODER_MODEL_LIVE_CANARY_MAX_OUTPUT_TOKENS: int = 8
    ICODER_MODEL_LIVE_CANARY_TIMEOUT_SECONDS: float = 15.0
    ICODER_MODEL_LIVE_CANARY_COOLDOWN_SECONDS: int = 300
    ICODER_MODEL_LIVE_CANARY_READINESS_TTL_SECONDS: int = 900

    # Explicitly development-only gate for transient verification of the
    # repository-owned synthetic clinical-model bundle.  The uploaded archive
    # is never persisted and a successful probe cannot enable Runtime loading.
    ICODER_CLINICAL_MODEL_SYNTHETIC_PROBE_ENABLED: bool = False
    ICODER_CLINICAL_MODEL_SHADOW_EVALUATION_ENABLED: bool = False
    ICODER_CLINICAL_MODEL_SHADOW_JOB_SIMULATION_ENABLED: bool = False
    ICODER_CLINICAL_MODEL_SHADOW_JOB_QUEUE_ALERT_COUNT: int = 10
    ICODER_CLINICAL_MODEL_SHADOW_JOB_MAX_QUEUE_AGE_SECONDS: int = 300
    ICODER_CLINICAL_MODEL_SHADOW_JOB_EXPIRED_LEASE_ALERT_COUNT: int = 1
    # The database remains the durable authority. Optional Redis is used only
    # for PHI-free wake-up signals, so missed/duplicated signals cannot lose or
    # duplicate authoritative work.
    ICODER_CLINICAL_MODEL_SHADOW_QUEUE_BACKEND: str = "database"
    ICODER_CLINICAL_MODEL_SHADOW_QUEUE_REDIS_URL: str = ""
    ICODER_CLINICAL_MODEL_SHADOW_QUEUE_ALLOW_INSECURE_REDIS: bool = False
    ICODER_CLINICAL_MODEL_SHADOW_SCHEDULER_ENABLED: bool = False
    ICODER_CLINICAL_MODEL_SHADOW_SCHEDULER_LEASE_SECONDS: int = 30
    ICODER_CLINICAL_MODEL_SHADOW_SCHEDULER_INTERVAL_SECONDS: float = 5.0
    ICODER_CLINICAL_MODEL_SHADOW_DEAD_LETTER_ALERT_COUNT: int = 1

    # Native BGE/FAISS is isolated in a dedicated Linux service. Cloud mode
    # requires HTTPS plus a strong service credential; local Compose may opt
    # into explicit HTTP for the internal development network.
    MEDCODER_RETRIEVER_URL: str = ""
    MEDCODER_RETRIEVER_ALLOW_HTTP: bool = False
    MEDCODER_RETRIEVER_TIMEOUT_SECONDS: float = 15.0

    # Persistent Memory uses an isolated, same-region embedding service. The
    # API sends deidentified text only; vectors are encrypted in Memory rows.
    # Cloud deployments must fail closed instead of using lexical fallback.
    ICODER_MEMORY_SEMANTIC_URL: str = ""
    ICODER_MEMORY_SEMANTIC_REQUIRED: bool = False

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

    # ── Phase A1A Gate 3.3 — fail-closed trace persistence ─────────────────
    # When True: cloud-mode deployment MUST use RUNTRACE_STORE=db. If a
    # process boots with memory store in cloud mode, Settings validation
    # raises and the process refuses to start. Local dev keeps memory
    # store as the default for tests that don't touch DB.
    #
    # When a DB write fails inside DbRunTraceStore.append, the failure
    # is recorded on the run_history row (trace_capture_status=FAILED)
    # and the run itself is allowed to continue. Setting this to True
    # would propagate the exception to the caller instead — useful for
    # compliance environments that demand strict "no trace left behind".
    RUNTRACE_FAIL_CLOSED: bool = False

    # ── Phase A1A Gate 3R.3 — named deployment profile ───────────────────
    # Optional explicit override that pins the trace-capture deployment
    # policy without forcing the operator to set three separate vars
    # (RUNTRACE_STORE + RUNTRACE_FAIL_CLOSED + ICODER_DEPLOYMENT_MODE).
    #
    # Values (see app/services/deployment_profile.py):
    #   MEMORY_DEV      — local dev (memory store, no fail-closed)
    #   BEST_EFFORT_DB  — cloud default (DB store, transient failures
    #                     logged but don't fail the run)
    #   REQUIRED_DB     — compliance envs (DB store, strict fail-closed)
    #
    # When empty (default), the profile is derived from the triple
    # (ICODER_DEPLOYMENT_MODE, RUNTRACE_STORE, RUNTRACE_FAIL_CLOSED)
    # so existing Gate 3.3 deployments continue to work unchanged.
    RUNTRACE_DEPLOYMENT_PROFILE: str = ""
    ICODER_RUN_HISTORY_TTL_DAYS: int = 90
    ICODER_RUN_TRACE_EVENTS_TTL_DAYS: int = 90

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
    ICODER_METRICS_BEARER_TOKEN: str = ""  # per-pod monitoring scrape credential
    ICODER_INVITE_DELIVERY_MODE: str = "manual"  # local manual | cloud webhook
    ICODER_INVITE_WEBHOOK_URL: str = ""
    ICODER_INVITE_WEBHOOK_BEARER_TOKEN: str = ""
    ICODER_INVITE_ALLOWED_EMAIL_DOMAINS: List[str] = []
    ICODER_INVITE_MAX_ATTEMPTS: int = 5
    ICODER_INVITE_RETRY_BASE_SECONDS: int = 30
    ICODER_INVITE_CLAIM_TIMEOUT_SECONDS: int = 120
    ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS: float = 10.0

    # ── PHI & Audit ───────────────────────────────────────────────────────────
    # Cloud default is `edge` (强制 PHI 脱敏 before Agent processing). Local
    # dev override via docker-compose.local-dev.yml to `disabled`.
    ICODER_PHI_REDACTION_MODE: str = "edge"   # edge | disabled
    ICODER_AUDIT_SINK: str = "cloud_audit"   # cloud_audit | local

    # ── Phase A1A Gate 4.2 — single-tenant org binding (local mode) ───────────
    # When ICODER_DEPLOYMENT_MODE=local and a request arrives without a bearer
    # JWT (e.g. console test traffic), the tenant middleware derives the org
    # from this setting rather than silently passing through. Empty = refuse
    # the request with tenant_context_required. Closes GATE3R_011 leak vector
    # where a missing Tenant-Name header caused the console trace path to
    # skip the org filter and return rows across all tenants.
    #
    # Default is the canonical dev/test org ``org_default1`` so the local
    # docker-compose workflow keeps working without extra env config.
    # Production (cloud mode) MUST leave this empty — the JWT org_id claim
    # is the only authoritative source in cloud mode.
    ICODER_SINGLE_TENANT_ORG_ID: str = "org_default1"

    # ── STT (Speech-to-Text) Configuration ────────────────────────────────────
    # Cloud uses server-side STT service, not bundled Whisper. Local dev can
    # opt into the native stack explicitly.  Keep it disabled in the API
    # process by default because native ASR/diarization imports are not an
    # acceptable implicit egress or process-stability dependency.
    ICODER_ENABLE_LOCAL_STT: bool = False
    # Encoded Streams media must be decoded in a separate, bounded process
    # before ASR or encrypted retention. `header_only` is a local diagnostic
    # escape hatch and is forbidden by the cloud fail-closed policy.
    ICODER_STREAM_MEDIA_VALIDATION_MODE: str = "decoder"  # decoder | header_only
    ICODER_STREAM_MEDIA_DECODER_PATH: str = "ffmpeg"
    ICODER_STREAM_MEDIA_DECODER_TIMEOUT_SECONDS: float = 3.0
    ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY: int = 2
    ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS: float = 0.5
    # Prerecorded encoded multichannel audio uses a separate full-file decode
    # budget. ffprobe first enforces exact channel/container/duration metadata;
    # ffmpeg then writes only bounded 16 kHz/16-bit mono WAVs to temporary files.
    ICODER_TRANSCRIPTS_MEDIA_DECODER_PATH: str = "ffmpeg"
    ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH: str = "ffprobe"
    ICODER_TRANSCRIPTS_MEDIA_DECODER_TIMEOUT_SECONDS: float = 120.0
    ICODER_TRANSCRIPTS_MEDIA_PROBE_TIMEOUT_SECONDS: float = 10.0
    ICODER_TRANSCRIPTS_MEDIA_DECODER_MAX_CONCURRENCY: int = 2
    ICODER_TRANSCRIPTS_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS: float = 1.0
    ICODER_TRANSCRIPTS_MAX_DURATION_SECONDS: int = 7200
    # Cross-worker Streams ownership TTL. Runtime clamps any direct process
    # override to 6..300 seconds; 30 seconds balances crash recovery and DB
    # heartbeat load for ordinary deployments.
    ICODER_STREAM_LEASE_SECONDS: int = 30
    STT_WHISPER_MODEL: str = ""  # tiny | base | small | medium | large (empty = use managed STT)
    STT_DEVICE: str = "auto"  # auto/cuda/cpu
    STT_MEDICAL_TERMS_BOOST: bool = True  # Enable medical terminology enhancement

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 30

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    AUDIT_LOG_RETENTION_DAYS: int = 365

    # Non-secret NCBI E-utilities operational contact. PubMed Registry calls
    # remain unavailable when this is empty.
    ICODER_NCBI_CONTACT_EMAIL: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()


def icoder_corti_capability_scopes() -> List[str]:
    """Backwards-compatible accessor (some tests import the function).

    Lives at module scope (not inside ``Settings``) so that callers reading
    the field at runtime get the current config — useful for tests that
    monkey-patch settings via env vars.
    """
    return list(settings.OAUTH_CAPABILITY_SCOPES or [])
