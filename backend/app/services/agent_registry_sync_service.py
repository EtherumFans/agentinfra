"""Agent Registry Sync Service — ensures RuntimeAgentRegistry and DB Agent table consistency.

Registry = master data source for Runtime execution.
DB Agent table = display/search/admin data source for platform UI.

This service checks consistency, reports inconsistencies, and provides repair.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _registry_agent_ref(record: Any) -> str:
    raw_pack = getattr(record, "pack_data", None)
    pack = raw_pack if isinstance(raw_pack, dict) else {}
    return str(pack.get("agent_ref") or "").strip()


def _db_agent_ref(agent: Any) -> str:
    config = agent.config if isinstance(agent.config, dict) else {}
    return str(config.get("agent_ref") or "").strip()


def _is_registry_projection_managed(agent: Any) -> bool:
    config = agent.config if isinstance(agent.config, dict) else {}
    return config.get("registry_projection_managed") is True


def _runtime_agent_id_from_ref(agent_ref: str) -> str:
    tail = str(agent_ref or "").rsplit("/", 1)[-1]
    return tail.split("@", 1)[0].strip()


def _registry_record_db_fields(record: Any) -> dict[str, Any]:
    """Project one installed Pack into a complete global prebuilt DB row."""
    pack = record.pack_data if isinstance(record.pack_data, dict) else {}
    manifest = pack.get("manifest") if isinstance(pack.get("manifest"), dict) else {}
    experts = pack.get("experts") if isinstance(pack.get("experts"), list) else []
    expert_ids = [
        str(item.get("expert_id") or item.get("id") or "").strip()
        for item in experts
        if isinstance(item, dict)
        and str(item.get("expert_id") or item.get("id") or "").strip()
    ]
    agent_ref = _registry_agent_ref(record)
    runtime_agent_id = _runtime_agent_id_from_ref(agent_ref)
    return {
        "organization_id": None,
        "name": str(manifest.get("name") or record.name or runtime_agent_id),
        "description": str(manifest.get("description") or record.description or ""),
        "category": str(manifest.get("category") or record.category or "general"),
        "icon": str(manifest.get("icon") or record.icon or "Bot"),
        "system_prompt": str(pack.get("system_prompt") or record.system_prompt or ""),
        "expert_ids": expert_ids,
        "default_expert_id": expert_ids[0] if expert_ids else "",
        "a2a_enabled": bool(pack.get("a2a")),
        "config": {
            "agent_ref": agent_ref,
            "runtime_agent_id": runtime_agent_id,
            "registry_agent_id": str(record.agent_id or ""),
            "registry_projection_managed": True,
            "agent_type": pack.get("agent_type", "certified"),
            "format_version": pack.get("format_version", "1.2"),
            "use_case": manifest.get("use_case", ""),
            "maturity": manifest.get("maturity", ""),
            "human_review": manifest.get("human_review", "required"),
            "production_ready": bool(manifest.get("production_ready", False)),
            "hidden_from_hub": bool(manifest.get("hidden_from_hub", False)),
            "non_goals": list(pack.get("non_goals") or []),
            "output_contract": dict(pack.get("output_contract") or {}),
            "permissions": dict(pack.get("permissions") or {}),
            "requirements": dict(pack.get("requirements") or {}),
            "llm_capabilities": dict(pack.get("llm_capabilities") or {}),
            "a2a": dict(pack.get("a2a") or {}),
            "runtime_binding": {
                "internal_engine": dict(pack.get("internal_engine") or {}),
                "code": dict(pack.get("code") or {}),
                "integrity": dict(pack.get("integrity") or {}),
            },
        },
        "version": str(manifest.get("version") or record.version or "1.0.0"),
        "status": "published",
        "is_prebuilt": True,
        "is_published": True,
        "created_by": "",
        "usage_count": 0,
        "canonical_key": runtime_agent_id or None,
        "agent_type": "orchestrator",
        "aliases": [str(record.agent_id)] if record.agent_id else [],
    }


_PACK_PROJECTION_FIELDS = (
    "organization_id",
    "name",
    "description",
    "category",
    "icon",
    "system_prompt",
    "expert_ids",
    "default_expert_id",
    "a2a_enabled",
    "config",
    "version",
    "status",
    "is_prebuilt",
    "is_published",
    "canonical_key",
    "agent_type",
    "aliases",
)


def _projection_mismatches(agent: Any, expected: dict[str, Any]) -> list[str]:
    """Return Pack-mastered fields whose DB projection has drifted.

    Operational counters and timestamps are intentionally excluded because
    they are DB-owned state, not Pack metadata.
    """
    return [
        field_name
        for field_name in _PACK_PROJECTION_FIELDS
        if getattr(agent, field_name, None) != expected[field_name]
    ]


@dataclass
class Inconsistency:
    type: str  # "missing_in_db" | "missing_in_registry" | "field_mismatch"
    agent_ref: str
    detail: str = ""
    registry_data: dict | None = None
    db_data: dict | None = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "agent_ref": self.agent_ref,
            "detail": self.detail,
            "registry_data": self.registry_data,
            "db_data": self.db_data,
        }


@dataclass
class SyncReport:
    consistent: bool
    total_registry: int = 0
    total_db: int = 0
    inconsistencies: list[Inconsistency] = field(default_factory=list)
    checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "consistent": self.consistent,
            "total_registry": self.total_registry,
            "total_db": self.total_db,
            "inconsistency_count": len(self.inconsistencies),
            "inconsistencies": [i.to_dict() for i in self.inconsistencies],
            "checked_at": self.checked_at,
        }


@dataclass
class SyncState:
    """Snapshot of the last registry→DB sync run. In-memory only, resets on restart.

    Set by repair_from_registry(), read by /api/runtime/status. Cycle 25 introduced
    this so that startup sync failures can't be silently swallowed — the status
    endpoint always reports the latest outcome.
    """
    last_sync_at: datetime | None = None
    last_status: str = "never_run"  # "success" | "failed" | "never_run"
    last_error: str | None = None
    agents_created: int = 0
    agents_failed: int = 0
    total_in_registry: int = 0
    total_in_db: int = 0
    checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "agents_created": self.agents_created,
            "agents_failed": self.agents_failed,
            "total_in_registry": self.total_in_registry,
            "total_in_db": self.total_in_db,
            "checked_at": self.checked_at,
        }


class AgentRegistrySyncService:
    """Checks and repairs consistency between RuntimeAgentRegistry and DB Agent table."""

    # Class-level sync state — set by repair_from_registry(), read by status endpoints.
    # In-memory only; resets on restart. Acceptable because sync runs at every startup,
    # so last_state is always fresh post-startup.
    last_state: SyncState | None = None

    def __init__(self, registry=None):
        from icoder_runtime.core.registry import RuntimeAgentRegistry, get_registry
        self._registry: RuntimeAgentRegistry = registry or get_registry()

    async def check_consistency(self, db: AsyncSession) -> SyncReport:
        """Compare registry with DB. Returns a SyncReport with all inconsistencies."""
        from app.models.agent import Agent as AgentModel

        registry_records = self._registry.list_all()
        result = await db.execute(
            select(AgentModel).where(AgentModel.is_prebuilt == True)  # noqa: E712
        )
        db_agents = [
            agent for agent in result.scalars().all()
            if _is_registry_projection_managed(agent)
        ]

        # Build lookup maps
        reg_map: dict[str, Any] = {}
        reg_refs: dict[str, Any] = {}
        for r in registry_records:
            reg_map[r.agent_id] = r
            ref = _registry_agent_ref(r)
            if ref:
                reg_refs[ref] = r

        db_map: dict[str, Any] = {a.id: a for a in db_agents}
        db_refs: dict[str, Any] = {
            ref: agent
            for agent in db_agents
            if (ref := _db_agent_ref(agent))
        }
        db_registry_ids: dict[str, Any] = {
            str(agent.config.get("registry_agent_id")): agent
            for agent in db_agents
            if isinstance(agent.config, dict)
            and agent.config.get("registry_agent_id")
        }

        inconsistencies: list[Inconsistency] = []

        # Registry agents missing from DB
        for registry_id, reg_rec in reg_map.items():
            ref = _registry_agent_ref(reg_rec)
            db_agent = (
                db_map.get(registry_id)
                or db_registry_ids.get(registry_id)
                or (db_refs.get(ref) if ref else None)
            )
            if db_agent is None:
                inconsistencies.append(Inconsistency(
                    type="missing_in_db",
                    agent_ref=reg_rec.agent_id,
                    detail=f"Agent '{reg_rec.name}' present in Registry but missing from DB.",
                ))
                continue

            expected = _registry_record_db_fields(reg_rec)
            mismatches = _projection_mismatches(db_agent, expected)
            if mismatches:
                inconsistencies.append(Inconsistency(
                    type="field_mismatch",
                    agent_ref=reg_rec.agent_id,
                    detail=(
                        f"Agent '{reg_rec.name}' DB projection differs from "
                        f"Registry Pack fields: {', '.join(mismatches)}."
                    ),
                    registry_data={
                        "agent_ref": ref,
                        "fields": {key: expected[key] for key in mismatches},
                    },
                    db_data={
                        "id": db_agent.id,
                        "fields": {
                            key: getattr(db_agent, key, None) for key in mismatches
                        },
                    },
                ))

        # DB agents missing from Registry (stale/orphaned references)
        for db_id, db_agent in db_map.items():
            config = db_agent.config if isinstance(db_agent.config, dict) else {}
            registry_id = str(config.get("registry_agent_id") or "")
            ref = _db_agent_ref(db_agent)
            found = (
                db_id in reg_map
                or bool(registry_id and registry_id in reg_map)
                or bool(ref and ref in reg_refs)
            )
            if not found:
                inconsistencies.append(Inconsistency(
                    type="missing_in_registry",
                    agent_ref=db_id,
                    detail=f"Agent '{getattr(db_agent, 'name', db_id)}' present in DB but missing from Registry.",
                    db_data={"id": db_id, "name": getattr(db_agent, "name", ""), "status": getattr(db_agent, "status", "")},
                ))

        report = SyncReport(
            consistent=len(inconsistencies) == 0,
            total_registry=len(registry_records),
            total_db=len(db_agents),
            inconsistencies=inconsistencies,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

        if not report.consistent:
            logger.warning(f"Registry-DB inconsistency: {len(inconsistencies)} issues found.")
        return report

    async def repair_from_registry(self, db: AsyncSession) -> dict[str, Any]:
        """Create/update DB Agent records for all agents in the Registry that are missing from DB.

        This is the primary repair direction: Registry is authoritative.
        Sets AgentRegistrySyncService.last_state — never re-raises so that callers
        (main.py startup) can't silently swallow the failure.
        """
        from app.models.agent import Agent as AgentModel

        state = SyncState(
            last_sync_at=datetime.now(timezone.utc),
            last_status="failed",  # Set to "success" only on full success
        )
        AgentRegistrySyncService.last_state = state

        repaired: list[str] = []
        failed: list[str] = []

        try:
            report = await self.check_consistency(db)
            state.total_in_registry = report.total_registry
            state.total_in_db = report.total_db
            state.checked_at = report.checked_at

            for inc in report.inconsistencies:
                if inc.type in {"missing_in_db", "field_mismatch"}:
                    reg_rec = self._registry.get(inc.agent_ref)
                    try:
                        fields = _registry_record_db_fields(reg_rec)
                        ref = str(fields["config"].get("agent_ref") or "")
                        db_agent = None
                        if inc.db_data and inc.db_data.get("id"):
                            existing = await db.execute(
                                select(AgentModel).where(
                                    AgentModel.id == str(inc.db_data["id"])
                                )
                            )
                            db_agent = existing.scalar_one_or_none()
                        if db_agent is None:
                            existing = await db.execute(
                                select(AgentModel).where(
                                    AgentModel.id == inc.agent_ref
                                )
                            )
                            db_agent = existing.scalar_one_or_none()
                        if db_agent is None and ref:
                            candidates = await db.execute(
                                select(AgentModel).where(
                                    AgentModel.is_prebuilt == True  # noqa: E712
                                )
                            )
                            db_agent = next(
                                (
                                    item for item in candidates.scalars().all()
                                    if _db_agent_ref(item) == ref
                                ),
                                None,
                            )
                        if db_agent is None:
                            db_agent = AgentModel(**fields)
                            db.add(db_agent)
                        else:
                            # Upgrade rows created by the former incomplete
                            # repair path instead of leaving an orphan clone-like row.
                            for key, value in fields.items():
                                setattr(db_agent, key, value)
                        repaired.append(inc.agent_ref)
                    except Exception as e:
                        logger.error(f"Failed to repair DB for {inc.agent_ref}: {e}")
                        failed.append(inc.agent_ref)

            if repaired:
                await db.commit()
                logger.info(f"Repaired {len(repaired)} agent(s) from Registry to DB: {repaired}")

            state.last_status = "success" if not failed else "failed"
        except Exception as e:
            state.last_status = "failed"
            state.last_error = str(e)
            logger.exception("Registry→DB sync failed (captured in SyncState)")
        finally:
            state.agents_created = len(repaired)
            state.agents_failed = len(failed)

        return {
            "repaired": repaired,
            "failed": failed,
            "total_repaired": len(repaired),
            "total_failed": len(failed),
        }

    async def repair_from_db(self, db: AsyncSession) -> dict[str, Any]:
        """Create Registry records for DB agents missing from Registry.

        Secondary repair direction: reconstructs Registry from DB data.
        """
        from app.models.agent import Agent as AgentModel

        report = await self.check_consistency(db)
        repaired: list[str] = []
        failed: list[str] = []

        for inc in report.inconsistencies:
            if inc.type == "missing_in_registry" and inc.db_data:
                try:
                    # Build a minimal pack from DB data
                    db_agent_result = await db.execute(
                        select(AgentModel).where(AgentModel.id == inc.agent_ref)
                    )
                    db_agent = db_agent_result.scalar_one_or_none()
                    if not db_agent:
                        continue

                    pack = {
                        "format_version": "1.1",
                        "agent_type": "certified",
                        "manifest": {
                            "name": getattr(db_agent, "name", inc.agent_ref),
                            "version": "1.0.0",
                            "description": getattr(db_agent, "description", ""),
                            "category": getattr(db_agent, "category", "general"),
                            "icon": getattr(db_agent, "icon", "Bot"),
                        },
                        "system_prompt": getattr(db_agent, "system_prompt", ""),
                        "experts": [],
                        "tools": [],
                        "permissions": {},
                        "requirements": {"min_runtime_version": "1.0.0"},
                        "llm_capabilities": {},
                    }
                    self._registry.install(pack)
                    repaired.append(inc.agent_ref)
                except Exception as e:
                    logger.error(f"Failed to repair Registry for {inc.agent_ref}: {e}")
                    failed.append(inc.agent_ref)

        return {
            "repaired": repaired,
            "failed": failed,
            "total_repaired": len(repaired),
            "total_failed": len(failed),
        }
