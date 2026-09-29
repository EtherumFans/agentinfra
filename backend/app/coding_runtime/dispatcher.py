"""Authenticated tenant binding -> capability validation -> one engine invocation."""
from __future__ import annotations

import asyncio
import copy
import math
import os
import uuid

from app.coding_runtime.base import (
    CodingRequest,
    CodingResult,
    CodingResultCode,
    CodingRuntime,
    RuntimeMode,
)
from app.coding_runtime.fast_runtime import FastCodingRuntime
from app.coding_runtime.medcoder_runtime import MedCoderRuntime

from app.coding_runtime.engines import (
    EngineManifest, EngineRegistry, TenantEngineBindings,
)

class LegacyCodingEngine:
    """Compatibility provider; only this adapter knows the Fast/Deep runtimes."""
    manifest = EngineManifest("icoder.legacy", "1.0.0", supports_legacy_variants=True)

    def __init__(self, owner):
        self.owner = owner

    async def predict(self, request):
        if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip() and os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY") != "1":
            raise ValueError("llm_credential_missing")
        return await self.owner.select_runtime(request.mode).predict(request)



class CodingRuntimeDispatcher:
    """Process-local immutable configuration with request-local execution data."""

    def __init__(self, *, registry=None, bindings=None, timeout_seconds=None):
        self._fast: FastCodingRuntime | None = None
        self._deep: MedCoderRuntime | None = None
        self.registry = registry if registry is not None else EngineRegistry((LegacyCodingEngine(self),))
        self.bindings = bindings if bindings is not None else TenantEngineBindings.from_json(
            os.environ.get("ICODER_CODING_ENGINE_BINDINGS", ""))
        self.timeout_seconds = timeout_seconds or {RuntimeMode.CORTI_LIKE_FAST: 30, RuntimeMode.MEDCODER_DEEP: 90}

    def _get_fast(self) -> FastCodingRuntime:
        if self._fast is None:
            self._fast = FastCodingRuntime()
        return self._fast

    def _get_deep(self) -> MedCoderRuntime:
        if self._deep is None:
            self._deep = MedCoderRuntime()
        return self._deep

    def select_runtime(self, mode: RuntimeMode) -> CodingRuntime:
        """Legacy adapter implementation detail; reject unknown modes."""
        if mode == RuntimeMode.MEDCODER_DEEP:
            return self._get_deep()
        if mode == RuntimeMode.CORTI_LIKE_FAST:
            return self._get_fast()
        raise ValueError("unsupported_runtime_mode")

    async def dispatch(self, request: CodingRequest) -> CodingResult:
        """Bind by authenticated tenant, negotiate, invoke once, force review."""
        invocation_id = str(uuid.uuid4())
        metadata = {"contract_version": "1.0", "invocation_id": invocation_id}
        run_id = request.run_id or str(uuid.uuid4())
        try:
            binding = self.bindings.resolve(request.tenant_id)
            metadata.update(engine_id=binding.engine_id, engine_version=binding.engine_version,
                            binding_revision=binding.revision)
            engine = self.registry.resolve(binding)
            m = engine.manifest
            # Deliberately bypass coerce's legacy unknown-value fallback.
            try:
                mode = RuntimeMode(request.mode)
            except ValueError:
                raise ValueError("engine_mode_unsupported") from None
            if mode.value not in m.modes or not set(request.coding_systems) <= set(m.coding_systems):
                raise ValueError("engine_capability_unsupported")
            if not request.coding_systems or not request.text.strip() or len(request.text) > m.max_input_chars:
                raise ValueError("engine_input_invalid")
            if request.legacy_variant != "medcoder.full" and not m.supports_legacy_variants:
                raise ValueError("engine_capability_unsupported")
            owned = copy.deepcopy(request)
            owned.mode, owned.run_id = mode, run_id
            result = await asyncio.wait_for(engine.predict(owned), timeout=self.timeout_seconds[mode])
            if (not isinstance(result, CodingResult) or not isinstance(result.raw_schema, dict)
                    or not isinstance(result.trace_events, list) or not isinstance(result.codes, list)):
                raise ValueError("engine_output_invalid")
            if result.run_id and result.run_id != run_id:
                raise ValueError("engine_run_id_mismatch")
            if result.raw_schema.get("is_mock") or result.degraded:
                raise ValueError("engine_output_degraded")
            if any(not isinstance(c, CodingResultCode) or not c.code.strip()
                   or not math.isfinite(c.confidence) or not 0 <= c.confidence <= 1
                   for c in result.codes):
                raise ValueError("engine_output_invalid")
            result = copy.deepcopy(result)
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            result = self._failure("engine_timeout", run_id)
        except Exception as exc:
            # Never expose plugin exception text (it may contain medical records).
            allowed = {"engine_mode_unsupported", "tenant_required", "tenant_engine_not_bound", "engine_not_registered",
                       "engine_capability_unsupported", "engine_input_invalid", "engine_output_invalid",
                       "engine_run_id_mismatch", "engine_output_degraded", "llm_credential_missing"}
            reason = str(exc) if isinstance(exc, ValueError) and str(exc) in allowed else "engine_failed"
            result = self._failure(reason, run_id)
        result.run_id = run_id
        result.runtime_mode = request.mode.value if isinstance(request.mode, RuntimeMode) else str(request.mode)
        result.trace_id = result.trace_id or f"trace-{uuid.uuid4().hex}"
        result.engine = metadata
        result.manual_review_required = True
        result.production_writeback_blocked = True
        if result.error:
            result.codes = []
            result.raw_schema = {}
        else:
            result.raw_schema["manual_review_required"] = True
        result.raw_schema["engine"] = dict(metadata)
        result.raw_schema["production_writeback_blocked"] = True
        result.trace_events.append({"step": "engine_dispatch", "status": "error" if result.error else "ok",
                                    "metadata": {**metadata, "reason": result.error_reason}})
        return result

    @staticmethod
    def _failure(reason: str, run_id: str) -> CodingResult:
        return CodingResult(codes=[], run_id=run_id, error=True, error_reason=reason,
                            llm_provider="", summary="编码引擎未完成，请转人工审核。")


_dispatcher: CodingRuntimeDispatcher | None = None


def get_dispatcher() -> CodingRuntimeDispatcher:
    """Return the shared dispatcher (singleton)."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = CodingRuntimeDispatcher()
    return _dispatcher


def reset_dispatcher() -> None:
    """Reset the singleton (for tests)."""
    global _dispatcher
    _dispatcher = None


def configure_coding_engines(engines, *, bindings=None) -> None:
    """Trusted bootstrap hook; call before serving, identically in every worker.

    This is not a runtime administration API. Reconfiguration requires a deployment.
    The legacy provider remains registered but is never used as failure fallback.
    """
    global _dispatcher
    if _dispatcher is not None:
        raise RuntimeError("coding_engines_already_initialized")
    dispatcher = CodingRuntimeDispatcher(bindings=bindings)
    dispatcher.registry = EngineRegistry((LegacyCodingEngine(dispatcher), *engines))
    dispatcher.bindings.validate_registry(dispatcher.registry)
    _dispatcher = dispatcher
