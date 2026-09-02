"""Phase A1A Gate 4.4 — PHI at-rest encryption + key lifecycle.

The pre-Gate-4.4 threat model (Gate 4.1 §T-CC-10) flagged that
SQLite stores all PHI in plaintext: a stolen DB file (backup
mis-handling, dev-laptop theft, cloud-snapshot leak) yields all
PHI columns without any further work. The risk score was 4.4 /
5.0 — the highest in the threat model.

This module implements envelope-style encryption for high-PHI
columns using Fernet (AES-128-CBC + HMAC-SHA256). The design
must satisfy three constraints:

1. **Cloud-mode fail-closed.** If no encryption key is configured
   in cloud mode, the platform refuses to boot. Plaintext PHI at
   rest is forbidden in cloud mode.
2. **Local SQLite works without a key.** SQLite development and unit-test
   databases retain the plaintext fallback. PostgreSQL is always strict for
   mapped PHI columns, irrespective of deployment mode.
3. **Key rotation is survivable.** Each encrypted value carries
   a ``key_id`` prefix (``v1:`` / ``v2:`` / ...) so the decrypt
   path can pick the right key. The ``rotate_encrypted_columns``
   helper re-encrypts all rows from ``v1`` to ``v2`` on rotation.

Schema convention (stored in DB):

  - Plaintext: ``"free text"`` (length N)
  - Encrypted: ``"v1:gAAAAA...=="`` (length ~N + 100 overhead)

The decrypt path sniffs the prefix: ``v`` + digit + ``:`` means
encrypted; anything else is treated as plaintext (local-dev
fallback). This means encrypted and plaintext rows can coexist
during the rotation window.

Revision 071 maps clinical PHI attributes through transparent SQLAlchemy
types, stores JSON as one opaque encrypted text envelope, and adds matching
PostgreSQL constraints. Existing explicitly encrypted repositories continue
to use the same versioned envelope contract.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from typing import Optional

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

# Versioned-key prefix. ``v1:`` / ``v2:`` / ...
_ENCRYPTED_PREFIX_RE = re.compile(r"^v(\d+):")
_ENCRYPTED_VALUE_RE = re.compile(
    r"^v([1-9][0-9]*):gAAAAA[A-Za-z0-9_-]{90,}={0,2}$"
)


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
    return _resolve_active_key() is not None


def is_encrypted_value(value: Optional[str]) -> bool:
    """Return whether a value has the structural form of a Fernet envelope."""
    if not value or not isinstance(value, str):
        return False
    return bool(_ENCRYPTED_VALUE_RE.fullmatch(value))


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
    "generate_key",
    "rotate_encrypted_columns",
    "EncryptedPHIText",
    "EncryptedPHIJSON",
]
