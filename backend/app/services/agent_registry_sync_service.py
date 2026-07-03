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
        result = await db.execute(select(AgentModel))
        db_agents = result.scalars().all()

        # Build lookup maps
        reg_map: dict[str, Any] = {}
        for r in registry_records:
            reg_map[r.agent_id] = r
            # Also index by publisher/name@version pattern for fuzzy matching
            ref = f"{r.publisher_name or 'unknown'}/{r.name}@{r.version}"
            reg_map[ref] = r

        db_map: dict[str, Any] = {a.id: a for a in db_agents}

        inconsistencies: list[Inconsistency] = []

        # Registry agents missing from DB
        for agent_ref, reg_rec in reg_map.items():
            if agent_ref not in db_map and reg_rec.agent_id not in db_map:
                inconsistencies.append(Inconsistency(
                    type="missing_in_db",
                    agent_ref=reg_rec.agent_id,
                    detail=f"Agent '{reg_rec.name}' present in Registry but missing from DB.",
                ))

        # DB agents missing from Registry (stale/orphaned references)
        for db_id, db_agent in db_map.items():
            found = db_id in reg_map
            if not found:
                # Try partial match
                for reg_id, reg_rec in reg_map.items():
                    if db_id in reg_id or reg_id in db_id:
                        found = True
                        break
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
                if inc.type == "missing_in_db":
                    reg_rec = self._registry.get(inc.agent_ref)
                    try:
                        existing = await db.execute(
                            select(AgentModel).where(AgentModel.id == inc.agent_ref)
                        )
                        if existing.scalar_one_or_none():
                            continue  # Already exists (race)

                        db_agent = AgentModel(
                            id=reg_rec.agent_id,
                            name=reg_rec.name,
                            description=reg_rec.description,
                            category=reg_rec.category,
                            icon=reg_rec.icon,
                            system_prompt=reg_rec.system_prompt,
                            expert_ids=reg_rec.expert_ids or [],
                            status="published",
                        )
                        db.add(db_agent)
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
