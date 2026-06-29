"""Registry compatibility layer (P1.1-B).

Computes per-pack compatibility status from disk, independent of the
RuntimeAgentRegistry (which only stores packs that passed the legacy
``AgentPackageV1.from_dict`` v1.1 validator).

This is the single read surface for:
* The Agent Hub — surfaces 16 packs (10 installed + 4 metadata_only + 2 INVALID-or-recovered)
* The Doctor — per-pack status counts
* The new ``/api/icoder/registry/compatibility`` endpoint
* The CLI ``icoder_agent.py validate`` (P1.1-E)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .agent_pack_loader import load_packs_from_dir, why_not_executable
from .agent_pack_schema import NormalizedPack, PackStatus

logger = logging.getLogger(__name__)


@dataclass
class AgentCompatibilityEntry:
    """One row in the compatibility report."""

    agent_ref: str
    name: str
    version: str
    agent_type: str
    format_version: str
    status: str             # "executable" | "metadata_only" | "invalid"
    production_ready: bool
    experimental: bool
    enabled_by_default: bool
    tier: int
    expert_count: int
    tool_count: int
    category: str
    icon: str
    source_path: str | None
    registered: bool        # True iff an InstalledAgentRecord exists in RuntimeAgentRegistry
    registry_agent_id: str | None
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    why_not_executable: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RegistryCompatibilityReport:
    """Full compat report + summary counters."""

    entries: list[AgentCompatibilityEntry]
    by_status: dict[str, int]            # {"executable": N, "metadata_only": N, "invalid": N}
    by_type: dict[str, int]
    by_format: dict[str, int]
    total_discovered: int
    total_registered: int
    production_ready: int
    metadata_only: int
    invalid: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "by_status": self.by_status,
            "by_type": self.by_type,
            "by_format": self.by_format,
            "total_discovered": self.total_discovered,
            "total_registered": self.total_registered,
            "production_ready": self.production_ready,
            "metadata_only": self.metadata_only,
            "invalid": self.invalid,
        }


def _why_not_executable(p: NormalizedPack) -> list[str]:
    """Re-export of the loader's why_not_executable to keep this module
    self-contained."""
    from .agent_pack_loader import why_not_executable as _wne
    return _wne(p)


def _registry_index(registry) -> dict[str, str]:
    """Return ``{agent_ref: agent_id}`` for everything currently in registry."""
    if registry is None:
        return {}
    out: dict[str, str] = {}
    for rec in registry.list_all():
        # rec.pack_data has the agent_ref
        try:
            ref = (rec.pack_data or {}).get("agent_ref", "")
        except Exception:
            ref = ""
        if ref:
            out[ref] = rec.agent_id
    return out


def compute_compatibility(
    agents_dir: str | Path,
    registry=None,
) -> RegistryCompatibilityReport:
    """Compute a compat report for every pack on disk + cross-ref the registry.

    Args:
        agents_dir: directory containing ``<pack_name>/agent_pack.json``
        registry: optional RuntimeAgentRegistry — if provided, each entry
            gets ``registered`` + ``registry_agent_id`` set
    """
    packs = load_packs_from_dir(agents_dir)
    reg_index = _registry_index(registry)

    entries: list[AgentCompatibilityEntry] = []
    by_status: dict[str, int] = {"executable": 0, "metadata_only": 0, "invalid": 0}
    by_type: dict[str, int] = {}
    by_format: dict[str, int] = {}
    production_ready = 0
    metadata_only = 0
    invalid = 0

    for p in packs:
        reg_id = reg_index.get(p.agent_ref)
        entry = AgentCompatibilityEntry(
            agent_ref=p.agent_ref,
            name=p.name,
            version=p.version,
            agent_type=p.agent_type,
            format_version=p.format_version,
            status=p.status.value,
            production_ready=p.production_ready,
            experimental=p.experimental,
            enabled_by_default=p.enabled_by_default,
            tier=p.tier,
            expert_count=p.expert_count,
            tool_count=p.tool_count,
            category=p.category,
            icon=p.icon,
            source_path=p.source_path,
            registered=reg_id is not None,
            registry_agent_id=reg_id,
            validation_errors=list(p.validation_errors),
            validation_warnings=list(p.validation_warnings),
            why_not_executable=_why_not_executable(p),
        )
        entries.append(entry)

        by_status[p.status.value] = by_status.get(p.status.value, 0) + 1
        by_type[p.agent_type] = by_type.get(p.agent_type, 0) + 1
        by_format[p.format_version] = by_format.get(p.format_version, 0) + 1
        if p.production_ready:
            production_ready += 1
        if p.status == PackStatus.METADATA_ONLY:
            metadata_only += 1
        if p.status == PackStatus.INVALID:
            invalid += 1

    return RegistryCompatibilityReport(
        entries=entries,
        by_status=by_status,
        by_type=by_type,
        by_format=by_format,
        total_discovered=len(entries),
        total_registered=sum(1 for e in entries if e.registered),
        production_ready=production_ready,
        metadata_only=metadata_only,
        invalid=invalid,
    )