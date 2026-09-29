"""Phase-1 engine contract and immutable deployment-time tenant bindings.

Plugins are trusted server code, registered explicitly at application bootstrap.
No client-supplied imports, URLs, engine IDs or policy overrides are resolved here.
This compatibility contract does not yet implement CoderFlow clinical compilation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Protocol

from app.coding_runtime.base import CodingRequest, CodingResult, RuntimeMode


@dataclass(frozen=True)
class EngineManifest:
    engine_id: str
    engine_version: str
    contract_version: str = "1.0"
    modes: tuple[str, ...] = tuple(m.value for m in RuntimeMode)
    coding_systems: tuple[str, ...] = ("icd10cn", "icd9cm3")
    max_input_chars: int = 16000
    supports_legacy_variants: bool = False


class CodingEngine(Protocol):
    manifest: EngineManifest

    async def predict(self, request: CodingRequest) -> CodingResult: ...


@dataclass(frozen=True)
class EngineBinding:
    engine_id: str
    engine_version: str
    revision: str


LEGACY_BINDING = EngineBinding("icoder.legacy", "1.0.0", "migration-default-v1")


class EngineRegistry:
    """Snapshot of explicitly registered engines; duplicate versions are invalid."""

    def __init__(self, engines: tuple[CodingEngine, ...]):
        entries = {}
        for engine in engines:
            m = engine.manifest
            key = (m.engine_id, m.engine_version)
            if not all(key) or key in entries or m.contract_version != "1.0":
                raise ValueError("invalid_engine_registration")
            if any(not isinstance(v, str) or not v.strip() or len(v) > 256 for v in key):
                raise ValueError("invalid_engine_registration")
            if m.max_input_chars < 1 or not m.modes or not m.coding_systems:
                raise ValueError("invalid_engine_registration")
            entries[key] = engine
        self._entries = MappingProxyType(entries)

    def resolve(self, binding: EngineBinding) -> CodingEngine:
        try:
            return self._entries[(binding.engine_id, binding.engine_version)]
        except KeyError:
            raise ValueError("engine_not_registered") from None


class TenantEngineBindings:
    def __init__(self, bindings: Mapping[str, EngineBinding], *,
                 default: EngineBinding | None = LEGACY_BINDING):
        if any(not key.strip() or not b.revision for key, b in bindings.items()):
            raise ValueError("invalid_engine_binding")
        self._bindings = MappingProxyType(dict(bindings))
        self._default = default

    @classmethod
    def from_json(cls, value: str) -> "TenantEngineBindings":
        # Empty configuration is an explicit legacy migration default, never failover.
        if not value.strip():
            return cls({})
        data = json.loads(value)
        if not isinstance(data, dict) or set(data) != {"tenants", "legacy_default"}:
            raise ValueError("invalid_engine_bindings_configuration")
        if type(data["legacy_default"]) is not bool or not isinstance(data["tenants"], dict):
            raise ValueError("invalid_engine_bindings_configuration")
        bindings = {}
        for tenant, raw in data["tenants"].items():
            if not isinstance(raw, dict) or set(raw) != {"engine_id", "engine_version", "revision"}:
                raise ValueError("invalid_engine_binding")
            if not all(isinstance(v, str) and v.strip() for v in raw.values()):
                raise ValueError("invalid_engine_binding")
            bindings[tenant] = EngineBinding(**raw)
        return cls(bindings, default=LEGACY_BINDING if data["legacy_default"] else None)

    def resolve(self, tenant_id: str) -> EngineBinding:
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_required")
        binding = self._bindings.get(tenant_id, self._default)
        if binding is None:
            raise ValueError("tenant_engine_not_bound")
        return binding

    def validate_registry(self, registry: EngineRegistry) -> None:
        for binding in self._bindings.values():
            registry.resolve(binding)
        if self._default is not None:
            registry.resolve(self._default)
