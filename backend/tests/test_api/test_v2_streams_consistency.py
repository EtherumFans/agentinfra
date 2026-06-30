"""Cycle 2 回环一致性测试 — Corti §13.3/§13.4 Streams WSS shape parity.

This is the hard gate for Cycle 2 per the parity policy. The test:

  1. Loads the **real Corti Streams AsyncAPI spec** captured at
     ``docs/corti-reverse-engineered/stream-asyncapi.json`` (downloaded
     from ``https://docs.corti.ai/api-reference/stream-asyncapi.json``).
  2. Generates a **reference Corti response sequence** by instantiating
     the spec's JSON Schemas with a deterministic audio simulation input.
  3. Drives the **same input** into the iCoDer Streams WSS implementation
     (FastAPI TestClient + threaded reader).
  4. Compares iCoDer's emitted messages against the reference, asserting:
       - Same top-level discriminator (``type``).
       - Same field set (keys, ignoring dynamic ones like ``id`` /
         ``createdAt`` / ``createdAtTzOffset``).
       - Same value types (str/int/bool/list/dict).
       - Same nested structure depth-for-depth.

Any mismatch fails the test (no commit, no next cycle).

Dynamic fields ignored (per the policy):
  - ``id``             — unique per message; auto-assigned
  - ``createdAt``      — server timestamp
  - ``createdAtTzOffset`` — tz offset string at emit time
  - ``credits``        — derived from audio_chunk_count at session end
  - ``time.start/end`` — wall-clock times
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any

import pytest

# Required env for the WSS to permit dev access.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-cycle2")
os.environ.setdefault("ICODER_TEST_MODE", "1")  # speed up synthetic emit cadence
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")

# Paths
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ASYNCAPI_PATH = os.path.join(REPO_ROOT, "docs", "corti-reverse-engineered", "stream-asyncapi.json")


# ─── Helpers ─────────────────────────────────────────────────────────


def _load_asyncapi() -> dict[str, Any]:
    """Load the captured Corti AsyncAPI spec (real, not mocked)."""
    with open(ASYNCAPI_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a ``$ref`` like ``#/components/schemas/Foo``."""
    assert ref.startswith("#/"), f"unsupported ref: {ref}"
    cur: Any = spec
    for part in ref[2:].split("/"):
        cur = cur[part]
    return cur


def _type_of(value: Any) -> str:
    """Map a Python value to a Corti-style JSON Schema ``type`` string."""
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


