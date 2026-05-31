"""Expert Registry — capability-based expert discovery and matching"""
import json
import logging
import time
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.expert import Expert
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 600  # 10 minutes


class ExpertRegistry:
    """Programmatic registry for discovering and matching experts by capability.

    iCoDer Agentic Framework equivalent: Expert Registry API endpoint that returns
    available experts with their capabilities, descriptions, and configuration.
    """

    # Registry metadata for LLM planner
    SYSTEM_REGISTRY_PROMPT = """You have access to an Expert Registry. Based on the user's request,
determine which experts should be called and in what order.

Available experts (name: capabilities):
{expert_list}

Respond with a JSON plan:
{
  "reasoning": "why these experts were chosen",
  "steps": [
    {"expert_name": "exact name from registry", "input_summary": "what to pass", "reason": "why this expert"}
  ]
}"""

    def __init__(self):
        self._cache: dict = {}
        self._cache_ts: float = 0

    def _cache_valid(self) -> bool:
        return (time.time() - self._cache_ts) < CACHE_TTL_SECONDS and bool(self._cache)

    def _invalidate_cache(self):
        self._cache = {}
        self._cache_ts = 0

    async def list_all(self, db: AsyncSession) -> list[dict]:
        """List all registered experts with their capabilities (cached)."""
        cache_key = "all_experts"
        if self._cache_valid() and cache_key in self._cache:
            return self._cache[cache_key]

        result = await db.execute(
            select(Expert).where(Expert.is_published == True).order_by(Expert.category, Expert.name)
        )
        experts = result.scalars().all()
        entries = [self._expert_to_registry_entry(e) for e in experts]
        self._cache[cache_key] = entries
        self._cache["capability_index"] = self._build_capability_index(experts)
        self._cache_ts = time.time()
        return entries

    async def find_by_capability(self, capability: str, db: AsyncSession) -> list[dict]:
        """Find experts that support a specific capability (cached).

        Capabilities include: diagnosis_coding, procedure_coding, fact_extraction,
        medication_lookup, literature_search, clinical_calculation, etc.
        """
        # Use capability index from cache if available
        if self._cache_valid() and "capability_index" in self._cache:
            idx = self._cache["capability_index"]
            experts = idx.get(capability, [])
            if experts:
                return [self._expert_to_registry_entry(e) for e in experts]

        # Load all published experts and filter in Python (SQLite JSON contains is unreliable)
        result = await db.execute(
            select(Expert).where(Expert.is_published == True)
        )
        all_experts = result.scalars().all()
        experts = [e for e in all_experts if capability in (e.capabilities or [])]
        # Fallback: search by name/description/tags if no capability match
        if not experts:
            cap_lower = capability.lower()
            experts = [e for e in all_experts if (
                cap_lower in e.name.lower() or
                cap_lower in e.description.lower() or
                cap_lower in e.category.lower() or
                any(cap_lower in t.lower() for t in (e.tags or []))
            )]
        # Populate cache on miss
        self._cache["all_experts"] = [self._expert_to_registry_entry(e) for e in all_experts]
        self._cache["capability_index"] = self._build_capability_index(all_experts)
        self._cache_ts = time.time()
        return [self._expert_to_registry_entry(e) for e in experts]

    def _build_capability_index(self, experts: list) -> dict[str, list]:
        """Build a capability → experts index for fast lookup."""
        idx: dict[str, list] = {}
        for e in experts:
            for cap in (e.capabilities or []):
                if cap not in idx:
                    idx[cap] = []
                idx[cap].append(e)
        return idx

    async def match_experts(self, user_request: str, db: AsyncSession) -> dict:
        """Use LLM to match user request to the best experts.

        This is the core of iCoDer-style intelligent orchestration:
        the LLM analyzes the request and selects which experts to invoke.
        """
        all_experts = await self.list_all(db)
        if not all_experts:
            return {"plan": [], "reasoning": "No experts registered"}

        expert_list = "\n".join(
            f"- {e['name']}: {', '.join(e.get('capabilities', []))} ({e['category']})"
            for e in all_experts
        )

        prompt = self.SYSTEM_REGISTRY_PROMPT.format(expert_list=expert_list)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_request},
        ]

        try:
            result = await llm_service.extract_json(
                prompt=prompt,
                text=user_request,
                schema_hint="plan with steps array"
            )
            return result if isinstance(result, dict) else {"plan": [], "reasoning": str(result)}
        except Exception as e:
            logger.error(f"Expert matching failed: {e}")
            # Fallback: return all coding experts
            coding_experts = [e for e in all_experts if "coding" in e.get("category", "")]
            return {
                "plan": [{"expert_name": "Medical Coding Expert (General)", "input_summary": user_request[:100]}],
                "reasoning": f"Fallback to coding experts (LLM matching failed: {e})",
            }

    async def get_capabilities(self, db: AsyncSession) -> list[str]:
        """Get all unique capabilities across all registered experts."""
        result = await db.execute(
            select(Expert).where(Expert.is_published == True)
        )
        experts = result.scalars().all()
        caps = set()
        for e in experts:
            for c in (e.capabilities or []):
                caps.add(c)
        return sorted(caps)

    def _expert_to_registry_entry(self, expert: Expert) -> dict:
        return {
            "id": expert.id,
            "name": expert.name,
            "description": expert.description,
            "category": expert.category,
            "capabilities": expert.capabilities or [],
            "input_schema": expert.input_schema,
            "output_schema": expert.output_schema,
            "tags": expert.tags or [],
            "is_prebuilt": expert.is_prebuilt,
            "usage_count": expert.usage_count,
        }


expert_registry = ExpertRegistry()
