"""Shared, PHI-safe provenance helpers for controlled Agent Hub live E2E.

The E2E runners intentionally keep response bodies in their existing response
artifacts.  Release summaries receive only hashes, bounded provider/model
identifiers, Pack digests, and execution-source metadata.  A resumed or seeded
artifact is useful for development regression, but is never classified as a
fresh live run.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


MOCK_IDENTIFIERS = frozenset({"mock", "fake", "stub", "test", "none", "unknown"})
LLM_BACKEND_TYPES = frozenset({"pure_llm", "llm_with_tools"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sanitized_endpoint(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "invalid"
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}"


def pack_snapshot(packs: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    snapshot: dict[str, dict[str, str]] = {}
    for pack in packs:
        agent_id = str(pack.get("agent_ref") or "").rsplit("/", 1)[-1].split("@", 1)[0]
        snapshot[agent_id] = {
            "agent_ref": str(pack.get("agent_ref") or ""),
            "pack_sha256": str((pack.get("integrity") or {}).get("sha256") or ""),
            "output_schema_ref": str((pack.get("output_contract") or {}).get("schema_ref") or ""),
            "backend_provider": str(pack.get("backend_provider") or ""),
        }
    return {key: snapshot[key] for key in sorted(snapshot)}


def _b64url_json(value: str) -> dict[str, Any] | None:
    try:
        raw = base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))
        decoded = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return decoded if isinstance(decoded, dict) else None


def result_attestation_evidence(
    response: dict[str, Any],
    *,
    agent_id: str,
    output_schema_ref: str,
) -> dict[str, Any]:
    """Validate the non-secret claims and result digest in a server token.

    Signature verification remains a server/CI trust-boundary concern because
    the API uses a server-only HMAC key.  The live evidence gate additionally
    binds this response to a freshly fetched tenant-scoped RunTrace artifact.
    """

    token = str(response.get("result_attestation") or "")
    result = response.get("result")
    result = result if isinstance(result, dict) else {}
    claims = _b64url_json(token.split(".", 1)[0]) if token.count(".") == 1 else None
    run_id = str(response.get("run_id") or "")
    expected_digest = canonical_sha256(result)
    claims_bound = bool(
        claims
        and claims.get("v") == 1
        and claims.get("r") == run_id
        and claims.get("a") == agent_id
        and claims.get("s") == output_schema_ref
        and claims.get("d") == expected_digest
        and isinstance(claims.get("e"), int)
    )
    signature_verified = False
    if claims_bound:
        try:
            from app.services.result_attestation import verify_result_attestation

            verify_result_attestation(
                token,
                expected_run_id=run_id,
                expected_agent_id=agent_id,
                expected_schema_ref=output_schema_ref,
                expected_organization_id=str(claims.get("o") or ""),
                result=result,
            )
            signature_verified = True
        except Exception:
            signature_verified = False
    return {
        "present": bool(token),
        "claims_bound": claims_bound,
        "signature_verified": signature_verified,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest() if token else "",
        "result_sha256": expected_digest,
        "expires_at_epoch": int(claims.get("e") or 0) if claims else 0,
    }


def _bounded_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 160:
        return ""
    if any(char in text for char in "\r\n\t"):
        return ""
    return text


def extract_trace_evidence(trace: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    events = trace.get("events")
    if not isinstance(events, list):
        events = trace.get("timeline")
    events = events if isinstance(events, list) else []
    trace_token = str(trace.get("trace_attestation") or "")
    trace_claims = (
        _b64url_json(trace_token.split(".", 1)[0])
        if trace_token.count(".") == 1
        else None
    )
    trace_claims_bound = bool(
        trace_claims
        and trace_claims.get("v") == 1
        and trace_claims.get("r") == run_id
        and bool(str(trace_claims.get("o") or ""))
        and trace_claims.get("d") == canonical_sha256(events)
        and isinstance(trace_claims.get("e"), int)
    )
    trace_signature_verified = False
    if trace_claims_bound:
        try:
            from app.services.trace_attestation import verify_trace_attestation

            verify_trace_attestation(
                trace_token,
                expected_run_id=run_id,
                expected_organization_id=str(trace_claims.get("o") or ""),
                events=events,
            )
            trace_signature_verified = True
        except Exception:
            trace_signature_verified = False
    backend_providers: set[str] = set()
    backend_types: set[str] = set()
    model_providers: set[str] = set()
    model_names: set[str] = set()
    degraded = False
    for event in events:
        if not isinstance(event, dict):
            continue
        metadata = event.get("safe_metadata")
        if not isinstance(metadata, dict):
            metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            continue
        backend_provider = _bounded_identifier(metadata.get("backend_provider"))
        backend_type = _bounded_identifier(metadata.get("backend_type"))
        model_provider = _bounded_identifier(
            metadata.get("model_provider") or metadata.get("model_system")
        )
        model_name = _bounded_identifier(metadata.get("model_name"))
        if backend_provider:
            backend_providers.add(backend_provider)
        if backend_type:
            backend_types.add(backend_type)
        if model_provider:
            model_providers.add(model_provider)
        if model_name:
            model_names.add(model_name)
        finish_reason = str(metadata.get("finish_reason") or "").lower()
        finish_state = str(metadata.get("finish_state") or "").lower()
        degraded = degraded or bool(
            metadata.get("fallback_used") is True
            or finish_state in {"failed", "incomplete"}
            or finish_reason.startswith(("degraded", "gateway_error:", "llm_incomplete:"))
        )
    normalized_models = {
        value.casefold() for value in model_providers | model_names if value
    }
    mock_detected = any(
        value in MOCK_IDENTIFIERS or value.startswith(("mock-", "test-", "fake-"))
        for value in normalized_models
    )
    return {
        "http_status": int(trace.get("_http_status") or 0),
        "run_id_matches": str(trace.get("run_id") or "") == run_id,
        "event_count": len(events),
        "trace_attestation_present": bool(trace_token),
        "trace_attestation_claims_bound": trace_claims_bound,
        "trace_attestation_signature_verified": trace_signature_verified,
        "trace_attestation_token_sha256": (
            hashlib.sha256(trace_token.encode("utf-8")).hexdigest()
            if trace_token
            else ""
        ),
        "trace_attestation_expires_at_epoch": (
            int(trace_claims.get("e") or 0) if trace_claims else 0
        ),
        "backend_providers": sorted(backend_providers),
        "backend_types": sorted(backend_types),
        "model_providers": sorted(model_providers),
        "model_names": sorted(model_names),
        "model_call_observed": bool(model_providers and model_names),
        "mock_detected": mock_detected,
        "degraded_detected": degraded,
    }


def capture_trace_artifact(
    *,
    base_url: str,
    headers: dict[str, str],
    response: dict[str, Any],
    trace_path: Path,
    timeout: float,
) -> dict[str, Any]:
    """Fetch and persist one tenant-scoped, display-safe RunTrace artifact."""

    run_id = str(response.get("run_id") or "")
    trace: dict[str, Any]
    if not run_id:
        trace = {"_http_status": 0, "error_reason": "run_id_missing"}
    else:
        try:
            raw = requests.get(
                f"{base_url.rstrip('/')}/api/runtime/runs/{run_id}/trace",
                headers=headers,
                params={"format": "raw"},
                timeout=min(max(timeout, 1.0), 30.0),
            )
            try:
                trace = raw.json()
            except ValueError:
                trace = {"error_reason": "non_json_trace_response"}
            if not isinstance(trace, dict):
                trace = {"error_reason": "non_object_trace_response"}
            trace["_http_status"] = raw.status_code
        except requests.RequestException as exc:
            trace = {"_http_status": 0, "error_reason": type(exc).__name__}
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    evidence = extract_trace_evidence(trace, run_id=run_id)
    evidence.update({
        "artifact_path": str(trace_path.resolve()),
        "artifact_sha256": sha256_file(trace_path),
    })
    return evidence


def row_execution_evidence(
    *,
    action: str,
    response: dict[str, Any],
    response_path: Path,
    pack: dict[str, Any],
    trace_evidence: dict[str, Any] | None,
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    agent_id = str(pack.get("agent_ref") or "").rsplit("/", 1)[-1].split("@", 1)[0]
    schema_ref = str((pack.get("output_contract") or {}).get("schema_ref") or "")
    return {
        "artifact_source": action,
        "started_at": started_at,
        "completed_at": completed_at,
        "response_sha256": sha256_file(response_path),
        "pack_sha256": str((pack.get("integrity") or {}).get("sha256") or ""),
        "output_schema_ref": schema_ref,
        "result_attestation": result_attestation_evidence(
            response,
            agent_id=agent_id,
            output_schema_ref=schema_ref,
        ),
        "trace": trace_evidence or {
            "http_status": 0,
            "run_id_matches": False,
            "event_count": 0,
            "trace_attestation_present": False,
            "trace_attestation_claims_bound": False,
            "trace_attestation_signature_verified": False,
            "trace_attestation_token_sha256": "",
            "trace_attestation_expires_at_epoch": 0,
            "backend_providers": [],
            "backend_types": [],
            "model_providers": [],
            "model_names": [],
            "model_call_observed": False,
            "mock_detected": False,
            "degraded_detected": False,
            "artifact_path": "",
            "artifact_sha256": "",
        },
    }


def execution_provenance(
    rows: list[dict[str, Any]],
    *,
    base_url: str,
    session_started_at: str,
) -> dict[str, Any]:
    sources = [
        str((row.get("execution_evidence") or {}).get("artifact_source") or "unknown")
        for row in rows
    ]
    return {
        "transport": "http",
        "endpoint": sanitized_endpoint(base_url),
        "session_started_at": session_started_at,
        "fresh_http_runs": sum(source == "run" for source in sources),
        "resumed_artifacts": sum(source == "resume" for source in sources),
        "seeded_artifacts": sum(source == "seed" for source in sources),
        "unknown_artifacts": sum(source not in {"run", "resume", "seed"} for source in sources),
        "all_rows_fresh_http": bool(rows) and all(source == "run" for source in sources),
    }