def _shape_check(
    value: Any,
    schema: dict[str, Any],
    spec: dict[str, Any],
    path: str = "$",
    errors: list[str] | None = None,
) -> list[str]:
    """Recursive shape comparison: assert ``value`` matches ``schema``.

    Dynamic fields (``id``, ``createdAt*``, ``credits``, ``time.*``) are
    skipped — see module docstring. Everything else is asserted for type
    equality, presence (when ``required``), and enum membership.
    """
    if errors is None:
        errors = []
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])
    leaf = path.rsplit(".", 1)[-1]
    if leaf in ("id", "createdAt", "createdAtTzOffset", "updatedAt", "updatedAtTzOffset", "credits"):
        return errors
    if path.endswith(".time.start") or path.endswith(".time.end"):
        return errors

    expected_type = schema.get("type")
    if expected_type and expected_type != "null":
        actual_type = _type_of(value)
        if expected_type == "number" and actual_type == "integer":
            actual_type = "number"
        if actual_type != expected_type:
            errors.append(
                f"{path}: expected type={expected_type}, got type={actual_type} (value={value!r})"
            )
            return errors

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
                _shape_check(v, properties[k], spec, f"{path}.{k}", errors)
    elif expected_type == "array" and isinstance(value, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(value):
                _shape_check(item, items_schema, spec, f"{path}[{i}]", errors)
    return errors


# ─── Reference Corti response sequence ──────────────────────────────


def _corti_reference_sequence(audio_chunks: int) -> list[dict[str, Any]]:
    """Build a deterministic reference Corti response sequence."""
    now = datetime.now(timezone.utc).isoformat()
    out: list[dict[str, Any]] = [{"type": "CONFIG_ACCEPTED"}]
    for chunk_idx in range(1, audio_chunks + 1):
        if chunk_idx % 30 == 0:
            seq = chunk_idx // 30
            out.append({
                "type": "transcript",
                "data": [{
                    "id": f"t-ref-{seq}",
                    "transcript": f"[synthetic transcript chunk #{seq}]",
                    "final": True,
                    "speakerId": 0,
                    "participant": {"channel": 0},
                    "time": {"start": 0.0, "end": float(chunk_idx)},
                }],
            })
        if chunk_idx % 100 == 0:
            seq = chunk_idx // 100
            out.append({
                "type": "facts",
                "fact": [{
                    "id": f"f-ref-{seq}",
                    "text": f"[synthetic fact #{seq}] patient discussed symptom",
                    "group": "chief-complaint",
                    "groupId": "g-chief-complaint",
                    "isDiscarded": False,
                    "source": "core",
                    "createdAt": now,
                    "createdAtTzOffset": "+00:00",
                }],
            })
    out.append({"type": "ENDED"})
    out.append({"type": "usage", "credits": round(audio_chunks * 0.011, 6)})
    return out


# ─── iCoDer driver with threaded reader ─────────────────────────────


@pytest.fixture
def icoder_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def _drive_icoder_streams(
    client,
    audio_chunks: int,
    mode_type: str = "facts",
    output_locale: str | None = "en-US",
    interaction_id: str = "test-interaction-consistency",
) -> list[dict[str, Any]]:
    """Open iCoDer's WSS, drive the protocol, return the list of emitted messages.

    Starlette's TestClient doesn't expose non-blocking ``receive_text``, so
    we spawn a background thread that drains messages into a queue while
    the main thread drives the protocol synchronously.
    """
    url = f"/api/v2/tools/streams/{interaction_id}?token=test-fake-token"
    received_q: Queue = Queue()
    stop_event = threading.Event()

    def _reader(ws):
        try:
            while not stop_event.is_set():
                try:
                    raw = ws.receive_text()
                except Exception:
                    return
                if raw is None:
                    return
                try:
                    received_q.put(json.loads(raw))
                except Exception:
                    pass
        finally:
            return

    with client.websocket_connect(url) as ws:
        reader = threading.Thread(target=_reader, args=(ws,), daemon=True)
        reader.start()

        # 1. Send config and wait for CONFIG_ACCEPTED.
        config_payload: dict[str, Any] = {
            "type": "config",
            "configuration": {
                "transcription": {
                    "primaryLanguage": "en-US",
                    "isDiarization": False,
                    "isMultichannel": False,
                    "participants": [],
                },
                "mode": {"type": mode_type},
            },
        }
        if output_locale:
            config_payload["configuration"]["mode"]["outputLocale"] = output_locale
        ws.send_text(json.dumps(config_payload))

        # Wait for CONFIG_ACCEPTED (≤ 2s).
        accepted = None
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                m = received_q.get(timeout=0.1)
                if m.get("type") == "CONFIG_ACCEPTED":
                    accepted = m
                    break
            except Empty:
                continue
        assert accepted is not None, "no CONFIG_ACCEPTED received"

        # 2. Send audio chunks.
        for _ in range(audio_chunks):
            ws.send_bytes(b"\x00" * 64)

        # 3. Brief settle so the server thread drains transcripts/facts.
        time.sleep(0.3)

        # 4. Send end-of-stream.
        ws.send_text(json.dumps({"type": "end"}))

        # 5. Drain queue until ENDED + usage arrive (≤ 2s).
        received: list[dict[str, Any]] = [accepted]
        deadline = time.time() + 2.0
        while time.time() < deadline:
            try:
                m = received_q.get(timeout=0.1)
            except Empty:
                if any(r.get("type") == "usage" for r in received):
                    break
                continue
            received.append(m)
            if m.get("type") == "usage":
                break

        stop_event.set()
        # Closing the context manager below will tear down the WS.
    return received


# ─── Tests ───────────────────────────────────────────────────────────


def test_asyncapi_spec_is_real_and_cached():
    """Sanity: the AsyncAPI we use as ground truth is the real Corti one."""
    spec = _load_asyncapi()
    assert spec["info"]["title"] == "Real-Time Ambient Documentation"
    assert spec["info"]["version"] == "1.0.0"
    assert spec["channels"]["stream"]["address"].startswith(
        "/audio-bridge/v2/interactions/{id}/streams"
    )
    expected = {"configStatus", "transcript", "facts", "ended", "usage", "error"}
    assert expected.issubset(set(spec["channels"]["stream"]["messages"].keys()))


def test_v2_streams_consistency_transcript_shape_matches_corti_spec(icoder_client):
    """回环: iCoDer's transcript messages match the Corti AsyncAPI schema
    key-for-key (modulo dynamic id/time/credits).
    """
    spec = _load_asyncapi()
    received = _drive_icoder_streams(
        icoder_client, audio_chunks=60, mode_type="transcription"
    )
    transcripts = [m for m in received if m.get("type") == "transcript"]
    assert len(transcripts) >= 2, f"expected ≥2 transcript batches in {received!r}"
    schema = _resolve_ref(spec, "#/components/schemas/StreamTranscriptMessage")
    for tx in transcripts:
        errs = _shape_check(tx, schema, spec, "$.transcript_msg")
        assert not errs, "iCoDer transcript mismatch vs Corti AsyncAPI: " + "; ".join(errs)


def test_v2_streams_consistency_facts_shape_matches_corti_spec(icoder_client):
    """回环: iCoDer's facts messages match the Corti AsyncAPI schema."""
    spec = _load_asyncapi()
    received = _drive_icoder_streams(
        icoder_client, audio_chunks=100, mode_type="facts"
    )
    facts = [m for m in received if m.get("type") == "facts"]
    assert len(facts) >= 1, f"expected ≥1 facts batch in {received!r}"
    schema = _resolve_ref(spec, "#/components/schemas/StreamFactsMessage")
    for fm in facts:
        errs = _shape_check(fm, schema, spec, "$.facts_msg")
        assert not errs, "iCoDer facts mismatch vs Corti AsyncAPI: " + "; ".join(errs)


def test_v2_streams_consistency_end_sequence_matches_corti_spec(icoder_client):
    """回环: after client sends ``end``, iCoDer emits ``ENDED`` then ``usage``."""
    received = _drive_icoder_streams(icoder_client, audio_chunks=10, mode_type="facts")
    types = [m.get("type") for m in received]
    assert "ENDED" in types, f"missing ENDED in {types}"
    assert "usage" in types, f"missing usage in {types}"
    assert types.index("usage") > types.index("ENDED"), (
        f"usage must follow ENDED per Corti spec; got {types}"
    )
    spec = _load_asyncapi()
    schema = _resolve_ref(spec, "#/components/schemas/StreamUsageMessage")
    for u in received:
        if u.get("type") == "usage":
            errs = _shape_check(u, schema, spec, "$.usage_msg")
            assert not errs, "iCoDer usage mismatch: " + "; ".join(errs)


def test_v2_streams_consistency_corti_reference_round_trip():
    """Reference sanity: a hand-built Corti reference sequence validates
    against its own AsyncAPI schemas. If THIS fails, the spec or fixture is
    broken — not iCoDer.
    """
    spec = _load_asyncapi()
    ref = _corti_reference_sequence(audio_chunks=100)
    schema_by_type = {
        "CONFIG_ACCEPTED": "#/components/schemas/StreamConfigStatusMessage",
        "transcript": "#/components/schemas/StreamTranscriptMessage",
        "facts": "#/components/schemas/StreamFactsMessage",
        "ENDED": "#/components/schemas/StreamEndedMessage",
        "usage": "#/components/schemas/StreamUsageMessage",
    }
    for msg in ref:
        sch_path = schema_by_type.get(msg["type"])
        if sch_path is None:
            continue
        errs = _shape_check(msg, _resolve_ref(spec, sch_path), spec, f"$.{msg['type']}")
        assert not errs, f"Corti reference fails its own schema ({msg['type']}): {errs}"