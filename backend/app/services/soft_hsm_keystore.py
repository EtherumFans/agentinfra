"""Encrypted-at-rest key store for the software HSM simulator.

The file contains only an authenticated AES-256-GCM envelope.  Its independent
bootstrap key must be injected by the workload secret mechanism and never
stored beside the file.  A monotonic generation floor provides operator-owned
rollback detection when persisted outside the key store.
"""

from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


SCHEMA = "icoder.software-hsm-keystore/v1"
_CIPHER = "AES-256-GCM"
_KDF = "HKDF-SHA256"
_MAX_FILE_BYTES = 1024 * 1024


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("base64url value is required")
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(
        (value + padding).encode("ascii"), altchars=b"-_", validate=True,
    )


def bootstrap_key_from_environment(
    variable_name: str = "ICODER_SOFT_HSM_BOOTSTRAP_KEY",
) -> bytearray:
    raw = os.environ.get(variable_name, "").strip()
    if not raw:
        raise RuntimeError(f"{variable_name} is required")
    try:
        key = bytearray(_b64decode(raw))
    except Exception as exc:
        raise RuntimeError(f"{variable_name} is not valid base64url") from exc
    if len(key) != 32:
        raise RuntimeError(f"{variable_name} must decode to 32 bytes")
    return key


def _metadata(generation: int) -> dict[str, Any]:
    return {
        "cipher": _CIPHER,
        "generation": generation,
        "kdf": _KDF,
        "schema": SCHEMA,
    }


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _derive_key(bootstrap_key: bytes | bytearray, salt: bytes) -> bytearray:
    return bytearray(HKDF(
        algorithm=hashes.SHA256(), length=32, salt=salt,
        info=b"icoder/software-hsm/keystore/v1",
    ).derive(bytes(bootstrap_key)))


def _zeroize(value: bytearray) -> None:
    for index in range(len(value)):
        value[index] = 0


def seal_keyring(payload: dict[str, Any], *, bootstrap_key: bytes, generation: int) -> bytes:
    if generation < 1:
        raise ValueError("software HSM key store generation must be positive")
    salt, nonce = os.urandom(32), os.urandom(12)
    derived = _derive_key(bootstrap_key, salt)
    try:
        ciphertext = AESGCM(bytes(derived)).encrypt(
            nonce, _canonical(payload), _canonical(_metadata(generation)),
        )
    finally:
        _zeroize(derived)
    document = {
        **_metadata(generation),
        "salt": _b64encode(salt),
        "nonce": _b64encode(nonce),
        "ciphertext": _b64encode(ciphertext),
    }
    return _canonical(document) + b"\n"


def unseal_keyring(
    document: bytes, *, bootstrap_key: bytes | bytearray, minimum_generation: int,
) -> tuple[dict[str, Any], int]:
    if minimum_generation < 1:
        raise ValueError("software HSM minimum generation must be positive")
    if len(document) > _MAX_FILE_BYTES:
        raise RuntimeError("software HSM key store exceeds maximum size")
    try:
        parsed = json.loads(document)
    except Exception as exc:
        raise RuntimeError("software HSM key store is not valid JSON") from exc
    expected = {"schema", "generation", "cipher", "kdf", "salt", "nonce", "ciphertext"}
    if not isinstance(parsed, dict) or set(parsed) != expected:
        raise RuntimeError("software HSM key store structure is invalid")
    generation = parsed["generation"]
    if (
        parsed["schema"] != SCHEMA or parsed["cipher"] != _CIPHER
        or parsed["kdf"] != _KDF or not isinstance(generation, int)
        or isinstance(generation, bool) or generation < 1
    ):
        raise RuntimeError("software HSM key store metadata is invalid")
    if generation < minimum_generation:
        raise RuntimeError("software HSM key store rollback detected")
    try:
        salt = _b64decode(parsed["salt"])
        nonce = _b64decode(parsed["nonce"])
        ciphertext = _b64decode(parsed["ciphertext"])
    except Exception as exc:
        raise RuntimeError("software HSM key store binary fields are malformed") from exc
    if len(salt) != 32 or len(nonce) != 12 or len(ciphertext) < 16:
        raise RuntimeError("software HSM key store binary fields are invalid")
    derived = _derive_key(bootstrap_key, salt)
    try:
        plaintext = bytearray(AESGCM(bytes(derived)).decrypt(
            nonce, ciphertext, _canonical(_metadata(generation)),
        ))
    except Exception as exc:
        raise RuntimeError("software HSM key store authentication failed") from exc
    finally:
        _zeroize(derived)
    try:
        payload = json.loads(bytes(plaintext))
    except Exception as exc:
        raise RuntimeError("software HSM key store payload is invalid") from exc
    finally:
        _zeroize(plaintext)
    if not isinstance(payload, dict):
        raise RuntimeError("software HSM key store payload is invalid")
    return payload, generation


