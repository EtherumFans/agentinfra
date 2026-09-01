"""Validation and graph-safety helpers for Agentic v2 connectors."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.agent_connector import AgentConnector
from app.schemas.agent_connector import CONFIG_MODELS
from app.services.database_tenancy import bind_tenant_to_transaction
from app.services.ssrf_guard import check_url


REGISTRY_KEYS = frozenset({
    "memory", "clinical-trials", "drugbank", "medical-calculator",
    "medical-coding", "posos", "pubmed", "interviewing", "web-search",
})
REGISTRY_OPERATIONS = {
    "memory": frozenset({"retrieve", "remember", "recall", "forget"}),
    "clinical-trials": frozenset({"search"}),
    "drugbank": frozenset({"lookup"}),
    "medical-calculator": frozenset({"calculate"}),
    "medical-coding": frozenset({
        "search_icd", "verify_code", "get_guidelines", "explore_code",
        "search_codes", "get_differentiation_hint", "rerank_codes",
        "calibrate_confidence", "validate_codes", "evaluate_compliance",
        "check_documentation_gaps",
    }),
    "posos": frozenset({"guide"}),
    "pubmed": frozenset({"search"}),
    "interviewing": frozenset({"start", "advance", "transcript"}),
    "web-search": frozenset({"search"}),
}
INTERNAL_AGENT_OPERATIONS = frozenset({"run", "delegate", "SendMessage"})
CAPABILITY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
MAX_CONFIG_BYTES = 64 * 1024
MAX_SCHEMA_DEPTH = 16
MAX_SCHEMA_NODES = 512
MAX_AGENT_GRAPH_DEPTH = 8
MAX_AGENT_GRAPH_FAN_OUT = 16
SECRET_KEY_RE = re.compile(
    r"(?:secret|token|password|authorization|auth[_-]?header|api[_-]?key|client[_-]?secret)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"(?:^|\s)(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
RISKY_REGEX_RE = re.compile(r"\([^)]*[+*][^)]*\)[+*]")


@dataclass(frozen=True)
class NormalizedConnectorConfig:
    config: dict
    target_agent_id: str | None = None
    normalized_url: str | None = None
    schema_ref: str | None = None
    schema_digest: str | None = None


class ConnectorValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _raise(code: str, message: str) -> None:
    raise ConnectorValidationError(code, message)


def assert_secret_free(value: object) -> None:
    """Reject secret-shaped keys/values anywhere in a connector config."""
    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > 2048 or depth > 32:
            _raise("CONNECTOR_CONFIG_TOO_COMPLEX", "connector config exceeds complexity limits")
        if isinstance(current, dict):
            for key, item in current.items():
                if SECRET_KEY_RE.search(str(key)):
                    _raise("CONNECTOR_SECRET_FORBIDDEN", "connector config must not contain secret fields")
                stack.append((item, depth + 1))
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str) and SECRET_VALUE_RE.search(current):
            _raise("CONNECTOR_SECRET_FORBIDDEN", "connector config must not contain secret values")


def normalize_remote_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme.lower() != "https" or not parsed.netloc or not parsed.hostname:
        _raise("CONNECTOR_URL_INVALID", "connector URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        _raise(
            "CONNECTOR_URL_INVALID",
            "connector URL cannot contain userinfo, query, or fragment",
        )
    host = parsed.hostname.rstrip(".").lower()
    if not host or any(ord(char) > 127 for char in host):
        _raise("CONNECTOR_URL_INVALID", "connector hostname must be canonical ASCII")
    try:
        host.encode("idna").decode("ascii")
    except UnicodeError:
        _raise("CONNECTOR_URL_INVALID", "connector hostname is not valid IDNA")
    try:
        port = parsed.port
    except ValueError:
        _raise("CONNECTOR_URL_INVALID", "connector port is invalid")
    if port not in (None, 443):
        _raise("CONNECTOR_URL_INVALID", "only the canonical HTTPS port is allowed")
    netloc = f"[{host}]" if ":" in host else host
    normalized = urlunparse(("https", netloc, parsed.path or "", "", "", ""))
    result = check_url(normalized)
    if not result.permitted:
        _raise("CONNECTOR_URL_BLOCKED", "connector URL failed the SSRF policy")
    return normalized.rstrip("/") or normalized


def _validate_egress_when_enabled(url: str | None, enabled: bool) -> None:
    if not enabled or not url:
        return
    environment = os.environ.get("ICODER_ENVIRONMENT", "").strip().lower()
    if environment != "cn":
        return
    allowlist = {
        item.strip().lower()
        for item in os.environ.get("ICODER_CONNECTOR_EGRESS_ALLOWLIST", "").split(",")
        if item.strip()
    }
    host = (urlparse(url).hostname or "").lower()
    if host not in allowlist:
        _raise(
            "CONNECTOR_EGRESS_NOT_APPROVED",
            "external connector host is not approved for the CN environment",
        )


def _inspect_schema(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_SCHEMA_NODES or depth > MAX_SCHEMA_DEPTH:
            _raise("CONNECTOR_SCHEMA_TOO_COMPLEX", "JSON Schema exceeds depth or node limits")
        if isinstance(current, dict):
            dialect = current.get("$schema")
            if dialect and dialect not in {
                "https://json-schema.org/draft/2020-12/schema",
                "https://json-schema.org/draft/2019-09/schema",
            }:
                _raise("CONNECTOR_SCHEMA_DIALECT_UNSUPPORTED", "JSON Schema dialect is not supported")
            ref = current.get("$ref")
            if isinstance(ref, str) and not ref.startswith("#"):
                _raise("CONNECTOR_SCHEMA_EXTERNAL_REF_FORBIDDEN", "external JSON Schema references are forbidden")
            pattern = current.get("pattern")
            if isinstance(pattern, str) and (
                len(pattern) > 256 or RISKY_REGEX_RE.search(pattern)
            ):
                _raise("CONNECTOR_SCHEMA_PATTERN_UNSAFE", "JSON Schema regex is unsafe")
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


def normalize_config(connector_type: str, config: dict, *, enabled: bool) -> NormalizedConnectorConfig:
    if not isinstance(config, dict):
        _raise("CONNECTOR_CONFIG_INVALID", "connector config must be an object")
    try:
        raw = json.dumps(config, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        _raise("CONNECTOR_CONFIG_INVALID", "connector config must be JSON serializable")
    if len(raw) > MAX_CONFIG_BYTES:
        _raise("CONNECTOR_CONFIG_TOO_LARGE", "connector config exceeds 64 KiB")
    assert_secret_free(config)
    model = CONFIG_MODELS.get(connector_type)
    if model is None:
        _raise("CONNECTOR_TYPE_UNSUPPORTED", "connector type is not supported")
    try:
        parsed = model.model_validate(config)
    except ValidationError as exc:
        _raise("CONNECTOR_CONFIG_INVALID", str(exc))
    canonical = parsed.model_dump(mode="json", exclude_none=True)

    if connector_type == "registry":
        if canonical["registry_key"] not in REGISTRY_KEYS:
            _raise("CONNECTOR_REGISTRY_ENTRY_UNAVAILABLE", "registry entry is not server-approved")
        capabilities = canonical.get("capabilities") or []
        if enabled and not capabilities:
            _raise(
                "CONNECTOR_CAPABILITY_ALLOWLIST_REQUIRED",
                "enabled registry connectors require an explicit capability allowlist",
            )
        if (
            len(capabilities) != len(set(capabilities))
            or any(
                CAPABILITY_RE.fullmatch(item or "") is None
                for item in capabilities
            )
        ):
            _raise(
                "CONNECTOR_CAPABILITY_NOT_ALLOWED",
                "registry capability is not approved for this entry",
            )
        return NormalizedConnectorConfig(config=canonical)
    if connector_type == "agent":
        capabilities = canonical.get("capabilities") or []
        if enabled and not capabilities:
            _raise(
                "CONNECTOR_CAPABILITY_ALLOWLIST_REQUIRED",
                "enabled Agent connectors require an explicit capability allowlist",
            )
        if (
            len(capabilities) != len(set(capabilities))
            or any(CAPABILITY_RE.fullmatch(item or "") is None for item in capabilities)
        ):
            _raise(
                "CONNECTOR_CAPABILITY_NOT_ALLOWED",
                "internal Agent capability is not approved",
            )
        return NormalizedConnectorConfig(
            config=canonical,
            target_agent_id=canonical["target_agent_id"],
        )
    if connector_type in {"mcp", "a2a"}:
        key = "url" if connector_type == "mcp" else "endpoint"
        normalized_url = normalize_remote_url(canonical[key])
        canonical[key] = normalized_url
        if connector_type == "mcp":
            tools = canonical.get("tool_allowlist") or []
            if enabled and not tools:
                _raise(
                    "CONNECTOR_TOOL_ALLOWLIST_REQUIRED",
                    "enabled MCP connectors require an explicit tool allowlist",
                )
            if (
                len(tools) != len(set(tools))
                or any(CAPABILITY_RE.fullmatch(item or "") is None for item in tools)
            ):
                _raise(
                    "CONNECTOR_TOOL_NOT_ALLOWED",
                    "MCP tool allowlist is invalid",
                )
        if connector_type == "a2a":
            card_url = canonical.get("agent_card_url")
            if not card_url:
                endpoint = urlparse(normalized_url)
                card_url = urlunparse((
                    "https",
                    endpoint.netloc,
                    "/.well-known/agent-card.json",
                    "",
                    "",
                    "",
                ))
            canonical["agent_card_url"] = normalize_remote_url(card_url)
            if (
                urlparse(canonical["agent_card_url"]).netloc.casefold()
                != urlparse(normalized_url).netloc.casefold()
            ):
                _raise(
                    "CONNECTOR_AGENT_CARD_ORIGIN_MISMATCH",
                    "Agent Card and A2A endpoint must use the same origin",
                )
        _validate_egress_when_enabled(normalized_url, enabled)
        if connector_type == "a2a":
            _validate_egress_when_enabled(canonical["agent_card_url"], enabled)
        return NormalizedConnectorConfig(config=canonical, normalized_url=normalized_url)

    schema_ref = canonical.get("schema_ref")
    if schema_ref and not re.fullmatch(r"schema://[A-Za-z0-9._/-]{1,480}", schema_ref):
        _raise("CONNECTOR_SCHEMA_REF_INVALID", "schema_ref must use the schema:// namespace")
    for key in ("input_schema", "output_schema"):
        if key in canonical:
            _inspect_schema(canonical[key])
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return NormalizedConnectorConfig(
        config=canonical,
        schema_ref=schema_ref,
        schema_digest=digest,
    )


async def require_agent_in_tenant(db: AsyncSession, organization_id: str, agent_id: str) -> Agent:
    await bind_tenant_to_transaction(db, organization_id)
    agent = (
        await db.execute(
            select(Agent).where(
                Agent.organization_id == organization_id,
                Agent.id == agent_id,
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        _raise("AGENT_NOT_FOUND", "agent was not found")
    return agent


async def validate_agent_graph(
    db: AsyncSession,
    *,
    organization_id: str,
    source_agent_id: str,
    target_agent_id: str,
    replacing_connector_id: str | None = None,
) -> None:
    if source_agent_id == target_agent_id:
        _raise("CONNECTOR_AGENT_SELF_LOOP", "agent connector cannot target itself")
    await require_agent_in_tenant(db, organization_id, target_agent_id)
    rows = (
        await db.execute(
            select(
                AgentConnector.id,
                AgentConnector.agent_id,
                AgentConnector.target_agent_id,
            ).where(
                AgentConnector.organization_id == organization_id,
                AgentConnector.type == "agent",
                AgentConnector.target_agent_id.is_not(None),
                AgentConnector.deleted_at.is_(None),
            )
        )
    ).all()
    graph: dict[str, list[str]] = {}
    for connector_id, agent_id, target_id in rows:
        if replacing_connector_id and connector_id == replacing_connector_id:
            continue
        graph.setdefault(agent_id, []).append(target_id)
    graph.setdefault(source_agent_id, []).append(target_agent_id)
    if any(len(targets) > MAX_AGENT_GRAPH_FAN_OUT for targets in graph.values()):
        _raise("CONNECTOR_AGENT_FAN_OUT_EXCEEDED", "agent connector fan-out exceeds the limit")

    stack: list[tuple[str, tuple[str, ...]]] = [(source_agent_id, ())]
    while stack:
        node, path = stack.pop()
        if node in path:
            _raise("CONNECTOR_AGENT_CYCLE", "agent connector graph contains a cycle")
        if len(path) >= MAX_AGENT_GRAPH_DEPTH:
            _raise("CONNECTOR_AGENT_DEPTH_EXCEEDED", "agent connector graph exceeds maximum depth")
        next_path = (*path, node)
        stack.extend((target, next_path) for target in graph.get(node, ()))


def validate_secret_ref(provider: str, secret_ref: str) -> str:
    parsed = urlparse(secret_ref.strip())
    schemes = {
        "vault": "vault",
        "kms": "kms",
        "secret-manager": "secret",
    }
    if parsed.scheme != schemes[provider] or not parsed.netloc or not parsed.path.strip("/"):
        _raise("CONNECTOR_CREDENTIAL_REF_INVALID", "credential must be an external secret-manager reference")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        _raise("CONNECTOR_CREDENTIAL_REF_INVALID", "credential reference is not canonical")
    return secret_ref.strip()


def credential_fingerprint(secret_ref: str) -> str:
    return hashlib.sha256(secret_ref.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "ConnectorValidationError", "NormalizedConnectorConfig", "assert_secret_free",
    "normalize_config", "normalize_remote_url", "require_agent_in_tenant",
    "validate_agent_graph", "validate_secret_ref", "credential_fingerprint",
    "INTERNAL_AGENT_OPERATIONS", "REGISTRY_OPERATIONS",
]
