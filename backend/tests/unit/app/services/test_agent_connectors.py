import pytest

from app.services.agent_connectors import (
    ConnectorValidationError,
    normalize_config,
    normalize_remote_url,
    validate_secret_ref,
)


@pytest.mark.parametrize(
    ("connector_type", "config"),
    [
        ("registry", {"registry_key": "pubmed", "capabilities": ["search"]}),
        (
            "mcp",
            {
                "url": "https://8.8.8.8/mcp/",
                "transport": "streamable-http",
                "auth_policy": "none",
                "tool_allowlist": ["search"],
            },
        ),
        (
            "agent",
            {"target_agent_id": "agt-dst-001", "capabilities": ["delegate"]},
        ),
        (
            "a2a",
            {
                "endpoint": "https://8.8.8.8/a2a/",
                "agent_card_digest": "a" * 64,
                "bindings": ["JSONRPC", "HTTP+JSON"],
            },
        ),
        (
            "schema",
            {
                "input_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                }
            },
        ),
    ],
)
def test_all_five_connector_configs_are_canonical(connector_type, config):
    result = normalize_config(connector_type, config, enabled=False)
    assert result.config
    if connector_type in {"mcp", "a2a"}:
        assert result.normalized_url == "https://8.8.8.8/" + connector_type
    if connector_type == "schema":
        assert len(result.schema_digest or "") == 64


@pytest.mark.parametrize(
    "url",
    [
        "http://8.8.8.8/mcp",
        "https://user:pass@8.8.8.8/mcp",
        "https://127.0.0.1/mcp",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/mcp",
        "https://[::]/mcp",
        "https://[ff02::1]/mcp",
        "https://203.0.113.10/mcp",
        "https://8.8.8.8:8443/mcp",
        "https://8.8.8.8/mcp?token=x",
        "https://例子.测试/mcp",
    ],
)
def test_remote_url_negative_security_matrix(url):
    with pytest.raises(ConnectorValidationError):
        normalize_remote_url(url)


@pytest.mark.parametrize(
    "config",
    [
        {"url": "https://8.8.8.8/mcp", "auth_token": "value"},
        {"url": "https://8.8.8.8/mcp", "headers": {"Authorization": "Bearer abcdefgh"}},
        {"url": "https://8.8.8.8/mcp", "note": "sk-abcdefgh123456"},
    ],
)
def test_connector_config_rejects_secret_shapes(config):
    with pytest.raises(ConnectorValidationError) as raised:
        normalize_config("mcp", config, enabled=False)
    assert raised.value.code == "CONNECTOR_SECRET_FORBIDDEN"


def test_schema_rejects_external_ref_and_regex_bomb():
    for schema in (
        {"$ref": "https://evil.invalid/schema.json"},
        {"type": "string", "pattern": "(a+)+"},
    ):
        with pytest.raises(ConnectorValidationError):
            normalize_config("schema", {"input_schema": schema}, enabled=False)


def test_cn_enabled_external_connector_fails_closed_without_allowlist(monkeypatch):
    monkeypatch.setenv("ICODER_ENVIRONMENT", "cn")
    monkeypatch.delenv("ICODER_CONNECTOR_EGRESS_ALLOWLIST", raising=False)
    with pytest.raises(ConnectorValidationError) as raised:
        normalize_config(
            "mcp",
            {
                "url": "https://8.8.8.8/mcp",
                "auth_policy": "none",
                "tool_allowlist": ["search"],
            },
            enabled=True,
        )
    assert raised.value.code == "CONNECTOR_EGRESS_NOT_APPROVED"


def test_credential_reference_accepts_reference_but_not_raw_secret():
    assert validate_secret_ref("vault", "vault://tenant/connector/key") == (
        "vault://tenant/connector/key"
    )
    with pytest.raises(ConnectorValidationError):
        validate_secret_ref("vault", "sk-raw-secret-value")


def test_remote_connector_redirect_contract_and_legacy_sse_fail_closed():
    with pytest.raises(ConnectorValidationError) as legacy_sse:
        normalize_config(
            "mcp",
            {"url": "https://8.8.8.8/mcp", "transport": "sse"},
            enabled=False,
        )
    assert legacy_sse.value.code == "CONNECTOR_CONFIG_INVALID"

    with pytest.raises(ConnectorValidationError) as contradictory:
        normalize_config(
            "a2a",
            {
                "endpoint": "https://8.8.8.8/a2a",
                "agent_card_digest": "a" * 64,
                "bindings": ["JSONRPC"],
                "redirect_policy": "deny",
                "max_redirects": 1,
            },
            enabled=False,
        )
    assert contradictory.value.code == "CONNECTOR_CONFIG_INVALID"

    configured = normalize_config(
        "mcp",
        {
            "url": "https://8.8.8.8/mcp",
            "redirect_policy": "same-origin",
            "max_redirects": 2,
        },
        enabled=False,
    )
    assert configured.config["redirect_policy"] == "same-origin"
    assert configured.config["max_redirects"] == 2


@pytest.mark.parametrize(
    ("connector_type", "config", "code"),
    [
        (
            "registry",
            {"registry_key": "memory"},
            "CONNECTOR_CAPABILITY_ALLOWLIST_REQUIRED",
        ),
        (
            "agent",
            {"target_agent_id": "agt-dst-001"},
            "CONNECTOR_CAPABILITY_ALLOWLIST_REQUIRED",
        ),
        (
            "mcp",
            {"url": "https://8.8.8.8/mcp"},
            "CONNECTOR_TOOL_ALLOWLIST_REQUIRED",
        ),
    ],
)
def test_enabled_callable_connectors_require_explicit_allowlists(
    connector_type, config, code,
):
    with pytest.raises(ConnectorValidationError) as raised:
        normalize_config(connector_type, config, enabled=True)
    assert raised.value.code == code
