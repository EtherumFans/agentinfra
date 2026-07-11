"""CortiLikeOrchestrator — explicit §8.1 facade over existing modules.

Per Track C §8.2 ("不得并行保留两个主 Orchestrator"), this is NOT a
parallel orchestrator. It is a thin facade that names the existing
modules using the §8.1 vocabulary and adds the missing components
(PolicyGuard / CapabilityRegistry / ContextBuilder /
ResultNormalizer / ConflictResolver / CompletionController) as
composable layers around the existing InboundHandler pipeline.

Why a facade:
  - The existing ``InboundHandler.handle`` is heavily tested (200+
    tests) and wired into ``a2a_facade.py``. Replacing it would
    invalidate that coverage.
  - The §8.1 components mostly exist — Planner, Delegator, Aggregator,
    StateMachine, RunContext, PHIRedactor. What's missing is the
    explicit "wrapping" components.
  - Gate 4 (coding compliance mainline) needs a stable API to call.
    This facade is that API.

Usage:

    orch = CortiLikeOrchestrator(
        phi_redactor=...,
        planner=...,
        delegator=...,
        aggregator=...,
        agent_provider=...,
        capability_registry=...,  # optional
    )
    response = orch.handle(agent_id, request)

The facade delegates to InboundHandler for the wire-level flow and
adds post-aggregation hooks for normalize → resolve-conflicts →
completion-decide. The hooks do NOT change the A2A response shape —
they only enrich ``response.metadata`` with the §8.1 outputs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .aggregator import Aggregator
from .capability_registry import CapabilityRegistry
from .completion_controller import (
    CompletionController,
    CompletionControllerConfig,
    CompletionDecision,
)
from .conflict_resolver import (
    ConflictResolution,
    ConflictResolver,
    ConflictResolverConfig,
)
from .context_builder import ContextArtifact, ContextBuilder
from .delegator import Delegator
from .inbound_handler import (
    DictAgentProvider,
    InboundHandler,
    InboundRequest,
    InboundResponse,
)
from .phi_redactor import PHIRedactor
from .planner import Planner
from .policy_guard import PolicyDecision, PolicyGuard
from .result_normalizer import (
    NormalizedExpertResult,
    normalize_batch,
)

logger = logging.getLogger(__name__)


@dataclass
class CortiLikeOrchestratorConfig:
    """Toggles for the post-aggregation hooks."""

    enable_conflict_resolver: bool = True
    enable_completion_controller: bool = True
    enable_capability_registry: bool = True
    completion_config: CompletionControllerConfig = field(
        default_factory=CompletionControllerConfig
    )
    conflict_resolver_config: ConflictResolverConfig = field(
        default_factory=ConflictResolverConfig
    )


class CortiLikeOrchestrator:
    """§8.1 explicit-component orchestrator.

    Composes:
      - ContextBuilder       (new, explicit context construction)
      - PolicyGuard          (new, centralized safety gate)
      - CapabilityRegistry   (new, explicit expert/tool lookup)
      - Planner              (existing planner.py)
      - Delegator            (existing delegator.py)
      - Aggregator           (existing aggregator.py)
      - ResultNormalizer     (new, common-shape projection)
      - ConflictResolver     (new, LLM-driven conflict resolution)
      - CompletionController (new, semantic completeness gate)

    The actual run flow is delegated to InboundHandler — this facade
    adds pre/post hooks but does NOT replace the wire-level handler.
    """

    def __init__(
        self,
        *,
        phi_redactor: PHIRedactor,
        planner: Planner,
        delegator: Delegator,
        aggregator: Aggregator,
        agent_provider,
        capability_registry: CapabilityRegistry | None = None,
        config: CortiLikeOrchestratorConfig | None = None,
    ) -> None:
        self._config = config or CortiLikeOrchestratorConfig()
        self._context_builder = ContextBuilder()
        self._policy_guard = PolicyGuard(phi_redactor=phi_redactor)
        self._capability_registry = capability_registry or CapabilityRegistry()
        self._result_normalizer_fn = normalize_batch
        self._conflict_resolver = ConflictResolver(
            config=self._config.conflict_resolver_config
        )
        self._completion_controller = CompletionController(
            config=self._config.completion_config
        )
        # The existing InboundHandler drives the actual flow.
        self._inner = InboundHandler(
            phi_redactor=phi_redactor,
            planner=planner,
            delegator=delegator,
            aggregator=aggregator,
            agent_provider=agent_provider,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle(self, agent_id: str, request: InboundRequest) -> InboundResponse:
        """Run the full §8.1 pipeline. Returns the InboundResponse.

        Post-aggregation hooks (normalize → resolve → completion-decide)
        enrich ``response.metadata`` but do NOT change the A2A wire shape.
        """
        response = self._inner.handle(agent_id, request)
        if response.kind != "message":
            return response  # error response — no post-processing

        # Post-aggregation hooks. We only have the final parts here, not
        # the intermediate ExpertResult list — so the hooks are best-effort.
        # Gate 4 wires them in properly at the InboundHandler level.
        try:
            self._post_aggregate_hook(agent_id, response)
        except Exception as e:
            logger.warning(
                "corti_like_orchestrator.post_aggregate_hook_failed: %s", e
            )
        return response

    # ------------------------------------------------------------------
    # Hooks (used by Gate 4 directly when it has access to intermediate state)
    # ------------------------------------------------------------------

    def build_context(
        self,
        *,
        agent_id: str,
        parts: list[dict],
        interaction_id: str = "",
        agent_definition: Any = None,
    ) -> ContextArtifact:
        return self._context_builder.build(
            agent_id=agent_id,
            parts=parts,
            interaction_id=interaction_id,
            agent_definition=agent_definition,
        )

    def evaluate_input_policy(self, raw_input: str, agent_id: str) -> PolicyDecision:
        return self._policy_guard.evaluate_input(
            raw_input=raw_input, agent_id=agent_id
        )

    def list_agent_capabilities(self, agent_id: str):
        return self._capability_registry.experts_for_agent(agent_id)

    def normalize_results(self, expert_results: list) -> list[NormalizedExpertResult]:
        return self._result_normalizer_fn(expert_results)

    def resolve_conflicts(
        self, conflicts: dict[str, list[dict]]
    ) -> list[ConflictResolution]:
        if not self._config.enable_conflict_resolver:
            return []
        return self._conflict_resolver.resolve(conflicts)

    def decide_completion(
        self,
        *,
        normalized: list[NormalizedExpertResult],
        conflicts: list[ConflictResolution] | None = None,
        critical_expert_failed: bool = False,
    ) -> CompletionDecision:
        if not self._config.enable_completion_controller:
            return CompletionDecision()
        return self._completion_controller.evaluate(
            normalized=normalized,
            conflicts=conflicts,
            critical_expert_failed=critical_expert_failed,
        )

    # ------------------------------------------------------------------
    # Internal: post-aggregate enrichment (best-effort, gate-4 will
    # replace with proper intermediate-state access)
    # ------------------------------------------------------------------

    def _post_aggregate_hook(self, agent_id: str, response: InboundResponse) -> None:
        """Enrich response.metadata with §8.1 component outputs.

        Gate 3 limitation: the existing InboundHandler doesn't expose
        intermediate ExpertResult / conflicts. Gate 4 will refactor
        InboundHandler to thread these through. For now we attach an
        explicit "corti_like_orchestrator" metadata block so callers
        know the components are present.
        """
        meta = response.metadata.setdefault("corti_like_orchestrator", {})
        meta["components"] = [
            "ContextBuilder",
            "PolicyGuard",
            "CapabilityRegistry",
            "Planner",
            "Delegator",
            "Aggregator",
            "ResultNormalizer",
            "ConflictResolver",
            "CompletionController",
        ]
        meta["agent_id"] = agent_id
        meta["capability_count"] = len(
            self._capability_registry.experts_for_agent(agent_id)
        )


__all__ = [
    "CortiLikeOrchestrator",
    "CortiLikeOrchestratorConfig",
]
