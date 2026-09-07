# iCoDer Medical Coding Agent - FastAPI Application
import json
import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import get_db, init_db, verify_production_database
from app.services.access_log_privacy import install_uvicorn_access_log_privacy
import app.models  # noqa: F401 — register all models with Base before init_db() creates tables

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
install_uvicorn_access_log_privacy()
logger = logging.getLogger(__name__)


def _test_fail_closed_a2a_mode_enabled() -> bool:
    """True only for an explicit pytest-only fail-closed wiring exercise."""

    import sys

    return (
        os.environ.get("ICODER_PHASE1_STUB_LLM", "0") == "1"
        and "pytest" in sys.modules
    )


async def _recover_runtime_sessions() -> int:
    """Recover active RuntimeSessions from DB after restart.

    Loads all non-terminal sessions back into the runtime_registry.
    Checks timeout state and escalates if needed.
    Returns count of recovered sessions.
    """
    from app.database import async_session_factory
    from app.models.runtime_persistence import RuntimeSession as RTSession
    from app.services.runtime import runtime_registry, DeterministicRuntime, CaseState
    from sqlalchemy import select as _select

    terminal_states = {"ARCHIVED", "FAILED", "ESCALATED"}
    recovered = 0

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                _select(RTSession).where(
                    RTSession.current_state.notin_(terminal_states)
                )
            )
            sessions = result.scalars().all()

            for s in sessions:
                rt = DeterministicRuntime(
                    case_id=s.runtime_id,
                    pipeline_id=s.pipeline_id,
                    execution_path=s.execution_path,
                    review_id=s.review_id or "",
                    agent_id=s.agent_id or "",
                )
                # Restore state via force_transition (audited as "recovery")
                try:
                    target_state = CaseState(s.current_state)
                    rt.force_transition(
                        target_state,
                        reason=f"Recovered from DB after restart (was {s.current_state})",
                        actor="system_recovery",
                    )
                    # Adjust state_entered_at for timeout continuity
                    if s.state_entered_at:
                        rt.state_entered_at = s.state_entered_at.timestamp()
                    # Restore flags
                    if s.escalated and rt.state != CaseState.ESCALATED:
                        rt.force_transition(CaseState.ESCALATED,
                            reason="Recovered escalated session", actor="system_recovery")
                    if s.failed and rt.state != CaseState.FAILED:
                        rt.force_transition(CaseState.FAILED,
                            reason="Recovered failed session", actor="system_recovery")
                    if s.archived and rt.state != CaseState.ARCHIVED:
                        rt.force_transition(CaseState.ARCHIVED,
                            reason="Recovered archived session", actor="system_recovery")

                    # Check timeout
                    action = rt.check_timeout()
                    if action:
                        logger.warning(f"Runtime recovery: {s.runtime_id} timed out during downtime → {action}")

                    runtime_registry._runtimes[s.runtime_id] = rt
                    recovered += 1
                    logger.info(f"Runtime recovery: restored {s.runtime_id} (state={s.current_state})")

                except ValueError:
                    logger.warning(f"Runtime recovery: unknown state '{s.current_state}' for {s.runtime_id}, skipping")

        if recovered:
            # Check stale after recovery
            stale = runtime_registry.stale_cases(max_age_hours=4)
            if stale:
                logger.warning(f"Runtime recovery: {len(stale)} stale case(s) found: {stale}")

    except Exception as e:
        logger.warning(f"Runtime recovery failed (table may not exist yet): {e}")

    return recovered


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} V{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"LLM: {settings.LLM_PROVIDER} / {settings.LLM_MODEL}")
    # CodingRuntimeDispatcher caches a FastCodingRuntime, which in turn caches
    # the gateway-bound DeepSeek adapter. Repeated application lifespans (test
    # workers, reloads, embedded hosts) must never reuse an adapter from the
    # prior platform_gateway instance.
    from app.coding_runtime import reset_dispatcher
    reset_dispatcher()
    if settings.ICODER_DEPLOYMENT_MODE == "cloud":
        await verify_production_database()
        logger.info("Production PostgreSQL schema and tenant RLS verified")
    else:
        await init_db()
        logger.info("Local database initialized")
    try:
        from app.services.stt_jobs import recover_pending_stt_jobs

        await recover_pending_stt_jobs()
    except Exception as e:
        logger.error("STT pending-job recovery failed: %s", e, exc_info=True)
    # Auto-seed demo users on first startup (idempotent — seed.py checks if already seeded)
    if settings.APP_ENV in ("development", "dev") or settings.SEED_ON_STARTUP:
        try:
            from app.seed import seed as _seed
            await _seed()
            logger.info("Seed: completed (admin/admin123 demo user available)")
        except Exception as e:
            logger.warning(f"Seed: skipped (non-fatal): {e}")
        # Seed built-in templates (Corti /templates parity) — idempotent.
        try:
            from app.seed import seed_builtin_templates as _seed_tpl
            await _seed_tpl()
            logger.info("Seed: built-in templates ensured (Templates Beta)")
        except Exception as e:
            logger.warning(f"Seed: built-in templates skipped (non-fatal): {e}")
        # Phase 3-B2 Loop 0 (2026-07-05): seed agent_definitions DB from
        # official_agents/**/agent_pack.json. Idempotent upsert by
        # (name, version, is_prebuilt=True). Prebuilt agents are global
        # (organization_id=NULL) so the /api/rest/v1/agent_definitions
        # surface stays consistent with the pack-mastered Hub endpoint.
        try:
            from scripts.seed_agents import seed_agents_from_packs as _seed_agents
            await _seed_agents()
            logger.info("Seed: agent_definitions synced from official_agents/ packs")
        except Exception as e:
            logger.warning(f"Seed: agent_definitions sync skipped (non-fatal): {e}")
    # --- Runtime Recovery: restore active sessions from DB ---
    recovered = await _recover_runtime_sessions()
    logger.info(f"Runtime recovery: {recovered} active session(s) restored")
    # --- Embedded Runtime: initialize LLMGateway + PlatformRuntime ---
    from icoder_runtime.core.llm_gateway import (
        LLMGateway, MockLLMProvider, MedicalCodingLLMProvider,
    )
    from icoder_runtime.core.llm_provider_factory import (
        create_configured_llm_deployments,
        create_primary_llm_provider,
    )
    from icoder_runtime.core.registry import init_registry
    from icoder_runtime.core.runtime_config import RuntimeConfig
    from icoder_runtime.embedded.platform_runtime import PlatformRuntime

    # Load runtime config (env vars or runtime.yaml)
    runtime_config = RuntimeConfig.from_env()
    logger.info(
        f"Runtime config: execution_mode={runtime_config.execution_mode}, "
        f"review_coding_mode={runtime_config.review_coding_mode}, "
        f"fallback_to_legacy={runtime_config.fallback_to_legacy}"
    )

    # Initialize the unified Agent Registry (persistent, shared)
    agent_registry = init_registry(runtime_config.registry_dir)
    logger.info(f"Agent Registry: {agent_registry.count} agent(s) loaded from {runtime_config.registry_dir}")

    # Create the policy before the gateway so every provider invocation,
    # including native streaming and fallbacks, is guarded at the last common
    # network boundary.
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    from app.services.tenant_model_routing import resolve_tenant_model_route
    data_policy = RuntimeDataPolicy.from_env()
    app.state.data_policy = data_policy

    platform_gateway = LLMGateway(
        data_policy=data_policy,
        tenant_provider_resolver=resolve_tenant_model_route,
    )
    # Mock provider (always available as fallback)
    platform_gateway.register(MockLLMProvider(), alias="mock")

    # MedicalCodingLLMProvider — uses PromptLLMAdapter when gateway is available
    medical_coding_provider = MedicalCodingLLMProvider(gateway=platform_gateway)
    platform_gateway.register(medical_coding_provider, alias="medical-coding")
    mc_health = medical_coding_provider.health_check()
    mc_mode = mc_health.get("mode", "unknown")
    if mc_mode == "real":
        logger.info(f"MedicalCodingLLMProvider registered (mode=real via PromptLLMAdapter)")
    else:
        logger.info(
            "MedicalCodingLLMProvider registered (mode=%s). "
            "No real coding engine; requests fail closed.",
            mc_mode,
        )

    # Primary LLM if configured. Canonical key env var is
    # ICODER_CREDENTIAL_LLM (matches credential_vault + llm_service).
    # settings.LLM_API_KEY is the legacy alias; fall back to it for
    # backward compatibility with .env-based dev setups.
    #
    # Phase 3-C0 A1 (2026-07-05): LLM_PROVIDER=mock strictly suppresses
    # DeepSeek registration even when ICODER_CREDENTIAL_LLM is set in the
    # OS env (a persisted dev key leaks through the truthy-key check and
    # causes real DeepSeek HTTP 401s in tests). Mock mode = no real
    # external LLM HTTP, period.
    #
    # Read LLM_PROVIDER from os.environ directly (NOT settings.LLM_PROVIDER)
    # because Settings() captures the env snapshot at import time, and
    # pytest's monkeypatch.setenv() runs after import — settings would
    # still report the import-time value.
    _llm_key = (
        os.environ.get("ICODER_CREDENTIAL_LLM", "").strip()
        or settings.LLM_API_KEY
    )
    _llm_provider_cfg = os.environ.get(
        "LLM_PROVIDER", settings.LLM_PROVIDER or ""
    ).lower()
    model_deployments: dict[str, dict[str, Any]] = {}
    if _llm_provider_cfg == "mock":
        mock_provider = MockLLMProvider()
        # FastCodingRuntime's legacy DeepSeek adapter still requests the
        # stable ``deepseek`` alias explicitly. In mock mode bind that alias
        # to the degraded mock provider so the runtime fails immediately and
        # truthfully as ``llm_degraded`` instead of retrying a missing name.
        platform_gateway.register(mock_provider, default=True, alias="deepseek")
        model_deployments[mock_provider.name] = {
            "id": mock_provider.name,
            "provider_id": "mock",
            "model": "mock/1.0",
            "is_default": True,
            "tenant_selectable": False,
            "credential_configured": False,
            "endpoint_configuration_valid": True,
        }
        logger.info(
            "LLM_PROVIDER=mock — MockLLMProvider registered as default "
            "(external providers suppressed, key_present=%s)",
            bool(_llm_key),
        )
    else:
        try:
            primary_provider = create_primary_llm_provider(
                provider_name=_llm_provider_cfg,
                api_key=_llm_key,
                base_url=settings.LLM_BASE_URL,
                model=settings.LLM_MODEL,
                max_tokens=settings.LLM_MAX_TOKENS,
                temperature=settings.LLM_TEMPERATURE,
                timeout=settings.LLM_TIMEOUT,
            )
            platform_gateway.register(primary_provider, default=True)
            model_deployments[primary_provider.name] = {
                "id": primary_provider.name,
                "provider_id": str(
                    getattr(primary_provider, "policy_provider_name", "")
                    or primary_provider.name
                ),
                "model": settings.LLM_MODEL,
                "is_default": True,
                "tenant_selectable": primary_provider.name != "mock",
                "credential_configured": bool(_llm_key),
                "endpoint_configuration_valid": True,
            }
            logger.info(
                "Embedded Runtime: %s registered as default "
                "(credential source=%s, model=%s)",
                primary_provider.name,
                "env" if os.environ.get("ICODER_CREDENTIAL_LLM", "").strip() else "settings",
                settings.LLM_MODEL,
            )
        except Exception as e:
            logger.warning("Primary LLM registration failed closed; using mock: %s", e)
            mock_provider = MockLLMProvider()
            # No configured provider is available. Preserve the same
            # fail-closed legacy alias used by FastCodingRuntime.
            platform_gateway.register(mock_provider, default=True, alias="deepseek")
            model_deployments[mock_provider.name] = {
                "id": mock_provider.name,
                "provider_id": "mock",
                "model": "mock/1.0",
                "is_default": True,
                "tenant_selectable": False,
                "credential_configured": False,
                "endpoint_configuration_valid": True,
            }
    try:
        extra_deployments = create_configured_llm_deployments()
        for deployment, public_metadata in extra_deployments:
            if deployment.name in platform_gateway.registered_deployments:
                raise ValueError(
                    f"duplicate configured LLM deployment: {deployment.name}"
                )
            platform_gateway.register(deployment)
            model_deployments[deployment.name] = public_metadata
        if extra_deployments:
            logger.info(
                "Registered %d additional tenant-selectable LLM deployment(s)",
                len(extra_deployments),
            )
    except Exception as e:
        if settings.ICODER_DEPLOYMENT_MODE == "cloud":
            raise RuntimeError(
                "Invalid ICODER_LLM_DEPLOYMENTS_JSON configuration"
            ) from e
        logger.warning(
            "Additional LLM deployments ignored in local mode error_type=%s",
            type(e).__name__,
        )
    app.state.model_deployments = model_deployments

    # ── Data Policy (must be created before PlatformRuntime) ──
    platform_runtime = PlatformRuntime(
        gateway=platform_gateway,
        config=runtime_config,
        registry=agent_registry,
        data_policy=data_policy,
    )
    await platform_runtime.start()
    app.state.platform_runtime = platform_runtime
    app.state.platform_gateway = platform_gateway
    app.state.agent_registry = agent_registry
    app.state.runtime_config = runtime_config
    # Five-type Agentic Connector resources are useful only when the runtime
    # owns a real execution boundary.  The governed transport is inert at
    # startup (no probe or external call), ignores OS proxy variables, pins
    # approved DNS results to the TCP socket, and still requires per-node data
    # policy authorization before any outbound request.
    from app.services.connector_runtime import build_connector_runtime

    connector_runtime = build_connector_runtime(app)
    app.state.connector_runtime = connector_runtime
    app.state.connector_executor = connector_runtime.executor
    logger.info(
        "Connector runtime wired (registry/internal-agent=governed, "
        "MCP/A2A transport=governed, external PHI default=deny)"
    )
    # Phase 4-B Step 3: register the platform gateway with the backend
    # provider registry so ``PureLLMProvider`` can lazy-resolve it on
    # first ``invoke()``. Lazy — startup doesn't pay for the lookup
    # until an agent actually runs.
    from icoder_runtime.backends.registry import set_gateway_lookup
    set_gateway_lookup(lambda: app.state.platform_gateway)
    logger.info(
        "Backend provider gateway lookup registered (PureLLMProvider will "
        "lazy-resolve platform_gateway on first invoke)"
    )
    logger.info(f"Data policy: allow_external_llm={data_policy.allow_external_llm}, "
                f"persist_full_input={data_policy.persist_full_input}")

    # ── Observability ──
    from icoder_runtime.observability.run_history import RunHistoryStore
    from icoder_runtime.observability.fallback import FallbackTracker
    from icoder_runtime.observability.shadow_diff import ShadowDiffService
    from icoder_runtime.observability.audit_log import RuntimeAuditLogger

    run_history = RunHistoryStore(
        storage_dir=runtime_config.registry_dir,
        persist_full_input=data_policy.persist_full_input,
    )
    fallback_tracker = FallbackTracker(storage_dir=runtime_config.registry_dir)
    shadow_diff_service = ShadowDiffService(storage_dir=runtime_config.registry_dir)
    runtime_audit_logger = RuntimeAuditLogger(storage_dir=runtime_config.registry_dir)

    app.state.run_history = run_history
    app.state.fallback_tracker = fallback_tracker
    app.state.shadow_diff_service = shadow_diff_service
    app.state.runtime_audit_logger = runtime_audit_logger
    logger.info("Observability initialized: run_history, fallback, shadow_diff, audit_log")

    # ── MedCodER index flag (lazy-init on first /api/medical-coding/medcoder call) ──
    # Setting it to False here means /api/health can report "medcoder not ready"
    # honestly, and the heavy BGE-M3 + FAISS index only loads on demand.
    app.state.medcoder_index_ready = False
    app.state.medcoder_index_error: str | None = None
    app.state.medcoder_index_loading = False
    app.state.medcoder_retriever = None  # populated by C7 if subprocess mode is on
    logger.info("MedCodER index: not yet loaded (lazy init on first request)")

    from icoder_runtime.providers.medical_coding.runtime_safety import (
        assess_bge_runtime_safety,
    )
    _bge_safety = assess_bge_runtime_safety()

    # ── M2.5: FAISS index health check (governance — NO silent continue) ──
    # Runs synchronously at startup so /api/health + MCP /tools/call can
    # observe the structured health report. If the index is missing or
    # corrupt, status="degraded" with a specific reason; downstream
    # search_icd calls return -32002 instead of silently returning empty.
    try:
        from app.services.medcoder_index_health import (
            index_health_check,
            is_icd9cm3_retriever_available,
        )
        _medcoder_index_dir = Path("data/medcoder")
        _medcoder_health = index_health_check(
            _medcoder_index_dir,
            allow_native=_bge_safety.safe,
            native_disabled_reason=_bge_safety.reason,
        )
        app.state.medcoder_index_health = _medcoder_health
        if _medcoder_health["status"] == "ok":
            logger.info(
                "MedCodER FAISS index: OK (ntotal=%d, dim=%d, dir=%s)",
                _medcoder_health["ntotal"],
                _medcoder_health["dim"],
                _medcoder_index_dir,
            )
        else:
            logger.error(
                "MedCodER FAISS index: DEGRADED — %s. "
                "MCP /mcp/v1/tools/call/search_icd will return -32002 "
                "until the index is rebuilt. "
                "Run: python scripts/build_medcoder_index.py",
                _medcoder_health["reason"],
            )
        # ICD-9-CM-3 index is optional (NEW in M2.5). Log a warning if
        # it's not built yet — it's expected to be missing on first run.
        _icd9cm3_ok = is_icd9cm3_retriever_available(
            _medcoder_index_dir,
            allow_native=_bge_safety.safe,
            native_disabled_reason=_bge_safety.reason,
        )
        if not _icd9cm3_ok:
            logger.warning(
                "MedCodER ICD-9-CM-3 FAISS index: not yet built. "
                "Run: python scripts/build_medcoder_icd9cm3_index.py"
            )
    except Exception as _e:  # noqa: BLE001 — surface any unexpected error
        # Belt-and-suspenders: even if the health check itself raises,
        # record a degraded report so the rest of the app knows.
        logger.exception("MedCodER index health check crashed: %s", _e)
        app.state.medcoder_index_health = {
            "status": "degraded",
            "reason": f"health check itself crashed: {_e}",
            "checks": {},
            "ntotal": None,
            "dim": None,
            "metadata_len": None,
        }

    # C7: When running with the subprocess retriever, eagerly spawn the
    # worker and probe it so /api/health can report medcoder_index_ready
    # accurately (vs. always-False lazy init). The probe is sync
    # (queue.get with timeout) so we run it in a thread to keep the
    # startup event loop unblocked.
    _subprocess_mode = (
        os.environ.get("MEDCODER_SUBPROCESS") == "1" or os.name == "nt"
    ) and _bge_safety.safe
    if not _bge_safety.safe:
        app.state.medcoder_index_ready = False
        app.state.medcoder_index_error = _bge_safety.reason
        logger.error(
            "MedCodER local BGE runtime disabled: %s",
            _bge_safety.reason,
        )
    if _subprocess_mode:
        import asyncio as _asyncio
        try:
            app.state.medcoder_index_loading = True
            from icoder_runtime.providers.medical_coding.medcoder_retriever import (
                SubprocessMedCodERRetriever,
            )
            # E1.9 (2026-06-27): pin BGE-M3 to fp16 before spawning the
            # worker. Windows ``_mp.Process`` (spawn) inherits the parent
            # env at start time, so the worker's BGEEmbedder() reads these
            # values via MEDCODER_BGE_DTYPE / MEDCODER_BGE_DEVICE and
            # loads in fp16 (~1.5-2 GB peak) instead of fp32 (~3-4 GB,
            # which OOMs on the Windows 1 GB malloc limit).
            os.environ.setdefault("MEDCODER_BGE_DTYPE", "float16")
            os.environ.setdefault("MEDCODER_BGE_DEVICE", "cpu")
            loop = _asyncio.get_running_loop()
            # T7: probe_timeout=10s is too short for first-time BGE-M3 load
            # (~30-90s on Windows). Bump to 90s. Also keep the retriever
            # alive on probe failure so HybridCodingAdapter can reuse the
            # in-progress load (avoid triggering a second 30-90s load).
            retriever: SubprocessMedCodERRetriever = await loop.run_in_executor(
                None,
                lambda: SubprocessMedCodERRetriever(
                    timeout=120.0,
                    probe_timeout=90.0,
                ),
            )
            if retriever.is_ready:
                app.state.medcoder_index_ready = True
                app.state.medcoder_retriever = retriever
                logger.info(
                    "MedCodER subprocess retriever: ready (pid=%s)", retriever.pid
                )
            else:
                # Probe timed out but worker is still loading — KEEP IT
                # ALIVE. The first request will wait up to ``timeout``
                # (120s) and may succeed once BGE-M3 finishes loading.
                app.state.medcoder_index_error = (
                    "SubprocessMedCodERRetriever probe timed out (worker "
                    "still loading BGE-M3+FAISS); first request may block "
                    "until ready"
                )
                app.state.medcoder_retriever = retriever
                logger.warning(
                    "MedCodER subprocess retriever: probe timed out but "
                    "worker kept alive (pid=%s); ready flag=False",
                    retriever.pid,
                )
        except Exception as e:
            app.state.medcoder_index_error = f"Failed to start MedCodER worker: {e}"
            logger.warning(
                "MedCodER subprocess retriever: startup failed: %s", e
            )
        finally:
            app.state.medcoder_index_loading = False

    # A separately built Linux worker is the production-equivalent path.
    # It takes precedence over local/subprocess state and keeps Torch/FAISS
    # entirely out of the API image.  The probe is bounded and fails closed;
    # no credential value or remote response body is logged.
    _remote_retriever_url = os.environ.get("MEDCODER_RETRIEVER_URL", "").strip()
    app.state.medcoder_retriever_mode = "remote" if _remote_retriever_url else (
        "subprocess" if _subprocess_mode else (
            "local_in_process" if _bge_safety.safe else "local_disabled"
        )
    )
    app.state.medcoder_retriever_worker_version = ""
    app.state.medcoder_retriever_index_version = ""
    if _remote_retriever_url:
        try:
            from icoder_runtime.providers.medical_coding.remote_retriever import (
                RemoteMedCodERRetriever,
            )

            _remote_retriever = RemoteMedCodERRetriever.from_env(
                code_system="ICD-10-CN"
            )
            _remote_health = await _remote_retriever.health_async()
            app.state.medcoder_index_ready = _remote_health.ready
            app.state.medcoder_index_error = (
                None if _remote_health.ready else _remote_health.reason
            )
            app.state.medcoder_retriever_worker_version = (
                _remote_health.worker_version
            )
            app.state.medcoder_retriever_index_version = (
                _remote_health.index_version
            )
            # MCP handlers consume this structured gate rather than the
            # convenience ``medcoder_index_ready`` flag.  A remote worker is
            # authoritative when configured, so do not leave the earlier
            # local/native health result in place (that would make a healthy
            # isolated worker look degraded and silently bypass remote
            # semantic retrieval on Windows).
            app.state.medcoder_index_health = {
                "status": "ok" if _remote_health.ready else "degraded",
                "reason": None if _remote_health.ready else _remote_health.reason,
                "mode": "remote",
                "code_system": _remote_health.code_system,
                "worker_version": _remote_health.worker_version,
                "index_version": _remote_health.index_version,
                "checks": {
                    "remote_configured": True,
                    "remote_ready": _remote_health.ready,
                },
                "ntotal": None,
                "dim": None,
                "metadata_len": None,
            }
            logger.info(
                "MedCodER remote retriever probe ready=%s worker_version=%s index_version=%s",
                _remote_health.ready,
                _remote_health.worker_version or "unknown",
                _remote_health.index_version or "unknown",
            )
        except Exception as exc:
            app.state.medcoder_index_ready = False
            app.state.medcoder_index_error = (
                f"remote_retriever_configuration_{type(exc).__name__}"
            )
            app.state.medcoder_index_health = {
                "status": "degraded",
                "reason": app.state.medcoder_index_error,
                "mode": "remote",
                "checks": {
                    "remote_configured": True,
                    "remote_ready": False,
                },
                "ntotal": None,
                "dim": None,
                "metadata_len": None,
            }
            logger.error(
                "MedCodER remote retriever configuration failed error_type=%s",
                type(exc).__name__,
            )

    logger.info(f"Embedded Runtime started: {platform_runtime.status()}")

    # ── Register Official Agent Packs (BuiltinAgentPackProvider) ──
    from icoder_runtime.core.builtin_pack_provider import BuiltinAgentPackProvider
    _official_agents_dir = Path(__file__).parent.parent / "official_agents"
    if _official_agents_dir.exists():
        provider = BuiltinAgentPackProvider(_official_agents_dir)
        discovered = provider.discover()
        registered = provider.register_all(platform_runtime)
        logger.info(f"BuiltinAgentPackProvider: {len(discovered)} packs discovered, {registered} registered")

        # Sync all installed Runtime agents into their derived DB projection.
        # Registry/Pack is authoritative for executable prebuilt rows; custom
        # tenant Agents remain DB-owned.
        from app.services.agent_registry_sync_service import AgentRegistrySyncService
        from app.models.agent import Agent as AgentModel
        from app.database import async_session_factory
        try:
            sync_svc = AgentRegistrySyncService(agent_registry)
            async with async_session_factory() as session:
                result = await sync_svc.repair_from_registry(session)
                logger.info(
                    f"Registry→DB sync: {result['total_repaired']} repaired, "
                    f"{result['total_failed']} failed"
                )
        except Exception as e:
            # repair_from_registry itself doesn't re-raise (state captures failure),
            # so this only fires for constructor/session-creation failures.
            logger.warning(f"Registry→DB sync skipped (DB may not be ready): {e}")

    # --- Mount new A2A v0.3 package (replaces a2a_registry in Commit 3) ---
    # T5/T6: LLMCall/ExpertInvoker wire to the real LLMGateway + MedCodER
    # HybridCodingAdapter via sync adapters. The fail-closed test switch is
    # accepted only inside a pytest process and can never alter a deployment.
    try:
        from app.icoder.agent_runtime.a2a import (
            mount_a2a,
            AgentProvider,
            ExpertCaller,
        )
        from app.icoder.agent_runtime.a2a.agent_card import (
            medcoder_coding_review_card,
            medical_coding_agent_card,
            code_validation_agent_card,
            compliance_guardrail_agent_card,
            note_completeness_agent_card,
        )
        from app.icoder.agent_runtime.orchestrator import (
            Aggregator,
            Delegator,
            DictAgentProvider,
            InboundHandler,
            PHIRedactor,
            Planner,
        )
        from app.icoder.agent_runtime.orchestrator.planner import PlannerConfig
        from app.icoder.agent_runtime.orchestrator.delegator import DelegatorConfig
        from app.icoder.agent_runtime.orchestrator.wiring import (
            build_expert_invoker_for_medcoder,
            build_llm_call_from_gateway,
            unavailable_expert_invoker,
        )

        _phase1_stub_llm = _test_fail_closed_a2a_mode_enabled()

        # E1.1 (2026-06-26): hoist `_hybrid_adapter = None` to the outer
        # scope so the MCP mount code (which runs unconditionally AFTER
        # this if/else) can safely check `if _hybrid_adapter is not None`
        # even when ICODER_PHASE1_STUB_LLM=1 (i.e., we skipped the else
        # branch where it would have been constructed). Pre-fix: when
        # stub mode is on, the else branch never ran, so `_hybrid_adapter`
        # was never bound — but the MCP block still tried to read it,
        # causing UnboundLocalError → MCP mount skipped with warning.
        _hybrid_adapter: Any = None

        if _phase1_stub_llm:
            logger.info(
                "A2A wiring: ICODER_PHASE1_STUB_LLM=1 — using inline stubs "
                "(no real LLM, no MedCodER)"
            )
            _llm_call: Callable[[str, str], dict] = lambda _s, _u: {"content": "{}"}
            _expert_invoker: Callable[[Any], dict] = unavailable_expert_invoker
        else:
            # Construct HybridCodingAdapter in mode="medcoder" so the NAACL
            # 5-stage pipeline runs when coding-expert is invoked. The
            # retriever is lazy — BGE-M3 + FAISS only load on first
            # infer_async() call (see hybrid_adapter._get_retriever).
            try:
                from icoder_runtime.providers.medical_coding import (
                    HybridCodingAdapter,
                )
                # T7: pass the lifespan's already-spawned retriever (if any)
                # so HybridCodingAdapter doesn't trigger a SECOND BGE-M3
                # load in its own subprocess (30-90s wasted).
                _shared_retriever = (
                    getattr(app.state, "medcoder_retriever", None)
                )
                _hybrid_adapter = HybridCodingAdapter(
                    gateway=platform_gateway,
                    mode="medcoder",
                    retriever=_shared_retriever,
                )
                logger.info(
                    "A2A wiring: HybridCodingAdapter(mode='medcoder') constructed "
                    "(retriever=%s)",
                    "shared" if _shared_retriever is not None else "lazy",
                )
            except Exception as _he:
                logger.warning(
                    "A2A wiring: HybridCodingAdapter unavailable; legacy "
                    "coding-expert will fail closed error_type=%s",
                    type(_he).__name__,
                )

            _llm_call = build_llm_call_from_gateway(
                platform_gateway,
                default_provider=platform_gateway.default_provider or "",
            )
            # E1 (2026-06-26): canonical MedCodER path now routes to 4
            # D2 expert packs (evidence_extractor / index_navigator /
            # code_reconciler / tabular_validator) instead of the single
            # ``coding-expert`` glue. ``hybrid_fallback=_hybrid_adapter``
            # keeps the M1 coding-expert back-compat dispatch alive for
            # any legacy caller.
            _rule_engine = None
            try:
                from compliance_services.rule_engine import RuleEngine
                _rule_engine = RuleEngine()
            except Exception as _re:
                logger.warning(
                    "A2A wiring: RuleEngine unavailable; tabular-validator "
                    "will lazy-import error_type=%s",
                    type(_re).__name__,
                )
            _expert_invoker = build_expert_invoker_for_medcoder(
                platform_gateway,
                medcoder_retriever=getattr(app.state, "medcoder_retriever", None),
                rule_engine=_rule_engine,
                hybrid_fallback=_hybrid_adapter,
            )
            logger.info(
                "A2A wiring: LLMGateway=%s, MedCodER=%s, RuleEngine=%s, "
                "expert_packs=E1_4pack",
                "real" if platform_gateway.is_configured else "unavailable_fail_closed",
                "real" if _hybrid_adapter is not None else "unavailable_fail_closed",
                "real" if _rule_engine is not None else "lazy",
            )

        def _build_phase1_agent_provider() -> "DictAgentProvider":
            """Build DictAgentProvider with a real AgentDefinition for
            ``medcoder-coding-review`` so the Planner has system_prompt +
            expert_ids context (the planner calls ``agent.name`` /
            ``agent.expert_ids`` / ``agent.config``).

            Loads the official ``agent_pack.json`` when available; falls
            back to a minimal definition that just exposes
            ``coding-expert`` so the CodingExpert (via the wiring factory)
            can route.
            """
            from icoder_runtime.types import AgentDefinition
            _agent = AgentDefinition(
                id="medcoder-coding-review",
                name="MedCodER Coding Review Agent",
                description="iCoDer 病案首页编码审核 Agent (MedCodER 5 阶段)",
                system_prompt="你是 iCoDer 病案首页编码审核助手。",
                icon="FileSearch",
                category="medical-coding",
                expert_ids=["coding-expert"],
                default_expert_id="coding-expert",
                config={
                    "non_goals": ["不可用于生产写回", "不可用于医保上传"],
                    "output_contract": "MedicalCodingOutputSchema",
                },
                is_prebuilt=True,
                version="1.0.0",
                status="published",
            )
            # Try to enrich from official pack if present (system_prompt
            # is the main value; expert_ids stay ["coding-expert"] for
            # Phase 1 — drg-expert / compliance-expert are Phase 5).
            try:
                from icoder_runtime.agent_pack import import_pack
                _pack_path = (
                    Path(__file__).parent.parent
                    / "official_agents"
                    / "medcoder-coding-review"
                    / "agent_pack.json"
                )
                if _pack_path.exists():
                    _pack = json.loads(_pack_path.read_text(encoding="utf-8"))
                    _pack_agent, _, _, _ = import_pack(_pack)
                    _agent = AgentDefinition(
                        id="medcoder-coding-review",
                        name=_pack_agent.name,
                        description=_pack_agent.description,
                        system_prompt=_pack_agent.system_prompt or _agent.system_prompt,
                        icon=_pack_agent.icon,
                        category=_pack_agent.category,
                        expert_ids=_pack_agent.expert_ids or _agent.expert_ids,
                        default_expert_id=_agent.default_expert_id,
                        config=_agent.config,
                        is_prebuilt=True,
                        version=_pack_agent.version,
                        status="published",
                    )
            except Exception as _ae:
                logger.warning(
                    "A2A wiring: official agent pack enrichment failed "
                    "error_type=%s",
                    type(_ae).__name__,
                )

            # Phase 3-B1 (2026-07-04): Medical Coding Agent public facade.
            # Same expert_ids (coding-expert routes to 4 D2 packs via the
            # build_expert_invoker_for_medcoder wiring), but the output_contract
            # is v2 (MedicalCodingAgentOutputV2, 8 Corti fields). The v1→v2
            # projection happens in the response post-processor (see below).
            _medical_agent = AgentDefinition(
                id="medical-coding-agent",
                name="医学编码智能体",
                description="iCoDer 官方医学编码 Agent (controlled rollout)",
                system_prompt=(
                    "你是 iCoDer Medical Coding Agent (controlled rollout)。"
                    "基于病历证据生成 ICD-10-CN 诊断编码与 ICD-9-CM-3 手术操作编码建议, "
                    "输出 Corti-style 8-field 结构化结果。"
                    "AI-assisted coding — 不替代编码员, 不 upcoding, 不推断未记录的诊断/手术。"
                ),
                icon="Stethoscope",
                category="medical-coding",
                expert_ids=["coding-expert"],
                default_expert_id="coding-expert",
                config={
                    "non_goals": [
                        "不替代编码员",
                        "不 upcoding",
                        "不推断未记录的诊断/手术",
                        "不写回 EMR/HIS/医保",
                        "不声称 fully automated coding",
                    ],
                    "output_contract": "MedicalCodingAgentOutputV2",
                    "agent_ref": "icoder/medical-coding-agent@2.0.0",
                },
                is_prebuilt=True,
                version="2.0.0",
                status="published",
            )
            # Try to enrich from the medical_coding official pack
            try:
                from icoder_runtime.agent_pack import import_pack as _import_pack2
                _mpack_path = (
                    Path(__file__).parent.parent
                    / "official_agents"
                    / "medical_coding"
                    / "agent_pack.json"
                )
                if _mpack_path.exists():
                    _mpack = json.loads(_mpack_path.read_text(encoding="utf-8"))
                    _mpack_agent, _, _, _ = _import_pack2(_mpack)
                    _medical_agent = AgentDefinition(
                        id="medical-coding-agent",
                        name=_mpack_agent.name,
                        description=_mpack_agent.description,
                        system_prompt=_mpack_agent.system_prompt or _medical_agent.system_prompt,
                        icon=_mpack_agent.icon,
                        category=_mpack_agent.category,
                        expert_ids=_mpack_agent.expert_ids or _medical_agent.expert_ids,
                        default_expert_id=_medical_agent.default_expert_id,
                        config=_mpack_agent.config,
                        is_prebuilt=True,
                        version=_mpack_agent.version,
                        status="published",
                    )
                    logger.info(
                        "A2A wiring: medical-coding-agent enriched from official pack "
                        "(version=%s, experts=%s)",
                        _mpack_agent.version,
                        _mpack_agent.expert_ids,
                    )
            except Exception as _mae:
                logger.warning(
                    "A2A wiring: medical-coding pack enrichment failed "
                    "error_type=%s",
                    type(_mae).__name__,
                )
            return DictAgentProvider({"medcoder-coding-review": _agent, "medical-coding-agent": _medical_agent})

        phase1_handler_raw = InboundHandler(
            phi_redactor=PHIRedactor(),
            planner=Planner(
                llm_call=_llm_call,
                config=PlannerConfig(sleep_fn=lambda _: None),
            ),
            delegator=Delegator(
                invoker=_expert_invoker,
                config=DelegatorConfig(sleep_fn=lambda _: None),
            ),
            aggregator=Aggregator(),
            agent_provider=_build_phase1_agent_provider(),
        )

        # Phase 3-B1 (2026-07-04): v1→v2 projection wrapper for
        # medical-coding-agent. The coding-expert returns v1
        # MedicalCodingOutputSchema (MedCodER 5-stage technical output).
        # For the public medical-coding-agent facade, we project v1 → v2
        # MedicalCodingAgentOutputV2 (Corti 8-field) in the response parts
        # so the A2A mainline returns the 8-field contract.
        # For medcoder-coding-review (internal engine), pass through v1.
        # Phase 4-F2 (2026-07-10): this handler now ALSO owns the medical-
        # coding-agent default runtime dispatch. When the A2A message:send
        # path is called for medical-coding-agent with no runtime_mode (or
        # runtime_mode="corti_like_fast"), we route directly to
        # CodingRuntimeDispatcher (G001 fast path, ~6-8s) instead of the
        # full InboundHandler 5-stage MedCODER pipeline (60s+ timeout).
        # Only explicit runtime_mode="medcoder_deep" falls through to the
        # inner InboundHandler (5-stage). Both entry points (unified
        # endpoint + A2A message:send) now default to corti_like_fast.
        class _MedicalCodingV2ProjectingHandler:
            """Wraps InboundHandler; routes medical-coding to fast path
            by default and projects v1→v2 for medcoder_deep responses."""

            def __init__(self, inner):
                self._inner = inner

            def handle(self, agent_id: str, request):
                import asyncio as _asyncio
                from app.icoder.agent_runtime.a2a_facade import (
                    run_medical_coding_a2a,
                )
                from app.icoder.agent_runtime.orchestrator.inbound_handler import (
                    InboundResponse,
                    extract_text_from_parts,
                )

                # Phase 4-F2 §4.2: medical-coding default runtime dispatch.
                # A2A message:send defaults to corti_like_fast (bypass 5-stage).
                if agent_id == "medical-coding-agent":
                    meta = request.metadata or {}
                    from app.services.dedicated_project_policy import (
                        DedicatedProjectPolicy,
                    )
                    project_policy_token = meta.get(
                        "_dedicated_project_policy_token"
                    )
                    is_dedicated_project_clone = isinstance(
                        project_policy_token,
                        DedicatedProjectPolicy,
                    )
                    public_agent_id = str(
                        meta.get("project_agent_id") or agent_id
                    )
                    source_runtime_agent_id = str(
                        meta.get("source_runtime_agent_id") or agent_id
                    )
                    execution_tenant_id = str(
                        meta.get("organization_id")
                        or meta.get("tenant_id")
                        or "default"
                    )
                    runtime_mode = meta.get("runtime_mode") or "corti_like_fast"
                    if (
                        runtime_mode != "medcoder_deep"
                        or is_dedicated_project_clone
                    ):
                        # Fast path: route to CodingRuntimeDispatcher directly.
                        from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                            redact_payload,
                        )
                        from icoder_runtime.backends.output_contract_validation import (
                            prepare_source_documents,
                        )
                        from app.services.result_attestation import (
                            ResultAttestationError,
                            verify_upstream_result_attestations,
                        )
                        raw_data_input = {}
                        for part in request.message.parts:
                            if not isinstance(part, dict) or part.get("kind") != "data":
                                continue
                            raw_data = part.get("data")
                            raw_value = (
                                raw_data.get("value")
                                if isinstance(raw_data, dict) else None
                            )
                            if isinstance(raw_value, dict):
                                raw_data_input.update(raw_value)
                        raw_upstream_results = raw_data_input.get("upstream_results")
                        if not isinstance(raw_upstream_results, list):
                            raw_upstream_results = []
                        attestation_org_id = str(
                            meta.get("organization_id")
                            or meta.get("tenant_id")
                            or "default"
                        )
                        if meta.get("upstream_result_attestations_verified") is not True:
                            try:
                                verify_upstream_result_attestations(
                                    raw_upstream_results,
                                    organization_id=attestation_org_id,
                                )
                            except ResultAttestationError:
                                return InboundResponse(
                                    kind="error",
                                    context_id=meta.get("context_id", ""),
                                    metadata={
                                        "run_id": meta.get("run_id", ""),
                                        "trace_id": meta.get("trace_id", ""),
                                        "agent_id": agent_id,
                                        "phi_redacted": True,
                                    },
                                    error={
                                        "code": "INVALID_UPSTREAM_ATTESTATION",
                                        "message": "An upstream Agent result could not be authenticated.",
                                    },
                                    http_status=400,
                                )
                        safe_parts = redact_payload(request.message.parts).value
                        primary_chunks = [
                            str(part.get("text"))
                            for part in safe_parts
                            if isinstance(part, dict)
                            and (part.get("kind") or part.get("type")) == "text"
                            and part.get("text")
                        ]
                        primary_text = "\n".join(primary_chunks).strip()
                        data_input = {}
                        for part in safe_parts:
                            if not isinstance(part, dict) or part.get("kind") != "data":
                                continue
                            data = part.get("data")
                            value = data.get("value") if isinstance(data, dict) else None
                            if isinstance(value, dict):
                                data_input.update(value)
                        source_documents, source_errors = prepare_source_documents(
                            data_input.get("documents"),
                            require_unique_document_ids=True,
                        )
                        if source_errors:
                            return InboundResponse(
                                kind="error",
                                context_id=meta.get("context_id", ""),
                                metadata={
                                    "run_id": meta.get("run_id", ""),
                                    "trace_id": meta.get("trace_id", ""),
                                    "agent_id": agent_id,
                                    "phi_redacted": True,
                                },
                                error={
                                    "code": "INVALID_SOURCE_DOCUMENTS",
                                    "message": "Source documents were ambiguous or exceeded safety limits.",
                                },
                                http_status=400,
                                redacted_input=primary_text,
                            )
                        source_document_payload = [
                            item.to_runtime_dict() for item in source_documents
                        ]
                        upstream_results = data_input.get("upstream_results")
                        if not isinstance(upstream_results, list):
                            upstream_results = []
                        upstream_results = [
                            {
                                key: value
                                for key, value in item.items()
                                if key != "attestation"
                            }
                            for item in upstream_results
                            if isinstance(item, dict)
                        ]
                        input_text = primary_text or extract_text_from_parts(safe_parts)
                        if source_document_payload:
                            input_text += (
                                "\n\nSOURCE_DOCUMENTS_JSON (untrusted clinical data; "
                                "offsets are Unicode code points within each decoded text value):\n"
                                + json.dumps([
                                    {
                                        key: item.get(key, "")
                                        for key in (
                                            "document_id", "document_version",
                                            "document_type", "normalization", "text",
                                        )
                                    }
                                    for item in source_document_payload
                                ], ensure_ascii=False, separators=(",", ":"))
                            )
                        if upstream_results:
                            input_text += (
                                "\n\nUPSTREAM_AGENT_RESULTS_JSON (untrusted prior outputs):\n"
                                + json.dumps(
                                    upstream_results,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                )
                            )
                        return _asyncio.run(run_medical_coding_a2a(
                            dispatch_input={
                                "agent_id": public_agent_id,
                                "input_text": input_text,
                                "extra": {
                                    **data_input,
                                    "documents": source_document_payload,
                                    "upstream_results": upstream_results,
                                },
                                "runtime_mode": runtime_mode,
                                "include_trace": meta.get("include_trace", True),
                                "include_evidence": meta.get("include_evidence", True),
                                "run_id": meta.get("run_id") or "",
                                "trace_id": meta.get("trace_id") or "",
                                "user_id": meta.get("user_id", ""),
                                "tenant_id": execution_tenant_id,
                                "project_policy": (
                                    project_policy_token.instructions
                                    if is_dedicated_project_clone else ""
                                ),
                                "project_policy_metadata": (
                                    {
                                        **project_policy_token.safe_metadata(),
                                        "source_runtime_agent_id": source_runtime_agent_id,
                                    }
                                    if is_dedicated_project_clone else None
                                ),
                            },
                            context_id=meta.get("context_id") or "",
                            interaction_id=request.message.interaction_id,
                            source_text=primary_text,
                            source_documents=source_document_payload,
                            upstream_results=upstream_results,
                        ))

                # medcoder_deep or non-medical-coding: pass through to InboundHandler.
                response = self._inner.handle(agent_id, request)
                if (
                    agent_id == "medical-coding-agent"
                    and response.kind == "message"
                ):
                    response = self._project_v1_to_v2(response)
                return response

            def _project_v1_to_v2(self, response):
                """Find v1 MedicalCodingOutputSchema in parts → project to v2.

                The Aggregator wraps each expert result as
                ``part.data = {"expert_id": ..., "result": <v1 schema>, ...}``.
                We detect v1 by inspecting ``data["result"]`` (preferred) or
                ``data`` itself (back-compat for flat v1 parts), then replace
                the whole part with a v2 data Part whose ``data`` is the 8-field
                ``MedicalCodingAgentOutputV2``. Orchestrator trace fields
                (expert_id, latency_ms, etc.) move into ``part.metadata``.
                """
                try:
                    from official_agents.medical_coding.schema import (
                        MedicalCodingOutputSchema,
                        MedicalCodingAgentOutputV2,
                    )
                    from app.icoder.agent_runtime.a2a_facade import (
                        medical_coding_schema_ref,
                    )
                except Exception:
                    return response  # schema not available, pass through

                run_id = (response.metadata or {}).get("run_id", "")
                schema_ref = medical_coding_schema_ref()
                new_parts = []
                for part in response.parts or []:
                    if not isinstance(part, dict) or part.get("kind") != "data":
                        new_parts.append(part)
                        continue
                    data = part.get("data") or {}
                    if not isinstance(data, dict):
                        new_parts.append(part)
                        continue
                    # Aggregator wraps expert result under data["result"].
                    inner = data.get("result") if isinstance(data.get("result"), dict) else None
                    v1_candidate = inner if inner is not None else data
                    is_v1 = (
                        "primary_diagnosis" in v1_candidate
                        or "extracted_diagnoses" in v1_candidate
                        or "review_conclusion" in v1_candidate
                    )
                    if not is_v1:
                        new_parts.append(part)
                        continue
                    try:
                        v1 = MedicalCodingOutputSchema.from_dict(v1_candidate)
                        v2 = MedicalCodingAgentOutputV2.from_legacy_v1(
                            v1, run_id=run_id
                        )
                        # Phase 3-B2 Loop 3 (Gap 4.3): pre-render Markdown
                        # for the chat UI's "Rendered" tab. Fallback-safe —
                        # if generation fails, we still ship the v2 dict.
                        v2_dict = v2.to_dict()
                        try:
                            from app.icoder.markdown_generator import (
                                generate_markdown,
                            )
                            v2_dict["markdown"] = generate_markdown(v2_dict)
                        except Exception as _me:
                            logger.warning(
                                "Markdown generation failed (non-fatal): %s",
                                _me,
                            )
                        part_meta = dict(part.get("metadata") or {})
                        # Stash orchestrator trace fields for observability.
                        for _k in ("expert_id", "priority", "critical", "attempt", "latency_ms", "ok"):
                            if _k in data:
                                part_meta[f"orchestrator_{_k}"] = data[_k]
                        part_meta.update({
                            "schema_ref": schema_ref,
                            "projected_from": "MedicalCodingOutputSchema/v1",
                            "phi_redacted": True,
                            "production_writeback_blocked": True,
                        })
                        new_parts.append({
                            "kind": "data",
                            "data": v2_dict,
                            "metadata": part_meta,
                        })
                    except Exception as _pe:
                        logger.warning(
                            "A2A v1→v2 projection failed: %s; passing through v1",
                            _pe,
                        )
                        new_parts.append(part)
                response.parts = new_parts
                response.metadata = dict(response.metadata or {})
                response.metadata["output_contract"] = schema_ref
                response.metadata["v1_to_v2_projected"] = True
                return response

        phase1_handler = _MedicalCodingV2ProjectingHandler(phase1_handler_raw)

        # Phase 3-D1 Task 5: 3 simple runnable agents (code-validation /
        # compliance-guardrail / note-completeness). These bypass the
        # orchestrator (Planner/Delegator/Aggregator) and call the
        # agent's governed entry point directly. Compliance Guardrail and Note
        # Completeness are local deterministic runtimes; Code Validation uses
        # a governed local catalog baseline with optional LLM/tool review. The
        # dispatch handler:
        #   1. Generates run_id + context_id (consistent with InboundHandler)
        #   2. Emits RunTrace events (USER_MESSAGE_RECEIVED + OUTPUT_GENERATED
        #      + COMPLETION) so /api/runtime/runs/{id}/trace works for them
        #   3. Calls agent.run(input_text, run_id=run_id)
        #   4. Wraps the result as a DataPart in an InboundResponse
        from app.icoder.agent_runtime.orchestrator.run_trace import (
            RunTraceStep,
            RunTraceStatus,
            emit_trace_event,
        )
        from app.icoder.agent_runtime.orchestrator.inbound_handler import (
            InboundResponse,
            extract_text_from_parts,
            make_context_id,
            make_message_id,
            make_run_id,
        )
        # Phase 3-D2 Task 3 — agent_id → MCP tool_name mapping.
        # The 3 simple agents route through the MCP dispatcher (single code
        # path for scope check + auth + trace + handler invoke) instead of
        # bypassing it. The handler functions (app/icoder/mcp/handlers/
        # {validate_codes,evaluate_compliance,check_documentation_gaps}.py)
        # wrap the agent.run() SSOT.
        _SIMPLE_AGENT_TOOLS: dict[str, str] = {
            "code-validation-agent": "validate_codes",
            "compliance-guardrail-agent": "evaluate_compliance",
            "note-completeness-agent": "check_documentation_gaps",
        }
        _SIMPLE_AGENT_PACK_DIRS: dict[str, str] = {
            "code-validation-agent": "code-validation",
            "compliance-guardrail-agent": "compliance-guardrail",
            "note-completeness-agent": "note-completeness",
        }

        def _simple_agent_pack(agent_id: str) -> dict[str, Any]:
            """Load the authoritative current Pack used by Hub and Agent Run."""
            import json as _json

            pack_dir = _SIMPLE_AGENT_PACK_DIRS[agent_id]
            pack_path = (
                Path(__file__).parent.parent
                / "official_agents"
                / pack_dir
                / "agent_pack.json"
            )
            return _json.loads(pack_path.read_text(encoding="utf-8"))

        def _simple_agent_schema_ref(agent_id: str) -> str:
            """Resolve A2A metadata from the same current Pack as Hub/Run."""
            pack = _simple_agent_pack(agent_id)
            schema_ref = str(
                (pack.get("output_contract") or {}).get("schema_ref") or ""
            )
            if not schema_ref:
                raise RuntimeError(f"missing output schema_ref for {agent_id}")
            return schema_ref

        class _SimpleAgentDispatchHandler:
            """Routes 3 simple agent_ids through the MCP dispatcher; falls
            through to the inner handler for everything else.

            Phase 3-D2 Task 3: previously this called agent.run() directly,
            bypassing the MCP dispatcher's scope check + trace emit. Now it
            constructs a lightweight request-like object and calls
            ``dispatch_tool()`` — single code path with the HTTP route, with
            zero HTTP overhead. The agent's required_scopes (coding:validate
            / compliance:evaluate / documentation:check) are pre-granted
            via the in-process AuthHeader, since the A2A route has already
            authenticated the caller (Phase 3-C1 wiring).
            """

            def __init__(self, inner):
                self._inner = inner

            def handle(self, agent_id: str, request):
                if agent_id not in _SIMPLE_AGENT_TOOLS:
                    return self._inner.handle(agent_id, request)
                return self._handle_simple(agent_id, request)

            def _contract_response(
                self,
                *,
                agent_id: str,
                result: dict[str, Any],
                input_text: str,
                run_id: str,
                context_id: str,
                request,
                redaction_entity_types: list[str],
                backend_provider: str,
                backend_type: str,
                runtime_mode: str,
            ) -> InboundResponse:
                """Project, validate and attest a dedicated Agent result."""
                import json as _json
                import time as _time

                from app.api.agent_run import map_backend_response
                from app.services.result_attestation import (
                    ResultAttestationError,
                    issue_result_attestation,
                )
                from icoder_runtime.backends.contracts import BackendResponse
                from icoder_runtime.backends.output_contract_validation import (
                    declared_optional_fields,
                )

                pack = _simple_agent_pack(agent_id)
                output_contract = pack.get("output_contract") or {}
                schema_ref = _simple_agent_schema_ref(agent_id)
                required_fields = list(output_contract.get("required_fields") or [])
                optional_fields = declared_optional_fields(output_contract)
                declared_fields = [*required_fields, *optional_fields]
                allowed_fields = set(declared_fields)

                candidate = dict(result)
                if agent_id == "code-validation-agent":
                    from official_agents.code_validation.agent import (
                        to_current_pack_candidate,
                    )

                    candidate = to_current_pack_candidate(candidate)
                elif agent_id == "note-completeness-agent":
                    candidate.setdefault("incomplete_sections", [])
                    candidate.setdefault("conflicts", [])
                    candidate.setdefault("corrected_draft", "")

                # Compatibility/audit fields remain internal. Missing required
                # fields stay missing so the common validator fails closed.
                candidate = {
                    key: value
                    for key, value in candidate.items()
                    if key in allowed_fields
                }
                requires_review = (
                    str((pack.get("manifest") or {}).get("human_review") or "")
                    == "required"
                )
                response = BackendResponse(
                    status="requires_review" if requires_review else "pass",
                    summary=str(
                        candidate.get("summary")
                        or candidate.get("review_conclusion")
                        or ""
                    ),
                    backend_provider=backend_provider,
                    backend_type=backend_type,
                    fallback_used=bool(result.get("degraded")),
                    markdown=_json.dumps(
                        candidate,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
                public = map_backend_response(
                    agent_id=agent_id,
                    run_id=run_id,
                    trace_id=str(request.metadata.get("trace_id") or run_id),
                    runtime_mode=runtime_mode,
                    resp=response,
                    include_trace=False,
                    include_evidence=False,
                    agent_pack=pack,
                    source_text=input_text,
                    upstream_results=[],
                    t0=_time.perf_counter(),
                )
                if public.error:
                    extraction = public.result.get("structured_extraction") or {}
                    emit_trace_event(
                        run_id,
                        RunTraceStep.COMPLETION,
                        status=RunTraceStatus.FAILED,
                        safe_metadata={
                            "agent_id": agent_id,
                            "reason": "output_contract_violation",
                        },
                    )
                    return InboundResponse(
                        kind="error",
                        context_id=context_id,
                        metadata={
                            "run_id": run_id,
                            "agent_id": agent_id,
                            "backend_provider": backend_provider,
                            "backend_type": backend_type,
                            "output_contract": schema_ref,
                            "phi_redacted": True,
                            "redaction_entity_types": redaction_entity_types,
                            "production_writeback_blocked": True,
                            "manual_review_required": True,
                            "missing_required_fields": list(
                                extraction.get("missing_required_fields") or []
                            ),
                            "invalid_field_types": list(
                                extraction.get("invalid_field_types") or []
                            ),
                            "invalid_field_schemas": list(
                                extraction.get("invalid_field_schemas") or []
                            ),
                        },
                        error={
                            "code": "OUTPUT_CONTRACT_VIOLATION",
                            "message": (
                                "Dedicated Agent output did not satisfy the "
                                "current Agent Pack contract."
                            ),
                        },
                        http_status=503,
                        redacted_input=input_text,
                    )

                public_result = {
                    field: public.result[field]
                    for field in declared_fields
                    if field in public.result
                }
                tenant_id = str(
                    request.metadata.get("organization_id") or "default"
                )
                try:
                    result_attestation = issue_result_attestation(
                        run_id=run_id,
                        agent_id=agent_id,
                        schema_ref=schema_ref,
                        organization_id=tenant_id,
                        result=public_result,
                    )
                except ResultAttestationError as exc:
                    logger.error(
                        "Dedicated A2A attestation failed agent_id=%s error_type=%s",
                        agent_id,
                        type(exc).__name__,
                    )
                    emit_trace_event(
                        run_id,
                        RunTraceStep.COMPLETION,
                        status=RunTraceStatus.FAILED,
                        safe_metadata={
                            "agent_id": agent_id,
                            "reason": "result_attestation_failed",
                        },
                    )
                    return InboundResponse(
                        kind="error",
                        context_id=context_id,
                        metadata={
                            "run_id": run_id,
                            "agent_id": agent_id,
                            "phi_redacted": True,
                            "production_writeback_blocked": True,
                        },
                        error={
                            "code": "RESULT_ATTESTATION_FAILED",
                            "message": (
                                "The Agent result authenticity proof could not "
                                "be created."
                            ),
                        },
                        http_status=503,
                        redacted_input=input_text,
                    )

                emit_trace_event(
                    run_id,
                    RunTraceStep.COMPLETION,
                    status=RunTraceStatus.OK,
                    safe_metadata={
                        "agent_id": agent_id,
                        "backend_provider": backend_provider,
                        "backend_type": backend_type,
                    },
                )
                return InboundResponse(
                    kind="message",
                    message_id=make_message_id(),
                    context_id=context_id,
                    role="agent",
                    parts=[{
                        "kind": "data",
                        "data": public_result,
                        "metadata": {
                            "schema_ref": schema_ref,
                            "agent_ref": str(pack.get("agent_ref") or ""),
                            "result_attestation": result_attestation,
                            "phi_redacted": True,
                            "production_writeback_blocked": True,
                            "orchestrator_expert_id": agent_id,
                            "orchestrator_latency_ms": 0,
                            "orchestrator_ok": True,
                            "backend_provider": backend_provider,
                            "backend_type": backend_type,
                        },
                    }],
                    metadata={
                        "run_id": run_id,
                        "agent_id": agent_id,
                        "interaction_id": request.message.interaction_id,
                        "backend_provider": backend_provider,
                        "backend_type": backend_type,
                        "output_contract": schema_ref,
                        "result_attestation": result_attestation,
                        "provider_latency_ms": public.latency_ms,
                        "phi_redacted": True,
                        "redaction_entity_types": redaction_entity_types,
                        "redaction_applied": bool(redaction_entity_types),
                        "production_writeback_blocked": True,
                        "manual_review_required": public.manual_review_required,
                    },
                    http_status=200,
                    redacted_input=input_text,
                )

            def _handle_simple(self, agent_id: str, request) -> InboundResponse:
                import asyncio as _asyncio
                from types import SimpleNamespace as _NS
                from app.icoder.mcp.server import dispatch_tool
                from app.icoder.mcp.auth import AuthHeader

                run_id = make_run_id()
                # The route has already created or tenant-validated this
                # context. Reusing it is required for real multi-turn A2A;
                # generating another ID here would orphan the persisted turn.
                context_id = request.message.context_id or make_context_id()
                # Trace step 1: user message received
                emit_trace_event(
                    run_id, RunTraceStep.USER_MESSAGE_RECEIVED,
                    safe_metadata={
                        "agent_id": agent_id,
                        "input_parts": len(request.message.parts),
                    },
                )
                # Simple agents bypass the orchestrator, so the planner step
                # is SKIPPED — emit it so the RunTrace timeline still shows
                # all 9 steps (Corti parity).
                emit_trace_event(
                    run_id, RunTraceStep.PLANNER_SELECTED_EXPERTS,
                    status=RunTraceStatus.SKIPPED,
                    safe_metadata={"reason": "simple_agent_no_orchestrator"},
                )
                # Extract and redact before the deterministic Agent/MCP path.
                # This path bypasses InboundHandler, so it must enforce the
                # same PHI boundary itself; only redacted text may reach a
                # tool, Context persistence, trace metadata, or an error.
                raw_input_text = extract_text_from_parts(request.message.parts)
                redaction = PHIRedactor().redact(raw_input_text)
                input_text = redaction.redacted_text

                # Code Validation routes to its governed v2 Agent directly —
                # bypassing
                # the validate_codes MCP tool which stays v1 (RuleEngine)
                # for other MCP consumers. The two local rule Agents go
                # through the MCP dispatcher.
                if agent_id == "code-validation-agent":
                    return self._handle_code_validation_v2(
                        agent_id, input_text, run_id, context_id, request,
                        redaction.entity_types,
                    )

                # Map agent_id → MCP tool_name + build tool arguments.
                tool_name = _SIMPLE_AGENT_TOOLS[agent_id]
                if agent_id == "note-completeness-agent":
                    tool_args: dict = {"encounter_text": input_text}
                else:
                    # compliance-guardrail takes a coding_set.
                    # The agent's _normalize_input parses JSON input_text —
                    # pass it through as coding_set (dict) so the handler
                    # can re-serialize. If input_text isn't JSON, fall back
                    # to an empty coding_set with encounter_text=input_text.
                    import json as _json
                    try:
                        coding_set = _json.loads(input_text) if input_text else {}
                        if not isinstance(coding_set, dict):
                            coding_set = {}
                        tool_args = {"coding_set": coding_set}
                    except Exception:
                        tool_args = {"coding_set": {}, "encounter_text": input_text}

                # Build a lightweight request-like object so dispatch_tool
                # can read app.state (phi_redactor etc.) and state (run_id,
                # context_id, pre-resolved auth_header). The 3 simple tools
                # have auth_config=None, so dispatch_tool skips auth
                # resolution and reads state.auth_header instead — we
                # pre-set it with all 3 required scopes granted (the A2A
                # route already authenticated the caller).
                fake_state = _NS()
                fake_state.context_id = context_id
                fake_state.run_id = run_id
                fake_state.mcp_run_auth_context = None
                fake_state.auth_header = AuthHeader(
                    kind="none",
                    granted_scopes=[
                        "coding:validate",
                        "compliance:evaluate",
                        "documentation:check",
                    ],
                    redacted_view="(in-process, all scopes granted)",
                )
                fake_request = _NS()
                fake_request.app = app  # closure: lifespan(app)
                fake_request.state = fake_state

                try:
                    dispatch_result = _asyncio.new_event_loop().run_until_complete(
                        dispatch_tool(
                            tool_name, tool_args, fake_request,
                            run_id=run_id,
                        )
                    )
                    # dispatch_tool returns {"content": <handler result>, "isError": False}
                    result = dispatch_result.get("content") or {}
                except Exception as e:
                    # MCPError / MCPAuthError / any other failure — emit
                    # COMPLETION=FAILED and return an error envelope.
                    emit_trace_event(
                        run_id, RunTraceStep.COMPLETION,
                        status=RunTraceStatus.FAILED,
                        safe_metadata={
                            "tool_name": tool_name,
                            "error": type(e).__name__,
                        },
                    )
                    return InboundResponse(
                        kind="error",
                        context_id=context_id,
                        metadata={
                            "run_id": run_id,
                            "agent_id": agent_id,
                            "phi_redacted": True,
                            "production_writeback_blocked": True,
                            "redaction_entity_types": redaction.entity_types,
                        },
                        error={
                            "code": "INTERNAL_ERROR",
                            "message": f"Tool execution failed ({type(e).__name__}).",
                        },
                        http_status=500,
                        redacted_input=input_text,
                    )
                # Trace step: output generated + completion
                emit_trace_event(
                    run_id, RunTraceStep.OUTPUT_GENERATED,
                    safe_metadata={
                        "review_conclusion": result.get("review_conclusion", ""),
                        "issues_count": len(result.get("issues_found", []) or []),
                    },
                )
                return self._contract_response(
                    agent_id=agent_id,
                    result=result,
                    input_text=input_text,
                    run_id=run_id,
                    context_id=context_id,
                    request=request,
                    redaction_entity_types=redaction.entity_types,
                    backend_provider=(
                        "icoder.rule-engine.v1"
                        if agent_id == "compliance-guardrail-agent"
                        else "icoder.documentation-rule-engine.v1"
                    ),
                    backend_type="rule_engine",
                    runtime_mode=f"a2a_dedicated_{agent_id}",
                )

            def _handle_code_validation_v2(
                self, agent_id: str, input_text: str,
                run_id: str, context_id: str, request,
                redaction_entity_types: list[str],
            ) -> InboundResponse:
                """Invoke the governed catalog baseline with optional semantic
                LLM/tool review — bypassing
                the v1 ``validate_codes`` MCP tool. Other MCP consumers of
                ``validate_codes`` (if any) stay on v1 (RuleEngine).
                """
                import asyncio as _asyncio
                from official_agents.code_validation.agent import run as _cv_run

                try:
                    result = _asyncio.new_event_loop().run_until_complete(
                        _cv_run(input_text, run_id=run_id)
                    )
                    if not isinstance(result, dict):
                        result = {"raw": str(result)}
                except Exception as e:
                    emit_trace_event(
                        run_id, RunTraceStep.COMPLETION,
                        status=RunTraceStatus.FAILED,
                        safe_metadata={
                            "agent_id": agent_id,
                            "error": type(e).__name__,
                        },
                    )
                    return InboundResponse(
                        kind="error",
                        context_id=context_id,
                        metadata={
                            "run_id": run_id,
                            "agent_id": agent_id,
                            "phi_redacted": True,
                            "redaction_entity_types": redaction_entity_types,
                            "production_writeback_blocked": True,
                        },
                        error={
                            "code": "INTERNAL_ERROR",
                            "message": f"Code validation failed ({type(e).__name__}).",
                        },
                        http_status=500,
                        redacted_input=input_text,
                    )
                # Trace step: output generated + completion
                emit_trace_event(
                    run_id, RunTraceStep.OUTPUT_GENERATED,
                    safe_metadata={
                        "review_conclusion": result.get("review_conclusion", ""),
                        "validated_codes_count": len(result.get("validated_codes", []) or []),
                        "cross_code_issues_count": len(result.get("cross_code_issues", []) or []),
                        "clinical_asset_ids": "+".join(
                            str(item)
                            for item in (
                                (result.get("trace_refs") or {}).get(
                                    "catalog_asset_ids"
                                )
                                or []
                            )
                            if item
                        ),
                        "clinical_asset_versions": "+".join(
                            str(item)
                            for item in (
                                (result.get("trace_refs") or {}).get(
                                    "catalog_asset_versions"
                                )
                                or []
                            )
                            if item
                        ),
                        "clinical_asset_authority_statuses": "+".join(
                            str(item)
                            for item in (
                                (result.get("trace_refs") or {}).get(
                                    "catalog_authority_statuses"
                                )
                                or []
                            )
                            if item
                        ),
                        "clinical_asset_license_statuses": "+".join(
                            str(item)
                            for item in (
                                (result.get("trace_refs") or {}).get(
                                    "catalog_license_statuses"
                                )
                                or []
                            )
                            if item
                        ),
                        "clinical_asset_integrity_verified": bool(
                            (result.get("trace_refs") or {}).get(
                                "catalog_integrity_verified"
                            )
                        ),
                        "semantic_enhancement_used": bool(
                            (result.get("trace_refs") or {}).get(
                                "semantic_enhancement_used"
                            )
                        ),
                    },
                )
                return self._contract_response(
                    agent_id=agent_id,
                    result=result,
                    input_text=input_text,
                    run_id=run_id,
                    context_id=context_id,
                    request=request,
                    redaction_entity_types=redaction_entity_types,
                    backend_provider="icoder.governed-code-validation.v1",
                    backend_type="hybrid",
                    runtime_mode="a2a_governed_code_validation",
                )

        phase1_handler = _SimpleAgentDispatchHandler(phase1_handler)

        # All remaining visible official packs with an explicit
        # backend_provider share the same A2A execution adapter as the
        # unified Agent Run endpoint. This makes every advertised Hub A2A URL
        # executable instead of falling through to agent_not_found.
        from app.icoder.agent_runtime.provider_a2a_handler import (
            ProviderA2AHandler,
        )
        _provider_a2a_handler = ProviderA2AHandler(
            Path(__file__).parent.parent / "official_agents"
        )

        class _OfficialProviderDispatchHandler:
            def __init__(self, inner, provider_handler):
                self._inner = inner
                self._provider_handler = provider_handler

            def handle(self, agent_id: str, request):
                if self._provider_handler.can_handle_candidate(agent_id):
                    return self._provider_handler.handle(agent_id, request)
                return self._inner.handle(agent_id, request)

        phase1_handler = _OfficialProviderDispatchHandler(
            phase1_handler, _provider_a2a_handler
        )

        from app.icoder.agent_runtime.cdi_a2a_handler import CDIA2AHandler
        _cdi_a2a_handler = CDIA2AHandler()

        class _CDIDispatchHandler:
            def __init__(self, inner, cdi_handler):
                self._inner = inner
                self._cdi_handler = cdi_handler

            def handle(self, agent_id: str, request):
                if agent_id == self._cdi_handler.AGENT_ID:
                    return self._cdi_handler.handle(agent_id, request)
                return self._inner.handle(agent_id, request)

        phase1_handler = _CDIDispatchHandler(phase1_handler, _cdi_a2a_handler)

        # Project clones of dedicated clinical runtimes have no
        # backend_provider to resolve. Delegate to the exact source adapter,
        # then restore project identity for proof, history and trace ownership.
        from app.icoder.agent_runtime.tenant_clone_a2a_dispatch_handler import (
            TenantCloneA2ADispatchHandler,
        )
        phase1_handler = TenantCloneA2ADispatchHandler(phase1_handler)

        # Connector graphs are Agent policy, not a Provider implementation
        # detail. Apply the tenant-owned graph outside every A2A dispatch path
        # so dedicated coding/CDI adapters cannot bypass it. Provider-backed
        # handlers receive a pre-executed marker and therefore run it once.
        from app.icoder.agent_runtime.connector_graph_dispatch_handler import (
            ConnectorGraphDispatchHandler,
        )
        phase1_handler = ConnectorGraphDispatchHandler(phase1_handler)

        def _phase1_agent_provider(agent_id: str):
            if agent_id == "medcoder-coding-review":
                return medcoder_coding_review_card()
            if agent_id == "medical-coding-agent":
                return medical_coding_agent_card()
            if agent_id == "code-validation-agent":
                return code_validation_agent_card()
            if agent_id == "compliance-guardrail-agent":
                return compliance_guardrail_agent_card()
            if agent_id == "note-completeness-agent":
                return note_completeness_agent_card()
            if agent_id == _cdi_a2a_handler.AGENT_ID:
                import json as _json
                from app.icoder.agent_runtime.a2a.agent_card import (
                    agent_card_from_pack,
                )
                _cdi_pack_path = (
                    Path(__file__).parent.parent
                    / "official_agents"
                    / "clinical-documentation-improvement-agent"
                    / "agent_pack.json"
                )
                return agent_card_from_pack(
                    _json.loads(_cdi_pack_path.read_text(encoding="utf-8"))
                )
            pack = _provider_a2a_handler.pack_for(agent_id)
            if pack is not None:
                from app.icoder.agent_runtime.a2a.agent_card import (
                    agent_card_from_pack,
                )
                return agent_card_from_pack(pack)
            return None

        _phase1_agent_provider.agent_ids = tuple(sorted({
            *_provider_a2a_handler.agent_ids,
            _cdi_a2a_handler.AGENT_ID,
        }))
        # The standard root well-known URI can describe only one Agent. Keep
        # tenant/private Agents behind authenticated per-Agent discovery and
        # publish the public Medical Coding Agent as the truthful default.
        _phase1_agent_provider.default_agent_id = "medical-coding-agent"

        def _phase1_expert_caller(expert_id: str, body: dict):
            from app.icoder.agent_runtime.a2a.errors import agent_not_found
            raise agent_not_found(expert_id)

        mount_a2a(
            app,
            handler=phase1_handler,
            agent_provider=_phase1_agent_provider,
            expert_caller=_phase1_expert_caller,
        )
        _a2a_task_runtime = getattr(app.state, "a2a_task_runtime", None)
        if _a2a_task_runtime is not None:
            await _a2a_task_runtime.start(app)
            logger.info("A2A durable Task runtime started")
        logger.info(
            "A2A v0.3 package mounted (fail-closed test LLM mode)"
            if _phase1_stub_llm
            else "A2A v0.3 package mounted (real wiring)"
        )

        # ── M2: Mount MCP server (5 MedCodER tools) ──
        # The MCP server reuses the same MedCodERStrategy that the A2A
        # CodingExpert path uses (via _hybrid_adapter._strategy). This
        # guarantees one BGE-M3 + FAISS load is shared across both routes.
        try:
            from app.icoder.mcp import mount_mcp
            from pathlib import Path as _Path
            _mcp_pack_path = (
                _Path(__file__).parent.parent
                / "official_agents"
                / "medcoder-coding-review"
                / "agent_pack.json"
            )
            _mcp_pack_tools: list[dict] = []
            if _mcp_pack_path.is_file():
                import json as _json
                _mcp_pack_tools = _json.loads(
                    _mcp_pack_path.read_text(encoding="utf-8"),
                ).get("tools", [])

            _mcp_strategy = (
                getattr(_hybrid_adapter, "_strategy", None)
                if _hybrid_adapter is not None
                else None
            )
            if _mcp_strategy is not None:
                # Optional PHI redactor (fail-closed when missing + ctx_id).
                _phi_redactor = None
                try:
                    from app.icoder.agent_runtime.orchestrator.phi_redactor import (
                        PHIRedactor,
                    )
                    _phi_redactor = PHIRedactor()
                except Exception:
                    _phi_redactor = None

                mount_mcp(
                    app,
                    strategy=_mcp_strategy,
                    phi_redactor=_phi_redactor,
                    agent_pack_tools=_mcp_pack_tools,
                )
                logger.info(
                    "MCP server mounted (5 MedCodER tools, strategy=%s, "
                    "phi_redactor=%s)",
                    type(_mcp_strategy).__name__,
                    "real" if _phi_redactor is not None else "fail-closed",
                )
            else:
                logger.warning(
                    "MCP mount skipped: no MedCodERStrategy available "
                    "(hybrid_adapter=%s)",
                    _hybrid_adapter,
                )
        except Exception as e:
            logger.warning("MCP mount skipped error_type=%s", type(e).__name__)
    except Exception as e:
        logger.warning("A2A v0.3 mount skipped error_type=%s", type(e).__name__)
    # Start runtime timeout checker (background task)
    import asyncio as _asyncio
    async def _check_timeouts():
        from app.services.runtime import runtime_registry
        while True:
            await _asyncio.sleep(300)  # Every 5 minutes
            try:
                for case_id in runtime_registry.stale_cases(max_age_hours=4):
                    rt = runtime_registry.get(case_id)
                    if rt:
                        action = rt.check_timeout()
                        if action:
                            logger.warning(f"Runtime timeout: {case_id} in state {rt.state.value} → {action}")
            except Exception:
                pass
    _timeout_task = _asyncio.create_task(_check_timeouts())
    app.state.runtime_timeout_task = _timeout_task
    logger.info("Runtime timeout checker started")

    # ── M2a Run Trace recorder (wired into HybridCodingAdapter + AgentRunner) ──
    # M2b will consume this; M2a exposes it for platform-wide run tracking.
    from icoder_runtime.m2a.recorder import M2aRecorder
    from icoder_runtime.m2a.run_trace import RunTraceService
    m2a_recorder = M2aRecorder(
        run_trace=RunTraceService(),
        default_agent_ref="icoder_runtime",
    )
    app.state.m2a_recorder = m2a_recorder
    logger.info("M2a recorder: wired into Runtime (recorder=%s)", "active" if m2a_recorder.is_active() else "inactive")

    # ── Version metadata (M3-0 Commit 8) ──
    # Read once at startup from data/versions.json. The report renderer
    # reads these from app.state.icoder_versions via the API endpoint.
    import json as _json_versions
    from pathlib import Path as _PathVersions
    _versions_path = _PathVersions(__file__).parent.parent / "data" / "versions.json"
    try:
        with open(_versions_path, encoding="utf-8") as _vf:
            app.state.icoder_versions = _json_versions.load(_vf)
    except Exception as _e:
        logger.warning(f"versions.json load failed: {_e!r}; using defaults")
        # Phase D3 (2026-06-26): default to the canonical MedCodER agent_ref.
        app.state.icoder_versions = {
            "model_version": "unknown",
            "code_dict_version": "unknown",
            "rule_version": "unknown",
            "agent_version": "icoder/medcoder-coding-review-agent@1.0.0",
            "data_asset_version": "iCoDerA v1.0.0",
        }

    yield
    logger.info("Shutting down")
    _a2a_task_runtime = getattr(app.state, "a2a_task_runtime", None)
    if _a2a_task_runtime is not None:
        await _a2a_task_runtime.stop()
    _connector_runtime = getattr(app.state, "connector_runtime", None)
    if _connector_runtime is not None:
        await _connector_runtime.aclose()
    # Phase 3-C0 A2 (2026-07-05): cancel the runtime timeout checker
    # background task so it doesn't leak as a "Task was destroyed but it
    # is pending" warning during TestClient / uvicorn shutdown.
    _timeout_task = getattr(app.state, "runtime_timeout_task", None)
    if _timeout_task is not None and not _timeout_task.done():
        _timeout_task.cancel()
        try:
            await _timeout_task
        except _asyncio.CancelledError:
            pass
    # The BGE/FAISS worker is a native multiprocessing child. Explicitly
    # close it on every lifespan exit; otherwise repeated TestClient/uvicorn
    # lifespans leave orphaned torch workers that retain gigabytes of virtual
    # memory and can destabilize the desktop host.
    _medcoder_retriever = getattr(app.state, "medcoder_retriever", None)
    if _medcoder_retriever is not None and hasattr(_medcoder_retriever, "close"):
        try:
            await _asyncio.to_thread(_medcoder_retriever.close)
        except Exception as _close_error:
            logger.warning(
                "MedCodER retriever shutdown failed (%s)",
                type(_close_error).__name__,
            )
        finally:
            app.state.medcoder_retriever = None
    # The backend provider registry holds a process-global lazy callback to
    # ``app.state.platform_gateway``.  Clear it when this application
    # lifespan ends; otherwise a later app/test lifespan can resolve a stale
    # mock or closed gateway and turn an intended ``llm_unavailable`` failure
    # into order-dependent behaviour.
    set_gateway_lookup(None)
    # Release the cached Fast/MedCodER runtime instances together with the
    # gateway callback. A later lifespan will construct fresh, correctly
    # policy-bound runtimes.
    reset_dispatcher()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="面向中国医院病案首页与医保结算清单场景的编码审核智能体",
    lifespan=lifespan,
)

# CORS (static allowlist for the Console SPA — see settings.CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 7 Gate 6 §11.1 — Partner CORS enforcement (per-client allowed_origins).
# Layered AFTER CORSMiddleware so it runs BEFORE the static layer on partner
# routes (/api/v1/agents/, /api/v1/runs/, /api/embedded/, /examples/).
# For an Origin matching any OAuthClient.allowed_origins, this middleware
# echoes the Origin and lets the request through; otherwise 403.
try:
    from app.middleware.partner_cors import PartnerCORSMiddleware
    app.add_middleware(PartnerCORSMiddleware)
    app.state._partner_cors_middleware_installed = True
    logger.info("PartnerCORSMiddleware installed at module load time")
except Exception as _partner_cors_e:
    logger.warning(f"PartnerCORSMiddleware install skipped: {_partner_cors_e}")

# E1.1 (2026-06-26): MCP context_id middleware must be added at module
# load time, BEFORE the lifespan runs. Starlette eagerly builds
# ``middleware_stack`` on the first ``__call__`` (which is the lifespan
# startup scope). Once that happens, ``app.add_middleware()`` raises
# RuntimeError("Cannot add middleware after an application has started").
# Pre-fix: mount_mcp() was called from inside the lifespan and tried to
# add the context_id middleware then → the whole MCP mount was skipped.
# This install is idempotent: ``mount_mcp`` checks for the attribute on
# ``app.state`` and skips the duplicate middleware add.
try:
    from app.icoder.mcp.server import _context_id_middleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=_context_id_middleware)
    app.state._mcp_context_id_middleware_installed = True
    logger.info("MCP context_id middleware installed at module load time")
