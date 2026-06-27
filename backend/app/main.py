# iCoDer Medical Coding Agent - FastAPI Application
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db
import app.models  # noqa: F401 — register all models with Base before init_db() creates tables

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
    # Auto-seed demo users on first startup (idempotent — seed.py checks if already seeded)
    if settings.APP_ENV in ("development", "dev") or settings.SEED_ON_STARTUP:
        try:
            from app.seed import seed as _seed
            await _seed()
            logger.info("Seed: completed (admin/admin123 demo user available)")
        except Exception as e:
            logger.warning(f"Seed: skipped (non-fatal): {e}")
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

    # DeepSeek (real LLM) if configured. Canonical key env var is
    # ICODER_CREDENTIAL_LLM (matches credential_vault + llm_service).
    # settings.LLM_API_KEY is the legacy alias; fall back to it for
    # backward compatibility with .env-based dev setups.
    _deepseek_key = (
        os.environ.get("ICODER_CREDENTIAL_LLM", "").strip()
        or settings.LLM_API_KEY
    )
    if _deepseek_key or settings.LLM_PROVIDER == "deepseek":
        try:
            platform_gateway.register(
                DeepSeekProvider(
                    api_key=_deepseek_key,
                    base_url=settings.LLM_BASE_URL,
                    model=settings.LLM_MODEL,
                ),
                default=True,
            )
            logger.info(
                "Embedded Runtime: DeepSeekProvider registered as default "
                "(key source=%s, model=%s)",
                "env" if os.environ.get("ICODER_CREDENTIAL_LLM", "").strip() else "settings",
                settings.LLM_MODEL,
            )
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

    # ── MedCodER index flag (lazy-init on first /api/medical-coding/medcoder call) ──
    # Setting it to False here means /api/health can report "medcoder not ready"
    # honestly, and the heavy BGE-M3 + FAISS index only loads on demand.
    app.state.medcoder_index_ready = False
    app.state.medcoder_index_error: str | None = None
    app.state.medcoder_index_loading = False
    app.state.medcoder_retriever = None  # populated by C7 if subprocess mode is on
    logger.info("MedCodER index: not yet loaded (lazy init on first request)")

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
        _medcoder_health = index_health_check(_medcoder_index_dir)
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
        _icd9cm3_ok = is_icd9cm3_retriever_available(_medcoder_index_dir)
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

    logger.info(f"Embedded Runtime started: {platform_runtime.status()}")

    # ── Register Official Agent Packs (BuiltinAgentPackProvider) ──
    from icoder_runtime.core.builtin_pack_provider import BuiltinAgentPackProvider
    _official_agents_dir = Path(__file__).parent.parent / "official_agents"
    if _official_agents_dir.exists():
        provider = BuiltinAgentPackProvider(_official_agents_dir)
        discovered = provider.discover()
        registered = provider.register_all(platform_runtime)
        logger.info(f"BuiltinAgentPackProvider: {len(discovered)} packs discovered, {registered} registered")

        # Sync all Runtime agents to DB (DB is master for CRUD)
        from app.services.agent_registry_sync_service import AgentRegistrySyncService
        from app.models.agent import Agent as AgentModel
        try:
            sync_svc = AgentRegistrySyncService(agent_registry)
            async with async_session_factory() as session:
                result = await sync_svc.repair_from_registry(session)
                logger.info(f"Registry→DB sync: {result.get('created', 0)} created, {result.get('updated', 0)} updated")
        except Exception as e:
            logger.warning(f"Registry→DB sync skipped (DB may not be ready): {e}")

    # --- Mount new A2A v0.3 package (replaces a2a_registry in Commit 3) ---
    # T5/T6: LLMCall/ExpertInvoker wire to the real LLMGateway + MedCodER
    # HybridCodingAdapter via sync adapters. Set ICODER_PHASE1_STUB_LLM=1
    # to short-circuit to inline stubs (used by tests + smoke checks).
    try:
        from app.icoder.agent_runtime.a2a import (
            mount_a2a,
            AgentProvider,
            ExpertCaller,
        )
        from app.icoder.agent_runtime.a2a.agent_card import (
            medcoder_coding_review_card,
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
        )

        _phase1_stub_llm = os.environ.get("ICODER_PHASE1_STUB_LLM", "0") == "1"

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
            _expert_invoker: Callable[[Any], dict] = lambda _i: {"echo": True}
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
                    f"A2A wiring: HybridCodingAdapter construction failed, "
                    f"falling back to stub invoker: {_he}"
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
                    f"A2A wiring: RuleEngine construction failed, "
                    f"tabular-validator will lazy-import at call time: {_re}"
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
                "real" if platform_gateway.is_configured else "stub",
                "real" if _hybrid_adapter is not None else "stub",
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
                    f"A2A wiring: failed to enrich agent from official pack, "
                    f"using minimal definition: {_ae}"
                )
            return DictAgentProvider({"medcoder-coding-review": _agent})

        phase1_handler = InboundHandler(
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

        def _phase1_agent_provider(agent_id: str):
            if agent_id == "medcoder-coding-review":
                return medcoder_coding_review_card()
            return None

        def _phase1_expert_caller(expert_id: str, body: dict):
            return {
                "kind": "message",
                "role": "agent",
                "messageId": "phase1-stub",
                "contextId": "",
                "parts": [{"kind": "data", "data": {"expert_id": expert_id, "echo": body}}],
                "metadata": {},
            }

        mount_a2a(
            app,
            handler=phase1_handler,
            agent_provider=_phase1_agent_provider,
            expert_caller=_phase1_expert_caller,
        )
        logger.info("A2A v0.3 package mounted (Phase 1 stub)" if _phase1_stub_llm else "A2A v0.3 package mounted (real wiring)")

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
            logger.warning(f"MCP mount skipped: {e}")
    except Exception as e:
        logger.warning(f"A2A v0.3 mount skipped: {e}")
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
        "medcoder_index_ready": getattr(app.state, "medcoder_index_ready", False),
        "medcoder_index_loading": getattr(app.state, "medcoder_index_loading", False),
        "medcoder_index_error": getattr(app.state, "medcoder_index_error", None),
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
from app.api.platform_environments import router as platform_environments_router
from app.api.platform_api_clients import router as platform_api_clients_router
from app.api.platform_tenants import router as platform_tenants_router
from app.api.fhir import router as fhir_router
from app.api.tools import router as tools_router
from app.api.marketplace import router as marketplace_router
from app.api.runtime_platform import router as runtime_platform_router
from app.api.runtime_platform import runtime_router as standard_runtime_router
from app.api.compliance import router as compliance_router
from app.api.medical_docs import router as medical_docs_router
from app.api.agent_evaluation import router as agent_eval_router
from app.api.embedded import router as embedded_router
from app.api.drg import router as drg_router
from app.api.m2a import router as m2a_router
from app.api.icoder_coding_review import router as icoder_coding_review_router
from app.api.icoder_coding_methods import (
    router as icoder_coding_methods_router,
    compare_router as icoder_coding_compare_router,
)
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
app.include_router(icoder_coding_review_router)  # M3-0 病案首页编码审核 Agent API
app.include_router(icoder_coding_methods_router)  # Phase B /api/icoder/coding-methods/{list, {id}}
app.include_router(icoder_coding_compare_router)  # Phase B /api/icoder/coding-review/{compare, run-v2}
app.include_router(organizations_router)
app.include_router(platform_environments_router)  # Phase 1 cloud-flip stub (501)
app.include_router(platform_api_clients_router)    # Phase 1 cloud-flip stub (501)
app.include_router(platform_tenants_router)         # Phase 1 cloud-flip stub (501)
app.include_router(fhir_router)
app.include_router(tools_router)
app.include_router(marketplace_router)
app.include_router(runtime_platform_router)  # /api/runtime-platform/* (backward compat)
app.include_router(standard_runtime_router)   # /api/runtime/* (standard)
app.include_router(compliance_router)          # /api/compliance/*
app.include_router(embedded_router)            # /api/embedded/*
app.include_router(medical_docs_router)        # /api/medical-docs/*
app.include_router(agent_eval_router)          # /api/agents/{id}/evaluate
app.include_router(drg_router)                 # /api/drg/*
app.include_router(m2a_router)                 # /api/m2a/* (M2a 技术闭环)


@app.get("/api/metrics")
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    from app.middleware.logging import get_metrics
    return get_metrics()


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }
