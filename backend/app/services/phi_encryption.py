"""Phase A1A Gate 4.4 — PHI at-rest encryption + key lifecycle.

The pre-Gate-4.4 threat model (Gate 4.1 §T-CC-10) flagged that
SQLite stores all PHI in plaintext: a stolen DB file (backup
mis-handling, dev-laptop theft, cloud-snapshot leak) yields all
PHI columns without any further work. The risk score was 4.4 /
5.0 — the highest in the threat model.

This module dual-reads legacy Fernet v1 and wrapped-DEK AES-256-GCM v2
envelopes. The local software-HSM provider exercises the future external
KMS/HSM boundary but is not a hardware security control. The design must
satisfy three constraints:

1. **Cloud-mode fail-closed.** If no encryption key is configured
   in cloud mode, the platform refuses to boot. Plaintext PHI at
   rest is forbidden in cloud mode.
2. **Local SQLite works without a key.** SQLite development and unit-test
   databases retain the plaintext fallback. PostgreSQL is always strict for
   mapped PHI columns, irrespective of deployment mode.
3. **Key rotation is survivable.** Each encrypted value carries a version
   prefix. Revision 072 permits v1 and v2 concurrently so the operated raw-SQL
   batch tool can rotate online and resume after interruption.

Schema convention (stored in DB):

  - Plaintext: ``"free text"`` (length N)
  - Legacy encrypted: ``"v1:gAAAAA...=="``
  - HSM envelope: ``"v2:<base64url canonical metadata + ciphertext>"``

The decrypt path distinguishes the authenticated envelope structures;
anything else is treated as plaintext only for the SQLite local-development
fallback. PostgreSQL mapped PHI rejects plaintext.

Revision 071 maps clinical PHI attributes through transparent SQLAlchemy
types, stores JSON as one opaque encrypted text envelope, and adds matching
PostgreSQL constraints. Existing explicitly encrypted repositories continue
to use the same versioned envelope contract.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
from typing import Optional

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.services.soft_hsm import SoftwareHSM, zeroize

logger = logging.getLogger(__name__)

# Versioned-key prefix. ``v1:`` / ``v2:`` / ...
_ENCRYPTED_PREFIX_RE = re.compile(r"^v(\d+):")
_LEGACY_ENCRYPTED_VALUE_RE = re.compile(
    r"^v([1-9][0-9]*):gAAAAA[A-Za-z0-9_-]{90,}={0,2}$"
)
_V2_ENCRYPTED_VALUE_RE = re.compile(r"^v2:[A-Za-z0-9_-]{160,}$")
_V2_SCHEMA = "icoder.phi-envelope/v2"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _key_provider_mode() -> str:
    mode = os.environ.get("ICODER_PHI_KEY_PROVIDER", "legacy_fernet").strip().lower()
    if mode not in {"legacy_fernet", "software_hsm", "soft_hsm"}:
        raise RuntimeError(f"unsupported PHI key provider: {mode!r}")
    return mode


def active_envelope_version() -> int:
    """Return the version emitted for new PHI writes."""
    if _key_provider_mode() in {"software_hsm", "soft_hsm"}:
        return 2
    return _active_key_id()


def _resolve_active_key() -> Optional[bytes]:
    """Return the active Fernet key as bytes, or None if disabled.

    Reads ``ICODER_PHI_ENCRYPTION_KEY`` from the environment. The
    value must be a URL-safe base64-encoded 32-byte key (the
    Fernet format). Generate one with::

        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """
    raw = os.environ.get("ICODER_PHI_ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    try:
        return raw.encode("ascii")
    except Exception as e:  # pragma: no cover — defensive
        logger.error("phi_encryption: invalid key encoding: %r", e)
        return None


def _resolve_key_by_id(key_id: int) -> Optional[bytes]:
    """Return a historical key by id, for decrypt during rotation.

    The key resolution order is:
      1. ``ICODER_PHI_ENCRYPTION_KEY_V{N}`` if set (explicit historical).
      2. ``ICODER_PHI_ENCRYPTION_KEY`` (the active key) if
         ``ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID`` equals ``N``.
      3. Otherwise None.

    This means a fresh deployment with no rotation history only
    configures ``ICODER_PHI_ENCRYPTION_KEY`` (active id defaults
    to 1) and v1 lookups resolve to it. After rotation, the
    operator sets ``V1`` explicitly so the v2 active key no
    longer masquerades as v1.
    """
    explicit = os.environ.get(f"ICODER_PHI_ENCRYPTION_KEY_V{key_id}", "").strip()
    if explicit:
        return explicit.encode("ascii")
    if _active_key_id() == key_id:
        return _resolve_active_key()
    return None


def _active_key_id() -> int:
    """The version prefix to apply on new encrypts."""
    try:
        return int(os.environ.get("ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID", "1"))
    except ValueError:
        return 1


def is_encryption_enabled() -> bool:
    """True iff a valid encryption key is configured.

    Cloud-mode Settings validation (Gate 4.4 §2) refuses to boot
    if this returns False in cloud mode.
    """
    if _key_provider_mode() in {"software_hsm", "soft_hsm"}:
        try:
            SoftwareHSM.from_environment()
            return True
        except RuntimeError:
            return False
    return _resolve_active_key() is not None


def is_legacy_v1_enabled() -> bool:
    """Return whether the rollback/backfill v1 key can be resolved."""
    return (_resolve_key_by_id(1) or _resolve_active_key()) is not None


def is_encrypted_value(value: Optional[str]) -> bool:
    """Return whether a value has a supported encrypted envelope structure."""
    if not value or not isinstance(value, str):
        return False
    return bool(
        _LEGACY_ENCRYPTED_VALUE_RE.fullmatch(value)
        or _V2_ENCRYPTED_VALUE_RE.fullmatch(value)
    )


def _v2_context(key_id: str) -> bytes:
    return json.dumps(
        {"algorithm": "A256GCM", "key_id": key_id, "schema": _V2_SCHEMA},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _encrypt_v2(plaintext: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    hsm = SoftwareHSM.from_environment()
    context = _v2_context(hsm.key_id)
    data_key, wrapped_key = hsm.generate_data_key(context=context)
    nonce = secrets.token_bytes(12)
    try:
        ciphertext = AESGCM(bytes(data_key)).encrypt(nonce, plaintext, context)
    finally:
        zeroize(data_key)
    payload = json.dumps(
        {
            "a": "A256GCM",
            "c": _b64encode(ciphertext),
            "k": hsm.key_id,
            "n": _b64encode(nonce),
            "s": _V2_SCHEMA,
            "w": _b64encode(wrapped_key),
        },
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return "v2:" + _b64encode(payload)


def _decrypt_v2(stored: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(stored) > 64 * 1024 * 1024:
        raise RuntimeError("PHI v2 envelope exceeds the maximum supported size")
    try:
        payload = json.loads(_b64decode(stored[3:]))
    except Exception as exc:
        raise RuntimeError("PHI v2 envelope metadata is malformed") from exc
    if not isinstance(payload, dict) or set(payload) != {"a", "c", "k", "n", "s", "w"}:
        raise RuntimeError("PHI v2 envelope metadata is invalid")
    if not all(isinstance(payload[key], str) for key in payload):
        raise RuntimeError("PHI v2 envelope metadata types are invalid")
    if payload["a"] != "A256GCM" or payload["s"] != _V2_SCHEMA:
        raise RuntimeError("PHI v2 envelope algorithm or schema is unsupported")
    hsm = SoftwareHSM.from_environment()
    if payload["k"] != hsm.key_id:
        raise RuntimeError("PHI v2 envelope requires an unavailable HSM key id")
    context = _v2_context(payload["k"])
    try:
        wrapped_key = _b64decode(payload["w"])
        nonce = _b64decode(payload["n"])
        ciphertext = _b64decode(payload["c"])
    except Exception as exc:
        raise RuntimeError("PHI v2 envelope binary fields are malformed") from exc
    if len(nonce) != 12 or len(ciphertext) < 16:
        raise RuntimeError("PHI v2 envelope binary fields are invalid")
    data_key = hsm.unwrap_data_key(wrapped_key, context=context)
    try:
        return AESGCM(bytes(data_key)).decrypt(nonce, ciphertext, context)
    except Exception as exc:
        raise RuntimeError("PHI v2 envelope authentication failed") from exc
    finally:
        zeroize(data_key)


def encrypt_phi_v1(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt explicitly with the legacy v1 key for controlled rollback."""
    if plaintext is None or plaintext == "":
        return plaintext
    key = _resolve_key_by_id(1) or _resolve_active_key()
    if key is None:
        raise RuntimeError("legacy v1 PHI key is required")
    from cryptography.fernet import Fernet

    return "v1:" + Fernet(key).encrypt(plaintext.encode("utf-8")).decode("ascii")


