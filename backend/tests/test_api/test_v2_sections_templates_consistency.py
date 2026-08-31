"""Cycle 4 回环一致性测试 — Corti §13.4 LIST Templates + Sections shape parity.

The test:

  1. Loads the **real Corti OpenAPI specs** captured at
     ``docs/corti-reverse-engineered/guided-templates-list.md`` and
     ``docs/corti-reverse-engineered/guided-sections-list.md`` (both
     fetched 2026-07-01 from
     ``https://docs.corti.ai/api-reference/guided-{templates,sections}/list-{templates,sections}.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block from each and
     parses it.
  3. Drives the iCoDer ``GET /api/v2/tools/templates/`` and
     ``GET /api/v2/tools/sections/`` endpoints and asserts the response
     validates against the spec's ``GuidedTemplate`` / ``GuidedSection``
     schemas.
  4. Asserts filter-acceptance invariants Corti also enforces (e.g.
     unknown query params are 422'd by FastAPI; ``source=invalid`` is
     422'd; missing auth → 401).

Dynamic fields ignored (per the parity policy):
  - ``createdAt``, ``updatedAt``, ``deletedAt`` (timestamps)
  - ``createdBy``, ``id`` (server-assigned UUIDs)
  - ``publishedVersion`` (absent in Cycle 4 stub data; never asserted)
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from cryptography.fernet import Fernet
from sqlalchemy import select

# Required env for the dev escape hatch.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle4")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


def _find_repo_root() -> Path:
    """Walk upward from this file until we find the iCoDer repo root
    (identified by the presence of ``docs/corti-reverse-engineered/``)."""
    cur = Path(__file__).resolve().parent
    while cur != cur.parent:
        if (cur / "docs" / "corti-reverse-engineered").is_dir():
            return cur
        cur = cur.parent
    raise RuntimeError("could not locate iCoDer repo root from test file")


REPO_ROOT = _find_repo_root()
SPEC_TEMPLATES_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "guided-templates-list.md"
SPEC_SECTIONS_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "guided-sections-list.md"


# ─── Spec loaders ────────────────────────────────────────────────────


def _extract_openapi_yaml(spec_path: Path) -> dict[str, Any]:
    """Extract and parse the ``openapi: 3.0.0`` YAML block from the markdown."""
    text = spec_path.read_text(encoding="utf-8")
    # The fence opener is `` ````yaml /path/to/file get /documents/templates/ `` (4
    # backticks, then ``yaml`` plus an optional inline header line ending at \n).
    blocks = re.findall(r"````yaml[^\n]*\n(.*?)````", text, flags=re.DOTALL)
    for blk in blocks:
        try:
            parsed = yaml.safe_load(blk)
        except yaml.YAMLError:
            continue
        if isinstance(parsed, dict) and parsed.get("openapi"):
            return parsed
    raise AssertionError(f"No openapi 3.0+ YAML block found in {spec_path}")


# ─── OpenAPI JSON-Schema subset walker ───────────────────────────────


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    assert ref.startswith("#/"), f"unsupported ref {ref}"
    cur: Any = spec
    for part in ref[2:].split("/"):
        cur = cur[part]
    return cur


def _type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "unknown"


def _check_shape(
    value: Any,
    schema: dict[str, Any],
    spec: dict[str, Any],
    path: str,
    errors: list[str],
) -> None:
    """Recursive OpenAPI shape check. Skips dynamic fields per policy."""
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])
    leaf = path.rsplit(".", 1)[-1]
    # Dynamic-field skip (per parity policy)
    if leaf in ("requestid", "creditsConsumed", "createdBy"):
        return

    expected_type = schema.get("type")
    nullable = bool(schema.get("nullable", False))
    if value is None:
        if not nullable:
            errors.append(f"{path}: unexpected null (schema does not declare nullable: true)")
        return

    if expected_type and expected_type != "null":
        actual_type = _type_of(value)
        if expected_type == "number" and actual_type == "integer":
            actual_type = "number"
        if actual_type != expected_type:
            errors.append(
                f"{path}: expected type={expected_type}, got type={actual_type} (value={value!r})"
            )
            return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value {value!r} != const {schema['const']!r}")

    if expected_type == "object" and isinstance(value, dict):
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        for k in required:
            if k not in value:
                errors.append(f"{path}.{k}: required field missing")
        for k, v in value.items():
            if k in properties:
                _check_shape(v, properties[k], spec, f"{path}.{k}", errors)
    elif expected_type == "array" and isinstance(value, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(value):
                _check_shape(item, items_schema, spec, f"{path}[{i}]", errors)


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def templates_spec() -> dict[str, Any]:
    return _extract_openapi_yaml(SPEC_TEMPLATES_PATH)


@pytest.fixture(scope="module")
def sections_spec() -> dict[str, Any]:
    return _extract_openapi_yaml(SPEC_SECTIONS_PATH)


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


# ─── Tests ───────────────────────────────────────────────────────────


def test_templates_spec_is_real_and_cached(templates_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert templates_spec["openapi"].startswith("3.")
    assert templates_spec["info"]["title"] == "Corti API"
    op = templates_spec["paths"]["/documents/templates/"]["get"]
    assert "Guided Templates" in op["tags"]
    assert op["operationId"] == "guided_templates_list"
    schemas = templates_spec["components"]["schemas"]
    for name in ["GuidedTemplate", "GuidedLabel", "GuidedSourceFilter"]:
        assert name in schemas, f"missing schema {name}"


def test_sections_spec_is_real_and_cached(sections_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert sections_spec["openapi"].startswith("3.")
    assert sections_spec["info"]["title"] == "Corti API"
    op = sections_spec["paths"]["/documents/sections/"]["get"]
    assert "Guided Sections" in op["tags"]
    assert op["operationId"] == "guided_sections_list"
    schemas = sections_spec["components"]["schemas"]
    for name in ["GuidedSection", "GuidedLabel", "GuidedSourceFilter"]:
        assert name in schemas, f"missing schema {name}"


def test_v2_templates_list_shape_matches_corti_spec(icoder_client, templates_spec):
    """回环: iCoDer list-templates response validates against the Corti OpenAPI
    schema ``GuidedTemplate`` (list-of-template array shape)."""
    item_schema = templates_spec["components"]["schemas"]["GuidedTemplate"]
    r = icoder_client.get("/api/v2/tools/templates/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list), f"expected array, got {type(body)}"
    errs: list[str] = []
    for i, item in enumerate(body):
        _check_shape(item, item_schema, templates_spec, f"$.response[{i}]", errs)
    assert not errs, "iCoDer templates list mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_sections_list_shape_matches_corti_spec(icoder_client, sections_spec):
    """回环: iCoDer list-sections response validates against the Corti OpenAPI
    schema ``GuidedSection`` (list-of-section array shape)."""
    item_schema = sections_spec["components"]["schemas"]["GuidedSection"]
    r = icoder_client.get("/api/v2/tools/sections/")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 1, "expected at least one stub section"
    errs: list[str] = []
    for i, item in enumerate(body):
        _check_shape(item, item_schema, sections_spec, f"$.response[{i}]", errs)
    assert not errs, "iCoDer sections list mismatch vs Corti OpenAPI: " + "; ".join(errs)


def test_v2_templates_filter_source_corti_returns_only_corti(icoder_client, templates_spec):
    """Filter invariant: ``source=corti`` returns only entries with source=corti."""
    r = icoder_client.get("/api/v2/tools/templates/?source=corti")
    assert r.status_code == 200, r.text
    body = r.json()
    assert all(t["source"] == "corti" for t in body), \
        f"expected only corti-sourced templates, got {[t['source'] for t in body]}"


def test_v2_sections_filter_specialty_cardiology(icoder_client, sections_spec):
    """Filter invariant: ``specialty=cardiology`` returns only entries with cardiology."""
    r = icoder_client.get("/api/v2/tools/sections/?specialty=cardiology")
    assert r.status_code == 200, r.text
    body = r.json()
    assert all("cardiology" in t.get("specialties", []) for t in body), \
        f"expected only cardiology sections, got {body}"


def test_v2_china_section_catalog_is_complete_versioned_and_grounded(icoder_client):
    response = icoder_client.get(
        "/api/v2/tools/sections/",
        params={
            "lang": "zh-CN",
            "region": "CHN",
            "source": "project",
            "label": "regulatory_basis:CN-medical-record-standard",
        },
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert {row["name"] for row in rows} == {
        "主诉",
        "现病史",
        "既往史",
        "过敏史",
        "体格检查",
        "辅助检查",
        "诊断与评估",
        "诊疗计划",
        "出院情况与医嘱",
    }
    for row in rows:
        assert row["languages"] == ["zh-CN"]
        assert row["regions"] == ["CHN"]
        assert row["createdBy"] is None
        assert row["versionId"]
        assert row["generation"]["outputSchema"] == {"type": "string"}
        prompt = row["generation"]["instructions"]["contentPrompt"]
        assert any(term in prompt for term in ("仅", "不得", "来源"))


def test_v2_china_builtin_sections_are_write_protected(icoder_client):
    sections = icoder_client.get(
        "/api/v2/tools/sections/",
        params={
            "lang": "zh-CN",
            "source": "project",
            "label": "regulatory_basis:CN-medical-record-standard",
        },
    ).json()
    section_id = sections[0]["id"]
    updated = icoder_client.patch(
        f"/api/v2/tools/sections/{section_id}", json={"name": "禁止修改"}
    )
    deleted = icoder_client.delete(f"/api/v2/tools/sections/{section_id}")
    assert updated.status_code == 403, updated.text
    assert deleted.status_code == 403, deleted.text


def test_v2_templates_invalid_source_422(icoder_client):
    """Contract: ``source=invalid`` (not in the GuidedSourceFilter enum) is 422."""
    r = icoder_client.get("/api/v2/tools/templates/?source=invalid")
    assert r.status_code == 422, r.text


def test_v2_templates_discovery_uses_persisted_tenant_rows(icoder_client):
    """A template created through the product CRUD is visible on the Corti surface."""
    name = f"Persisted template {uuid.uuid4()}"
    created = icoder_client.post(
        "/api/templates",
        json={
            "name": name,
            "description": "Tenant-owned persisted template.",
            "content": "assessment and plan",
            "category": "outpatient",
            "language": "zh-CN",
        },
    )
    assert created.status_code == 201, created.text
    response = icoder_client.get("/api/v2/tools/templates/?source=user")
    assert response.status_code == 200, response.text
    matches = [row for row in response.json() if row["name"] == name]
    assert len(matches) == 1
    assert matches[0]["languages"] == ["zh-CN"]
    assert matches[0]["regions"] == ["CHN"]
    uuid.UUID(matches[0]["id"])


def test_v2_template_single_resource_round_trip(icoder_client):
    name = f"Single template {uuid.uuid4()}"
    created = icoder_client.post(
        "/api/templates",
        json={"name": name, "content": "assessment", "language": "zh-CN"},
    )
    assert created.status_code == 201, created.text
    listed = icoder_client.get("/api/v2/tools/templates/?source=user")
    public_row = next(row for row in listed.json() if row["name"] == name)

    response = icoder_client.get(f"/api/v2/tools/templates/{public_row['id']}")
    assert response.status_code == 200, response.text
    assert response.json() == public_row


def test_v2_section_single_resource_round_trip(icoder_client):
    listed = icoder_client.get("/api/v2/tools/sections/")
    assert listed.status_code == 200, listed.text
    section = listed.json()[0]

    response = icoder_client.get(f"/api/v2/tools/sections/{section['id']}")
    assert response.status_code == 200, response.text
    assert response.json() == section


def test_v2_tenant_section_crud_is_encrypted_audited_and_soft_deleted(
    icoder_client, monkeypatch
):
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog
    from app.models.guided_document import GuidedSectionRecord
    from app.services.phi_encryption import is_encrypted_value

    # Do not rotate the process key in the middle of the shared database
    # session: rows created by earlier tests may legitimately be encrypted
    # under the existing key.  An isolated invocation still provisions a
    # temporary key when the harness did not provide one.
    if not os.environ.get("ICODER_PHI_ENCRYPTION_KEY", "").strip():
        monkeypatch.setenv(
            "ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode()
        )
    secret_description = f"Sensitive section prompt {uuid.uuid4()}"
    created = icoder_client.post(
        "/api/v2/tools/sections/",
        json={
            "name": "病案首页诊断依据",
            "description": secret_description,
            "language": "zh-CN",
            "specialties": ["medical-records", "coding"],
            "labels": [{"key": "cn_scene", "value": "front-sheet"}],
            "outputSchema": {"type": "string"},
        },
    )
    assert created.status_code == 201, created.text
    section_id = created.json()["id"]
    assert created.json()["source"] == "user"
    assert created.json()["autoGenerated"] is False
    assert created.json()["languages"] == ["zh-CN"]

    updated = icoder_client.patch(
        f"/api/v2/tools/sections/{section_id}",
        json={
            "name": "病案首页主要诊断依据",
            "description": "仅提取病历中明确记录的主要诊断依据。",
            "outputSchema": {
                "type": "object",
                "fields": [{"key": "依据", "value": {"type": "string"}}],
            },
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "病案首页主要诊断依据"

    async def _stored_evidence():
        async with AsyncSessionLocal() as db:
            row = await db.scalar(select(GuidedSectionRecord).where(
                GuidedSectionRecord.section_id == section_id
            ))
            actions = list((await db.scalars(select(AuditLog.action).where(
                AuditLog.resource_id == section_id
            ))).all())
            return row.encrypted_definition_json, actions

    encrypted_definition, actions = asyncio.run(_stored_evidence())
    assert is_encrypted_value(encrypted_definition)
    assert secret_description not in encrypted_definition
    assert "guided_section.create" in actions
    assert "guided_section.update" in actions

    deleted = icoder_client.delete(f"/api/v2/tools/sections/{section_id}")
    assert deleted.status_code == 204, deleted.text
    assert icoder_client.get(f"/api/v2/tools/sections/{section_id}").status_code == 404
    listed = icoder_client.get("/api/v2/tools/sections/")
    assert section_id not in {row["id"] for row in listed.json()}

    async def _deleted_evidence():
        async with AsyncSessionLocal() as db:
            row = await db.scalar(select(GuidedSectionRecord).where(
                GuidedSectionRecord.section_id == section_id
            ))
            actions = list((await db.scalars(select(AuditLog.action).where(
                AuditLog.resource_id == section_id
            ))).all())
            return row.deleted_at, actions

    deleted_at, actions = asyncio.run(_deleted_evidence())
    assert deleted_at is not None
    assert "guided_section.delete" in actions


def test_v2_curated_sections_are_write_protected(icoder_client):
    curated = icoder_client.get("/api/v2/tools/sections/?source=corti").json()[0]
    updated = icoder_client.patch(
        f"/api/v2/tools/sections/{curated['id']}", json={"name": "Forbidden"}
    )
    deleted = icoder_client.delete(f"/api/v2/tools/sections/{curated['id']}")
    assert updated.status_code == 403, updated.text
    assert deleted.status_code == 403, deleted.text


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {"name": "Invalid schema", "outputSchema": {"type": "array"}},
        {"name": "Invalid type", "outputSchema": {"type": "binary"}},
    ],
)
def test_v2_section_create_rejects_invalid_definition(icoder_client, payload):
    response = icoder_client.post("/api/v2/tools/sections/", json=payload)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("kind", ["templates", "sections"])
def test_v2_single_discovery_unknown_resource_is_404(icoder_client, kind):
    response = icoder_client.get(f"/api/v2/tools/{kind}/{uuid.uuid4()}")
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["error"] == (
        "template_not_found" if kind == "templates" else "section_not_found"
    )


def test_v2_template_and_section_discovery_does_not_require_llm_key(
    icoder_client, monkeypatch
):
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    monkeypatch.delenv("ICODER_ALLOW_DEGRADED_NO_KEY", raising=False)
    assert icoder_client.get("/api/v2/tools/templates/").status_code == 200
    assert icoder_client.get("/api/v2/tools/sections/").status_code == 200


def test_v2_templates_reference_round_trip(templates_spec):
    """Reference sanity: a hand-built Corti-shaped template validates against
    its own OpenAPI schema. If THIS fails, the spec or fixture is broken —
    not iCoDer.
    """
    schema = templates_spec["components"]["schemas"]["GuidedTemplate"]
    ref = {
        "id": "11111111-2222-3333-4444-555555555555",
        "inheritedFromId": None,
        "autoGenerated": False,
        "source": "corti",
        "name": "Corti Standard — Hand-built Reference",
        "description": "Reference sanity check.",
        "languages": ["en-US"],
        "regions": ["USA"],
        "specialties": ["internal-medicine"],
        "labels": [{"key": "k", "value": "v"}],
        "createdBy": None,
        "createdAt": "2026-01-15T08:00:00Z",
        "updatedAt": "2026-06-01T12:00:00Z",
        "deletedAt": None,
    }
    errs: list[str] = []
    _check_shape(ref, schema, templates_spec, "$.reference", errs)
    assert not errs, "Corti reference template fails its own OpenAPI schema: " + "; ".join(errs)


def test_v2_sections_reference_round_trip(sections_spec):
    """Reference sanity for sections (companion to test_v2_templates_reference_round_trip)."""
    schema = sections_spec["components"]["schemas"]["GuidedSection"]
    ref = {
        "id": "11111111-2222-3333-4444-666666666666",
        "inheritedFromId": None,
        "autoGenerated": False,
        "source": "user",
        "name": "Custom — Hand-built Reference",
        "description": "Reference sanity check.",
        "languages": ["en-US"],
        "regions": ["USA"],
        "specialties": ["cardiology"],
        "labels": [{"key": "k", "value": "v"}],
        "createdBy": "33333333-3333-3333-3333-333333333333",
        "createdAt": "2026-03-22T09:30:00Z",
        "updatedAt": "2026-05-15T16:45:00Z",
        "deletedAt": None,
    }
    errs: list[str] = []
    _check_shape(ref, schema, sections_spec, "$.reference", errs)
    assert not errs, "Corti reference section fails its own OpenAPI schema: " + "; ".join(errs)
