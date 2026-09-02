"""Minimal HSM boundary and a local software implementation.

The software implementation is deliberately API-compatible with the key
wrapping operations expected from a managed KMS/HSM, but it is not claimed to
provide a hardware security boundary.  It exists for integration, rotation and
disaster-recovery rehearsal before a real provider is connected.
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


class KeyWrappingProvider(Protocol):
    """Non-exporting KEK interface used by the PHI envelope layer."""

    @property
    def key_id(self) -> str: ...

    def generate_data_key(self, *, context: bytes) -> tuple[bytearray, bytes]: ...

    def unwrap_data_key(self, wrapped_key: bytes, *, context: bytes) -> bytearray: ...


@dataclass(frozen=True)
class SoftwareHSMConfig:
    key_id: str
    master_key: bytes

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
        return cls(key_id=key_id, master_key=master_key)


class SoftwareHSM:
    """AES-256-GCM KEK wrapper that simulates the future HSM contract.

    The KEK is never returned by the public interface.  Python cannot provide
    hardware-grade non-exportability or memory isolation; callers and reports
    must continue to label this provider as a simulation.
    """

    def __init__(self, config: SoftwareHSMConfig) -> None:
        self._key_id = config.key_id
        self._wrapper = AESGCM(config.master_key)

    @classmethod
    def from_environment(cls) -> "SoftwareHSM":
        return cls(SoftwareHSMConfig.from_environment())

    @property
    def key_id(self) -> str:
        return self._key_id

    def _aad(self, context: bytes) -> bytes:
        return b"icoder/soft-hsm/wrap/v1\x00" + self._key_id.encode("utf-8") + b"\x00" + context

    def generate_data_key(self, *, context: bytes) -> tuple[bytearray, bytes]:
        plaintext = bytearray(os.urandom(32))
        nonce = os.urandom(12)
        wrapped = nonce + self._wrapper.encrypt(nonce, bytes(plaintext), self._aad(context))
        return plaintext, wrapped

    def unwrap_data_key(self, wrapped_key: bytes, *, context: bytes) -> bytearray:
        if len(wrapped_key) < 12 + 16 + 32:
            raise RuntimeError("wrapped data key is malformed")
        nonce, ciphertext = wrapped_key[:12], wrapped_key[12:]
        try:
            plaintext = self._wrapper.decrypt(nonce, ciphertext, self._aad(context))
        except Exception as exc:
            raise RuntimeError("software HSM could not unwrap data key") from exc
        if len(plaintext) != 32:
            raise RuntimeError("unwrapped data key has invalid length")
        return bytearray(plaintext)


def zeroize(value: bytearray) -> None:
    """Best-effort overwrite for mutable plaintext key material."""
    for index in range(len(value)):
        value[index] = 0


__all__ = [
    "KeyWrappingProvider",
    "SoftwareHSM",
    "SoftwareHSMConfig",
    "zeroize",
]