except Exception as _mw_e:
    logger.warning(f"MCP context_id middleware install skipped: {_mw_e}")

# Phase 1.0 (2026-06-30): Tenant header middleware (Corti parity). Reads
# ``Tenant-Name`` / ``X-Tenant``, cross-checks with JWT ``org_id``, and —
# in cloud mode — makes the header mandatory on authenticated calls.
# OAuth itself is exempt so first-time callers can bootstrap a token.
try:
    from app.middleware.tenant_extractor import TenantHeaderMiddleware
    app.add_middleware(TenantHeaderMiddleware)
    app.state._tenant_middleware_installed = True
    logger.info("TenantHeaderMiddleware installed at module load time")
except Exception as _tenant_e:
    logger.warning(f"TenantHeaderMiddleware install skipped: {_tenant_e}")


# Connector request schemas are intentionally strict and may reject a body
# before the route-level secret scanner runs.  FastAPI's default validation
# response reflects the rejected ``input`` value, which could echo an
# accidentally supplied token.  Strip inputs only on this sensitive resource
# family while preserving the standard error shape and all other handlers.
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api/v2/agentic/agents/") and "/connectors" in request.url.path:
        safe_errors = []
        for error in exc.errors():
            safe_error = dict(error)
            safe_error.pop("input", None)
            safe_errors.append(safe_error)
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(safe_errors)},
        )
    return await request_validation_exception_handler(request, exc)


