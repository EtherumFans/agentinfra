"""Durable, integrity-checked A2A v1 Artifact persistence.

Artifacts are stored as encrypted canonical JSON and are always addressed by
the full ``(context_id, task_id, artifact_id)`` tuple.  File output is
represented by the v1 ``raw`` (base64) or ``url`` (HTTPS reference) Part
forms; this service never dereferences a URL.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.phi_encryption import decrypt_phi, encrypt_phi

from ...context.db_models import (
    A2ATaskArtifactRow,
    A2ATaskEventRow,
    ContextTaskRefRow,
)


MAX_ARTIFACTS_PER_TASK = 16
MAX_ARTIFACT_PARTS = 64
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_INLINE_FILE_BYTES = 768 * 1024
MAX_ARTIFACT_STREAM_EVENTS = 256
ARTIFACT_STREAM_CHUNK_CHARS = 8192
VALIDATED_STREAM_ARTIFACT_SUFFIX = "-validated-stream"


class ArtifactValidationError(ValueError):
    """Artifact output does not satisfy the bounded v1 wire contract."""


class ArtifactIntegrityError(RuntimeError):
    """Stored Artifact ciphertext or digest cannot be trusted."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError("Artifact must contain valid JSON values") from exc


def _bounded_string(value: Any, *, field: str, maximum: int, optional: bool = False) -> str:
    if optional and value is None:
        return ""
    if not isinstance(value, str) or (not optional and not value) or len(value) > maximum:
        qualifier = "optional " if optional else "non-empty "
        raise ArtifactValidationError(
            f"{field} must be an {qualifier}string up to {maximum} characters"
        )
    return value


def _normalize_part(part: Any) -> dict[str, Any]:
    if not isinstance(part, dict):
        raise ArtifactValidationError("Artifact Part must be an object")
    content = [key for key in ("text", "data", "raw", "url") if key in part]
    if len(content) != 1:
        raise ArtifactValidationError(
            "Artifact Part must contain exactly one of text, data, raw, or url"
        )
    key = content[0]
    normalized: dict[str, Any]
    if key == "text":
        normalized = {"text": _bounded_string(part[key], field="Part.text", maximum=262144, optional=True)}
    elif key == "data":
        # Canonical encoding below validates JSON serializability and bounds it.
        normalized = {"data": part[key]}
    elif key == "raw":
        raw = _bounded_string(part[key], field="Part.raw", maximum=MAX_ARTIFACT_BYTES * 2)
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (ValueError, TypeError) as exc:
            raise ArtifactValidationError("Part.raw must be canonical base64") from exc
        if len(decoded) > MAX_INLINE_FILE_BYTES:
            raise ArtifactValidationError("inline file Part exceeds 768 KiB")
        normalized = {"raw": base64.b64encode(decoded).decode("ascii")}
    else:
        url = _bounded_string(part[key], field="Part.url", maximum=2048)
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ArtifactValidationError(
                "Part.url must be an HTTPS URL without embedded credentials"
            )
        normalized = {"url": url}

    media_type = part.get("mediaType")
    if media_type is not None:
        normalized["mediaType"] = _bounded_string(
            media_type, field="Part.mediaType", maximum=128
        )
    filename = part.get("filename")
    if filename is not None:
        normalized["filename"] = _bounded_string(
            filename, field="Part.filename", maximum=255
        )
    metadata = part.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ArtifactValidationError("Part.metadata must be an object")
        normalized["metadata"] = metadata
    unknown = set(part) - {
        "text", "data", "raw", "url", "mediaType", "filename", "metadata"
    }
    if unknown:
        raise ArtifactValidationError(
            f"unknown Artifact Part fields: {', '.join(sorted(unknown))}"
        )
    return normalized


