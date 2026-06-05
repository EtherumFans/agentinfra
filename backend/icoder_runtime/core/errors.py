"""Structured errors for iCoDer Runtime.

All errors carry a machine-readable code and human-readable message.
Callers can match on code without parsing strings.
"""

from typing import Any


class RuntimeErrorBase(Exception):
    """Base for all Runtime errors with structured payload."""

    code: str = "RUNTIME_ERROR"
    message: str = "An unexpected runtime error occurred."
    detail: dict[str, Any] | None = None

    def __init__(self, message: str = "", detail: dict[str, Any] | None = None):
        self.message = message or self.message
        self.detail = detail
        super().__init__(self.message)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail:
            d["detail"] = self.detail
        return d


class RuntimeConfigurationError(RuntimeErrorBase):
    """Runtime is not properly configured — missing LLM provider, storage, etc."""

    code = "RUNTIME_CONFIGURATION_ERROR"


class LLMProviderNotConfigured(RuntimeConfigurationError):
    """No LLM provider has been configured for this Runtime instance."""

    code = "LLM_PROVIDER_NOT_CONFIGURED"
    message = "No LLM provider configured for this runtime."


class ValidationError(RuntimeErrorBase):
    """Agent package validation failed."""

    code = "VALIDATION_ERROR"

    def __init__(self, errors: list[str], message: str = ""):
        super().__init__(message=message or "Agent package validation failed.", detail={"errors": errors})


class AgentNotFoundError(RuntimeErrorBase):
    """Requested agent was not found in the registry."""

    code = "AGENT_NOT_FOUND"

    def __init__(self, agent_id: str):
        super().__init__(message=f"Agent not found: {agent_id}", detail={"agent_id": agent_id})


class InstallError(RuntimeErrorBase):
    """Agent installation failed."""

    code = "INSTALL_ERROR"


class MarketplaceError(RuntimeErrorBase):
    """Marketplace operation failed."""

    code = "MARKETPLACE_ERROR"


class ProviderError(RuntimeErrorBase):
    """LLM provider returned an error."""

    code = "PROVIDER_ERROR"