# Global exception handler — only catches truly unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from fastapi import HTTPException as FastAPIHTTPException
    # Pass through HTTPException (let FastAPI's built-in handler process it)
    if isinstance(exc, FastAPIHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers if hasattr(exc, "headers") else None,
        )
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc) if settings.DEBUG else "An error occurred"},
    )


# Health check
@app.get("/api/health")
async def health_check():
    from app.services.prerecorded_media_decoder import (
        prerecorded_media_decoder_snapshot,
    )
    from app.services.stream_media_decoder import stream_media_decoder_snapshot

    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "medcoder_index_ready": getattr(app.state, "medcoder_index_ready", False),
        "medcoder_index_loading": getattr(app.state, "medcoder_index_loading", False),
        "medcoder_index_error": getattr(app.state, "medcoder_index_error", None),
        "medcoder_retriever_mode": getattr(
            app.state, "medcoder_retriever_mode", "local_disabled"
        ),
        "medcoder_retriever_worker_version": getattr(
            app.state, "medcoder_retriever_worker_version", ""
        ),
        "medcoder_retriever_index_version": getattr(
            app.state, "medcoder_retriever_index_version", ""
        ),
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "stream_media_decoder": stream_media_decoder_snapshot(),
        "prerecorded_media_decoder": prerecorded_media_decoder_snapshot(),
        "connector_runtime": (
            app.state.connector_runtime.status()
            if getattr(app.state, "connector_runtime", None) is not None
            else {"configured": False, "live_external_verified": False}
        ),
    }


