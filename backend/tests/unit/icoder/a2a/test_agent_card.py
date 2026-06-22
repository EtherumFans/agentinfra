"""A2A AgentCard + substructure tests (SPEC §8)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.icoder.agent_runtime.a2a import (
    AgentCapabilities,
    AgentCard,
    AgentListResponse,
    AgentSkill,
    SecurityScheme,
    homepage_coding_review_card,
)


# ---------------------------------------------------------------------------
# AgentCapabilities
# ---------------------------------------------------------------------------


def test_capabilities_defaults():
    c = AgentCapabilities()
    assert c.streaming is False
    assert c.pushNotifications is False
    assert c.stateTransitionHistory is True
    assert c.extensions == []


def test_capabilities_allows_extension_dicts():
    c = AgentCapabilities(extensions=[{"uri": "x", "params": {}}])
    assert len(c.extensions) == 1


# ---------------------------------------------------------------------------
# AgentSkill
# ---------------------------------------------------------------------------


def test_skill_required_fields():
    s = AgentSkill(id="icd", name="ICD", description="...")
    assert s.id == "icd"
    assert s.examples == []


def test_skill_input_output_schema_via_alias():
    s = AgentSkill(
        id="x",
        name="X",
        description="d",
        inputSchema={"type": "object"},
        outputSchema={"$ref": "icoder/X/v1"},
    )
    assert s.input_schema == {"type": "object"}
    assert s.output_schema == {"$ref": "icoder/X/v1"}


def test_skill_input_output_schema_via_field_name():
    # populate_by_name=True allows both styles
    s = AgentSkill(
        id="x", name="X", description="d",
        input_schema={"type": "object"},
        output_schema={"$ref": "icoder/X/v1"},
    )
    assert s.input_schema == {"type": "object"}
    assert s.output_schema == {"$ref": "icoder/X/v1"}


def test_skill_serialize_uses_alias():
    s = AgentSkill(
        id="x", name="X", description="d",
        input_schema={"type": "object"},
        output_schema={"$ref": "icoder/X/v1"},
    )
    out = s.model_dump(by_alias=True)
    assert "inputSchema" in out
    assert "outputSchema" in out
    assert "input_schema" not in out


# ---------------------------------------------------------------------------
# SecurityScheme
# ---------------------------------------------------------------------------


def test_security_scheme_minimal():
    s = SecurityScheme(type="apiKey")
    assert s.type == "apiKey"
    assert s.description == ""


def test_security_scheme_with_description():
    s = SecurityScheme(type="oauth2", description="OAuth2 flow")
    assert s.description == "OAuth2 flow"


# ---------------------------------------------------------------------------
# AgentCard — required fields per SPEC §8.1
# ---------------------------------------------------------------------------


def _minimal_card(**overrides):
    base = {
        "name": "X",
        "description": "X agent",
        "url": "/api/icoder/agents/x/v1/message:send",
    }
    base.update(overrides)
    return AgentCard(**base)


def test_card_requires_name():
    with pytest.raises(ValidationError):
        AgentCard(description="x", url="/y")


def test_card_requires_description():
    with pytest.raises(ValidationError):
        AgentCard(name="x", url="/y")


def test_card_requires_url():
    with pytest.raises(ValidationError):
        AgentCard(name="x", description="y")


def test_card_defaults_version_and_provider():
    c = _minimal_card()
    assert c.version == "1.0.0"
    assert c.provider == "iCoDer"


def test_card_default_capabilities_state_history_true():
    c = _minimal_card()
    assert c.capabilities.stateTransitionHistory is True


def test_card_default_input_output_modes():
    c = _minimal_card()
    assert c.defaultInputModes == ["text"]
    assert c.defaultOutputModes == ["application/json"]


def test_card_default_security_schemes_empty():
    c = _minimal_card()
    assert c.securitySchemes == {}


def test_card_default_metadata_empty():
    c = _minimal_card()
    assert c.metadata == {}


def test_card_documentation_url_default_empty():
    c = _minimal_card()
    assert c.documentation_url == ""


def test_card_documentation_url_via_alias():
    c = _minimal_card(documentationUrl="/docs/x")
    assert c.documentation_url == "/docs/x"


# ---------------------------------------------------------------------------
# homepage_coding_review_card — Phase 1 fixture (SPEC §8.3)
# ---------------------------------------------------------------------------


def test_homepage_card_basics():
    c = homepage_coding_review_card()
    assert c.name == "Homepage Coding Review Agent"
    assert "首页" in c.description or "病案" in c.description
    assert "homepage-coding-review" in c.url
    assert c.version == "1.0.0"
    assert c.provider == "iCoDer"


def test_homepage_card_capabilities():
    c = homepage_coding_review_card()
    assert c.capabilities.streaming is False
    assert c.capabilities.pushNotifications is False
    assert c.capabilities.stateTransitionHistory is True


def test_homepage_card_skills():
    c = homepage_coding_review_card()
    ids = [s.id for s in c.skills]
    assert "icd_coding" in ids
    assert "drg_grouping" in ids


def test_homepage_card_skill_references_icoder_schema():
    c = homepage_coding_review_card()
    icd = next(s for s in c.skills if s.id == "icd_coding")
    assert "MedicalCodingOutputSchema" in icd.output_schema.get("$ref", "")


def test_homepage_card_security_schemes():
    c = homepage_coding_review_card()
    assert "bearer" in c.securitySchemes
    assert c.securitySchemes["bearer"].type == "apiKey"


def test_homepage_card_metadata_icoder_namespace():
    c = homepage_coding_review_card()
    assert "icoder" in c.metadata
    icoder = c.metadata["icoder"]
    assert icoder["production_writeback_blocked"] is True
    assert icoder["phi_redaction"] == "required"
    assert "medical_coding" in icoder["rule_sets"]
    assert "coding-expert" in icoder["experts"]


def test_homepage_card_base_url_prepends():
    c = homepage_coding_review_card(base_url="https://api.icoder.cn")
    assert c.url.startswith("https://api.icoder.cn")
    assert "homepage-coding-review" in c.url


def test_homepage_card_no_base_url_relative():
    c = homepage_coding_review_card()
    assert c.url.startswith("/api/icoder/agents/")


def test_homepage_card_default_input_output_modes():
    c = homepage_coding_review_card()
    assert c.defaultInputModes == ["text"]
    assert c.defaultOutputModes == ["application/json"]


# ---------------------------------------------------------------------------
# AgentListResponse
# ---------------------------------------------------------------------------


def test_agent_list_response_minimal():
    r = AgentListResponse(agents=[homepage_coding_review_card()])
    assert len(r.agents) == 1
    assert r.agents[0].name == "Homepage Coding Review Agent"


def test_agent_list_response_empty():
    r = AgentListResponse(agents=[])
    assert r.agents == []


# ---------------------------------------------------------------------------
# Card serialization
# ---------------------------------------------------------------------------


def test_card_roundtrip_via_dict():
    c = homepage_coding_review_card()
    d = c.model_dump(by_alias=True, exclude_none=False)
    c2 = AgentCard.model_validate(d)
    assert c2.name == c.name
    assert c2.url == c.url
    assert len(c2.skills) == len(c.skills)


def test_card_extra_fields_allowed():
    c = AgentCard(
        name="X", description="d", url="/y",
        some_extension={"foo": "bar"},
    )
    d = c.model_dump()
    assert d["some_extension"] == {"foo": "bar"}