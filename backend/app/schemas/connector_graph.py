"""Strict, server-governed Connector graph contract for Agent runs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_NODE_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"
_OPERATION_PATTERN = r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$"
_INPUT_KEY_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$"


ConditionScalar = str | int | float | bool


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectorGraphCondition(_StrictModel):
    """Deterministic routing predicate over already-redacted structured input.

    Conditions deliberately cannot inspect free text or execute expressions.
    This keeps graph routing auditable and prevents persisted configuration
    from becoming an eval/template injection surface.
    """

    input_key: str = Field(min_length=1, max_length=64, pattern=_INPUT_KEY_PATTERN)
    operator: Literal["exists", "equals", "not_equals", "in"]
    value: ConditionScalar | list[ConditionScalar] | None = None

    @model_validator(mode="after")
    def validate_value(self):
        if self.operator == "exists" and self.value is not None:
            raise ValueError("exists condition must not include value")
        if self.operator in {"equals", "not_equals"} and (
            self.value is None or isinstance(self.value, list)
        ):
            raise ValueError(f"{self.operator} condition requires a scalar value")
        if self.operator == "in" and (
            not isinstance(self.value, list)
            or not self.value
            or len(self.value) > 32
        ):
            raise ValueError("in condition requires 1 to 32 scalar values")
        return self


class ConnectorGraphNode(_StrictModel):
    """One deterministic graph node selected by an administrator, not an LLM."""

    id: str = Field(min_length=1, max_length=32, pattern=_NODE_PATTERN)
    connector_id: str = Field(min_length=1, max_length=12)
    operation: str = Field(min_length=1, max_length=64, pattern=_OPERATION_PATTERN)
    required: bool = True
    idempotent: bool = False
    include_text: bool = False
    input_keys: list[str] = Field(default_factory=list, max_length=32)
    depends_on: list[str] = Field(default_factory=list, max_length=16)
    when: ConnectorGraphCondition | None = None
    data_classification: Literal[
        "non_phi", "deidentified", "phi", "restricted",
    ] = "deidentified"
    purpose_of_use: Literal[
        "treatment",
        "payment",
        "healthcare_operations",
        "quality_improvement",
        "research",
        "public_health",
        "system_operations",
    ] = "treatment"

    @field_validator("input_keys")
    @classmethod
    def validate_input_keys(cls, values: list[str]) -> list[str]:
        import re

        if len(values) != len(set(values)):
            raise ValueError("input_keys must be unique")
        if any(re.fullmatch(_INPUT_KEY_PATTERN, value) is None for value in values):
            raise ValueError("input_keys contains an invalid key")
        return values

    @field_validator("depends_on")
    @classmethod
    def validate_dependencies(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("depends_on must be unique")
        return values

    @model_validator(mode="after")
    def validate_classification(self):
        if self.include_text and self.data_classification == "non_phi":
            raise ValueError("include_text requires deidentified or stricter classification")
        if self.id in self.depends_on:
            raise ValueError("a node cannot depend on itself")
        return self


class ConnectorGraphSpec(_StrictModel):
    version: Literal["1.0"] = "1.0"
    enabled: bool = False
    execution_mode: Literal["sequential", "parallel"] = "sequential"
    max_concurrency: int = Field(default=4, ge=1, le=8)
    nodes: list[ConnectorGraphNode] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_graph(self):
        if self.enabled and not self.nodes:
            raise ValueError("an enabled graph requires at least one node")
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("node ids must be unique")
        known = set(node_ids)
        for node in self.nodes:
            if not set(node.depends_on).issubset(known):
                raise ValueError("depends_on references an unknown node")

        indegree = {node.id: len(node.depends_on) for node in self.nodes}
        dependents: dict[str, list[str]] = {node.id: [] for node in self.nodes}
        for node in self.nodes:
            for dependency in node.depends_on:
                dependents[dependency].append(node.id)
        ready = [node_id for node_id in node_ids if indegree[node_id] == 0]
        visited = 0
        while ready:
            current = ready.pop(0)
            visited += 1
            for dependent in dependents[current]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
        if visited != len(self.nodes):
            raise ValueError("connector graph contains a cycle")
        return self


class ConnectorGraphPutRequest(ConnectorGraphSpec):
    expected_revision: int = Field(ge=0)


class ConnectorGraphResponse(ConnectorGraphSpec):
    revision: int = Field(ge=0)


__all__ = [
    "ConnectorGraphCondition",
    "ConnectorGraphNode",
    "ConnectorGraphSpec",
    "ConnectorGraphPutRequest",
    "ConnectorGraphResponse",
]