# Register API routers
from app.api.auth import router as auth_router
from app.api.encounters import router as encounters_router
from app.api.admin import router as admin_router
from app.api.codes import router as codes_router
from app.api.billing import router as billing_router
from app.api.keys import router as keys_router
from app.api.team import router as team_router
from app.api.usage import router as usage_router
from app.api.oauth import router as oauth_router
from app.api.agents import router as agents_router
from app.api.websocket import router as ws_router
from app.api.organizations import router as organizations_router
from app.api.platform_environments import router as platform_environments_router
from app.api.platform_api_clients import router as platform_api_clients_router
from app.api.platform_tenants import router as platform_tenants_router
from app.api.model_catalog import router as model_catalog_router
from app.api.clinical_model_packages import router as clinical_model_packages_router
from app.api.tools import router as tools_router
from app.api.runtime_platform import router as runtime_platform_router
from app.api.runtime_platform import runtime_router as standard_runtime_router
from app.api.compliance import router as compliance_router
from app.api.medical_docs import router as medical_docs_router
from app.api.embedded import router as embedded_router
from app.api.preview_sessions import router as preview_sessions_router
from app.api.drg import router as drg_router
from app.api.patient_context import router as patient_context_router  # A1C.3
from app.api.agent_connectors import router as agent_connectors_router
from app.api.agentic_observability import router as agentic_observability_router
from app.api.agentic_context_resources import (
    artifact_object_router,
    router as agentic_context_resources_router,
)
from app.api.examples import router as examples_router
from app.api.runs import router as runs_router
from app.api.v2_tools_coding import router as v2_tools_coding_router
from app.api.v2_tools_facts import router as v2_tools_facts_router
from app.api.v2_tools_streams import router as v2_tools_streams_router
from app.api.v2_tools_guided_document import router as v2_tools_guided_document_router
from app.api.v2_tools_sections_templates import router as v2_tools_sections_templates_router
from app.api.v2_tools_documents_classic import router as v2_tools_documents_classic_router
from app.api.v2_tools_stt import router as v2_tools_stt_router
from app.api.icoder_agents_hub import router as icoder_agents_hub_router
from app.api.customers import router as customers_router
from app.api.templates import router as templates_router
from app.api.tickets import router as tickets_router
from app.api.run_trace import router as run_trace_router
from app.api.coding_predict import router as coding_predict_router
from app.api.agent_run import router as agent_run_router
from app.api.coding_compliance import router as coding_compliance_router
from app.api.cdi import router as cdi_router
from app.api.experts import router as experts_router
from app.api.agent_cards import router as agent_cards_router
from app.api.presets import router as presets_router
from app.middleware.rate_limit import rate_limit_middleware
from app.middleware.request_body_limit import RequestBodyLimitMiddleware
from app.middleware.auth import get_current_user, security


