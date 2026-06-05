# iCoDer Medical Coding Agent - FastAPI Application
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
    await init_db()
    logger.info("Database initialized")
    # --- Runtime Recovery: restore active sessions from DB ---
    recovered = await _recover_runtime_sessions()
    logger.info(f"Runtime recovery: {recovered} active session(s) restored")
    # --- Embedded Runtime: initialize LLMGateway + PlatformRuntime ---
    from icoder_runtime.core.llm_gateway import (
        LLMGateway, MockLLMProvider, DeepSeekProvider, MedicalCodingLLMProvider,
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

    platform_gateway = LLMGateway()
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
        logger.info(f"MedicalCodingLLMProvider registered (mode={mc_mode}). No real coding engine — using MOCK.")

    # DeepSeek (real LLM) if configured
    if settings.LLM_API_KEY or settings.LLM_PROVIDER == "deepseek":
        try:
            platform_gateway.register(
                DeepSeekProvider(
                    api_key=settings.LLM_API_KEY,
                    base_url=settings.LLM_BASE_URL,
                    model=settings.LLM_MODEL,
                ),
                default=True,
            )
            logger.info("Embedded Runtime: DeepSeekProvider registered as default")
        except Exception as e:
            logger.warning(f"DeepSeekProvider registration failed, using mock: {e}")
            platform_gateway.register(MockLLMProvider(), default=True)
    else:
        platform_gateway.register(MockLLMProvider(), default=True)
        logger.info("Embedded Runtime: MockLLMProvider registered as default (development mode)")

    # ── Data Policy (must be created before PlatformRuntime) ──
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    data_policy = RuntimeDataPolicy.from_env()
    app.state.data_policy = data_policy

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

    logger.info(f"Embedded Runtime started: {platform_runtime.status()}")

    # ── Register Official Agent Packs (BuiltinAgentPackProvider) ──
    from icoder_runtime.core.builtin_pack_provider import BuiltinAgentPackProvider
    _official_agents_dir = Path(__file__).parent.parent / "official_agents"
    if _official_agents_dir.exists():
        provider = BuiltinAgentPackProvider(_official_agents_dir)
        discovered = provider.discover()
        registered = provider.register_all(platform_runtime)
        logger.info(f"BuiltinAgentPackProvider: {len(discovered)} packs discovered, {registered} registered")

    # Register A2A agents for discovery
    from app.services.a2a_protocol import a2a_registry
    a2a_registry.register_all_experts()
    logger.info(f"A2A: {a2a_registry.agent_count} agents registered")
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
    _asyncio.create_task(_check_timeouts())
    logger.info("Runtime timeout checker started")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="面向中国医院病案首页与医保结算清单场景的编码审核智能体",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
    }


# Register API routers
from app.api.auth import router as auth_router
from app.api.encounters import router as encounters_router
from app.api.reviews import router as reviews_router
from app.api.admin import router as admin_router
from app.api.codes import router as codes_router
from app.api.gold_cases import router as gold_cases_router
from app.api.evaluation import router as evaluation_router
from app.api.billing import router as billing_router
from app.api.keys import router as keys_router
from app.api.team import router as team_router
from app.api.usage import router as usage_router
from app.api.text_gen import router as text_gen_router
from app.api.experts import router as experts_router
from app.api.facts import router as facts_router
from app.api.oauth import router as oauth_router
from app.api.agents import router as agents_router
from app.api.runtime import router as runtime_router
from app.api.websocket import router as ws_router
from app.api.code_tables import router as code_tables_router
from app.api.organizations import router as organizations_router
from app.api.fhir import router as fhir_router
from app.api.tools import router as tools_router
from app.api.marketplace import router as marketplace_router
from app.api.runtime_platform import router as runtime_platform_router
from app.api.runtime_platform import runtime_router as standard_runtime_router
from app.api.compliance import router as compliance_router
from app.middleware.rate_limit import rate_limit_middleware

# Rate limiting middleware
app.middleware("http")(rate_limit_middleware)

app.include_router(runtime_router)
app.include_router(auth_router)
app.include_router(encounters_router)
app.include_router(reviews_router)
app.include_router(codes_router)
app.include_router(gold_cases_router)
app.include_router(evaluation_router)
app.include_router(billing_router)
app.include_router(keys_router)
app.include_router(team_router)
app.include_router(usage_router)
app.include_router(text_gen_router)
app.include_router(experts_router)
app.include_router(facts_router)
app.include_router(oauth_router)
app.include_router(agents_router)
app.include_router(admin_router)
app.include_router(ws_router)
app.include_router(code_tables_router)
app.include_router(organizations_router)
app.include_router(fhir_router)
app.include_router(tools_router)
app.include_router(marketplace_router)
app.include_router(runtime_platform_router)  # /api/runtime-platform/* (backward compat)
app.include_router(standard_runtime_router)   # /api/runtime/* (standard)
app.include_router(compliance_router)          # /api/compliance/*


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }
