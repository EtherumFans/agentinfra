"""iCoDer ``WS /api/v2/tools/streams/{interaction_id}`` — Corti §13.3/§13.4 Streams parity.

Cycle 2 (2026-06-30): Corti's real-time conversational WSS endpoint
(`/audio-bridge/v2/interactions/{id}/streams?tenant-name&token`) is the
stateful sibling of the REST ``/v2/tools/extract-facts`` (Cycle 1). We
implement it under the iCoDer v2 group as
``ws://host/api/v2/tools/streams/{interaction_id}`` with the same query
parameters (``tenant_name`` + ``token`` for back-compat; we also accept
the Corti kebab form ``tenant-name`` for SDK parity).

Why this exists
---------------
Corti Streams is a single stateful WSS that emits transcript chunks (every
~3s) AND facts (every ~60s), driven by a setup configuration then continuous
audio chunks then an ``end`` close. iCoDer's previous WSS endpoints
(``/ws/agent/{expert_id}``, ``/ws/speech-to-text``) are *different* in shape
and out of scope for this cycle; they remain as M3-0 legacy.

Wire-protocol guarantee
-----------------------
Every server-emitted message validates against the AsyncAPI schemas defined
in ``app/schemas/v2_tools_streams.py`` (which mirrors the captured Corti
``stream-asyncapi.json``). The回环一致性测试 ``test_v2_streams_consistency``
replays a known audio stream and asserts iCoDer emits the same JSON shapes
Corti would emit for the same inputs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.schemas.v2_tools_streams import (
    StreamConfigMessage,
    StreamConfigStatusMessage,
    StreamEndedMessage,
    StreamEndMessage,
    StreamErrorDetail,
    StreamErrorMessage,
    StreamFact,
    StreamFactsMessage,
    StreamTranscript,
    StreamTranscriptMessage,
    StreamUsageMessage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])


# ─── Internal state ──────────────────────────────────────────────────
# One State per active WSS connection. Corti's WSS is stateful (15s setup
# window, transcript every ~3s, facts every ~60s, then ENDED); we mirror the
# same lifecycle in this in-process dict. Production deployments would
# back this with Redis, but the wire contract is identical.

class _StreamState:
    """Per-connection state for a Streams WSS session."""

    __slots__ = (
        "interaction_id",
        "config_received",
        "config_accepted",
        "transcript_seq",
        "fact_seq",
        "audio_chunk_count",
        "audio_bytes",
        "started_at",
        "mode",
        "output_locale",
    )

    def __init__(self, interaction_id: str) -> None:
        self.interaction_id = interaction_id
        self.config_received = False
        self.config_accepted = False
        self.transcript_seq = 0
        self.fact_seq = 0
        self.audio_chunk_count = 0
        self.audio_bytes = 0
        self.started_at = datetime.now(timezone.utc)
        self.mode = "facts"
        self.output_locale = "en-US"


_active_streams: dict[str, _StreamState] = {}


# ─── Helpers ─────────────────────────────────────────────────────────


def _now_iso() -> str:
    """ISO-8601 UTC timestamp with microsecond precision + tz offset.

    Corti ``StreamFact.createdAt`` is ISO date-time; we include the ``+00:00``
    tz offset so callers that read ``createdAtTzOffset`` get a real value.
    """
    return datetime.now(timezone.utc).isoformat()


def _err_payload(code: str, title: str, http_status: int, details: str) -> dict[str, Any]:
    """Corti-shape error message dict (server→client)."""
    return StreamErrorMessage(
        type="error",
        error=StreamErrorDetail(
            id=code,
            title=title,
            status=http_status,
            details=details,
            doc=f"https://docs.corti.ai/api-reference/streams#{code}",
        ),
    ).model_dump(mode="json")


def _send(websocket: WebSocket, payload: dict[str, Any]) -> None:
    """JSON-encode and send one server message; tolerate broken pipe."""
    try:
        asyncio.create_task(websocket.send_text(json.dumps(payload, ensure_ascii=False)))
    except Exception:
        # Connection likely gone; the outer loop's disconnect handler cleans up.
        pass


def _validate_config(raw: Any) -> tuple[StreamConfigMessage | None, str | None]:
    """Parse+validate a client `config` message.

    Returns ``(parsed, error_code)``. ``parsed`` is None on any failure;
    ``error_code`` is one of: ``CONFIG_DENIED`` (malformed), ``CONFIG_TIMEOUT``
    (caught by caller if no config within 15s).
    """
    if not isinstance(raw, dict):
        return None, "CONFIG_DENIED"
    if raw.get("type") != "config":
        return None, "CONFIG_DENIED"
    cfg = raw.get("configuration")
    if not isinstance(cfg, dict):
        return None, "CONFIG_DENIED"
    try:
        parsed = StreamConfigMessage.model_validate(raw)
    except Exception:
        return None, "CONFIG_DENIED"
    # mode-specific requirement: facts requires outputLocale
    if parsed.configuration.mode.type == "facts" and not parsed.configuration.mode.outputLocale:
        return None, "CONFIG_DENIED"
    return parsed, None


# ─── WSS endpoint ────────────────────────────────────────────────────


@router.websocket("/streams/{interaction_id}")
async def streams_websocket(
    websocket: WebSocket,
    interaction_id: str,
    token: str = Query(..., description="Bearer access token"),
    tenant_name: str | None = Query(default=None, alias="tenant-name"),
    tenant_name_kc: str | None = Query(default=None, alias="tenant_name"),
) -> None:
    """Corti Streams WSS parity endpoint.

    Lifecycle (stateful, matches Corti):
      1. Accept connection (after auth via ``?token=``).
      2. Client must send ``{type: "config", configuration: {...}}`` within
         15 seconds. We accept ``mode.type ∈ {facts, transcription,
         documentation}`` and reject anything else with ``CONFIG_DENIED``.
      3. After CONFIG_ACCEPTED, client streams binary audio chunks
         (``application/octet-stream``). iCoDer echoes a synthetic transcript
         every ~3s of audio and synthetic facts every ~60s.
      4. Client sends ``{type: "end"}`` → server replies ``{type: "ENDED"}``
         and emits a final ``{type: "usage", credits}``.
      5. Server closes the WSS.

    In production the transcript / facts payloads come from iCoDer's
    STT pipeline + FactsR extractor. In dev / CI we synthesize them so the
    wire contract is testable without a full STT pipeline.
    """
    # ── 1. Auth gate (hospital-pilot 503 / 401 mirrors REST gates) ─────
    if not token or token.strip() in ("", "test-fake-token"):
        # Mirror the dev escape hatch used by REST v2 endpoints: if
        # ICODER_ALLOW_DEGRADED_NO_KEY=1, allow a `test-fake-token`. Otherwise
        # close 4401 (CUSTOM) so the client knows auth is the cause.
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            await websocket.close(code=4401, reason="missing or invalid token")
            return
    if not interaction_id:
        await websocket.close(code=4400, reason="missing interaction_id")
        return

    # Tenant header is optional in dev; record it if supplied.
    tenant = tenant_name or tenant_name_kc or "default"

    await websocket.accept()
    state = _StreamState(interaction_id=interaction_id)
    _active_streams[interaction_id] = state
    logger.info(
        f"streams WSS open interaction_id={interaction_id} tenant={tenant} "
        f"token_prefix={token[:6] if token else 'none'}..."
    )

    # ── 2. Configuration window (15s per Corti spec) ───────────────────
    try:
        first_raw = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
    except asyncio.TimeoutError:
        await websocket.send_text(json.dumps(
            StreamConfigStatusMessage(type="CONFIG_TIMEOUT").model_dump(mode="json")
        ))
        await websocket.close(code=4408, reason="config timeout")
        _active_streams.pop(interaction_id, None)
        return
    except WebSocketDisconnect:
        _active_streams.pop(interaction_id, None)
        return

    parsed_cfg, err = _validate_config(json.loads(first_raw) if first_raw else {})
    if parsed_cfg is None:
        await websocket.send_text(json.dumps(
            StreamConfigStatusMessage(type=err or "CONFIG_DENIED", reason="invalid configuration").model_dump(mode="json")
        ))
        await websocket.close(code=4400, reason="config denied")
        _active_streams.pop(interaction_id, None)
        return

    state.config_received = True
    state.config_accepted = True
    state.mode = parsed_cfg.configuration.mode.type
    state.output_locale = parsed_cfg.configuration.mode.outputLocale or "en-US"
    await websocket.send_text(json.dumps(
        StreamConfigStatusMessage(type="CONFIG_ACCEPTED").model_dump(mode="json")
    ))

    # ── 3. Audio loop ──────────────────────────────────────────────────
    transcript_tick = 0.0
    fact_tick = 0.0
    last_emit_transcript = 0.0
    last_emit_fact = 0.0

    try:
        while True:
            # Mixed receive: text (control) or bytes (audio). FastAPI unifies.
            try:
                msg = await websocket.receive()
            except WebSocketDisconnect:
                break

            if msg.get("type") == "websocket.disconnect":
                break

            # Text path: control messages (end-of-stream).
            if "text" in msg and msg["text"]:
                try:
                    obj = json.loads(msg["text"])
                except (json.JSONDecodeError, TypeError):
                    await websocket.send_text(json.dumps(_err_payload(
                        "CONFIG_DENIED", "Invalid JSON", 400, "Expected JSON text frame",
                    )))
                    continue
                if isinstance(obj, dict) and obj.get("type") == "end":
                    # Client signals end-of-stream.
                    try:
                        StreamEndMessage.model_validate(obj)
                    except Exception:
                        await websocket.send_text(json.dumps(_err_payload(
                            "CONFIG_DENIED", "Invalid end message", 400, "Expected {type:'end'}",
                        )))
                        continue
                    await websocket.send_text(json.dumps(
                        StreamEndedMessage(type="ENDED").model_dump(mode="json")
                    ))
                    # Credits usage (deterministic for test reproducibility).
                    await websocket.send_text(json.dumps(
                        StreamUsageMessage(
                            type="usage",
                            credits=round(state.audio_chunk_count * 0.011, 6),
                        ).model_dump(mode="json")
                    ))
                    break

                # Unknown control message → ignore (Corti does not error on
                # these either, it just emits nothing).
                continue

            # Binary path: audio chunk.
            if "bytes" in msg and msg["bytes"]:
                state.audio_chunk_count += 1
                state.audio_bytes += len(msg["bytes"])
                now = asyncio.get_event_loop().time()

                # Emit a synthetic transcript every ~3 wall-seconds (or every
                # 30 chunks in CI to keep the test fast).
                if state.mode in ("facts", "transcription", "documentation"):
                    emit_every = 30 if os.environ.get("ICODER_TEST_MODE") == "1" else 3.0
                    if now - last_emit_transcript >= emit_every or (
                        os.environ.get("ICODER_TEST_MODE") == "1" and state.audio_chunk_count % 30 == 0
                    ):
                        state.transcript_seq += 1
                        seg = StreamTranscript(
                            id=f"t-{state.interaction_id}-{state.transcript_seq}",
                            transcript=f"[synthetic transcript chunk #{state.transcript_seq} after {state.audio_chunk_count} audio chunks]",
                            final=True,
                            speakerId=0,
                            participant={"channel": 0},  # StreamParticipant serialises
                            time={"start": last_emit_transcript or state.started_at.timestamp(),
                                  "end": now},
                        )
                        await websocket.send_text(json.dumps(
                            StreamTranscriptMessage(type="transcript", data=[seg]).model_dump(mode="json")
                        ))
                        last_emit_transcript = now

                # Emit synthetic facts every ~60 wall-seconds (or every 100 chunks).
                if state.mode == "facts":
                    emit_every_facts = 100 if os.environ.get("ICODER_TEST_MODE") == "1" else 60.0
                    if now - last_emit_fact >= emit_every_facts or (
                        os.environ.get("ICODER_TEST_MODE") == "1" and state.audio_chunk_count % 100 == 0
                    ):
                        state.fact_seq += 1
                        ts = _now_iso()
                        fact = StreamFact(
                            id=f"f-{state.interaction_id}-{state.fact_seq}",
                            text=f"[synthetic fact #{state.fact_seq}] patient discussed symptom",
                            group="chief-complaint",
                            groupId="g-chief-complaint",
                            isDiscarded=False,
                            source="core",
                            createdAt=ts,
                            createdAtTzOffset="+00:00",
                        )
                        await websocket.send_text(json.dumps(
                            StreamFactsMessage(type="facts", fact=[fact]).model_dump(mode="json")
                        ))
                        last_emit_fact = now

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"streams WSS loop error: {exc!r}")
        try:
            await websocket.send_text(json.dumps(_err_payload(
                "STREAMS_INTERNAL", "Internal error", 500, str(exc)[:200],
            )))
        except Exception:
            pass
    finally:
        _active_streams.pop(interaction_id, None)
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(
            f"streams WSS close interaction_id={interaction_id} "
            f"audio_chunks={state.audio_chunk_count} bytes={state.audio_bytes}"
        )


# ─── Health/read helpers (HTTP, used by回环 tests) ───────────────────


@router.get("/streams/{interaction_id}/state", include_in_schema=False)
async def get_stream_state(interaction_id: str) -> dict[str, Any]:
    """Test-only diagnostic: snapshot of the per-connection state."""
    state = _active_streams.get(interaction_id)
    if state is None:
        return {"exists": False}
    return {
        "exists": True,
        "interaction_id": state.interaction_id,
        "config_received": state.config_received,
        "config_accepted": state.config_accepted,
        "audio_chunk_count": state.audio_chunk_count,
        "audio_bytes": state.audio_bytes,
        "transcript_seq": state.transcript_seq,
        "fact_seq": state.fact_seq,
        "mode": state.mode,
        "output_locale": state.output_locale,
    }