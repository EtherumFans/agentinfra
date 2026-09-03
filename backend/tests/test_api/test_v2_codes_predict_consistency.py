"""Cycle 18 回环一致性测试 — Corti §13.6 ``codes_predict`` (POST /tools/coding/).

The test:

  1. Loads the **real Corti OpenAPI spec** captured at
     ``docs/corti-reverse-engineered/codes-predict-codes.md`` (fetched
     2026-07-01 from
     ``https://docs.corti.ai/api-reference/codes/predict-codes.md``).
  2. Extracts the embedded ``openapi: 3.0.0`` YAML block and parses it.
  3. Drives the iCoDer ``POST /api/v2/tools/coding/`` endpoint.
  4. Asserts key invariants Corti also enforces:
     - Response 200 with the spec-shaped ``{codes, candidates, usageInfo}``
       envelope (all 3 fields **required**).
     - All 5 response-shape fields per code are present
       (``system / code / display / evidences / alternatives``).
     - All 4 evidence fields per item are present
       (``contextIndex / text / start / end``).
     - All 15 ``CommonCodingSystemEnum`` values are accepted (no Chinese-only
       restriction like the Phase 1.1 /coding/icoder/ sub-path).
     - Char-span evidence round-trips against the input context block.
     - ``usageInfo.creditsConsumed`` is a non-negative number.
     - Path-echo: response ``codes[0].system`` == request ``system[0]``.

Phase 1.1 endpoint (Chinese-only MedCodER 5-stage pipeline) was relocated to
``/api/v2/tools/coding/icoder/`` so the canonical Corti path
``/api/v2/tools/coding/`` is reserved for the §13.6 spec predictor.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

# Required env for the dev escape hatch.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle18")


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
SPEC_PATH = REPO_ROOT / "docs" / "corti-reverse-engineered" / "codes-predict-codes.md"


# ─── Spec loader (no walker — flat envelope) ─────────────────────────


def _extract_openapi_yaml() -> dict[str, Any]:
    """Extract and parse the ``openapi: 3.0.0`` YAML block from the markdown."""
    text = SPEC_PATH.read_text(encoding="utf-8")
    blocks = re.findall(r"````yaml[^\n]*\n(.*?)````", text, flags=re.DOTALL)
    for blk in blocks:
        try:
            parsed = yaml.safe_load(blk)
        except yaml.YAMLError:
            continue
        if isinstance(parsed, dict) and parsed.get("openapi"):
            return parsed
    raise AssertionError(f"No openapi 3.0+ YAML block found in {SPEC_PATH}")


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def codes_predict_spec() -> dict[str, Any]:
    return _extract_openapi_yaml()


@pytest.fixture
def icoder_client(monkeypatch):
    from app.main import app
    from app.api import v2_tools_coding as api_mod
    from fastapi.testclient import TestClient

    # Keep this contract test hermetic. The endpoint's credential gate must
    # remain fail-closed in real deployments, while the provider itself is
    # replaced below and must never consume a developer-machine/real key.
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle18")

    async def fake_real_provider(body):
        source_index, source_text = next(
            (index, item.text)
            for index, item in enumerate(body.context)
            if item.type == "text" and item.text and item.text.strip()
        )
        include = list(body.filter.include) if body.filter else []
        prefix = include[0] if include else "TST"
        primary_code = f"{prefix}.9"
        candidate_code = f"{prefix}.8"
        evidence = {
            "contextIndex": source_index,
            "text": source_text,
            "start": 0,
            "end": len(source_text),
        }
        system = body.system[0]
        return {
            "content": json.dumps({
                "codes": [{
                    "system": system,
                    "code": primary_code,
                    "display": "Test provider primary",
                    "evidences": [evidence],
                    "alternatives": [],
                }],
                "candidates": [{
                    "system": system,
                    "code": candidate_code,
                    "display": "Test provider candidate",
                    "evidences": [evidence],
                    "alternatives": [],
                }],
            }),
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "provider": "test-real-provider",
        }

    monkeypatch.setattr(api_mod, "_invoke_general_coding_model", fake_real_provider)
    return TestClient(app)


# ─── Spec-derived constants (enforce against the real spec) ──────────


CORTI_15_SYSTEMS: list[str] = [
    "icd10cm-inpatient", "icd10cm-outpatient", "icd10pcs", "cpt",
    "icd10int-inpatient", "icd10int-outpatient",
    "icd10uk-inpatient", "icd10uk-outpatient",
    "cim10fr-inpatient", "cim10fr-outpatient",
    "icd10gm-inpatient", "icd10gm-outpatient",
    "opcs4", "ops", "ccam",
]


# ─── Tests ───────────────────────────────────────────────────────────


def test_codes_predict_spec_is_real_and_cached(codes_predict_spec):
    """Sanity: the OpenAPI we use as ground truth is the real Corti one."""
    assert codes_predict_spec["openapi"].startswith("3.")
    assert codes_predict_spec["info"]["title"] == "Corti API"
    op = codes_predict_spec["paths"]["/tools/coding/"]["post"]
    assert "Codes" in op["tags"]
    assert op["operationId"] == "codes_predict"
    # Spec lists 400/403/500/502/504; iCoDer adds 503 hospital-pilot gate.
    for code in ("200", "400", "500", "502", "504"):
        assert code in op["responses"], f"missing response {code} in spec"
    # 200 schema is $ref to CodesGeneralResponse.
    assert "CodesGeneralResponse" in str(op["responses"]["200"])


def test_codes_predict_15_systems_enum_complete(codes_predict_spec):
    """Spec invariant: ``CommonCodingSystemEnum`` lists exactly 15 values."""
    enum_schema = codes_predict_spec["components"]["schemas"]["CommonCodingSystemEnum"]
    enum_values = enum_schema.get("enum", [])
    assert len(enum_values) == 15, f"expected 15 system values, got {len(enum_values)}"
    for sys_name in CORTI_15_SYSTEMS:
        assert sys_name in enum_values, f"missing system {sys_name} in spec enum"


def test_codes_predict_minimal_request(icoder_client):
    """回环: minimal request (1 system + 1 text context) → 200 with
    full ``{codes, candidates, usageInfo}`` envelope."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Short arm splint applied in ED."}],
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    # Spec requires codes, candidates, usageInfo all present.
    for key in ("codes", "candidates", "usageInfo"):
        assert key in j, f"missing required key {key} in response"
    assert isinstance(j["codes"], list)
    assert isinstance(j["candidates"], list)
    assert isinstance(j["usageInfo"], dict)


