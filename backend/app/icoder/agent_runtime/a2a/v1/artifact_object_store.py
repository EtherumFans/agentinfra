"""Quarantined, encrypted managed objects for Task-owned A2A Artifacts.

This is the development object-store boundary.  It deliberately supports a
small, fully inspected media set instead of marking opaque binaries clean.
Production deployments still need an independently operated AV/OCR/DLP
service and external object storage, but the authorization and lifecycle
contract here remains the same.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pypdf import PdfReader
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.phi_encryption import decrypt_phi, encrypt_phi

from ...context.db_models import (
    A2AArtifactDownloadGrantRow,
    A2AArtifactObjectRow,
)


MAX_OBJECT_BYTES = 5 * 1024 * 1024
MAX_OBJECTS_PER_ARTIFACT = 16
MAX_DOWNLOAD_TTL_SECONDS = 300
DEFAULT_DOWNLOAD_TTL_SECONDS = 60
MAX_EXTRACTED_TEXT_CHARS = 1_000_000
MAX_PDF_PAGES = 100
SCAN_ENGINE = "icoder-safe-file-v1"
MANAGED_OBJECT_EXTENSION = "urn:icoder:a2a:managed-artifact-object:v1"
ALLOWED_MEDIA_TYPES = frozenset(
    {"text/plain", "application/json", "application/pdf"}
)
ALLOWED_PURPOSES = frozenset(
    {"treatment", "payment", "healthcare_operations"}
)

_EICAR_SHA256 = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"
_DANGEROUS_PDF_KEYS = frozenset(
    {"/AA", "/AcroForm", "/EmbeddedFiles", "/JavaScript", "/JS", "/Launch", "/OpenAction", "/RichMedia"}
)
_MEDIA_EXTENSIONS = {
    "text/plain": {".txt"},
    "application/json": {".json"},
    "application/pdf": {".pdf"},
}
_DLP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "cn_resident_identity_number",
        re.compile(
            r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])"
            r"(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx](?!\d)"
        ),
    ),
    ("cn_mobile_number", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    (
        "email_address",
        re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"),
    ),
    (
        "explicit_patient_identifier",
        re.compile(
            r"(?:患者姓名|姓名|身份证号?|住院号|病案号|医保卡号|手机号|联系电话)"
            r"\s*[:：]\s*[^\s,，;；]{2,64}"
        ),
    ),
)


class ArtifactObjectError(RuntimeError):
    """Safe, machine-readable managed object failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ArtifactObjectNotFound(ArtifactObjectError):
    def __init__(self) -> None:
        super().__init__("OBJECT_NOT_FOUND", "Managed Artifact object not found")


class ArtifactObjectIntegrityError(ArtifactObjectError):
    def __init__(self) -> None:
        super().__init__(
            "OBJECT_INTEGRITY_FAILED",
            "Managed Artifact object integrity verification failed",
        )


class DownloadGrantError(ArtifactObjectError):
    pass


@dataclass(frozen=True)
class _ScanRejected(Exception):
    code: str
    malware_status: str
    dlp_status: str
    detected_media_type: str | None = None
    finding_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ScanResult:
    detected_media_type: str
    malware_status: str
    dlp_status: str
    finding_types: tuple[str, ...]


@dataclass(frozen=True)
class DownloadPayload:
    object_id: str
    organization_id: str
    filename: str
    media_type: str
    content: bytes
    sha256: str
    purpose_of_use: str


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _object_key() -> bytes:
    digest = hashlib.sha256(
        (settings.SECRET_KEY + ":a2a-managed-artifact-object:v1").encode("utf-8")
    ).digest()
    return base64.urlsafe_b64encode(digest)


def _actor_key() -> bytes:
    return hashlib.sha256(
        (settings.SECRET_KEY + ":a2a-managed-artifact-actor:v1").encode("utf-8")
    ).digest()


def _actor_hash(actor_type: str, actor_id: str) -> str:
    return hmac.new(
        _actor_key(), f"{actor_type}:{actor_id}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


def actor_fingerprint(actor_type: str, actor_id: str) -> str:
    if not actor_type or not actor_id:
        raise ArtifactObjectError("ACTOR_REQUIRED", "Authenticated actor is required")
    return _actor_hash(actor_type, actor_id)


def _encrypt_bytes(content: bytes) -> bytes:
    return b"ao1:" + Fernet(_object_key()).encrypt(content)


def _decrypt_bytes(ciphertext: bytes | None) -> bytes:
    if not ciphertext or not ciphertext.startswith(b"ao1:"):
        raise ArtifactObjectIntegrityError()
    try:
        return Fernet(_object_key()).decrypt(ciphertext[4:])
    except (InvalidToken, ValueError) as exc:
        raise ArtifactObjectIntegrityError() from exc


def decode_upload(raw: str) -> bytes:
    if not isinstance(raw, str) or not raw or len(raw) > 7_000_000:
        raise ArtifactObjectError(
            "INVALID_RAW_PAYLOAD", "raw must be canonical base64 up to 5 MiB"
        )
    try:
        content = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError) as exc:
        raise ArtifactObjectError(
            "INVALID_RAW_PAYLOAD", "raw must be canonical base64 up to 5 MiB"
        ) from exc
    if base64.b64encode(content).decode("ascii") != raw:
        raise ArtifactObjectError(
            "INVALID_RAW_PAYLOAD", "raw must use canonical padded base64"
        )
    if not content or len(content) > MAX_OBJECT_BYTES:
        raise ArtifactObjectError(
            "OBJECT_SIZE_INVALID", "Managed Artifact object must be 1 byte to 5 MiB"
        )
    return content


def _validate_filename(filename: str) -> str:
    if not isinstance(filename, str):
        raise ArtifactObjectError("FILENAME_INVALID", "filename must be a string")
    normalized = unicodedata.normalize("NFKC", filename).strip()
    if (
        not normalized
        or len(normalized) > 180
        or len(normalized.encode("utf-8")) > 240
        or normalized in {".", ".."}
        or normalized.startswith(".")
        or "/" in normalized
        or "\\" in normalized
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise ArtifactObjectError(
            "FILENAME_INVALID", "filename must be a safe basename up to 180 characters"
        )
    return normalized


def _validate_media_type(media_type: str, filename: str) -> str:
    normalized = str(media_type or "").strip().casefold()
    if normalized not in ALLOWED_MEDIA_TYPES:
        raise ArtifactObjectError(
            "MEDIA_TYPE_UNSUPPORTED",
            "Only text/plain, application/json, and application/pdf are accepted",
        )
    suffix = "." + filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""
    if suffix not in _MEDIA_EXTENSIONS[normalized]:
        raise ArtifactObjectError(
            "FILENAME_EXTENSION_MISMATCH",
            "filename extension does not match declared media type",
        )
    return normalized


def _dlp_findings(text: str) -> tuple[str, ...]:
    return tuple(name for name, pattern in _DLP_PATTERNS if pattern.search(text))


def _pdf_dangerous_keys(value: Any) -> tuple[str, ...]:
    found: set[str] = set()
    seen: set[int] = set()
    budget = 20_000

    def walk(node: Any, depth: int) -> None:
        nonlocal budget
        if depth > 20 or budget <= 0:
            raise _ScanRejected("PDF_STRUCTURE_LIMIT", "error", "error")
        budget -= 1
        try:
            if hasattr(node, "get_object") and not isinstance(node, (dict, list, tuple)):
                node = node.get_object()
        except Exception as exc:
            raise _ScanRejected("PDF_PARSE_FAILED", "error", "error") from exc
        identity = id(node)
        if identity in seen:
            return
        seen.add(identity)
        if isinstance(node, dict):
            for key, child in node.items():
                key_text = str(key)
                if key_text in _DANGEROUS_PDF_KEYS:
                    found.add(key_text)
                walk(child, depth + 1)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child, depth + 1)

    walk(value, 0)
    return tuple(sorted(found))


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise _ScanRejected("PDF_ENCRYPTED_UNSCANNABLE", "error", "error")
        if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
            raise _ScanRejected("PDF_PAGE_LIMIT", "error", "error")
        dangerous = _pdf_dangerous_keys(reader.trailer)
        if dangerous:
            raise _ScanRejected(
                "PDF_ACTIVE_CONTENT", "infected", "error", "application/pdf", dangerous
            )
        pieces: list[str] = []
        metadata = reader.metadata
        if metadata:
            pieces.extend(str(value) for value in metadata.values() if value)
        total = sum(len(piece) for piece in pieces)
        for page in reader.pages:
            text = page.extract_text() or ""
            total += len(text)
            if total > MAX_EXTRACTED_TEXT_CHARS:
                raise _ScanRejected("PDF_TEXT_LIMIT", "error", "error")
            pieces.append(text)
        return "\n".join(pieces)
    except _ScanRejected:
        raise
    except Exception as exc:
        raise _ScanRejected("PDF_PARSE_FAILED", "error", "error") from exc


