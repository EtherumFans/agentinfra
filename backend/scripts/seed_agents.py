"""Seed agent_definitions DB from official_agents/**/agent_pack.json.

Phase 3-B2 Loop 0 precondition: ensure the ``agents`` (agent_definitions)
table is populated by pack metadata, not hardcoded. Idempotent upsert by
``(name, version, is_prebuilt=True)`` — prebuilt agents are global
(organization_id=NULL) so they are visible across tenants.

The Hub endpoint ``GET /api/icoder/agents/hub`` is pack-mastered (reads
``official_agents/`` directly); this script seeds the DB-backed
``/api/rest/v1/agent_definitions`` REST API so the two surfaces stay
consistent.

Run standalone:
    python backend/scripts/seed_agents.py
Or import:
    from scripts.seed_agents import seed_agents_from_packs
    await seed_agents_from_packs()
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Allow running from repo root or backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

OFFICIAL_AGENTS_DIR = _BACKEND_DIR / "official_agents"


def _load_packs() -> list[dict[str, Any]]:
    """Read every agent_pack.json under official_agents/."""
    packs: list[dict[str, Any]] = []
    if not OFFICIAL_AGENTS_DIR.exists():
        return packs
    for path in sorted(OFFICIAL_AGENTS_DIR.rglob("agent_pack.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                packs.append(json.load(f))
        except Exception as e:  # noqa: BLE001
            print(f"  WARN: skip malformed pack {path.name}: {e}")
    return packs


def _validate_pack(pack: dict[str, Any]) -> bool:
    """Validate a pack using icoder_runtime.agent_pack.import_pack.

    Returns True if valid, False otherwise. import_pack raises on invalid
    format_version / missing required fields / integrity mismatch.
    """
    try:
        from icoder_runtime.agent_pack import import_pack  # type: ignore
        import_pack(pack)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  WARN: pack validation failed for {pack.get('agent_ref', '?')}: {e}")
        return False


def _build_fields(pack: dict[str, Any]) -> dict[str, Any]:
    """Project an agent_pack.json into Agent model fields."""
    manifest = pack.get("manifest") or {}
    experts = pack.get("experts") or []
    expert_ids = [e.get("expert_id") for e in experts if e.get("expert_id")]
    return dict(
        description=manifest.get("description", ""),
        system_prompt=pack.get("system_prompt", ""),
        icon=manifest.get("icon", "Bot"),
        category=manifest.get("category", "general"),
        expert_ids=expert_ids,
        default_expert_id=expert_ids[0] if expert_ids else "",
        a2a_enabled=bool(pack.get("a2a")),
        config={
            "agent_ref": pack.get("agent_ref", ""),
            "agent_type": pack.get("agent_type", "certified"),
            "format_version": pack.get("format_version", "1.2"),
            "use_case": manifest.get("use_case", ""),
            "maturity": manifest.get("maturity", ""),
            "human_review": manifest.get("human_review", "required"),
            "production_ready": manifest.get("production_ready", False),
            "hidden_from_hub": manifest.get("hidden_from_hub", False),
            "non_goals": pack.get("non_goals", []),
            "output_contract": pack.get("output_contract", {}),
            "permissions": pack.get("permissions", {}),
            "requirements": pack.get("requirements", {}),
            "llm_capabilities": pack.get("llm_capabilities", {}),
            "a2a": pack.get("a2a", {}),
            "runtime_binding": {
                "internal_engine": pack.get("internal_engine", {}),
                "code": pack.get("code", {}),
                "integrity": pack.get("integrity", {}),
            },
        },
        is_prebuilt=True,
        is_published=True,
        status="published",
    )


async def seed_agents_from_packs() -> dict[str, int]:
    """Upsert every official agent pack into the agents table.

    Returns a stats dict: {created, updated, skipped, errors}.
    """
    from app.database import init_db, AsyncSessionLocal
    from app.models.agent import Agent
    from sqlalchemy import select

    await init_db()
    packs = _load_packs()
    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

    if not packs:
        print(f"seed_agents: no packs found under {OFFICIAL_AGENTS_DIR}")
        return stats

    print(f"seed_agents: processing {len(packs)} pack(s)")
    async with AsyncSessionLocal() as session:
        for pack in packs:
            if not _validate_pack(pack):
                stats["errors"] += 1
                continue

            manifest = pack.get("manifest") or {}
            name = manifest.get("name") or pack.get("agent_ref", "").split("/")[-1]
            version = manifest.get("version") or pack.get("agent_ref", "").split("@")[-1]
            if not name or not version:
                print(f"  SKIP: pack missing name/version ({pack.get('agent_ref', '?')})")
                stats["skipped"] += 1
                continue

            q = select(Agent).where(
                Agent.name == name,
                Agent.version == version,
                Agent.is_prebuilt == True,  # noqa: E712
            )
            existing = (await session.execute(q)).scalar_one_or_none()
            fields = _build_fields(pack)

            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                stats["updated"] += 1
            else:
                agent = Agent(name=name, version=version, **fields)
                session.add(agent)
                stats["created"] += 1

        await session.commit()

    print(
        f"seed_agents: {stats['created']} created, "
        f"{stats['updated']} updated, "
        f"{stats['skipped']} skipped, "
        f"{stats['errors']} errors"
    )
    return stats


async def _main() -> int:
    await seed_agents_from_packs()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
