"""Phase 1.1 (2026-06-30) — Corti §3.1 Medical Coding shape parity (iCoDer 5-stage).

Plan reference: ``docs/PHASE_1_1_MEDICAL_CODING_PATH_SCHEMA.md``

These tests assert the wire-shape contract of ``POST /api/v2/tools/coding/icoder``
(Phase 1.1 endpoint, relocated to sub-path in cycle 18 to free the canonical
Corti path ``/api/v2/tools/coding/`` for the §13.6 ``codes_predict`` endpoint).

Approach
--------
All adapter calls go through a stub ``HybridCodingAdapter`` whose
``infer_async`` returns a fixed ``MedicalCodingOutputSchema``. The stub is
injected via ``monkeypatch.setattr`` on the endpoint module so the test
fixtures never touch a real LLM, BGE-M3 model, or FAISS index.

The seven test slots are documented in the Phase 1.1 plan:

  1. ``test_v2_coding_shape_minimal`` — full Corti envelope reaches the wire.
  2. ``test_v2_coding_evidence_span_roundtrip`` — char offsets agree with the
     source text (no off-by-one drift).
  3. ``test_v2_coding_alternatives_contains_rerank`` — alternatives[] ≥ 1.
  4. ``test_v2_coding_icoder_system_accepted`` — iCoDer system name accepted.
  5. ``test_v2_coding_corti_us_system_rejected`` — Corti US system names 400.
  6. ``test_v2_coding_multi_context_contextindex`` — contextIndex follows
     input order; no cross-block leakage.
  7. ``test_v2_coding_empty_context_rejected`` — empty input 400.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Must run before importing the app / endpoint modules to:
#   1. Bypass session auth (the v2 endpoint uses Depends(get_current_user)).
#   2. Mark the deepseek credential as present so the 503 hospital gate is
#      skipped (the LLM call itself is replaced by an injected stub adapter).
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-p11")


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


# ─── Helper: build a stubbed MedicalCodingOutputSchema ──────────────


def _make_stub_result(
    diseases: list[dict[str, Any]],
) -> Any:
    """Construct a MedicalCodingOutputSchema-like object for the stub.

    Each ``diseases[i]`` is a dict with keys:
        ``disease_text``        — str
        ``supporting_evidence`` — list of dicts with char_start/char_end/text
        ``final_top_k``         — list of dicts with code/name/score
        ``final_confidence``    — float
    """
    from official_agents.medical_coding.schema import (
        CandidateCode,
        EvidenceSpan,
        ExtractedDiagnosis,
        MedicalCodingOutputSchema,
    )
    extracted: list[ExtractedDiagnosis] = []
    for d in diseases:
        evidences = [
            EvidenceSpan.from_dict(ev) if isinstance(ev, dict) else ev
            for ev in d.get("supporting_evidence", [])
        ]
        top_k = [
            CandidateCode.from_dict(c) if isinstance(c, dict) else c
            for c in d.get("final_top_k", [])
        ]
        extracted.append(
            ExtractedDiagnosis(
                disease_text=d.get("disease_text", ""),
                supporting_evidence=evidences,
                final_top_k=top_k,
                final_confidence=float(d.get("final_confidence", 0.0)),
            )
        )
    return MedicalCodingOutputSchema(
        # Don't populate primary_diagnosis: the stub only needs
        # ``extracted_diagnoses`` to be present so the v2 endpoint can
        # project to Corti shape. A real DiagnosisEntry would force us to
        # guess the schema here; the production endpoint never reads
        # primary_diagnosis for Corti-shape projection.
        extracted_diagnoses=extracted,
        mode="medcoder.full",
        provider="stub",
        model="medcoder/stub-p11",
    )


@pytest.fixture
def stub_adapter(monkeypatch):
    """Inject a stub HybridCodingAdapter whose ``infer_async`` returns a
    caller-supplied MedicalCodingOutputSchema. The stub also captures the
    ``mode`` it was called with so mode-mapping tests can verify it.
    """
    from app.api import v2_tools_coding as api_mod

    captured: dict[str, Any] = {}

    class StubAdapter:
        def __init__(self, mode: str = "medcoder.full", *args, **kwargs):
            self.mode = mode
            # Hold a reference to the test's "next-result" slot.
            self._next_result: Any = None

        async def infer_async(self, messages, *args, **kwargs):
            captured["mode"] = self.mode
            captured["messages"] = list(messages)
            if self._next_result is None:
                # Default: empty pipeline result → forces the "no
                # extracted_diagnoses" 502 path in tests that don't opt in.
                from official_agents.medical_coding.schema import (
                    MedicalCodingOutputSchema,
                )
                return MedicalCodingOutputSchema(
                    extracted_diagnoses=[],
                    provider="stub",
                    model="medcoder/stub-empty",
                )
            return self._next_result

    monkeypatch.setattr(api_mod, "HybridCodingAdapter", StubAdapter)
    monkeypatch.setattr(api_mod, "_DISPLAY_INDEX", {
        "I50.900": "心力衰竭,未特指 (chronic)",
        "I50.901": "充血性心力衰竭",
        "I50.907": "慢性心力衰竭,详细",
        "I10.x00": "原发性高血压",
        "E11.900": "2型糖尿病不伴有并发症",
        "I21.401": "急性非ST段抬高型心肌梗死",
        "I50.000": "充血性心力衰竭",
        "I50.100": "左心衰竭",
    })
    return captured


def _set_next(adapter_capture: dict[str, Any], diseases: list[dict[str, Any]]) -> None:
    """Stage a custom next-result on the *next* StubAdapter instance.

    The fixture wires a class-level slot. We use ``__init__``-time storage
    by attaching it to the captured dictionary's ``pending`` field.
    """
    adapter_capture["pending"] = _make_stub_result(diseases)


def _patch_next_on_first_call(adapter_capture: dict[str, Any]) -> None:
    """Attach ``pending`` to the StubAdapter class so the next instance
    uses it.
    """
    adapter_capture.setdefault("_ready", True)
    original_infer = adapter_capture.get("_infer_async")
    pending = adapter_capture.get("pending")

    class PatchedStub:
        def __init__(self, mode: str = "medcoder.full", *a, **kw):
            self.mode = mode
            self._result = pending

        async def infer_async(self, messages, *a, **kw):
            adapter_capture["mode"] = self.mode
            adapter_capture["messages"] = list(messages)
            return self._result

    from app.api import v2_tools_coding as api_mod
    # Replace the stub class with the patched one for this test.
    api_mod.HybridCodingAdapter = PatchedStub  # type: ignore[assignment]


# ─── Tests ───────────────────────────────────────────────────────────


def test_v2_coding_shape_minimal(client, stub_adapter):
    """#1: standard Corti-shape request → 200 with ``codes[]`` envelope.

    The response codes[0] must carry ``system / code / display / evidences /
    alternatives``.
    """
    _patch_next_on_first_call({
        "pending": _make_stub_result([{
            "disease_text": "心力衰竭",
            "final_top_k": [
                {"code": "I50.901", "name": "充血性心力衰竭", "score": 0.92, "source": "rerank"},
                {"code": "I50.900", "name": "心力衰竭,未特指", "score": 0.71, "source": "rerank"},
            ],
            "final_confidence": 0.92,
            "supporting_evidence": [
                {"text": "LVEF 38%", "char_start": 110, "char_end": 118, "doc_id": "0"},
            ],
        }]),
    })

    body = {
        "context": [
            {"text": "患者男性,67 岁,因「反复胸闷...LVEF 38%。诊断:1. 慢性心力衰竭", "type": "text"}
        ],
        "system": ["icd10cn-outpatient"],
    }
    r = client.post("/api/v2/tools/coding/icoder", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "codes" in j and isinstance(j["codes"], list) and len(j["codes"]) >= 1
    first = j["codes"][0]
    for key in ("system", "code", "display", "evidences", "alternatives"):
        assert key in first, f"missing field {key} in codes[0]"
    assert first["system"] == "icd10cn-outpatient"
    assert first["code"] == "I50.901"
    assert isinstance(first["evidences"], list)
    assert isinstance(first["alternatives"], list)


def test_v2_coding_evidence_span_roundtrip(client, stub_adapter):
    """#2: char offsets must satisfy ``source_text[start:end] == text``.

    Without this guarantee the char-span claim is meaningless.
    """
    sentence = "心脏超声示左心扩大,LVEF 38%"
    full = f"诊断:1. 慢性心力衰竭 心功能 III 级(NYHA)。{sentence}。"
    # locate the sentence inside the full text (search anchor)
    idx = full.find(sentence)
    start = idx
    end = idx + len(sentence)

    _patch_next_on_first_call({
        "pending": _make_stub_result([{
            "disease_text": "心力衰竭",
            "final_top_k": [{"code": "I50.901", "name": "充血性心力衰竭", "score": 0.9, "source": "rerank"}],
            "final_confidence": 0.9,
            "supporting_evidence": [
                {"text": sentence, "char_start": start, "char_end": end, "doc_id": "0"},
            ],
        }]),
    })

    r = client.post("/api/v2/tools/coding/icoder", json={
        "context": [{"text": full, "type": "text"}],
        "system": ["icd10cn-outpatient"],
    })
    assert r.status_code == 200, r.text
    j = r.json()
    evidence = j["codes"][0]["evidences"][0]
    # The client does NOT see the upstream text; but the offset pair must
    # be internally consistent (start < end, length matches text length)
    # and the extracted slice from the *server-side* context must match.
    assert evidence["start"] == start
    assert evidence["end"] == end
    assert evidence["text"] == sentence
    # Independently verify the roundtrip against the input context.
    assert full[evidence["start"]:evidence["end"]] == evidence["text"]


def test_v2_coding_alternatives_contains_rerank(client, stub_adapter):
    """#3: rerank with ≥3 candidates → at least 2 alternatives on the wire.

    The primary candidate is the ``code`` field; only the rest of final_top_k
    become alternatives.
    """
    _patch_next_on_first_call({
        "pending": _make_stub_result([{
            "disease_text": "高血压",
            "final_top_k": [
                {"code": "I10.x00", "name": "原发性高血压", "score": 0.96, "source": "rerank"},
                {"code": "I50.901", "name": "充血性心力衰竭", "score": 0.84, "source": "rerank"},
                {"code": "E11.900", "name": "2型糖尿病不伴有并发症", "score": 0.78, "source": "rerank"},
            ],
            "final_confidence": 0.96,
            "supporting_evidence": [{"text": "血压 180/110 mmHg", "char_start": 0, "char_end": 17, "doc_id": "0"}],
        }]),
    })

    r = client.post("/api/v2/tools/coding/icoder", json={
        "context": [{"text": "血压 180/110 mmHg, 既往高血压病史 5 年", "type": "text"}],
        "system": ["icd10cn-outpatient"],
    })
    assert r.status_code == 200, r.text
    j = r.json()
    code = j["codes"][0]
    assert code["code"] == "I10.x00", "primary must be final_top_k[0]"
    assert len(code["alternatives"]) >= 2, f"expected ≥2 alternatives, got {len(code['alternatives'])}"
    alt_codes = {a["code"] for a in code["alternatives"]}
    assert {"I50.901", "E11.900"}.issubset(alt_codes)


def test_v2_coding_icoder_system_accepted(client, stub_adapter):
    """#4: ``icd10cn-outpatient`` is accepted; ``system`` echoes on the wire.

    Also checks ``icd10cn-inpatient`` and ``icd9cm3-procedure`` work.
    """
    for sys_name in ["icd10cn-outpatient", "icd10cn-inpatient", "icd9cm3-procedure", "icd9cm3-diagnostic"]:
        _patch_next_on_first_call({
            "pending": _make_stub_result([{
                "disease_text": "示例疾病",
                "final_top_k": [{"code": "I50.901", "name": "充血性心力衰竭", "score": 0.5, "source": "rerank"}],
                "final_confidence": 0.5,
                "supporting_evidence": [],
            }]),
        })
        r = client.post("/api/v2/tools/coding/icoder", json={
            "context": [{"text": "示例,用于验证 iCoDer system 命名空间。", "type": "text"}],
            "system": [sys_name],
        })
        assert r.status_code == 200, f"{sys_name}: {r.text}"
        assert r.json()["codes"][0]["system"] == sys_name, (
            f"system[{sys_name}] not echoed on the wire"
        )


def test_v2_coding_corti_us_system_rejected(client, stub_adapter):
    """#5: every Corti US system name → 400 ``unsupported_system``.

    iCoDer's Chinese system names are deliberately exclusive — the goal
    is to surface the standard difference, not to silently alias.
    """
    for corti_us_name in ["icd10cm-outpatient", "icd10cm-inpatient", "icd10pcs", "icd9cm", "cpt"]:
        r = client.post("/api/v2/tools/coding/icoder", json={
            "context": [{"text": "示例。", "type": "text"}],
            "system": [corti_us_name],
        })
        assert r.status_code == 400, f"{corti_us_name}: expected 400, got {r.status_code}"
        detail = r.json().get("detail", {})
        assert detail.get("error") == "unsupported_system", detail
        assert corti_us_name in detail.get("received", []), detail


def test_v2_coding_multi_context_contextindex(client, stub_adapter):
    """#6: multi-context blocks → ``contextIndex`` follows input order.

    The same evidence should not shift which block it points to; we feed
    each context block its own unique sentence and check the cited
    ``contextIndex`` matches the block it came from.
    """
    block0 = "第一段,患者主诉胸痛 3 天。"
    block1 = "第二段,既往高血压病史 5 年。"

    _patch_next_on_first_call({
        "pending": _make_stub_result([
            {
                "disease_text": "心力衰竭",
                "final_top_k": [
                    {"code": "I50.901", "name": "充血性心力衰竭", "score": 0.9, "source": "rerank"},
                ],
                "final_confidence": 0.9,
                "supporting_evidence": [
                    # Mimic doc_id="0" → first block
                    {"text": "主诉胸痛 3 天", "char_start": block0.find("主诉胸痛 3 天"),
                     "char_end": block0.find("主诉胸痛 3 天") + len("主诉胸痛 3 天"),
                     "doc_id": "0"},
                ],
            },
            {
                "disease_text": "原发性高血压",
                "final_top_k": [
                    {"code": "I10.x00", "name": "原发性高血压", "score": 0.93, "source": "rerank"},
                ],
                "final_confidence": 0.93,
                "supporting_evidence": [
                    # Mimic doc_id="1" → second block
                    {"text": "高血压病史 5 年", "char_start": block1.find("高血压病史 5 年"),
                     "char_end": block1.find("高血压病史 5 年") + len("高血压病史 5 年"),
                     "doc_id": "1"},
                ],
            },
        ]),
    })

    r = client.post("/api/v2/tools/coding/icoder", json={
        "context": [
            {"text": block0, "type": "text"},
            {"text": block1, "type": "text"},
        ],
        "system": ["icd10cn-outpatient"],
    })
    assert r.status_code == 200, r.text
    j = r.json()
    codes = j["codes"]
    assert len(codes) == 2
    # Two codes sorted by confidence desc — second (高血压, conf=0.93) is
    # first; first (心衰, conf=0.90) is second.
    ctx_index_to_code = {c["evidences"][0]["contextIndex"]: c["code"] for c in codes}
    assert set(ctx_index_to_code.keys()) <= {0, 1}
    assert ctx_index_to_code.get(0) == "I50.901", f"first-block evidence should cite I50.901, got {ctx_index_to_code}"
    assert ctx_index_to_code.get(1) == "I10.x00", f"second-block evidence should cite I10.x00, got {ctx_index_to_code}"


def test_v2_coding_empty_context_rejected(client, stub_adapter):
    """#7: empty input → 400 ``empty_context``.

    Two flavours of empty: explicit `[]` and array of empty-text blocks.
    """
    # Variant A: explicit empty list
    r = client.post("/api/v2/tools/coding/icoder", json={
        "context": [],
        "system": ["icd10cn-outpatient"],
    })
    assert r.status_code == 400
    assert r.json()["detail"].get("error") == "empty_context"

    # Variant B: list of items with whitespace-only text
    r = client.post("/api/v2/tools/coding/icoder", json={
        "context": [{"text": "   ", "type": "text"}, {"text": "", "type": "text"}],
        "system": ["icd10cn-outpatient"],
    })
    assert r.status_code == 400
    assert r.json()["detail"].get("error") == "empty_context"


def test_v2_coding_no_llm_credential_returns_503(client, monkeypatch):
    """No ``ICODER_CREDENTIAL_LLM`` and no dev opt-in → 503 hard-fail.

    Mirrors the M3-0 hospital-pilot gate in ``/api/icoder/coding-review/run``.
    The caller must not silently receive a fabricated codes[] array.
    """
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    monkeypatch.delenv("ICODER_ALLOW_DEGRADED_NO_KEY", raising=False)
    monkeypatch.delenv("ICODER_ALLOW_DEGRADED_NO_KEY", raising=False)

    r = client.post("/api/v2/tools/coding/icoder", json={
        "context": [{"text": "示例", "type": "text"}],
        "system": ["icd10cn-outpatient"],
    })
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail.get("reason") == "llm_credential_missing"