def normalize_artifact(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ArtifactValidationError("Artifact must be an object")
    artifact_id = _bounded_string(
        value.get("artifactId"), field="artifactId", maximum=128
    )
    name_value = value.get("name")
    name = None
    if name_value is not None:
        name = _bounded_string(name_value, field="name", maximum=256, optional=True)
    description_value = value.get("description")
    description = None
    if description_value is not None:
        description = _bounded_string(
            description_value,
            field="description",
            maximum=4096,
            optional=True,
        )
    parts = value.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_ARTIFACT_PARTS:
        raise ArtifactValidationError(
            f"Artifact parts must contain 1 to {MAX_ARTIFACT_PARTS} entries"
        )
    metadata = value.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ArtifactValidationError("Artifact metadata must be an object")
    extensions = value.get("extensions") or []
    if (
        not isinstance(extensions, list)
        or len(extensions) > 32
        or any(
            not isinstance(extension, str)
            or not extension
            or len(extension) > 1024
            or not urlsplit(extension).scheme
            for extension in extensions
        )
    ):
        raise ArtifactValidationError(
            "Artifact extensions must contain at most 32 absolute URI strings"
        )
    unknown = set(value) - {
        "artifactId", "name", "description", "parts", "metadata", "extensions"
    }
    if unknown:
        raise ArtifactValidationError(
            f"unknown Artifact fields: {', '.join(sorted(unknown))}"
        )
    normalized = {
        "artifactId": artifact_id,
        "name": name,
        "description": description,
        "parts": [_normalize_part(part) for part in parts],
        "metadata": metadata,
        "extensions": list(extensions),
    }
    if len(_canonical_bytes(normalized)) > MAX_ARTIFACT_BYTES:
        raise ArtifactValidationError("Artifact canonical payload exceeds 1 MiB")
    return normalized


def encode_event_artifact(
    value: Any,
) -> tuple[dict[str, Any], str, str, int]:
    """Normalize and encrypt one exact ArtifactUpdateEvent payload.

    Event payloads are immutable history.  Persisting only ``artifactId``
    would make old events resolve to the latest assembled Artifact and would
    therefore corrupt resumable stream semantics.
    """

    artifact = normalize_artifact(value)
    raw = _canonical_bytes(artifact)
    encrypted = encrypt_phi(raw.decode("utf-8"))
    if encrypted is None:
        raise ArtifactIntegrityError(
            "Artifact event encryption returned no payload"
        )
    return artifact, encrypted, hashlib.sha256(raw).hexdigest(), len(raw)


def decode_event_artifact(row: A2ATaskEventRow) -> dict[str, Any] | None:
    """Verify and decode the exact Artifact carried by a durable event.

    ``None`` is reserved for pre-052 events, whose payload columns are all
    null and whose compatibility projection may load the terminal Artifact.
    A partially populated payload is corruption and fails closed.
    """

    values = (
        row.artifact_payload_json,
        row.artifact_payload_sha256,
        row.artifact_payload_size_bytes,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ArtifactIntegrityError(
            "Artifact event payload integrity fields are incomplete"
        )
    try:
        plaintext = decrypt_phi(row.artifact_payload_json)
        if plaintext is None:
            raise ArtifactIntegrityError("Artifact event payload is missing")
        raw = plaintext.encode("utf-8")
        if len(raw) != row.artifact_payload_size_bytes:
            raise ArtifactIntegrityError(
                "Artifact event size integrity check failed"
            )
        if hashlib.sha256(raw).hexdigest() != row.artifact_payload_sha256:
            raise ArtifactIntegrityError(
                "Artifact event digest integrity check failed"
            )
        artifact = normalize_artifact(json.loads(plaintext))
    except ArtifactIntegrityError:
        raise
    except Exception as exc:
        raise ArtifactIntegrityError(
            "Artifact event payload cannot be verified"
        ) from exc
    if artifact["artifactId"] != row.artifact_id:
        raise ArtifactIntegrityError(
            "Artifact event identity integrity check failed"
        )
    return artifact


def _append_artifact_parts(
    assembled: dict[str, Any], chunk: dict[str, Any]
) -> dict[str, Any]:
    """Apply A2A ``append=true`` parts while keeping the durable result bounded."""

    merged = {
        **assembled,
        "parts": [dict(part) for part in assembled["parts"]],
    }
    for part in chunk["parts"]:
        candidate = dict(part)
        previous = merged["parts"][-1] if merged["parts"] else None
        text_compatible = (
            isinstance(previous, dict)
            and "text" in previous
            and "text" in candidate
            and previous.get("mediaType") == candidate.get("mediaType")
            and previous.get("filename") == candidate.get("filename")
            and previous.get("metadata") == candidate.get("metadata")
            and len(str(previous.get("text") or ""))
            + len(str(candidate.get("text") or ""))
            <= 262144
        )
        if text_compatible:
            previous["text"] = str(previous.get("text") or "") + str(
                candidate.get("text") or ""
            )
        else:
            merged["parts"].append(candidate)
    return normalize_artifact(merged)


def validated_stream_artifact_chunks(
    *,
    task_id: str,
    parts: list[dict[str, Any]],
    source_message_id: str = "",
) -> list[dict[str, Any]]:
    """Build exact bounded chunks for a validated, persisted A2A response.

    The stream Artifact is deliberately separate from the canonical result
    Artifact.  Its text is the deterministic JSON representation of the
    public Message Parts, while the canonical result retains native data/file
    Part types for downstream consumers.
    """

    if not isinstance(parts, list) or not parts:
        return []
    try:
        text = json.dumps(
            parts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError(
            "validated response Parts must contain valid JSON values"
        ) from exc
    if not text:
        return []
    artifact_id = f"{task_id}{VALIDATED_STREAM_ARTIFACT_SUFFIX}"
    chunks: list[dict[str, Any]] = []
    for offset in range(0, len(text), ARTIFACT_STREAM_CHUNK_CHARS):
        first = offset == 0
        chunks.append(normalize_artifact({
            "artifactId": artifact_id,
            "name": "Validated Agent response stream" if first else None,
            "description": (
                "Incremental JSON projection of the validated public A2A Message Parts"
                if first
                else None
            ),
            "parts": [{
                "text": text[offset:offset + ARTIFACT_STREAM_CHUNK_CHARS],
                "mediaType": "application/json",
            }],
            "metadata": (
                {
                    "sourceMessageId": source_message_id,
                    "representation": "a2a-message-parts-json",
                }
                if first
                else {}
            ),
            "extensions": (
                ["urn:icoder:a2a:validated-response-stream:v1"] if first else []
            ),
        }))
    if len(chunks) > MAX_ARTIFACT_STREAM_EVENTS:
        raise ArtifactValidationError("validated response stream has too many chunks")
    return chunks


async def load_completed_stream_artifact(
    db: AsyncSession,
    *,
    context_id: str,
    task_id: str,
    artifact_id: str,
) -> dict[str, Any] | None:
    """Reassemble the latest completed Artifact stream for terminal storage.

    A later ``append=false`` event resets an interrupted earlier attempt.
    This makes lease recovery deterministic without pretending an incomplete
    stream was final.  More than the bounded event count fails closed.
    """

    rows = (
        await db.execute(
            select(A2ATaskEventRow)
            .where(
                A2ATaskEventRow.context_id == context_id,
                A2ATaskEventRow.task_id == task_id,
                A2ATaskEventRow.artifact_id == artifact_id,
                A2ATaskEventRow.event_type == "artifact",
                A2ATaskEventRow.artifact_payload_json.is_not(None),
            )
            .order_by(A2ATaskEventRow.sequence_id)
            .limit(MAX_ARTIFACT_STREAM_EVENTS + 1)
        )
    ).scalars().all()
    if not rows:
        return None
    if len(rows) > MAX_ARTIFACT_STREAM_EVENTS:
        raise ArtifactIntegrityError("Artifact stream has too many events")

    assembled: dict[str, Any] | None = None
    completed = False
    for row in rows:
        chunk = decode_event_artifact(row)
        if chunk is None:
            raise ArtifactIntegrityError(
                "Artifact stream event omitted its immutable payload"
            )
        if row.artifact_append is False:
            assembled = chunk
            completed = bool(row.artifact_last_chunk)
            continue
        if assembled is None:
            raise ArtifactIntegrityError(
                "Artifact stream begins with append=true"
            )
        if completed:
            raise ArtifactIntegrityError(
                "Artifact stream appended after lastChunk=true"
            )
        assembled = _append_artifact_parts(assembled, chunk)
        completed = bool(row.artifact_last_chunk)

    if not completed:
        raise ArtifactIntegrityError(
            "Artifact stream ended without lastChunk=true"
        )
    return assembled


def _project_legacy_part(part: Any) -> dict[str, Any]:
    if not isinstance(part, dict):
        raise ArtifactValidationError("Agent result Part must be an object")
    kind = part.get("kind")
    if kind == "text":
        return {"text": str(part.get("text") or ""), "mediaType": "text/plain"}
    if kind == "data":
        data = part.get("data")
        if isinstance(data, dict) and "value" in data:
            projected: dict[str, Any] = {
                "data": data.get("value"),
                "mediaType": "application/json",
            }
            if isinstance(data.get("schema"), str) and data["schema"]:
                projected["metadata"] = {"schema": data["schema"]}
            return projected
        return {"data": data, "mediaType": "application/json"}
    if kind == "file":
        file_value = part.get("file")
        if not isinstance(file_value, dict):
            raise ArtifactValidationError("Agent file Part must contain a file object")
        projected = {
            key: file_value[key]
            for key in ("raw", "url", "mediaType", "filename")
            if key in file_value
        }
        if "bytes" in file_value:
            projected["raw"] = file_value["bytes"]
        if "uri" in file_value:
            projected["url"] = file_value["uri"]
        return projected
    # Already-v1 output is accepted only through the same strict normalizer.
    return _normalize_part(part)


def result_artifacts(task_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = result.get("artifacts") if result.get("kind") == "task" else None
    if isinstance(explicit, list):
        if not 1 <= len(explicit) <= MAX_ARTIFACTS_PER_TASK:
            raise ArtifactValidationError(
                f"Task must contain 1 to {MAX_ARTIFACTS_PER_TASK} Artifacts"
            )
        return [normalize_artifact(item) for item in explicit]
    parts = result.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ArtifactValidationError("completed Agent result must contain Parts")
    return [normalize_artifact({
        "artifactId": f"{task_id}-result",
        "name": "Agent result",
        "description": "Durable output generated by the Agent for this Task",
        "parts": [_project_legacy_part(part) for part in parts],
        "metadata": {"sourceMessageId": str(result.get("messageId") or "")},
        "extensions": [],
    })]


async def persist_artifacts(
    db: AsyncSession,
    *,
    context_id: str,
    task_id: str,
    artifacts: list[dict[str, Any]],
    created_at: datetime | None = None,
) -> None:
    if len(artifacts) > MAX_ARTIFACTS_PER_TASK:
        raise ArtifactValidationError("Task has too many Artifacts")
    parent = await db.get(
        ContextTaskRefRow, {"context_id": context_id, "task_id": task_id}
    )
    if parent is None:
        raise ArtifactValidationError("Artifact owner Task does not exist")
    when = created_at or datetime.now(timezone.utc)
    seen: set[str] = set()
    for candidate in artifacts:
        artifact = normalize_artifact(candidate)
        artifact_id = artifact["artifactId"]
        if artifact_id in seen:
            raise ArtifactValidationError("duplicate Artifact ID in Task result")
        seen.add(artifact_id)
        raw = _canonical_bytes(artifact)
        encrypted = encrypt_phi(raw.decode("utf-8"))
        if encrypted is None:
            raise ArtifactIntegrityError("Artifact encryption returned no payload")
        db.add(A2ATaskArtifactRow(
            context_id=context_id,
            task_id=task_id,
            artifact_id=artifact_id,
            payload_json=encrypted,
            payload_sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            created_at=when,
        ))


def _decode_row(row: A2ATaskArtifactRow) -> dict[str, Any]:
    try:
        plaintext = decrypt_phi(row.payload_json)
        if plaintext is None:
            raise ArtifactIntegrityError("Artifact payload is missing")
        raw = plaintext.encode("utf-8")
        if len(raw) != row.size_bytes:
            raise ArtifactIntegrityError("Artifact size integrity check failed")
        if hashlib.sha256(raw).hexdigest() != row.payload_sha256:
            raise ArtifactIntegrityError("Artifact digest integrity check failed")
        value = json.loads(plaintext)
        normalized = normalize_artifact(value)
    except ArtifactIntegrityError:
        raise
    except Exception as exc:
        raise ArtifactIntegrityError("Artifact payload cannot be verified") from exc
    if normalized["artifactId"] != row.artifact_id:
        raise ArtifactIntegrityError("Artifact identity integrity check failed")
    return normalized


async def load_task_artifacts(
    db: AsyncSession, *, context_id: str, task_id: str
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(A2ATaskArtifactRow)
            .where(
                A2ATaskArtifactRow.context_id == context_id,
                A2ATaskArtifactRow.task_id == task_id,
            )
            .order_by(A2ATaskArtifactRow.created_at, A2ATaskArtifactRow.artifact_id)
        )
    ).scalars().all()
    return [_decode_row(row) for row in rows]


async def load_task_artifact(
    db: AsyncSession, *, context_id: str, task_id: str, artifact_id: str
) -> dict[str, Any] | None:
    row = await db.get(A2ATaskArtifactRow, {
        "context_id": context_id,
        "task_id": task_id,
        "artifact_id": artifact_id,
    })
    return _decode_row(row) if row is not None else None


__all__ = [
    "ArtifactIntegrityError",
    "ArtifactValidationError",
    "ARTIFACT_STREAM_CHUNK_CHARS",
    "MAX_ARTIFACT_STREAM_EVENTS",
    "VALIDATED_STREAM_ARTIFACT_SUFFIX",
    "decode_event_artifact",
    "encode_event_artifact",
    "load_completed_stream_artifact",
    "load_task_artifact",
    "load_task_artifacts",
    "normalize_artifact",
    "persist_artifacts",
    "result_artifacts",
    "validated_stream_artifact_chunks",
]
