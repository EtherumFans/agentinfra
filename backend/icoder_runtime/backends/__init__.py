"""iCoDer Agent Backend Provider package.

Phase 4-A (2026-07-07): foundation for the unified
``AgentBackendProvider`` interface. Concrete providers and the
``ProviderRegistry`` live in this package.

Importing this package is cheap — it does NOT auto-register providers.
Registration happens lazily on first ``ProviderRegistry.get()`` /
``resolve_from_agent_pack()`` call, so importing this module does not
affect startup speed (per Task 2 requirement #5).
"""

from __future__ import annotations

from .contracts import (
    AgentBackendProvider,
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    BackendType,
    FinishState,
    OutputContract,
    OutputIssue,
    ProviderCapability,
    ProviderHealth,
    ProviderStatus,
    Severity,
    ToolCallRecord,
)
from .registry import (
    ProviderNotRegisteredError,
    ProviderRegistry,
    get_default_registry,
    reset_default_registry,
)

__all__ = [
    # Contracts
    "AgentBackendProvider",
    "BackendRequest",
    "BackendResponse",
    "AgentRunContext",
    "OutputContract",
    "OutputIssue",
    "ToolCallRecord",
    "ProviderHealth",
    "ProviderCapability",
    "BackendType",
    "FinishState",
    "ProviderStatus",
    "Severity",
    # Registry
    "ProviderRegistry",
    "ProviderNotRegisteredError",
    "get_default_registry",
    "reset_default_registry",
]