def encrypt_phi(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a PHI value. Returns ``None`` for ``None`` input.

    When encryption is disabled (no key configured), returns the
    original plaintext — local-dev fallback. Callers in
    cloud-mode code paths MUST check ``is_encryption_enabled()``
    first and refuse the write if it returns False.
    """
    if plaintext is None:
        return None
    if not plaintext:
        return plaintext
    if _key_provider_mode() in {"software_hsm", "soft_hsm"}:
        return _encrypt_v2(plaintext.encode("utf-8"))
    key = _resolve_active_key()
    if key is None:
        # Local-dev fallback: store as plaintext. ``is_encrypted_value``
        # returns False so decrypt_phi knows to skip the Fernet path.
        return plaintext
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key)
        token = f.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return f"v{_active_key_id()}:{token}"
    except Exception as e:
        logger.error("phi_encryption: encrypt failed: %r", e)
        # Fail-closed: never return plaintext on an encrypt failure.
        # Caller should surface the error rather than persist PHI
        # in the clear.
        raise


def decrypt_phi(stored: Optional[str]) -> Optional[str]:
    """Decrypt a value produced by ``encrypt_phi``.

    - ``None`` → ``None``.
    - Plaintext (no ``v`` prefix) → returned as-is. This is the
      local-dev fallback and the migration window where rows
      written before Gate 4.4 have not yet been re-encrypted.
    - Encrypted (``v{N}:...``) → decrypted with key v{N}.

    Raises ``RuntimeError`` if the matching key is not configured.
    """
    if stored is None:
        return None
    if not stored:
        return stored
    if stored.startswith("v2:") and not stored.startswith("v2:gAAAAA"):
        return _decrypt_v2(stored).decode("utf-8")
    match = _ENCRYPTED_PREFIX_RE.match(stored)
    if not match:
        # Plaintext fallback — local-dev or pre-migration row.
        return stored
    key_id = int(match.group(1))
    token = stored[match.end():]
    key = _resolve_key_by_id(key_id)
    if key is None:
        raise RuntimeError(
            f"phi_encryption: cannot decrypt value with key_id={key_id}; "
            f"set ICODER_PHI_ENCRYPTION_KEY_V{key_id} to enable"
        )
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key)
        return f.decrypt(token.encode("ascii")).decode("utf-8")
    except Exception as e:
        logger.error("phi_encryption: decrypt failed for key_id=%d: %r", key_id, e)
        raise


def _strict_postgresql_encrypt(value: Optional[str], dialect_name: str) -> Optional[str]:
    """Return a storage value and forbid PostgreSQL plaintext fallback."""
    if value is None or value == "":
        return value
    if is_encrypted_value(value):
        if dialect_name == "postgresql":
            # Do not let an attacker bypass encryption by submitting a string
            # that merely resembles an envelope. Authentication succeeds or
            # the write fails before reaching the database.
            decrypt_phi(value)
        return value
    if dialect_name == "postgresql" and not is_encryption_enabled():
        raise RuntimeError(
            "PHI envelope encryption key is required for PostgreSQL writes"
        )
    encrypted = encrypt_phi(value)
    if dialect_name == "postgresql" and not is_encrypted_value(encrypted):
        raise RuntimeError("PostgreSQL PHI write did not produce an envelope")
    return encrypted


def _strict_postgresql_decrypt(value: Optional[str], dialect_name: str) -> Optional[str]:
    """Decrypt a storage value and reject legacy plaintext on PostgreSQL."""
    if value is None or value == "":
        return value
    if dialect_name == "postgresql" and not is_encrypted_value(value):
        raise RuntimeError("plaintext PHI detected in PostgreSQL result")
    return decrypt_phi(value)


class EncryptedPHIText(TypeDecorator):
    """Transparent versioned PHI envelope for SQLAlchemy text attributes.

    SQLite retains the documented local-development fallback. PostgreSQL is
    always strict: a missing key or plaintext row fails closed.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return _strict_postgresql_encrypt(value, dialect.name)

    def process_result_value(self, value, dialect):
        return _strict_postgresql_decrypt(value, dialect.name)


class EncryptedPHIJSON(TypeDecorator):
    """JSON-compatible Python value stored as one encrypted text envelope."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        serialized = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
        return _strict_postgresql_encrypt(serialized, dialect.name)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        plaintext = _strict_postgresql_decrypt(value, dialect.name)
        return json.loads(plaintext or "null")


def encrypt_phi_bytes(plaintext: bytes) -> bytes:
    """Encrypt binary PHI with the same versioned Fernet key lifecycle.

    Local development without a configured key uses a ``plain:`` marker,
    mirroring :func:`encrypt_phi`'s documented plaintext fallback. Cloud mode
    cannot reach that branch because Settings refuses to boot without a key.
    """
    if not plaintext:
        return b"plain:"
    if _key_provider_mode() in {"software_hsm", "soft_hsm"}:
        return _encrypt_v2(plaintext).encode("ascii")
    key = _resolve_active_key()
    if key is None:
        return b"plain:" + plaintext
    from cryptography.fernet import Fernet

    token = Fernet(key).encrypt(plaintext)
    return f"v{_active_key_id()}:".encode("ascii") + token


def decrypt_phi_bytes(stored: bytes) -> bytes:
    """Decrypt bytes produced by :func:`encrypt_phi_bytes`."""
    if stored.startswith(b"plain:"):
        return stored[len(b"plain:"):]
    if stored.startswith(b"v2:") and not stored.startswith(b"v2:gAAAAA"):
        return _decrypt_v2(stored.decode("ascii"))
    match = re.match(br"^v(\d+):", stored)
    if not match:
        # Backward-compatible local rows written before the binary marker.
        return stored
    key_id = int(match.group(1))
    key = _resolve_key_by_id(key_id)
    if key is None:
        raise RuntimeError(
            f"phi_encryption: cannot decrypt binary value with key_id={key_id}; "
            f"set ICODER_PHI_ENCRYPTION_KEY_V{key_id} to enable"
        )
    from cryptography.fernet import Fernet

    return Fernet(key).decrypt(stored[match.end():])


def generate_key() -> str:
    """Generate a new Fernet key. Helper for the operator runbook.

        python -c "from app.services.phi_encryption import generate_key; print(generate_key())"
    """
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode("ascii")


# ── Phase A1A Gate 4.7 — batch key rotation ─────────────────────────
#
# Key rotation is the operation that makes the encryption lifecycle
# real. Gate 4.4 shipped the prefix-and-sniff scheme so old + new
# values can coexist during the rotation window, but did not ship
# the batch helper. Gate 4.7 closes that gap.
#
# Design:
# - Caller supplies a list of (db_session, model_class, column_name)
#   triples describing which columns to rotate. We don't hard-code
#   the list because new PHI columns may be added by future gates.
# - For each row, we read the current value, decrypt it (which
#   sniffs the prefix and picks the right key), and re-encrypt with
#   the active key. If the value is plaintext (local-dev fallback),
#   we encrypt it for the first time — this is the "adopt encryption"
#   path operators use when flipping from local-dev to cloud mode.
# - ``dry_run=True`` returns the count of rows that WOULD be rotated
#   without modifying anything. Useful for validating the operator's
#   "what would this touch?" question before pulling the trigger.
# - Errors per-row are logged and the row is skipped — a corrupt
#   value should not abort the whole rotation. Callers can re-run
#   after fixing the corrupt row.
#
# Operational notes (runbook will document these in a later gate):
# - Set ``ICODER_PHI_ENCRYPTION_KEY_V1`` to the OLD key before
#   flipping ``ICODER_PHI_ENCRYPTION_KEY`` to the NEW key.
# - Bump ``ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID`` to 2.
# - Run ``rotate_encrypted_columns(...)`` once. All values now carry
#   ``v2:`` prefix.
# - After validation, unset ``_V1`` to remove the historical key
#   from the environment (defence-in-depth — a leaked env file
#   should not yield decrypt capability).
async def rotate_encrypted_columns(
    db,
    columns: list[tuple],
    *,
    dry_run: bool = False,
    batch_size: int = 500,
) -> dict[str, int]:
    """Re-encrypt every value in the given columns with the active key.

    Args:
        db: SQLAlchemy AsyncSession.
        columns: list of ``(model_class, column_name)`` tuples. Each
            column must be a ``Text``/``VARCHAR`` column whose values
            follow the encrypt/decrypt contract of this module.
        dry_run: if True, count rows that would be rotated but do
            not modify any data.
        batch_size: number of rows to fetch per iteration. Larger
            batches = fewer round-trips but more memory.

    Returns:
        dict with per-column counts: ``{f"{table}.{col}": rotated_count}``.
        In dry-run mode, counts are the rows that would be rotated.
    """
    from sqlalchemy import select

    if not is_encryption_enabled():
        raise RuntimeError(
            "rotate_encrypted_columns: encryption is not enabled "
            "(ICODER_PHI_ENCRYPTION_KEY not set). Configure the active "
            "key before rotating."
        )

    active_id = _active_key_id()
    results: dict[str, int] = {}

    for model_class, column_name in columns:
        table_name = getattr(getattr(model_class, "__table__", None), "name", "?")
        key = f"{table_name}.{column_name}"
        count = 0

        # Stream rows in batches to bound memory.
        column_attr = getattr(model_class, column_name)
        # Use the primary key for ordering; assume single-column PK.
        pk_attrs = list(model_class.__mapper__.primary_key)
        if not pk_attrs:
            logger.error(
                "rotate_encrypted_columns: %s has no primary key; skipping",
                table_name,
            )
            results[key] = 0
            continue
        pk_attr = pk_attrs[0]

        # Iterate in batches. We re-query each batch by PK > last_pk
        # to avoid the cost of offset.
        last_pk = None
        while True:
            stmt = select(column_attr, pk_attr).order_by(pk_attr).limit(batch_size)
            if last_pk is not None:
                stmt = stmt.where(pk_attr > last_pk)
            rows = (await db.execute(stmt)).all()
            if not rows:
                break
            for value, pk in rows:
                last_pk = pk
                if value is None or value == "":
                    continue
                if not isinstance(value, str):
                    # Non-string columns are out of scope.
                    continue
                # Skip rows already at the active key id.
                match = _ENCRYPTED_PREFIX_RE.match(value)
                if match and int(match.group(1)) == active_id:
                    continue
                if dry_run:
                    count += 1
                    continue
                try:
                    plaintext = decrypt_phi(value)
                    new_value = encrypt_phi(plaintext)
                    if new_value is None:
                        continue
                    # Update via UPDATE to avoid loading the full ORM row.
                    await db.execute(
                        model_class.__table__.update()
                        .where(pk_attr == pk)
                        .values(**{column_name: new_value})
                    )
                    count += 1
                except Exception as e:
                    logger.error(
                        "rotate_encrypted_columns: %s pk=%s failed: %r",
                        table_name, pk, e,
                    )
                    # Continue with next row.
            if dry_run:
                # In dry-run we don't fetch again — counting the first
                # batch_size rows is enough to know "would this touch
                # anything". For a complete dry-run count, the operator
                # can run a SELECT COUNT(*) separately.
                break

        results[key] = count

    if not dry_run:
        await db.commit()
    return results


__all__ = [
    "encrypt_phi",
    "decrypt_phi",
    "encrypt_phi_bytes",
    "decrypt_phi_bytes",
    "is_encrypted_value",
    "is_encryption_enabled",
    "is_legacy_v1_enabled",
    "generate_key",
    "active_envelope_version",
    "encrypt_phi_v1",
    "rotate_encrypted_columns",
    "EncryptedPHIText",
    "EncryptedPHIJSON",
]
