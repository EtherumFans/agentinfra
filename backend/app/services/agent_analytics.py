"""Agent Analytics — usage statistics and monitoring for Agents.

iCoDer Agentic Framework equivalent: per-Agent usage tracking, performance
metrics, and operational monitoring.
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent import Agent
from app.models.expert import Expert
from app.models.billing import Transaction

logger = logging.getLogger(__name__)


class AgentAnalytics:
    """Collect and report per-Agent usage statistics."""

    async def get_agent_stats(self, agent_id: str, db: AsyncSession) -> dict:
        """Get usage stats for a specific Agent."""
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            return {"error": "Agent not found"}

        # Count bound experts
        expert_count = 0
        expert_names = []
        if agent.expert_ids:
            exp_result = await db.execute(
                select(Expert.name).where(Expert.id.in_(agent.expert_ids))
            )
            expert_names = [r[0] for r in exp_result]
            expert_count = len(expert_names)

        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "category": agent.category,
            "total_calls": agent.usage_count or 0,
            "experts_bound": expert_count,
            "expert_names": expert_names,
            "routing_strategy": (agent.config or {}).get("routing_strategy", "single_expert"),
            "a2a_enabled": agent.a2a_enabled,
            "is_prebuilt": agent.is_prebuilt,
            "created_at": agent.created_at.isoformat(),
        }

    async def get_overall_stats(self, db: AsyncSession) -> dict:
        """Get aggregate stats across all Agents."""
        # Agent counts
        total_result = await db.execute(select(func.count(Agent.id)))
        total_agents = total_result.scalar() or 0

        prebuilt_result = await db.execute(
            select(func.count(Agent.id)).where(Agent.is_prebuilt == True)
        )
        prebuilt_count = prebuilt_result.scalar() or 0

        # Total usage
        usage_result = await db.execute(
            select(func.sum(Agent.usage_count))
        )
        total_calls = usage_result.scalar() or 0

        # Agent by category
        cat_result = await db.execute(
            select(Agent.category, func.count(Agent.id))
            .group_by(Agent.category)
        )
        by_category = {r[0]: r[1] for r in cat_result}

        # Top agents by usage
        top_result = await db.execute(
            select(Agent.name, Agent.usage_count)
            .order_by(Agent.usage_count.desc())
            .limit(5)
        )
        top_agents = [{"name": r[0], "calls": r[1] or 0} for r in top_result]

        return {
            "total_agents": total_agents,
            "prebuilt_agents": prebuilt_count,
            "custom_agents": total_agents - prebuilt_count,
            "total_calls": total_calls,
            "by_category": by_category,
            "top_agents": top_agents,
        }


agent_analytics = AgentAnalytics()