def _detect_and_extract(content: bytes, declared_media_type: str) -> tuple[str, str]:
    if hashlib.sha256(content.rstrip(b"\r\n")).hexdigest() == _EICAR_SHA256:
        raise _ScanRejected("MALWARE_TEST_SIGNATURE", "infected", "error")
    if content.startswith((b"MZ", b"\x7fELF")):
        raise _ScanRejected("EXECUTABLE_CONTENT", "infected", "error")
    if content.startswith((b"PK\x03\x04", b"Rar!\x1a\x07", b"7z\xbc\xaf\x27\x1c")):
        raise _ScanRejected("ARCHIVE_CONTENT_UNSCANNABLE", "error", "error")

    if content.startswith(b"%PDF-"):
        detected = "application/pdf"
        if b"%%EOF" not in content[-4096:]:
            raise _ScanRejected("PDF_TRUNCATED", "error", "error", detected)
        extracted = _extract_pdf_text(content)
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        detected, extracted = "image/png", ""
    elif content.startswith(b"\xff\xd8\xff"):
        detected, extracted = "image/jpeg", ""
    else:
        try:
            extracted = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _ScanRejected("CONTENT_UNSCANNABLE", "error", "error") from exc
        if "\x00" in extracted:
            raise _ScanRejected("CONTENT_UNSCANNABLE", "error", "error")
        try:
            json_value = json.loads(extracted)
        except json.JSONDecodeError:
            detected = "text/plain"
        else:
            detected = "application/json" if isinstance(json_value, (dict, list)) else "text/plain"

    if detected != declared_media_type:
        raise _ScanRejected(
            "MEDIA_TYPE_MISMATCH", "error", "error", detected
        )
    return detected, extracted


def scan_content(
    content: bytes,
    *,
    filename: str,
    declared_media_type: str,
    data_classification: str,
) -> _ScanResult:
    if data_classification not in {"deidentified", "clinical-sensitive"}:
        raise ArtifactObjectError(
            "CLASSIFICATION_INVALID",
            "dataClassification must be deidentified or clinical-sensitive",
        )
    detected, extracted = _detect_and_extract(content, declared_media_type)
    filename_findings = _dlp_findings(filename)
    if filename_findings:
        raise _ScanRejected(
            "FILENAME_DLP_BLOCKED", "clean", "blocked", detected, filename_findings
        )
    findings = _dlp_findings(extracted)
    if findings and data_classification == "deidentified":
        raise _ScanRejected(
            "DEIDENTIFICATION_POLICY_BLOCKED", "clean", "blocked", detected, findings
        )
    return _ScanResult(
        detected_media_type=detected,
        malware_status="clean",
        dlp_status="restricted" if findings else "clear",
        finding_types=findings,
    )


