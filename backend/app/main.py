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
    _deepseek_key = (
        os.environ.get("ICODER_CREDENTIAL_LLM", "").strip()
        or settings.LLM_API_KEY
    )
    _llm_provider_cfg = os.environ.get(
        "LLM_PROVIDER", settings.LLM_PROVIDER or ""
    ).lower()
    if _llm_provider_cfg == "mock":
        platform_gateway.register(MockLLMProvider(), default=True)
        logger.info(
            "LLM_PROVIDER=mock — MockLLMProvider registered as default "
            "(DeepSeek suppressed, key_present=%s)",
            bool(_deepseek_key),
        )
    elif _deepseek_key or _llm_provider_cfg == "deepseek":
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

            # Phase 3-B1 (2026-07-04): Medical Coding Agent (user-facing MVP)
            # Same expert_ids (coding-expert routes to 4 D2 packs via the
            # build_expert_invoker_for_medcoder wiring), but the output_contract
            # is v2 (MedicalCodingAgentOutputV2, 8 Corti fields). The v1→v2
            # projection happens in the response post-processor (see below).
            _medical_agent = AgentDefinition(
                id="medical-coding-agent",
                name="医学编码智能体",
                description="iCoDer 官方医学编码 Agent (Corti-style MVP)",
                system_prompt=(
                    "你是 iCoDer Medical Coding Agent (Corti-style, MVP)。"
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
                    f"A2A wiring: failed to enrich medical-coding-agent from pack, "
                    f"using minimal definition: {_mae}"
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
        # For medical-coding-agent (user-facing MVP), we project v1 → v2
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
                    dispatch_medical_coding_fast,
                    build_medical_coding_inbound_response,
                    persist_trace_events,
                )
                from app.icoder.agent_runtime.orchestrator.inbound_handler import (
                    InboundResponse,
                    extract_text_from_parts,
                )

                # Phase 4-F2 §4.2: medical-coding default runtime dispatch.
                # A2A message:send defaults to corti_like_fast (bypass 5-stage).
                if agent_id == "medical-coding-agent":
                    meta = request.metadata or {}
                    runtime_mode = meta.get("runtime_mode") or "corti_like_fast"
                    if runtime_mode != "medcoder_deep":
                        # Fast path: route to CodingRuntimeDispatcher directly.
                        input_text = extract_text_from_parts(request.message.parts)
                        try:
                            result, out_run_id, out_trace_id = (
                                _asyncio.new_event_loop().run_until_complete(
                                    dispatch_medical_coding_fast(
                                        agent_id=agent_id,
                                        input_text=input_text,
                                        extra=None,
                                        runtime_mode=runtime_mode,
                                        include_trace=meta.get("include_trace", True),
                                        include_evidence=meta.get("include_evidence", True),
                                        run_id=meta.get("run_id") or "",
                                        trace_id=meta.get("trace_id") or "",
                                        user_id=meta.get("user_id", ""),
                                        tenant_id=meta.get("tenant_id", ""),
                                    )
                                )
                            )
                        except Exception as e:
                            from app.icoder.agent_runtime.orchestrator.run_trace import (
                                RunTraceStep, RunTraceStatus, emit_trace_event,
                            )
                            emit_trace_event(
                                meta.get("run_id") or "",
                                RunTraceStep.COMPLETION,
                                status=RunTraceStatus.FAILED,
                                safe_metadata={
                                    "agent_id": agent_id,
                                    "error": f"{type(e).__name__}: {str(e)[:200]}",
                                },
                            )
                            return InboundResponse(
                                kind="error",
                                context_id=meta.get("context_id", ""),
                                metadata={
                                    "run_id": meta.get("run_id", ""),
                                    "trace_id": meta.get("trace_id", ""),
                                    "agent_id": agent_id,
                                    "phi_redacted": True,
                                },
                                error={"code": "INTERNAL_ERROR", "message": str(e)},
                                http_status=500,
                            )
                        # Persist trace_events so /runs/{run_id}/trace works.
                        if result.trace_events and not result.error:
                            persist_trace_events(
                                run_id=out_run_id,
                                trace_events=list(result.trace_events),
                                agent_id=agent_id,
                                runtime_mode=result.runtime_mode,
                                trace_id=out_trace_id,
                            )
                        return build_medical_coding_inbound_response(
                            result=result,
                            run_id=out_run_id,
                            trace_id=out_trace_id,
                            context_id=meta.get("context_id") or "",
                            interaction_id=request.message.interaction_id,
                        )

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
                except Exception:
                    return response  # schema not available, pass through

                run_id = (response.metadata or {}).get("run_id", "")
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
                            "schema_ref": "icoder/MedicalCodingAgentOutputV2/v1",
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
                response.metadata["output_contract"] = (
                    "icoder/MedicalCodingAgentOutputV2/v1"
                )
                response.metadata["v1_to_v2_projected"] = True
                return response

        phase1_handler = _MedicalCodingV2ProjectingHandler(phase1_handler_raw)

        # Phase 3-D1 Task 5: 3 simple runnable agents (code-validation /
        # compliance-guardrail / note-completeness). These bypass the
        # orchestrator (Planner/Delegator/Aggregator) and call the
        # agent's run() function directly — they're deterministic, no-LLM,
        # and don't need expert delegation. The dispatch handler:
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

            def _handle_simple(self, agent_id: str, request) -> InboundResponse:
                import asyncio as _asyncio
                from types import SimpleNamespace as _NS
                from app.icoder.mcp.server import dispatch_tool
                from app.icoder.mcp.auth import AuthHeader

                run_id = make_run_id()
                context_id = make_context_id()
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
                # Extract text from parts
                input_text = extract_text_from_parts(request.message.parts)

                # Phase 4-D (D-5): code-validation-agent routes to v2
                # (LLMWithToolsProvider + 4 MCP tools) directly — bypassing
                # the validate_codes MCP tool which stays v1 (RuleEngine)
                # for other MCP consumers. Other 2 simple agents still go
                # through the MCP dispatcher.
                if agent_id == "code-validation-agent":
                    return self._handle_code_validation_v2(
                        agent_id, input_text, run_id, context_id, request,
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
                            "error": f"{type(e).__name__}: {str(e)[:200]}",
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
                        error={"code": "INTERNAL_ERROR", "message": str(e)},
                        http_status=500,
                    )
                # Trace step: output generated + completion
                emit_trace_event(
                    run_id, RunTraceStep.OUTPUT_GENERATED,
                    safe_metadata={
                        "review_conclusion": result.get("review_conclusion", ""),
                        "issues_count": len(result.get("issues_found", []) or []),
                    },
                )
                emit_trace_event(
                    run_id, RunTraceStep.COMPLETION,
                    status=RunTraceStatus.OK,
                    safe_metadata={"agent_id": agent_id},
                )
                # Phase 3-D2 Task 4 — pre-render markdown so the
                # frontend's Rendered tab shows structured tables (not
                # a JSON dump). The SSOT is generate_markdown_for(); the
                # frontend falls back to generateFallbackMarkdown() only
                # when this field is absent (legacy/old pack).
                from app.icoder.markdown_generator import generate_markdown_for
                try:
                    result_markdown = generate_markdown_for(agent_id, result)
                    # Embed markdown into the result dict so the existing
                    # DataPart pass-through carries it to the frontend.
                    result_with_md = dict(result)
                    result_with_md["markdown"] = result_markdown
                except Exception as _md_err:
                    logger.warning(
                        "markdown generation failed for %s: %s; "
                        "frontend will fall back to JSON dump",
                        agent_id, _md_err,
                    )
                    result_with_md = result
                # Build response — single DataPart with the result dict.
                # Match the projection wrapper's metadata shape so the
                # frontend's _mapA2AResultToRunResult works uniformly.
                return InboundResponse(
                    kind="message",
                    message_id=make_message_id(),
                    context_id=context_id,
                    role="agent",
                    parts=[{
                        "kind": "data",
                        "data": result_with_md,
                        "metadata": {
                            "schema_ref": (
                                "icoder/CodeValidationOutput/v1"
                                if agent_id == "code-validation-agent"
                                else "icoder/ComplianceGuardrailOutput/v1"
                                if agent_id == "compliance-guardrail-agent"
                                else "icoder/NoteCompletenessOutput/v1"
                            ),
                            "phi_redacted": True,
                            "production_writeback_blocked": True,
                            "orchestrator_expert_id": agent_id,
                            "orchestrator_latency_ms": 0,
                            "orchestrator_ok": True,
                        },
                    }],
                    metadata={
                        "run_id": run_id,
                        "agent_id": agent_id,
                        "interaction_id": request.message.interaction_id,
                        "phi_redacted": True,
                        "production_writeback_blocked": True,
                        "output_contract": (
                            "icoder/CodeValidationOutput/v1"
                            if agent_id == "code-validation-agent"
                            else "icoder/ComplianceGuardrailOutput/v1"
                            if agent_id == "compliance-guardrail-agent"
                            else "icoder/NoteCompletenessOutput/v1"
                        ),
                    },
                    http_status=200,
                )

            def _handle_code_validation_v2(
                self, agent_id: str, input_text: str,
                run_id: str, context_id: str, request,
            ) -> InboundResponse:
                """Phase 4-D (D-5): invoke code_validation/agent.py v2
                (LLMWithToolsProvider + 4 MCP tools) directly — bypassing
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
                            "error": f"{type(e).__name__}: {str(e)[:200]}",
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
                        error={"code": "INTERNAL_ERROR", "message": str(e)},
                        http_status=500,
                    )
                # Trace step: output generated + completion
                emit_trace_event(
                    run_id, RunTraceStep.OUTPUT_GENERATED,
                    safe_metadata={
                        "review_conclusion": result.get("review_conclusion", ""),
                        "validated_codes_count": len(result.get("validated_codes", []) or []),
                        "cross_code_issues_count": len(result.get("cross_code_issues", []) or []),
                    },
                )
                emit_trace_event(
                    run_id, RunTraceStep.COMPLETION,
                    status=RunTraceStatus.OK,
                    safe_metadata={
                        "agent_id": agent_id,
                        "backend_provider": "icoder.llm-with-tools.v1",
                    },
                )
                # v2 schema already includes a `markdown` field, but wrap
                # through generate_markdown_for() to ensure consistency for
                # the frontend's Rendered tab (no-op when markdown exists).
                from app.icoder.markdown_generator import generate_markdown_for
                try:
                    md = generate_markdown_for(agent_id, result) or result.get("markdown", "")
                except Exception:
                    md = result.get("markdown", "")
                result_with_md = dict(result)
                result_with_md["markdown"] = md
                # v2 agent_ref — frontend checks @2.0.0 for v2 vs v1.
                # Override trace_refs.agent_ref too: the legacy fallback
                # path carries v1's @1.0.0 trace_refs, which would mislead
                # the frontend into thinking this is a v1 response.
                result_with_md = dict(result)
                result_with_md["agent_ref"] = "icoder/code-validation-agent@2.0.0"
                tr = dict(result_with_md.get("trace_refs") or {})
                tr["agent_ref"] = "icoder/code-validation-agent@2.0.0"
                result_with_md["trace_refs"] = tr
                return InboundResponse(
                    kind="message",
                    message_id=make_message_id(),
                    context_id=context_id,
                    role="agent",
                    parts=[{
                        "kind": "data",
                        "data": result_with_md,
                        "metadata": {
                            "schema_ref": "icoder/CodeValidationOutputV2/1",
                            "agent_ref": "icoder/code-validation-agent@2.0.0",
                            "phi_redacted": True,
                            "production_writeback_blocked": True,
                            "orchestrator_expert_id": "code-validation-agent",
                            "orchestrator_latency_ms": 0,
                            "orchestrator_ok": True,
                            "backend_provider": "icoder.llm-with-tools.v1",
                        },
                    }],
                    metadata={
                        "run_id": run_id,
                        "agent_id": agent_id,
                        "interaction_id": request.message.interaction_id,
                        "phi_redacted": True,
                        "production_writeback_blocked": True,
                        "output_contract": "icoder/CodeValidationOutputV2/1",
                        "backend_provider": "icoder.llm-with-tools.v1",
                    },
                    http_status=200,
                )

        phase1_handler = _SimpleAgentDispatchHandler(phase1_handler)

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
from app.api.tools import router as tools_router
from app.api.runtime_platform import router as runtime_platform_router
from app.api.runtime_platform import runtime_router as standard_runtime_router
from app.api.compliance import router as compliance_router
from app.api.medical_docs import router as medical_docs_router
from app.api.embedded import router as embedded_router
from app.api.drg import router as drg_router
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
from app.middleware.rate_limit import rate_limit_middleware

# Rate limiting middleware
app.middleware("http")(rate_limit_middleware)

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
app.include_router(v2_tools_sections_templates_router) # Phase 1.2 cycle 4 (2026-07-01) /api/v2/tools/{templates,sections}/ (Corti §13.4 LIST, stub data)
app.include_router(v2_tools_documents_classic_router) # Phase 1.2 cycle 5 (2026-07-01) /api/v2/tools/interactions/{id}/documents/ (Corti §13.4 Documents Classic LIST, Planned deprecation, stub data)
app.include_router(v2_tools_stt_router)              # Phase 1.3 cycle 6 (2026-07-01) /api/v2/tools/interactions/{id}/transcripts/ (Corti §13.3 STT LIST, stub data)
app.include_router(icoder_agents_hub_router)          # Phase 3-B1 (2026-07-04) /api/icoder/agents/hub (Corti-style Agent Hub, pack-mastered)
app.include_router(customers_router)             # /api/customers/* (Corti parity)
app.include_router(templates_router)             # /api/templates/* (Templates Beta — Corti parity)
app.include_router(tickets_router)               # /api/tickets/* (Tickets Portal — Corti parity)
app.include_router(run_trace_router)             # /api/runtime/runs/{run_id}/trace (Phase 3-D1 Task 4)
app.include_router(coding_predict_router)        # /api/v1/coding/predict (G001 refactor 2026-07-09 — Corti-like Fast Coding default)
app.include_router(agent_run_router)             # /api/v1/agents/{id}/run (Phase 4-F 2026-07-09 — unified Agent Run facade)
app.include_router(coding_compliance_router)    # /api/v1/coding-compliance/run (Phase 5 Track C Gate 5 — 7-stage mainline)
app.include_router(cdi_router)                  # /api/v1/cdi/* (Phase 5 Track D Gate 9 — CDI Core Entry Agent)
app.include_router(organizations_router)
app.include_router(platform_environments_router)  # Phase 1 cloud-flip stub (501)
app.include_router(platform_api_clients_router)    # Phase 1 cloud-flip stub (501)
app.include_router(platform_tenants_router)         # Phase 1 cloud-flip stub (501)
app.include_router(tools_router)
app.include_router(runtime_platform_router)  # /api/runtime-platform/* (backward compat)
app.include_router(standard_runtime_router)   # /api/runtime/* (standard)
app.include_router(compliance_router)          # /api/compliance/*
app.include_router(embedded_router)            # /api/embedded/*
app.include_router(medical_docs_router)        # /api/medical-docs/*
app.include_router(drg_router)                 # /api/drg/*


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
