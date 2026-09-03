"""Server-owned OAuth Client Agent and purpose delegation grants."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent


DELEGATABLE_PURPOSES = frozenset({
    "treatment",
    "payment",
    "healthcare_operations",
    "quality_improvement",
    "research",
    "public_health",
})
AGENT_GRANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
MAX_AGENT_GRANTS = 64


class OAuthDelegationValidationError(ValueError):
    def __init__(self, code: str, *, values: list[str] | None = None) -> None:
        self.code = code
        self.values = values or []
        super().__init__(code)


def parse_grant_list(raw: str) -> list[str]:
    """Parse a legacy form field without supporting wildcard syntax."""
    return [item for item in re.split(r"[\s,]+", raw or "") if item]


def normalize_agent_grants(values: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = str(raw).strip()
        if not value:
            continue
        if value == "*" or AGENT_GRANT_RE.fullmatch(value) is None:
            raise OAuthDelegationValidationError(
                "INVALID_AGENT_GRANT", values=[value],
            )
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    if len(normalized) > MAX_AGENT_GRANTS:
        raise OAuthDelegationValidationError(
            "TOO_MANY_AGENT_GRANTS", values=normalized,
        )
    return normalized


def normalize_purpose_grants(values: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized = sorted({str(value).strip() for value in values or [] if str(value).strip()})
    invalid = [value for value in normalized if value not in DELEGATABLE_PURPOSES]
    if invalid:
        raise OAuthDelegationValidationError(
            "INVALID_PURPOSE_GRANT", values=invalid,
        )
    return normalized


@lru_cache(maxsize=1)
def runnable_official_agent_ids() -> frozenset[str]:
    """Return exact short IDs for executable, user-visible official Agents."""
    from icoder_runtime.core.agent_pack_loader import load_pack
    from icoder_runtime.core.agent_pack_schema import PackStatus

    official_dir = Path(__file__).resolve().parents[2] / "official_agents"
    result: set[str] = set()
    for path in official_dir.rglob("agent_pack.json") if official_dir.exists() else ():
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
            normalized = load_pack(pack)
        except Exception:
            continue
        manifest = pack.get("manifest") or {}
        if manifest.get("hidden_from_hub") is True:
            continue
        if pack.get("agent_type") in {"expert-stub", "internal_engine"}:
            continue
        if manifest.get("maturity") in {None, "metadata-only", "stub"}:
            continue
        if normalized.status != PackStatus.EXECUTABLE:
            continue
        reference = str(pack.get("agent_ref") or "")
        agent_id = reference.rsplit("/", 1)[-1].split("@", 1)[0].strip()
        if agent_id:
            result.add(agent_id)
    return frozenset(result)


async def validate_agent_grants_exist(
    db: AsyncSession,
    *,
    organization_id: str,
    agent_ids: list[str],
) -> list[str]:
    """Reject unknown and cross-tenant Agent grants without leaking ownership."""
    normalized = normalize_agent_grants(agent_ids)
    official = runnable_official_agent_ids()
    custom_candidates = [agent_id for agent_id in normalized if agent_id not in official]
    custom: set[str] = set()
    if custom_candidates:
        custom = set((await db.execute(select(Agent.id).where(
            Agent.organization_id == organization_id,
            Agent.id.in_(custom_candidates),
        ))).scalars().all())
    unknown = [
        agent_id for agent_id in normalized
        if agent_id not in official and agent_id not in custom
    ]
    if unknown:
        raise OAuthDelegationValidationError(
            "UNKNOWN_AGENT_GRANT", values=unknown,
        )
    return normalized


__all__ = [
    "DELEGATABLE_PURPOSES",
    "OAuthDelegationValidationError",
    "normalize_agent_grants",
    "normalize_purpose_grants",
    "parse_grant_list",
    "runnable_official_agent_ids",
    "validate_agent_grants_exist",
]