def validate_key_store_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        raise RuntimeError("software HSM key store path must be absolute")
    if path.is_symlink():
        raise RuntimeError("software HSM key store must not be a symbolic link")
    try:
        file_stat = path.stat()
    except OSError as exc:
        raise RuntimeError("software HSM key store cannot be read") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError("software HSM key store must be a regular file")
    if file_stat.st_size > _MAX_FILE_BYTES:
        raise RuntimeError("software HSM key store exceeds maximum size")
    if os.name != "nt":
        if file_stat.st_uid != os.geteuid():
            raise RuntimeError("software HSM key store must be owned by the runtime user")
        if stat.S_IMODE(file_stat.st_mode) & 0o077:
            raise RuntimeError("software HSM key store permissions must be 0600 or stricter")
    return path


def read_key_store(path_value: str) -> bytes:
    """Open and validate one regular file handle, avoiding POSIX symlink races."""
    path = Path(path_value)
    if not path.is_absolute():
        raise RuntimeError("software HSM key store path must be absolute")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("software HSM key store cannot be opened safely") from exc
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise RuntimeError("software HSM key store must be a regular file")
        if file_stat.st_size > _MAX_FILE_BYTES:
            raise RuntimeError("software HSM key store exceeds maximum size")
        if os.name != "nt":
            if file_stat.st_uid != os.geteuid():
                raise RuntimeError("software HSM key store must be owned by the runtime user")
            if stat.S_IMODE(file_stat.st_mode) & 0o077:
                raise RuntimeError("software HSM key store permissions must be 0600 or stricter")
        chunks: list[bytes] = []
        remaining = _MAX_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        document = b"".join(chunks)
        if len(document) > _MAX_FILE_BYTES:
            raise RuntimeError("software HSM key store exceeds maximum size")
        return document
    finally:
        os.close(descriptor)


def load_keyring_from_environment() -> tuple[dict[str, Any], int]:
    path_value = os.environ.get("ICODER_SOFT_HSM_KEYSTORE_PATH", "").strip()
    if not path_value:
        raise RuntimeError("ICODER_SOFT_HSM_KEYSTORE_PATH is required")
    raw_floor = os.environ.get("ICODER_SOFT_HSM_MIN_GENERATION", "").strip()
    if os.environ.get("ICODER_DEPLOYMENT_MODE", "local").strip().lower() == "cloud" and not raw_floor:
        raise RuntimeError("ICODER_SOFT_HSM_MIN_GENERATION is required in cloud mode")
    try:
        minimum_generation = int(raw_floor or "1")
    except ValueError as exc:
        raise RuntimeError("software HSM minimum generation must be an integer") from exc
    if minimum_generation < 1:
        raise RuntimeError("software HSM minimum generation must be positive")
    bootstrap_key = bootstrap_key_from_environment()
    try:
        document = read_key_store(path_value)
        return unseal_keyring(
            document, bootstrap_key=bootstrap_key,
            minimum_generation=minimum_generation,
        )
    finally:
        _zeroize(bootstrap_key)


__all__ = [
    "SCHEMA", "bootstrap_key_from_environment", "load_keyring_from_environment",
    "read_key_store", "seal_keyring", "unseal_keyring", "validate_key_store_path",
]