def test_codes_predict_path_echo_system(icoder_client):
    """Path-echo contract: response ``codes[0].system`` == request ``system[0]``."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Patient presents with abdominal pain."}],
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["codes"][0]["system"] == "icd10cm-outpatient"


def test_codes_predict_evidence_span_roundtrip(icoder_client):
    """Char offsets must satisfy ``context[contextIndex].text[start:end] == text``.

    Without this guarantee the char-span claim is meaningless.
    """
    sentence = "Patient presents with abdominal pain"
    full = f"History: {sentence}, denies nausea."

    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": full}],
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    code = j["codes"][0]
    # The stub emits evidence on every code (deterministic char-span).
    assert len(code["evidences"]) >= 1
    ev = code["evidences"][0]
    # The evidence text must be a substring of the input context (char-span invariant).
    assert ev["text"] in full
    assert full[ev["start"]:ev["end"]] == ev["text"]
    assert ev["contextIndex"] == 0  # only one context block


def test_codes_predict_all_5_response_fields_per_code(icoder_client):
    """All 5 ``CodesGeneralReadResponse`` fields present per code:
    ``system / code / display / evidences / alternatives``."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Acute appendicitis."}],
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    for entry in j["codes"] + j["candidates"]:
        for key in ("system", "code", "display", "evidences", "alternatives"):
            assert key in entry, f"missing {key} in code/candidate entry"


def test_codes_predict_all_4_evidence_fields(icoder_client):
    """All 4 evidence fields per item: ``contextIndex / text / start / end``."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Diabetes mellitus type 2."}],
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["codes"]) >= 1
    assert len(j["codes"][0]["evidences"]) >= 1
    ev = j["codes"][0]["evidences"][0]
    for key in ("contextIndex", "text", "start", "end"):
        assert key in ev, f"missing {key} in evidence"
    # Char-span invariant for every evidence entry across codes+candidates.
    for entry in j["codes"] + j["candidates"]:
        for e in entry["evidences"]:
            assert isinstance(e["contextIndex"], int)
            assert isinstance(e["text"], str)
            assert isinstance(e["start"], int) and e["start"] >= 0
            assert isinstance(e["end"], int) and e["end"] > e["start"]


def test_codes_predict_usage_info_credits_consumed(icoder_client):
    """``usageInfo.creditsConsumed`` is a non-negative number (per spec)."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Sample text."}],
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert "creditsConsumed" in j["usageInfo"]
    assert isinstance(j["usageInfo"]["creditsConsumed"], (int, float))
    assert j["usageInfo"]["creditsConsumed"] >= 0