_INFERENCE_JSON_MAX_BYTES = 1024 * 1024
_BOUNDED_INFERENCE_PATHS = frozenset({
    "/api/v2/tools/extract-facts",
    "/api/v2/tools/guided-documents",
})


# Rate limiting middleware
app.middleware("http")(rate_limit_middleware)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_bytes=_INFERENCE_JSON_MAX_BYTES,
    paths=_BOUNDED_INFERENCE_PATHS,
)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_bytes=7_100_000,
    paths=(),
    path_prefixes=("/api/v2/agentic/contexts",),
)

app.include_router(auth_router)
app.include_router(encounters_router)
app.include_router(codes_router)
app.include_router(billing_router)
app.include_router(keys_router)
app.include_router(team_router)
app.include_router(usage_router)
app.include_router(oauth_router)
app.include_router(agents_router)             # /rest/v1/agent_definitions/* (Phase 2.1-C Corti-style)
app.include_router(admin_router)
app.include_router(ws_router)
app.include_router(v2_tools_coding_router)         # Phase 1.1 (2026-06-30) /api/v2/tools/coding (Corti §3.1 parity)
app.include_router(v2_tools_facts_router)          # Phase 1.2 cycle 1 (2026-06-30) /api/v2/tools/extract-facts (Corti §3.2 / §13.4 FactsR™)
app.include_router(v2_tools_streams_router)        # Phase 1.2 cycle 2 (2026-06-30) /api/v2/tools/streams/{id} (Corti §13.3/§13.4 Streams WSS)
app.include_router(v2_tools_guided_document_router) # Phase 1.2 cycle 3 (2026-06-30) /api/v2/tools/guided-documents/ (Corti §13.4 Guided Documents, templateRef + ephemeral only)
app.include_router(v2_tools_sections_templates_router) # Corti-compatible tenant template/section discovery
app.include_router(v2_tools_documents_classic_router) # Documents Classic saved lifecycle compatibility
app.include_router(v2_tools_stt_router)              # Corti-compatible persisted STT transcript discovery
app.include_router(icoder_agents_hub_router)          # Phase 3-B1 (2026-07-04) /api/icoder/agents/hub (Corti-style Agent Hub, pack-mastered)
app.include_router(customers_router)             # /api/customers/* (Corti parity)
app.include_router(templates_router)             # /api/templates/* (Templates Beta — Corti parity)
app.include_router(tickets_router)               # /api/tickets/* (Tickets Portal — Corti parity)
app.include_router(run_trace_router)             # /api/runtime/runs/{run_id}/trace (Phase 3-D1 Task 4)
app.include_router(coding_predict_router)        # /api/v1/coding/predict (G001 refactor 2026-07-09 — Corti-like Fast Coding default)
app.include_router(agent_run_router)             # /api/v1/agents/{id}/run (Phase 4-F 2026-07-09 — unified Agent Run facade)
app.include_router(coding_compliance_router)    # /api/v1/coding-compliance/run (Phase 5 Track C Gate 5 — 7-stage mainline)
app.include_router(cdi_router)                  # /api/v1/cdi/* (Phase 5 Track D Gate 9 — CDI Core Entry Agent)
app.include_router(experts_router)              # /api/v1/experts/* (A1B-AE.3 Expert Registry provenance)
app.include_router(agent_cards_router)          # /api/v1/agents/{quick|resolve|card} (A1B-AE.4 Corti-compatible surfaces)
app.include_router(presets_router)              # /api/v1/presets/* (A1B-AE.9 Preset Agents REST)
app.include_router(organizations_router)
app.include_router(platform_environments_router)
app.include_router(platform_api_clients_router)    # Phase 1 cloud-flip stub (501)
app.include_router(platform_tenants_router)
app.include_router(model_catalog_router)
app.include_router(clinical_model_packages_router)
app.include_router(tools_router)
app.include_router(runtime_platform_router)  # /api/runtime-platform/* (backward compat)
app.include_router(standard_runtime_router)   # /api/runtime/* (standard)
app.include_router(compliance_router)          # /api/compliance/*
app.include_router(embedded_router)            # /api/embedded/*
app.include_router(preview_sessions_router)   # /api/embedded/preview-sessions/* (Phase 7 Gate 13A-1)
app.include_router(examples_router)            # /examples/* (Phase 7 Gate 1 partner demos)
app.include_router(runs_router)                # /api/v1/runs/{id}{,/cancel} (Phase 7 Gate 4)
app.include_router(medical_docs_router)        # /api/medical-docs/*
app.include_router(drg_router)                 # /api/drg/*
app.include_router(patient_context_router)    # /api/v1/patient-context/* (A1C.3 — closes RV.5 J8)
app.include_router(agent_connectors_router)   # /api/v2/agentic/agents/{id}/connectors
app.include_router(agentic_context_resources_router)  # /api/v2/agentic/contexts + Task/Artifact resources
app.include_router(artifact_object_router)  # signed, one-time managed Artifact object downloads
app.include_router(agentic_observability_router)  # /api/v2/agentic/contexts/{id}/{trace,tasks/.../feedback}


