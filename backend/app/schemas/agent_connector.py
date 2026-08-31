"""Strict public schemas for Agentic v2 connector resources."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ConnectorType = Literal["registry", "mcp", "agent", "a2a", "schema"]
AuthPolicy = Literal["none", "bearer", "oauth2"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegistryConnectorConfig(_StrictModel):
    registry_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: str = Field(default="latest", min_length=1, max_length=32)
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    total_timeout_seconds: float = Field(default=10.0, ge=0.1, le=60.0)
    max_response_bytes: int = Field(default=262_144, ge=1024, le=1_048_576)


class MCPConnectorConfig(_StrictModel):
    url: str = Field(min_length=1, max_length=2048)
    transport: Literal["streamable-http"] = "streamable-http"
    auth_policy: AuthPolicy = "none"
    tool_allowlist: list[str] = Field(default_factory=list, max_length=64)
    connect_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    total_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    max_attempts: int = Field(default=1, ge=1, le=3)
    max_response_bytes: int = Field(default=262_144, ge=1024, le=1_048_576)
    concurrency_limit: int = Field(default=4, ge=1, le=32)
    redirect_policy: Literal["deny", "same-origin"] = "deny"
    max_redirects: int = Field(default=0, ge=0, le=2)

    @model_validator(mode="after")
    def validate_timeouts(self):
        if self.total_timeout_seconds < self.connect_timeout_seconds:
            raise ValueError("total timeout must be >= connect timeout")
        if self.redirect_policy == "deny" and self.max_redirects != 0:
            raise ValueError("max_redirects must be 0 when redirect_policy=deny")
        if self.redirect_policy == "same-origin" and self.max_redirects == 0:
            raise ValueError("same-origin redirects require max_redirects >= 1")
        return self


class AgentConnectorConfig(_StrictModel):
    target_agent_id: str = Field(min_length=1, max_length=12)
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    max_fan_out: int = Field(default=4, ge=1, le=16)
    total_timeout_seconds: float = Field(default=30.0, ge=0.1, le=120.0)
    max_response_bytes: int = Field(default=262_144, ge=1024, le=1_048_576)


class A2AConnectorConfig(_StrictModel):
    endpoint: str = Field(min_length=1, max_length=2048)
    agent_card_url: str | None = Field(default=None, min_length=1, max_length=2048)
    agent_card_digest: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$",
    )
    versions: list[Literal["1.0"]] = Field(default_factory=lambda: ["1.0"], min_length=1, max_length=1)
    bindings: list[Literal["JSONRPC", "HTTP+JSON"]] = Field(min_length=1, max_length=2)
    auth_policy: AuthPolicy = "none"
    connect_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    total_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    max_attempts: int = Field(default=1, ge=1, le=3)
    max_response_bytes: int = Field(default=262_144, ge=1024, le=1_048_576)
    concurrency_limit: int = Field(default=4, ge=1, le=32)
    redirect_policy: Literal["deny", "same-origin"] = "deny"
    max_redirects: int = Field(default=0, ge=0, le=2)

    @model_validator(mode="after")
    def validate_timeouts(self):
        if self.total_timeout_seconds < self.connect_timeout_seconds:
            raise ValueError("total timeout must be >= connect timeout")
        if self.redirect_policy == "deny" and self.max_redirects != 0:
            raise ValueError("max_redirects must be 0 when redirect_policy=deny")
        if self.redirect_policy == "same-origin" and self.max_redirects == 0:
            raise ValueError("same-origin redirects require max_redirects >= 1")
        return self


class SchemaConnectorConfig(_StrictModel):
    input_schema: dict | None = None
    output_schema: dict | None = None
    schema_ref: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def require_schema(self):
        if self.input_schema is None and self.output_schema is None and not self.schema_ref:
            raise ValueError("input_schema, output_schema, or schema_ref is required")
        return self


ConnectorConfig = (
    RegistryConnectorConfig
    | MCPConnectorConfig
    | AgentConnectorConfig
    | A2AConnectorConfig
    | SchemaConnectorConfig
)


class ConnectorCreateRequest(_StrictModel):
    type: ConnectorType
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    enabled: bool = False
    config: ConnectorConfig

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized


class ConnectorUpdateRequest(_StrictModel):
    type: ConnectorType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    config: ConnectorConfig | None = None
    expected_version: int = Field(ge=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized


class CredentialBindRequest(_StrictModel):
    provider: Literal["vault", "kms", "secret-manager"]
    secret_ref: str = Field(
        min_length=8,
        max_length=512,
        json_schema_extra={"writeOnly": True},
    )
    secret_type: Literal["bearer", "oauth2-client", "api-key"]
    expected_version: int | None = Field(default=None, ge=1)


class CredentialMetadataResponse(_StrictModel):
    present: bool
    provider: str | None = None
    secret_type: str | None = None
    fingerprint: str | None = None
    status: str | None = None
    version: int | None = None
    rotated_at: datetime | None = None


class ConnectorResponse(_StrictModel):
    id: str
    agent_id: str
    type: ConnectorType
    name: str
    description: str
    enabled: bool
    config: dict
    target_agent_id: str | None
    normalized_url: str | None
    schema_ref: str | None
    schema_digest: str | None
    version: int
    credential: CredentialMetadataResponse
    created_by: str
    created_at: datetime
    updated_at: datetime


class ConnectorListResponse(_StrictModel):
    connectors: list[ConnectorResponse]
    total: int


CONFIG_MODELS = {
    "registry": RegistryConnectorConfig,
    "mcp": MCPConnectorConfig,
    "agent": AgentConnectorConfig,
    "a2a": A2AConnectorConfig,
    "schema": SchemaConnectorConfig,
}


__all__ = [
    "CONFIG_MODELS", "ConnectorType", "ConnectorCreateRequest",
    "ConnectorUpdateRequest", "CredentialBindRequest",
    "CredentialMetadataResponse", "ConnectorResponse", "ConnectorListResponse",
]