def test_codes_predict_filter_include(icoder_client):
    """``filter.include`` restricts every promoted code to that category."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Patient with E11.9 (Type 2 diabetes)."}],
            "filter": {
                "include": ["E11"],
                "exclude": [],
                "expand": True,
            },
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    returned_codes = {c["code"] for c in j["codes"] + j["candidates"]}
    assert returned_codes
    assert all(code.startswith("E11") for code in returned_codes)


def test_codes_predict_filter_expand_false_requires_exact_code(icoder_client):
    """``expand=false`` must not treat a category as a prefix."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Patient with E11.9."}],
            "filter": {
                "include": ["E11"],
                "exclude": [],
                "expand": False,
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["codes"] == []
    assert r.json()["candidates"] == []


def test_codes_predict_filter_exclude(icoder_client):
    """``filter.exclude`` is accepted (the stub does not silently drop codes,
    but the field round-trips through the request without 400)."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Patient with E11.9."}],
            "filter": {
                "include": ["E11"],
                "exclude": ["E11.0"],
            },
        },
    )
    assert r.status_code == 200, r.text


def test_codes_predict_all_15_systems_accepted(icoder_client):
    """All 15 ``CommonCodingSystemEnum`` values are accepted (no allow-list
    rejection like the Phase 1.1 Chinese-only policy)."""
    for sys_name in CORTI_15_SYSTEMS:
        r = icoder_client.post(
            "/api/v2/tools/coding/",
            json={
                "system": [sys_name],
                "context": [{"type": "text", "text": f"Sample text for {sys_name}."}],
            },
        )
        assert r.status_code == 200, f"{sys_name}: expected 200, got {r.status_code} - {r.text}"
        j = r.json()
        # The system echoes on the response (per spec: codes[].system echoes
        # request's system[0]).
        assert j["codes"][0]["system"] == sys_name, (
            f"system[{sys_name}] not echoed on the wire"
        )


def test_codes_predict_multi_system_in_one_request(icoder_client):
    """Caller can request multiple systems in one request; the response
    echoes the first system on ``codes[0].system`` (per spec's
    ``system: array<CommonCodingSystemEnum>`` with minItems=1, maxItems=15)."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient", "cpt"],
            "context": [{"type": "text", "text": "ED visit, splint applied."}],
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    # The stub projects to a single primary system (the first in the list)
    # per Corti spec semantics.
    assert j["codes"][0]["system"] == "icd10cm-outpatient"


def test_codes_predict_multi_context_contextindex(icoder_client):
    """Multi-context blocks: ``evidences[].contextIndex`` follows input order."""
    block0 = "First block: chest pain for 3 days."
    block1 = "Second block: history of hypertension for 5 years."

    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [
                {"type": "text", "text": block0},
                {"type": "text", "text": block1},
            ],
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    # The stub uses the first non-empty text context block as evidence.
    # The contextIndex must point to a valid index in the request context[].
    for entry in j["codes"] + j["candidates"]:
        for ev in entry["evidences"]:
            assert ev["contextIndex"] in (0, 1), f"unexpected contextIndex {ev['contextIndex']}"


def test_codes_predict_empty_context_rejected(icoder_client):
    """``context: []`` → 400 ``empty_context`` (spec invariant)."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [],
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"].get("error") == "empty_context"


def test_codes_predict_empty_system_rejected(icoder_client):
    """``system: []`` → 400 ``empty_system``."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": [],
            "context": [{"type": "text", "text": "Sample."}],
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"].get("error") == "empty_system"