def _findings_json(finding_types: tuple[str, ...]) -> str:
    return json.dumps(
        {"types": sorted(set(finding_types)), "count": len(set(finding_types))},
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_filename(row: A2AArtifactObjectRow) -> str:
    try:
        value = decrypt_phi(row.filename_encrypted)
    except Exception as exc:
        raise ArtifactObjectIntegrityError() from exc
    if not value:
        raise ArtifactObjectIntegrityError()
    return _validate_filename(value)


def project_object(row: A2AArtifactObjectRow) -> dict[str, Any]:
    return {
        "objectId": row.object_id,
        "artifactId": row.artifact_id,
        "filename": _decode_filename(row),
        "mediaType": row.detected_media_type or row.declared_media_type,
        "sizeBytes": row.size_bytes,
        "sha256": row.payload_sha256,
        "status": row.status,
        "malwareScanStatus": row.malware_scan_status,
        "dlpScanStatus": row.dlp_scan_status,
        "dataClassification": row.data_classification,
        "rejectionCode": row.rejection_code,
        "scanEngine": row.scan_engine,
        "createdAt": _utc(row.created_at),
        "scannedAt": _utc(row.scanned_at) if row.scanned_at else None,
    }


async def create_and_scan_object(
    db: AsyncSession,
    *,
    organization_id: str,
    context_id: str,
    task_id: str,
    artifact_id: str,
    filename: str,
    media_type: str,
    data_classification: str,
    content: bytes,
    actor_type: str,
    actor_id_hash: str,
    now: datetime | None = None,
) -> A2AArtifactObjectRow:
    filename = _validate_filename(filename)
    media_type = _validate_media_type(media_type, filename)
    if data_classification not in {"deidentified", "clinical-sensitive"}:
        raise ArtifactObjectError(
            "CLASSIFICATION_INVALID",
            "dataClassification must be deidentified or clinical-sensitive",
        )
    count = len(
        (
            await db.execute(
                select(A2AArtifactObjectRow.object_id).where(
                    A2AArtifactObjectRow.organization_id == organization_id,
                    A2AArtifactObjectRow.context_id == context_id,
                    A2AArtifactObjectRow.task_id == task_id,
                    A2AArtifactObjectRow.artifact_id == artifact_id,
                )
            )
        ).all()
    )
    if count >= MAX_OBJECTS_PER_ARTIFACT:
        raise ArtifactObjectError(
            "OBJECT_LIMIT_EXCEEDED", "Artifact already contains the maximum 16 objects"
        )
    when = now or datetime.now(timezone.utc)
    encrypted_filename = encrypt_phi(filename)
    if encrypted_filename is None:
        raise ArtifactObjectIntegrityError()
    row = A2AArtifactObjectRow(
        object_id=f"obj-{uuid.uuid4()}",
        organization_id=organization_id,
        context_id=context_id,
        task_id=task_id,
        artifact_id=artifact_id,
        filename_encrypted=encrypted_filename,
        declared_media_type=media_type,
        detected_media_type=None,
        data_classification=data_classification,
        payload_ciphertext=_encrypt_bytes(content),
        payload_sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        status="quarantined",
        malware_scan_status="pending",
        dlp_scan_status="pending",
        scan_engine=SCAN_ENGINE,
        scan_findings_json=_findings_json(()),
        rejection_code=None,
        actor_type=actor_type,
        actor_id_hash=actor_id_hash,
        created_at=when,
        scanned_at=None,
    )
    db.add(row)
    await db.commit()

    try:
        result = scan_content(
            content,
            filename=filename,
            declared_media_type=media_type,
            data_classification=data_classification,
        )
    except _ScanRejected as rejected:
        row.status = "rejected"
        row.malware_scan_status = rejected.malware_status
        row.dlp_scan_status = rejected.dlp_status
        row.detected_media_type = rejected.detected_media_type
        row.scan_findings_json = _findings_json(rejected.finding_types)
        row.rejection_code = rejected.code
        row.payload_ciphertext = None
    except Exception:
        row.status = "rejected"
        row.malware_scan_status = "error"
        row.dlp_scan_status = "error"
        row.rejection_code = "SCAN_ENGINE_ERROR"
        row.payload_ciphertext = None
    else:
        row.status = "available"
        row.malware_scan_status = result.malware_status
        row.dlp_scan_status = result.dlp_status
        row.detected_media_type = result.detected_media_type
        row.scan_findings_json = _findings_json(result.finding_types)
    row.scanned_at = datetime.now(timezone.utc)
    # The route commits the scan decision together with its mandatory audit
    # row.  If audit persistence fails, rollback leaves only the safe
    # quarantined row from the first commit; protected bytes never become
    # downloadable without an audit trail.
    await db.flush()
    return row


async def list_objects(
    db: AsyncSession,
    *,
    organization_id: str,
    context_id: str,
    task_id: str,
    artifact_id: str,
) -> list[A2AArtifactObjectRow]:
    return list(
        (
            await db.execute(
                select(A2AArtifactObjectRow)
                .where(
                    A2AArtifactObjectRow.organization_id == organization_id,
                    A2AArtifactObjectRow.context_id == context_id,
                    A2AArtifactObjectRow.task_id == task_id,
                    A2AArtifactObjectRow.artifact_id == artifact_id,
                )
                .order_by(A2AArtifactObjectRow.created_at, A2AArtifactObjectRow.object_id)
            )
        ).scalars()
    )


async def get_object(
    db: AsyncSession,
    *,
    organization_id: str,
    context_id: str,
    task_id: str,
    artifact_id: str,
    object_id: str,
) -> A2AArtifactObjectRow:
    row = (
        await db.execute(
            select(A2AArtifactObjectRow).where(
                A2AArtifactObjectRow.object_id == object_id,
                A2AArtifactObjectRow.organization_id == organization_id,
                A2AArtifactObjectRow.context_id == context_id,
                A2AArtifactObjectRow.task_id == task_id,
                A2AArtifactObjectRow.artifact_id == artifact_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ArtifactObjectNotFound()
    return row


_GRANT_ID_RE = re.compile(
    r"^grant-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _validate_grant_id(grant_id: str) -> str:
    if not isinstance(grant_id, str) or not _GRANT_ID_RE.fullmatch(grant_id):
        raise DownloadGrantError("DOWNLOAD_GRANT_INVALID", "Download grant is invalid")
    return grant_id


async def authorize_download(
    db: AsyncSession,
    *,
    row: A2AArtifactObjectRow,
    actor_type: str,
    actor_id_hash: str,
    purpose_of_use: str,
    ttl_seconds: int = DEFAULT_DOWNLOAD_TTL_SECONDS,
    now: datetime | None = None,
) -> A2AArtifactDownloadGrantRow:
    if row.status != "available" or row.payload_ciphertext is None:
        raise DownloadGrantError(
            "OBJECT_NOT_AVAILABLE", "Managed Artifact object is not available for download"
        )
    if purpose_of_use not in ALLOWED_PURPOSES:
        raise DownloadGrantError(
            "PURPOSE_OF_USE_INVALID",
            "purposeOfUse must be treatment, payment, or healthcare_operations",
        )
    if not 1 <= ttl_seconds <= MAX_DOWNLOAD_TTL_SECONDS:
        raise DownloadGrantError(
            "DOWNLOAD_TTL_INVALID", "expiresInSeconds must be between 1 and 300"
        )
    when = now or datetime.now(timezone.utc)
    grant = A2AArtifactDownloadGrantRow(
        grant_id=f"grant-{uuid.uuid4()}",
        object_id=row.object_id,
        organization_id=row.organization_id,
        actor_type=actor_type,
        actor_id_hash=actor_id_hash,
        purpose_of_use=purpose_of_use,
        created_at=when,
        expires_at=when + timedelta(seconds=ttl_seconds),
        consumed_at=None,
    )
    db.add(grant)
    await db.flush()
    return grant


async def consume_download(
    db: AsyncSession,
    *,
    grant_id: str,
    organization_id: str,
    actor_type: str,
    actor_id_hash: str,
    now: datetime | None = None,
) -> DownloadPayload:
    grant_id = _validate_grant_id(grant_id)
    if not organization_id or not actor_type or not actor_id_hash:
        raise DownloadGrantError("DOWNLOAD_GRANT_INVALID", "Download grant is invalid")
    when = now or datetime.now(timezone.utc)
    grant = await db.get(A2AArtifactDownloadGrantRow, grant_id)
    if (
        grant is None
        or grant.organization_id != organization_id
        or grant.actor_type != actor_type
        or not hmac.compare_digest(grant.actor_id_hash, actor_id_hash)
    ):
        raise DownloadGrantError("DOWNLOAD_GRANT_INVALID", "Download grant is invalid")
    if grant.consumed_at is not None:
        raise DownloadGrantError("DOWNLOAD_GRANT_CONSUMED", "Download grant was already used")
    if _utc(grant.expires_at) < when:
        raise DownloadGrantError("DOWNLOAD_GRANT_EXPIRED", "Download grant has expired")
    row = await db.get(A2AArtifactObjectRow, grant.object_id)
    if row is None or row.organization_id != grant.organization_id or row.status != "available":
        raise DownloadGrantError("OBJECT_NOT_AVAILABLE", "Managed Artifact object is not available")
    content = _decrypt_bytes(row.payload_ciphertext)
    if len(content) != row.size_bytes or hashlib.sha256(content).hexdigest() != row.payload_sha256:
        raise ArtifactObjectIntegrityError()
    consumed = await db.execute(
        update(A2AArtifactDownloadGrantRow)
        .where(
            A2AArtifactDownloadGrantRow.grant_id == grant.grant_id,
            A2AArtifactDownloadGrantRow.organization_id == organization_id,
            A2AArtifactDownloadGrantRow.actor_type == actor_type,
            A2AArtifactDownloadGrantRow.actor_id_hash == actor_id_hash,
            A2AArtifactDownloadGrantRow.consumed_at.is_(None),
            A2AArtifactDownloadGrantRow.expires_at >= when,
        )
        .values(consumed_at=when)
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        raise DownloadGrantError("DOWNLOAD_GRANT_CONSUMED", "Download grant was already used")
    return DownloadPayload(
        object_id=row.object_id,
        organization_id=row.organization_id,
        filename=_decode_filename(row),
        media_type=row.detected_media_type or row.declared_media_type,
        content=content,
        sha256=row.payload_sha256,
        purpose_of_use=grant.purpose_of_use,
    )


async def delete_object(
    db: AsyncSession,
    *,
    organization_id: str,
    context_id: str,
    task_id: str,
    artifact_id: str,
    object_id: str,
) -> bool:
    await get_object(
        db,
        organization_id=organization_id,
        context_id=context_id,
        task_id=task_id,
        artifact_id=artifact_id,
        object_id=object_id,
    )
    await db.execute(
        delete(A2AArtifactDownloadGrantRow).where(
            A2AArtifactDownloadGrantRow.object_id == object_id
        )
    )
    result = await db.execute(
        delete(A2AArtifactObjectRow).where(
            A2AArtifactObjectRow.object_id == object_id,
            A2AArtifactObjectRow.organization_id == organization_id,
        )
    )
    return result.rowcount == 1


def project_artifact_objects(
    artifact: dict[str, Any], rows: list[A2AArtifactObjectRow]
) -> dict[str, Any]:
    if not rows:
        return artifact
    projected = dict(artifact)
    metadata = dict(projected.get("metadata") or {})
    metadata["managedObjects"] = [project_object(row) for row in rows]
    projected["metadata"] = metadata
    extensions = list(projected.get("extensions") or [])
    if MANAGED_OBJECT_EXTENSION not in extensions:
        extensions.append(MANAGED_OBJECT_EXTENSION)
    projected["extensions"] = extensions
    return projected


__all__ = [
    "ALLOWED_PURPOSES",
    "ArtifactObjectError",
    "ArtifactObjectIntegrityError",
    "ArtifactObjectNotFound",
    "DEFAULT_DOWNLOAD_TTL_SECONDS",
    "DownloadGrantError",
    "DownloadPayload",
    "MANAGED_OBJECT_EXTENSION",
    "MAX_DOWNLOAD_TTL_SECONDS",
    "MAX_OBJECT_BYTES",
    "actor_fingerprint",
    "authorize_download",
    "consume_download",
    "create_and_scan_object",
    "decode_upload",
    "delete_object",
    "get_object",
    "list_objects",
    "project_artifact_objects",
    "project_object",
    "scan_content",
]
