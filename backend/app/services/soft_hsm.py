"""Minimal HSM boundary and a local software implementation.

The software implementation is deliberately API-compatible with the key
wrapping operations expected from a managed KMS/HSM, but it is not claimed to
provide a hardware security boundary.  It exists for integration, rotation and
disaster-recovery rehearsal before a real provider is connected.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_KEY_STATES = frozenset({"active", "decrypt-only", "retired", "revoked"})
_METRICS_LOCK = threading.Lock()
_KEY_OPERATION_METRICS: Counter[tuple[str, str, str]] = Counter()
_KEYRING_CACHE_LOCK = threading.Lock()
_KEYRING_CACHE: tuple[tuple[Any, ...], Any] | None = None


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(
        (value + padding).encode("ascii"), altchars=b"-_", validate=True,
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class KeyWrappingProvider(Protocol):
    """Non-exporting KEK interface used by the PHI envelope layer."""

    @property
    def key_id(self) -> str: ...

    def generate_data_key(self, *, context: bytes) -> tuple[bytearray, bytes]: ...

    def wrap_data_key(self, data_key: bytes | bytearray, *, context: bytes) -> bytes: ...

    def unwrap_data_key(self, wrapped_key: bytes, *, context: bytes) -> bytearray: ...


@dataclass(frozen=True)
class SoftwareHSMConfig:
    key_id: str
    master_key: bytes = field(repr=False)
    state: str = "active"

    @classmethod
    def from_environment(cls) -> "SoftwareHSMConfig":
        key_id = os.environ.get("ICODER_SOFT_HSM_KEY_ID", "soft-hsm-kek-v1").strip()
        if _KEY_ID.fullmatch(key_id) is None:
            raise RuntimeError("software HSM key id is invalid")
        raw = os.environ.get("ICODER_SOFT_HSM_MASTER_KEY", "").strip()
        if not raw:
            raise RuntimeError("ICODER_SOFT_HSM_MASTER_KEY is required")
        try:
            master_key = _b64decode(raw)
        except Exception as exc:
            raise RuntimeError("software HSM master key is not valid base64url") from exc
        if len(master_key) != 32:
            raise RuntimeError("software HSM master key must decode to 32 bytes")
        return cls(key_id=key_id, master_key=master_key, state="active")


def _record_key_operation(operation: str, key_id: str, status: str) -> None:
    with _METRICS_LOCK:
        _KEY_OPERATION_METRICS[(operation, key_id, status)] += 1


def key_operation_metrics_snapshot(*, reset: bool = False) -> list[dict[str, Any]]:
    """Return secret-free provider counters suitable for metrics export."""
    with _METRICS_LOCK:
        rows = [
            {"operation": operation, "key_id": key_id, "status": status, "count": count}
            for (operation, key_id, status), count in sorted(_KEY_OPERATION_METRICS.items())
        ]
        if reset:
            _KEY_OPERATION_METRICS.clear()
    return rows


@dataclass(frozen=True)
class SoftwareHSMKeyring:
    """Validated KEK registry with exactly one write-active key."""

    active_key_id: str
    keys: Mapping[str, SoftwareHSMConfig]
    generation: int = 0
    source: str = "environment"

    @classmethod
    def from_environment(cls) -> "SoftwareHSMKeyring":
        global _KEYRING_CACHE
        key_store_path = os.environ.get("ICODER_SOFT_HSM_KEYSTORE_PATH", "").strip()
        deployment_mode = os.environ.get("ICODER_DEPLOYMENT_MODE", "local").strip().lower()
        require_store = os.environ.get(
            "ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE", ""
        ).strip().lower()
        if require_store not in {"", "0", "1", "false", "true"}:
            raise RuntimeError("software HSM encrypted key store requirement is invalid")
        if key_store_path:
            from app.services.soft_hsm_keystore import load_keyring_from_environment

            try:
                file_stat = os.lstat(key_store_path)
            except OSError as exc:
                raise RuntimeError("software HSM key store cannot be inspected") from exc
            bootstrap_fingerprint = hashlib.sha256(
                os.environ.get("ICODER_SOFT_HSM_BOOTSTRAP_KEY", "").encode("utf-8")
            ).digest()
            signature = (
                os.path.abspath(key_store_path), file_stat.st_dev, file_stat.st_ino,
                file_stat.st_mtime_ns, file_stat.st_size, file_stat.st_mode,
                os.environ.get("ICODER_SOFT_HSM_MIN_GENERATION", ""),
                bootstrap_fingerprint,
            )
            with _KEYRING_CACHE_LOCK:
                if _KEYRING_CACHE is not None and _KEYRING_CACHE[0] == signature:
                    return _KEYRING_CACHE[1]
            payload, generation = load_keyring_from_environment()
            keyring = cls.from_payload(
                payload, generation=generation, source="encrypted_keystore"
            )
            with _KEYRING_CACHE_LOCK:
                _KEYRING_CACHE = (signature, keyring)
            return keyring
        if deployment_mode == "cloud" or require_store in {"1", "true"}:
            raise RuntimeError("encrypted software HSM key store is required")
        raw = os.environ.get("ICODER_SOFT_HSM_KEYRING_JSON", "").strip()
        if not raw:
            config = SoftwareHSMConfig.from_environment()
            return cls(active_key_id=config.key_id, keys={config.key_id: config})
        try:
            if len(raw) > 1024 * 1024:
                raise ValueError("keyring too large")
            payload = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
        except Exception as exc:
            raise RuntimeError("software HSM keyring is not valid JSON") from exc
        return cls.from_payload(payload, generation=0, source="environment_json")

    @classmethod
    def from_payload(
        cls, payload: object, *, generation: int, source: str,
    ) -> "SoftwareHSMKeyring":
        if not isinstance(payload, dict) or set(payload) != {"active_key_id", "keys"}:
            raise RuntimeError("software HSM keyring structure is invalid")
        active_key_id = payload["active_key_id"]
        entries = payload["keys"]
        if not isinstance(active_key_id, str) or _KEY_ID.fullmatch(active_key_id) is None:
            raise RuntimeError("software HSM active key id is invalid")
        if not isinstance(entries, dict) or not entries:
            raise RuntimeError("software HSM keyring must contain keys")
        if len(entries) > 64:
            raise RuntimeError("software HSM keyring contains too many keys")
        keys: dict[str, SoftwareHSMConfig] = {}
        for key_id, entry in entries.items():
            if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None:
                raise RuntimeError("software HSM keyring contains an invalid key id")
            if not isinstance(entry, dict) or set(entry) != {"key", "state"}:
                raise RuntimeError(f"software HSM key {key_id!r} structure is invalid")
            state = entry["state"]
            encoded_key = entry["key"]
            if state not in _KEY_STATES or not isinstance(encoded_key, str):
                raise RuntimeError(f"software HSM key {key_id!r} configuration is invalid")
            try:
                master_key = _b64decode(encoded_key)
            except Exception as exc:
                raise RuntimeError(f"software HSM key {key_id!r} is not valid base64url") from exc
            if len(master_key) != 32:
                raise RuntimeError(f"software HSM key {key_id!r} must decode to 32 bytes")
            keys[key_id] = SoftwareHSMConfig(key_id, master_key, state)
        active = [key_id for key_id, config in keys.items() if config.state == "active"]
        if active != [active_key_id]:
            raise RuntimeError("software HSM keyring must declare exactly one matching active key")
        return cls(
            active_key_id=active_key_id, keys=MappingProxyType(keys),
            generation=generation, source=source,
        )

    def active(self) -> "SoftwareHSM":
        return SoftwareHSM(self.keys[self.active_key_id])

    def resolve(self, key_id: str, *, operation: str = "unwrap") -> "SoftwareHSM":
        config = self.keys.get(key_id)
        if config is None:
            raise RuntimeError("PHI envelope requires an unavailable HSM key id")
        if operation == "unwrap" and config.state not in {"active", "decrypt-only"}:
            raise RuntimeError(f"software HSM key {key_id!r} is not enabled for decrypt")
        if operation in {"generate", "wrap"} and config.state != "active":
            raise RuntimeError(f"software HSM key {key_id!r} is not active for writes")
        if operation not in {"unwrap", "generate", "wrap"}:
            raise ValueError("unsupported software HSM operation")
        return SoftwareHSM(config)

    def public_statuses(self) -> dict[str, str]:
        return {key_id: config.state for key_id, config in sorted(self.keys.items())}

    def public_metadata(self) -> dict[str, Any]:
        return {
            "active_key_id": self.active_key_id,
            "generation": self.generation,
            "source": self.source,
            "key_states": self.public_statuses(),
        }


class SoftwareHSM:
    """AES-256-GCM KEK wrapper that simulates the future HSM contract.

    The KEK is never returned by the public interface.  Python cannot provide
    hardware-grade non-exportability or memory isolation; callers and reports
    must continue to label this provider as a simulation.
    """

    def __init__(self, config: SoftwareHSMConfig) -> None:
        self._key_id = config.key_id
        self._state = config.state
        self._wrapper = AESGCM(config.master_key)

    @classmethod
    def from_environment(cls) -> "SoftwareHSM":
        return SoftwareHSMKeyring.from_environment().active()

    @classmethod
    def for_key_id_from_environment(cls, key_id: str) -> "SoftwareHSM":
        return SoftwareHSMKeyring.from_environment().resolve(key_id, operation="unwrap")

    @property
    def key_id(self) -> str:
        return self._key_id

    def _aad(self, context: bytes) -> bytes:
        return b"icoder/soft-hsm/wrap/v1\x00" + self._key_id.encode("utf-8") + b"\x00" + context

    def generate_data_key(self, *, context: bytes) -> tuple[bytearray, bytes]:
        if self._state != "active":
            _record_key_operation("generate", self._key_id, "denied")
            raise RuntimeError("software HSM key is not active for data-key generation")
        plaintext = bytearray(os.urandom(32))
        try:
            wrapped = self._wrap(bytes(plaintext), context=context)
        except Exception:
            _record_key_operation("generate", self._key_id, "error")
            zeroize(plaintext)
            raise
        _record_key_operation("generate", self._key_id, "success")
        return plaintext, wrapped

    def _wrap(self, data_key: bytes, *, context: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._wrapper.encrypt(nonce, data_key, self._aad(context))

    def wrap_data_key(self, data_key: bytes | bytearray, *, context: bytes) -> bytes:
        if self._state != "active":
            _record_key_operation("wrap", self._key_id, "denied")
            raise RuntimeError("software HSM key is not active for data-key wrapping")
        if len(data_key) != 32:
            _record_key_operation("wrap", self._key_id, "error")
            raise RuntimeError("data key has invalid length")
        try:
            wrapped = self._wrap(bytes(data_key), context=context)
        except Exception:
            _record_key_operation("wrap", self._key_id, "error")
            raise
        _record_key_operation("wrap", self._key_id, "success")
        return wrapped

    def unwrap_data_key(self, wrapped_key: bytes, *, context: bytes) -> bytearray:
        if self._state not in {"active", "decrypt-only"}:
            _record_key_operation("unwrap", self._key_id, "denied")
            raise RuntimeError("software HSM key is not enabled for decrypt")
        if len(wrapped_key) < 12 + 16 + 32:
            _record_key_operation("unwrap", self._key_id, "error")
            raise RuntimeError("wrapped data key is malformed")
        nonce, ciphertext = wrapped_key[:12], wrapped_key[12:]
        try:
            plaintext = self._wrapper.decrypt(nonce, ciphertext, self._aad(context))
        except Exception as exc:
            _record_key_operation("unwrap", self._key_id, "error")
            raise RuntimeError("software HSM could not unwrap data key") from exc
        if len(plaintext) != 32:
            _record_key_operation("unwrap", self._key_id, "error")
            raise RuntimeError("unwrapped data key has invalid length")
        _record_key_operation("unwrap", self._key_id, "success")
        return bytearray(plaintext)


def zeroize(value: bytearray) -> None:
    """Best-effort overwrite for mutable plaintext key material."""
    for index in range(len(value)):
        value[index] = 0


__all__ = [
    "KeyWrappingProvider",
    "SoftwareHSM",
    "SoftwareHSMConfig",
    "SoftwareHSMKeyring",
    "key_operation_metrics_snapshot",
    "zeroize",
]