def test_codes_predict_unknown_system_rejected(icoder_client):
    """Unknown system name → 400 ``unsupported_system`` (spec invariant)."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["bogus-system-name"],
            "context": [{"type": "text", "text": "Sample."}],
        },
    )
    assert r.status_code == 400, r.text
    detail = r.json().get("detail", {})
    assert detail.get("error") == "unsupported_system"
    assert "bogus-system-name" in detail.get("received", [])


def test_codes_predict_resolves_saved_document_context(icoder_client):
    """A tenant-scoped saved Guided Document is accepted as coding input."""
    from app.database import AsyncSessionLocal
    from app.services.guided_document_repository import guided_document_repository

    source = "Acute appendicitis is documented in the discharge summary."

    async def _seed_document() -> str:
        async with AsyncSessionLocal() as db:
            row = await guided_document_repository.create(
                db,
                organization_id="org_default1",
                owner_id="u-test-bypass",
                interaction_id=None,
                name=f"Coding source {uuid.uuid4()}",
                template_id=str(uuid.uuid4()),
                template_version_id=str(uuid.uuid4()),
                language="en-US",
                string_document={"assessment": source},
                structured_document=None,
                labels=[],
                credits_consumed=0.0,
            )
            await db.commit()
            return row.document_id

    document_id = asyncio.run(_seed_document())
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "documentId", "documentId": document_id}],
        },
    )
    assert r.status_code == 200, r.text
    evidence = r.json()["codes"][0]["evidences"][0]
    assert evidence == {
        "contextIndex": 0,
        "text": source,
        "start": 0,
        "end": len(source),
    }


def test_codes_predict_unknown_document_is_404(icoder_client):
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "documentId", "documentId": str(uuid.uuid4())}],
        },
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"].get("error") == "document_not_found"


def test_codes_predict_rejects_mixed_document_and_text_context(icoder_client):
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [
                {"type": "documentId", "documentId": str(uuid.uuid4())},
                {"type": "text", "text": "Inline note."},
            ],
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"].get("error") == "mixed_context_not_supported"


@pytest.mark.parametrize(
    "context",
    [
        {"type": "documentId", "documentId": ""},
        {"type": "text", "text": ""},
        {"type": "documentId", "documentId": "doc", "text": "ambiguous"},
        {"type": "audio", "text": "unsupported"},
    ],
)
def test_codes_predict_rejects_invalid_context_variant(icoder_client, context):
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={"system": ["icd10cm-outpatient"], "context": [context]},
    )
    assert r.status_code == 422, r.text


def test_codes_predict_trailing_slash_optional(icoder_client):
    """Trailing slash is optional (FastAPI dual registration)."""
    body = {
        "system": ["icd10cm-outpatient"],
        "context": [{"type": "text", "text": "Sample."}],
    }
    r_slash = icoder_client.post("/api/v2/tools/coding/", json=body)
    r_noslash = icoder_client.post("/api/v2/tools/coding", json=body)
    assert r_slash.status_code == r_noslash.status_code == 200
    assert r_slash.json() == r_noslash.json()


def test_codes_predict_codes_candidates_split(icoder_client):
    """``codes[]`` and ``candidates[]`` are both populated and distinct.

    The stub emits 1 code + 1 candidate; they must not be the same entry
    (the spec defines them as separate sets: ``codes`` = predicted,
    ``candidates`` = lower-confidence considered-but-excluded)."""
    r = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Sample text."}],
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["codes"]) >= 1
    assert len(j["candidates"]) >= 1
    primary_code = j["codes"][0]["code"]
    candidate_codes = {c["code"] for c in j["candidates"]}
    assert primary_code not in candidate_codes, (
        "primary code must not appear in candidates (spec semantics)"
    )
    assert not primary_code.startswith("EXAMPLE-")


def test_codes_predict_invalid_model_evidence_fails_closed(icoder_client, monkeypatch):
    from app.api import v2_tools_coding as api_mod

    async def invalid_evidence_provider(body):
        return {
            "content": json.dumps({
                "codes": [{
                    "system": body.system[0],
                    "code": "R10.9",
                    "display": "Abdominal pain",
                    "evidences": [{
                        "contextIndex": 0,
                        "text": "invented text",
                        "start": 0,
                        "end": 13,
                    }],
                    "alternatives": [],
                }],
                "candidates": [],
            }),
            "usage": {},
        }

    monkeypatch.setattr(
        api_mod,
        "_invoke_general_coding_model",
        invalid_evidence_provider,
    )
    response = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Patient has abdominal pain."}],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "coding_provider_evidence_invalid"


def test_codes_predict_missing_credential_fails_before_model(
    icoder_client,
    monkeypatch,
):
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)

    response = icoder_client.post(
        "/api/v2/tools/coding/",
        json={
            "system": ["icd10cm-outpatient"],
            "context": [{"type": "text", "text": "Patient has abdominal pain."}],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "llm_credential_missing"


@pytest.mark.asyncio
async def test_codes_predict_rejects_degraded_gateway_result(monkeypatch):
    from app.main import app
    from app.api.v2_tools_coding import _invoke_general_coding_model
    from app.schemas.v2_tools_coding import CodesGeneralPredictRequest

    class DegradedGateway:
        async def generate(self, *args, **kwargs):
            return {
                "content": "{}",
                "provider": "mock",
                "is_mock": True,
                "degraded": True,
                "degraded_reason": "mock_provider",
            }

    monkeypatch.setattr(
        app.state,
        "platform_gateway",
        DegradedGateway(),
        raising=False,
    )
    body = CodesGeneralPredictRequest.model_validate({
        "system": ["icd10cm-outpatient"],
        "context": [{"type": "text", "text": "Patient has abdominal pain."}],
    })

    with pytest.raises(RuntimeError, match="coding_provider_degraded"):
        await _invoke_general_coding_model(body)