async def _require_metrics_access(
    credentials=Depends(security),
    db=Depends(get_db),
):
    """Allow a platform admin JWT or a dedicated monitoring bearer.

    The monitoring token is read from the runtime-injected environment. It
    must be at least 32 characters and is compared in constant time; normal
    platform secret rotation may still restart the pod/process.
    """
    from fastapi import HTTPException, status

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    candidate = credentials.credentials
    monitoring_token = os.environ.get("ICODER_METRICS_BEARER_TOKEN", "")
    if (
        len(monitoring_token) >= 32
        and hmac.compare_digest(candidate, monitoring_token)
    ):
        return "monitoring_service"

    user = await get_current_user(credentials=credentials, db=db)
    if getattr(getattr(user, "role", None), "value", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return "platform_admin"


@app.get(
    "/api/metrics",
    operation_id="get_process_metrics",
    responses={
        200: {
            "description": "PHI-safe, process-scoped operational metrics.",
            "headers": {
                "Cache-Control": {
                    "schema": {"type": "string", "example": "no-store"},
                },
            },
        },
        401: {"description": "Authentication required."},
        403: {"description": "Administrator access required."},
    },
)
async def metrics(
    http_response: Response,
    _metrics_principal=Depends(_require_metrics_access),
):
    """Return a PHI-safe snapshot for this API process.

    External monitoring must scrape every worker/pod and aggregate the
    snapshots. This endpoint deliberately does not expose run, cursor, tenant,
    user, token, or clinical labels.
    """
    from app.middleware.logging import get_metrics
    from app.services.run_sse_observability import get_run_sse_metrics
    from app.services.clinical_model_shadow_observability import (
        get_clinical_shadow_metrics,
    )

    snapshot = get_metrics()
    snapshot["schema_version"] = "icoder.process-metrics/v1"
    snapshot["scope"] = "single_api_process"
    snapshot["run_sse"] = get_run_sse_metrics().snapshot()
    snapshot["clinical_shadow"] = get_clinical_shadow_metrics().snapshot()
    http_response.headers["Cache-Control"] = "no-store"
    return snapshot


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }
