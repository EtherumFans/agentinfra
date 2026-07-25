"""HIS/EMR simulator scenario generators.

Each scenario function yields dicts of the form:
    {
        "step": int,
        "action": "POST" | "GET" | "DELETE" | "WAIT",
        "path": str,           # URL path
        "headers": {...},      # additional headers
        "body": {...} | None,
        "expect_status": int,  # for assertion
        "expect_error_code": str | None,
        "note": str,           # human description
    }

Scenarios correspond to PDF A1C.3 §七's 16 enumerated cases.
"""
from datetime import datetime, timezone, timedelta
import uuid


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _trace_id():
    return f"00-{uuid.uuid4().hex}-{uuid.uuid4().hex[:16]}-01"


# ---------- scenario 1: smoke / normal case ----------

def scenario_01_smoke():
    """正常病例 — happy path."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/patient-context",
        "headers": {"Idempotency-Key": f"sim-01-{uuid.uuid4().hex[:8]}"},
        "body": {
            "tenant_id": "zju-fh-cn-hangzhou",
            "source_system": "HIS_SIMULATOR",
            "patient_id": "P-smoke-001",
            "visit_type": "inpatient",
            "department_id": "DEPT-CARDIO",
            "ward_id": "WARD-3A",
            "clinician_id": "DR-SMITH",
            "purpose_of_use": "treatment",
            "consent_legal_basis": "patient-consent",
        },
        "expect_status": 201,
        "expect_error_code": None,
        "note": "create patient context for inpatient cardio",
    }


# ---------- scenario 2: missing fields ----------

def scenario_02_missing_fields():
    """缺字段 — required field omitted."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/patient-context",
        "headers": {"Idempotency-Key": f"sim-02-{uuid.uuid4().hex[:8]}"},
        "body": {
            "tenant_id": "zju-fh-cn-hangzhou",
            "source_system": "HIS_SIMULATOR",
            # missing patient_id, visit_type, department_id, clinician_id, purpose_of_use, consent_legal_basis
            "clinician_id": "DR-X",
        },
        "expect_status": 400,
        "expect_error_code": "INVALID_REQUEST",
        "note": "missing required fields triggers Pydantic validation 400",
    }


# ---------- scenario 3: duplicate message (idempotency cache hit) ----------

def scenario_03_duplicate_message():
    """重复消息 — same Idempotency-Key returns cached response."""
    idem_key = f"sim-03-{uuid.uuid4().hex[:8]}"
    base_body = {
        "tenant_id": "zju-fh-cn-hangzhou",
        "source_system": "HIS_SIMULATOR",
        "patient_id": "P-dup-001",
        "visit_type": "outpatient",
        "department_id": "DEPT-GP",
        "clinician_id": "DR-1",
        "purpose_of_use": "treatment",
        "consent_legal_basis": "patient-consent",
    }
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/patient-context",
        "headers": {"Idempotency-Key": idem_key},
        "body": base_body,
        "expect_status": 201,
        "expect_error_code": None,
        "note": "first request with Idempotency-Key",
    }
    yield {
        "step": 2,
        "action": "POST",
        "path": "/api/v1/patient-context",
        "headers": {"Idempotency-Key": idem_key},
        "body": base_body,
        "expect_status": 200,  # cache hit returns 200 not 201
        "expect_error_code": None,
        "note": "second request with same Idempotency-Key should hit cache",
    }


# ---------- scenario 4: out-of-order message ----------

def scenario_04_out_of_order():
    """乱序消息 — document before context."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/patient-context/ctx-nonexistent/ documents".replace(" ", ""),
        "headers": {"Idempotency-Key": f"sim-04-{uuid.uuid4().hex[:8]}"},
        "body": {
            "documents": [
                {"doc_type": "discharge-summary", "content": "patient discharged..."}
            ]
        },
        "expect_status": 404,
        "expect_error_code": "NOT_FOUND",
        "note": "document ingestion requires an existing context — 404",
    }


# ---------- scenario 5: delayed message ----------

def scenario_05_delayed_message():
    """延迟消息 — client slow, server should still handle within timeout."""
    yield {
        "step": 1,
        "action": "WAIT",
        "path": "",
        "headers": {},
        "body": None,
        "expect_status": 0,
        "expect_error_code": None,
        "note": "simulate client delay of 90 seconds (AbortController limit on frontend)",
        "wait_seconds": 90,
    }
    yield {
        "step": 2,
        "action": "POST",
        "path": "/api/v1/patient-context",
        "headers": {"Idempotency-Key": f"sim-05-{uuid.uuid4().hex[:8]}"},
        "body": {
            "tenant_id": "zju-fh-cn-hangzhou",
            "source_system": "HIS_SIMULATOR",
            "patient_id": "P-delayed-001",
            "visit_type": "day-case",
            "department_id": "DEPT-DIALYSIS",
            "ward_id": "WARD-DC-1",
            "clinician_id": "DR-2",
            "purpose_of_use": "treatment",
            "consent_legal_basis": "treatment-necessity",
        },
        "expect_status": 201,
        "expect_error_code": None,
        "note": "delayed message still creates context (server has no rate degradation)",
    }


# ---------- scenario 6: withdraw document ----------

def scenario_06_withdraw_document():
    """撤回文书 — DELETE document (soft delete)."""
    # First create context + document
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/patient-context",
        "headers": {"Idempotency-Key": f"sim-06-{uuid.uuid4().hex[:8]}"},
        "body": {
            "tenant_id": "zju-fh-cn-hangzhou",
            "source_system": "HIS_SIMULATOR",
            "patient_id": "P-withdraw-001",
            "visit_type": "inpatient",
            "department_id": "DEPT-NEURO",
            "ward_id": "WARD-5",
            "clinician_id": "DR-3",
            "purpose_of_use": "treatment",
            "consent_legal_basis": "patient-consent",
        },
        "expect_status": 201,
        "expect_error_code": None,
        "note": "create context for document withdrawal test",
    }
    yield {
        "step": 2,
        "action": "DELETE",
        "path": "/api/v1/patient-context/{context_id}/documents/{doc_id}",
        "headers": {},
        "body": None,
        "expect_status": 204,
        "expect_error_code": None,
        "note": "soft-delete the document; subsequent GET returns 410 GONE",
    }


# ---------- scenario 7: document version update ----------

def scenario_07_document_version_update():
    """文书版本更新 — POST new version with source_doc_id + source_version."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/patient-context/{context_id}/documents",
        "headers": {"Idempotency-Key": f"sim-07-{uuid.uuid4().hex[:8]}"},
        "body": {
            "documents": [
                {"doc_type": "progress-note", "content": "v1 original", "source_doc_id": "DOC-X", "source_version": "v1"}
            ]
        },
        "expect_status": 201,
        "expect_error_code": None,
        "note": "first version of progress note",
    }
    yield {
        "step": 2,
        "action": "POST",
        "path": "/api/v1/patient-context/{context_id}/documents",
        "headers": {"Idempotency-Key": f"sim-07-{uuid.uuid4().hex[:8]}-v2"},
        "body": {
            "documents": [
                {"doc_type": "progress-note", "content": "v2 updated content", "source_doc_id": "DOC-X", "source_version": "v2"}
            ]
        },
        "expect_status": 201,
        "expect_error_code": None,
        "note": "second version of same source_doc_id; server keeps both with version label",
    }


# ---------- scenario 8: patient merge ----------

def scenario_08_patient_merge():
    """患者合并 — POST patient-merge event (new endpoint)."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/patient-merge",
        "headers": {"Idempotency-Key": f"sim-08-{uuid.uuid4().hex[:8]}"},
        "body": {
            "source_patient_id": "P-old-001",
            "target_patient_id": "P-new-001",
            "merge_reason": "duplicate_registration",
            "merged_at": _now_iso(),
        },
        "expect_status": 202,
        "expect_error_code": None,
        "note": "async patient merge event accepted; server rewrites patient_id in contexts/documents",
    }


# ---------- scenario 9: encounter ID change ----------

def scenario_09_encounter_id_change():
    """就诊号变更 — PUT encounter_id."""
    yield {
        "step": 1,
        "action": "PUT",
        "path": "/api/v1/patient-context/{context_id}/encounter-id",
        "headers": {"Idempotency-Key": f"sim-09-{uuid.uuid4().hex[:8]}"},
        "body": {
            "old_encounter_id": "ENC-OLD-001",
            "new_encounter_id": "ENC-NEW-001",
            "change_reason": "transfer_to_icu",
        },
        "expect_status": 200,
        "expect_error_code": None,
        "note": "encounter ID rewritten; audit log records the change",
    }


# ---------- scenario 10: cross-tenant error ----------

def scenario_10_cross_tenant_error():
    """跨机构错误 — A1A Gate 2/3 tenant_read_policy deny."""
    yield {
        "step": 1,
        "action": "GET",
        "path": "/api/v1/patient-context/ctx-OTHER-TENANT-id",
        "headers": {},  # JWT says org=ZJU; target context belongs to WCH
        "body": None,
        "expect_status": 404,
        "expect_error_code": "NOT_FOUND",
        "note": "cross-tenant GET returns 404 (no leak) per A1A Gate 3",
    }


# ---------- scenario 11: network timeout ----------

def scenario_11_network_timeout():
    """网络超时 — server 504."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/patient-context",
        "headers": {
            "Idempotency-Key": f"sim-11-{uuid.uuid4().hex[:8]}",
            "X-Test-Inject": "timeout-after-120s",  # simulator-only flag
        },
        "body": {
            "tenant_id": "zju-fh-cn-hangzhou",
            "source_system": "HIS_SIMULATOR",
            "patient_id": "P-timeout-001",
            "visit_type": "outpatient",
            "department_id": "DEPT-GP",
            "clinician_id": "DR-4",
            "purpose_of_use": "treatment",
            "consent_legal_basis": "patient-consent",
        },
        "expect_status": 504,
        "expect_error_code": "UPSTREAM_TIMEOUT",
        "note": "server returns 504 when upstream LLM provider times out",
    }


# ---------- scenario 12: 5xx upstream ----------

def scenario_12_upstream_5xx():
    """5xx — DeepSeek 502."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/agent_run",
        "headers": {
            "Idempotency-Key": f"sim-12-{uuid.uuid4().hex[:8]}",
            "X-Test-Inject": "deepseek-502",
        },
        "body": {
            "agent_id": "icoder/medical-coding-agent",
            "context_id": "ctx-smoke-001",
            "message": "test",
        },
        "expect_status": 502,
        "expect_error_code": "UPSTREAM_ERROR",
        "note": "DeepSeek returns 502; iCoDer surfaces as 502 to client",
    }


# ---------- scenario 13: rate limit (429) ----------

def scenario_13_rate_limit():
    """429 — Phase 7 Gate 8 quota exceeded."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/agent_run",
        "headers": {
            "Idempotency-Key": f"sim-13-{uuid.uuid4().hex[:8]}",
            "X-Test-Inject": "force-rate-limit",
        },
        "body": {
            "agent_id": "icoder/medical-coding-agent",
            "context_id": "ctx-smoke-001",
            "message": "rate limit test",
        },
        "expect_status": 429,
        "expect_error_code": "RATE_LIMITED",
        "note": "Phase 7 Gate 8 quota returns 429 + Retry-After",
    }


# ---------- scenario 14: callback failure (webhook dead letter) ----------

def scenario_14_callback_failure():
    """回调失败 — webhook delivery to HIS fails, retry exhausted, dead-letter."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/webhooks",
        "headers": {"Idempotency-Key": f"sim-14-{uuid.uuid4().hex[:8]}"},
        "body": {
            "url": "https://his-nonexistent.example/icoder-callback",
            "events": ["run.completed"],
        },
        "expect_status": 201,
        "expect_error_code": None,
        "note": "register a webhook that will fail (DNS resolution fail)",
    }
    yield {
        "step": 2,
        "action": "WAIT",
        "path": "",
        "headers": {},
        "body": None,
        "expect_status": 0,
        "expect_error_code": None,
        "wait_seconds": 30,
        "note": "wait 30s for webhook delivery retries to exhaust",
    }
    yield {
        "step": 3,
        "action": "GET",
        "path": "/api/v1/webhooks/{webhook_id}/deliveries?status=dead_letter",
        "headers": {},
        "body": None,
        "expect_status": 200,
        "expect_error_code": None,
        "note": "fetch dead-letter queue; expect at least 1 entry with last_error=DNS_RESOLVE_FAIL",
    }


# ---------- scenario 15: duplicate write-back ----------

def scenario_15_duplicate_writeback():
    """重复回写 — same delivery_id posted twice; HIS must dedupe."""
    delivery_id = str(uuid.uuid4())
    yield {
        "step": 1,
        "action": "POST",
        "path": "https://his.hospital.cn/icoder-callback",
        "headers": {
            "X-iCoDer-Event": "run.completed",
            "X-iCoDer-Delivery": delivery_id,
            "X-iCoDer-Signature": "sha256=deadbeef",
        },
        "body": {
            "delivery_id": delivery_id,
            "event": "run.completed",
            "run_id": "run-abc",
            "result": {"review_status": "auto_approved"},
        },
        "expect_status": 200,
        "expect_error_code": None,
        "note": "first delivery: HIS returns 2xx",
    }
    yield {
        "step": 2,
        "action": "POST",
        "path": "https://his.hospital.cn/icoder-callback",
        "headers": {
            "X-iCoDer-Event": "run.completed",
            "X-iCoDer-Delivery": delivery_id,  # same delivery_id
            "X-iCoDer-Signature": "sha256=deadbeef",
        },
        "body": {
            "delivery_id": delivery_id,
            "event": "run.completed",
            "run_id": "run-abc",
            "result": {"review_status": "auto_approved"},
        },
        "expect_status": 200,
        "expect_error_code": None,
        "note": "HIS must dedupe on delivery_id; idempotent 200",
    }


# ---------- scenario 16: consent rejection ----------

def scenario_16_consent_rejected():
    """consent 拒绝 — consent_legal_basis missing or invalid."""
    yield {
        "step": 1,
        "action": "POST",
        "path": "/api/v1/patient-context",
        "headers": {"Idempotency-Key": f"sim-16-{uuid.uuid4().hex[:8]}"},
        "body": {
            "tenant_id": "zju-fh-cn-hangzhou",
            "source_system": "HIS_SIMULATOR",
            "patient_id": "P-no-consent-001",
            "visit_type": "outpatient",
            "department_id": "DEPT-GP",
            "clinician_id": "DR-5",
            "purpose_of_use": "research",   # research requires explicit consent
            # consent_legal_basis missing — should fail
        },
        "expect_status": 422,
        "expect_error_code": "BUSINESS_RULE_VIOLATION",
        "note": "research purpose without explicit patient-consent triggers 422",
    }


SCENARIO_REGISTRY = {
    1: ("正常病例 (smoke)", scenario_01_smoke),
    2: ("缺字段 (missing fields)", scenario_02_missing_fields),
    3: ("重复消息 (duplicate / idempotency)", scenario_03_duplicate_message),
    4: ("乱序消息 (out-of-order)", scenario_04_out_of_order),
    5: ("延迟消息 (delayed)", scenario_05_delayed_message),
    6: ("撤回文书 (withdraw document)", scenario_06_withdraw_document),
    7: ("文书版本更新 (version update)", scenario_07_document_version_update),
    8: ("患者合并 (patient merge)", scenario_08_patient_merge),
    9: ("就诊号变更 (encounter ID change)", scenario_09_encounter_id_change),
    10: ("跨机构错误 (cross-tenant deny)", scenario_10_cross_tenant_error),
    11: ("网络超时 (timeout / 504)", scenario_11_network_timeout),
    12: ("5xx upstream", scenario_12_upstream_5xx),
    13: ("429 rate limit", scenario_13_rate_limit),
    14: ("回调失败 (callback dead letter)", scenario_14_callback_failure),
    15: ("重复回写 (duplicate write-back)", scenario_15_duplicate_writeback),
    16: ("consent 拒绝 (consent rejection / 422)", scenario_16_consent_rejected),
}
