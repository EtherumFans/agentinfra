"""Offline lifecycle manager for the encrypted software-HSM key store.

All mutating commands require an expected generation and replace the encrypted
file atomically.  Output is metadata-only: key material and the bootstrap key
are never printed.  Keep the bootstrap key in a separate secret manager.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.soft_hsm import SoftwareHSMKeyring  # noqa: E402
from app.services.soft_hsm_keystore import (  # noqa: E402
    bootstrap_key_from_environment,
    read_key_store,
    seal_keyring,
    unseal_keyring,
    validate_key_store_path,
)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _payload(keyring: SoftwareHSMKeyring) -> dict[str, Any]:
    return {
        "active_key_id": keyring.active_key_id,
        "keys": {
            key_id: {"key": _encode(config.master_key), "state": config.state}
            for key_id, config in keyring.keys.items()
        },
    }


def _atomic_write(path: Path, document: bytes, *, must_not_exist: bool) -> None:
    if not path.is_absolute():
        raise RuntimeError("software HSM key store path must be absolute")
    if not path.parent.is_dir():
        raise RuntimeError("software HSM key store parent directory must exist")
    if path.is_symlink():
        raise RuntimeError("software HSM key store path must not be a symbolic link")
    if must_not_exist and path.exists():
        raise RuntimeError("software HSM key store already exists")
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        if must_not_exist:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise RuntimeError("software HSM key store already exists") from exc
            temporary.unlink()
        else:
            if not path.exists():
                raise RuntimeError("software HSM key store disappeared during update")
            os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


@contextlib.contextmanager
def _operator_lock(path: Path):
    """Fail fast when another cooperative key-store operator is active."""
    lock_path = path.parent / f".{path.name}.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("software HSM operator lock cannot be opened safely") from exc
    locked = False
    try:
        os.chmod(lock_path, 0o600)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise RuntimeError("another software HSM operator holds the key store lock") from exc
        yield
    finally:
        if locked:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _load(path: Path, bootstrap_key: bytearray) -> SoftwareHSMKeyring:
    validate_key_store_path(str(path))
    payload, generation = unseal_keyring(
        read_key_store(str(path)), bootstrap_key=bootstrap_key, minimum_generation=1,
    )
    return SoftwareHSMKeyring.from_payload(
        payload, generation=generation, source="encrypted_keystore",
    )


def _require_generation(keyring: SoftwareHSMKeyring, expected: int) -> None:
    if keyring.generation != expected:
        raise RuntimeError(
            f"software HSM key store generation mismatch: expected {expected}, "
            f"found {keyring.generation}"
        )


def create(path: Path, *, key_id: str, bootstrap_key: bytearray) -> dict[str, Any]:
    with _operator_lock(path):
        payload = {
            "active_key_id": key_id,
            "keys": {key_id: {"key": _encode(os.urandom(32)), "state": "active"}},
        }
        keyring = SoftwareHSMKeyring.from_payload(
            payload, generation=1, source="encrypted_keystore",
        )
        _atomic_write(
            path, seal_keyring(payload, bootstrap_key=bootstrap_key, generation=1),
            must_not_exist=True,
        )
    return {"operation": "create", **keyring.public_metadata()}


def rotate(
    path: Path, *, new_key_id: str, expected_generation: int,
    bootstrap_key: bytearray,
) -> dict[str, Any]:
    with _operator_lock(path):
        current = _load(path, bootstrap_key)
        _require_generation(current, expected_generation)
        if new_key_id in current.keys:
            raise RuntimeError("new software HSM key id already exists")
        payload = _payload(current)
        payload["keys"][current.active_key_id]["state"] = "decrypt-only"
        payload["keys"][new_key_id] = {
            "key": _encode(os.urandom(32)), "state": "active",
        }
        payload["active_key_id"] = new_key_id
        generation = current.generation + 1
        next_keyring = SoftwareHSMKeyring.from_payload(
            payload, generation=generation, source="encrypted_keystore",
        )
        _atomic_write(
            path, seal_keyring(payload, bootstrap_key=bootstrap_key, generation=generation),
            must_not_exist=False,
        )
    return {"operation": "rotate", **next_keyring.public_metadata()}


def set_state(
    path: Path, *, key_id: str, state: str, expected_generation: int,
    bootstrap_key: bytearray, authorization: str,
) -> dict[str, Any]:
    with _operator_lock(path):
        current = _load(path, bootstrap_key)
        _require_generation(current, expected_generation)
        config = current.keys.get(key_id)
        if config is None:
            raise RuntimeError("software HSM key id does not exist")
        required_authorization = {
            "retired": "ZERO_REFERENCES_VERIFIED",
            "revoked": "EMERGENCY_REVOKE",
        }[state]
        if authorization != required_authorization:
            raise RuntimeError(
                f"software HSM {state} transition requires explicit authorization"
            )
        allowed = {
            "decrypt-only": {"retired", "revoked"},
            "retired": {"revoked"},
        }
        if state not in allowed.get(config.state, set()):
            raise RuntimeError(
                f"software HSM key state transition {config.state!r} -> {state!r} is forbidden"
            )
        payload = _payload(current)
        payload["keys"][key_id]["state"] = state
        generation = current.generation + 1
        next_keyring = SoftwareHSMKeyring.from_payload(
            payload, generation=generation, source="encrypted_keystore",
        )
        _atomic_write(
            path, seal_keyring(payload, bootstrap_key=bootstrap_key, generation=generation),
            must_not_exist=False,
        )
    return {"operation": f"set-state:{state}", **next_keyring.public_metadata()}


def inspect(path: Path, *, bootstrap_key: bytearray) -> dict[str, Any]:
    return {"operation": "inspect", **_load(path, bootstrap_key).public_metadata()}


def _zeroize(value: bytearray) -> None:
    for index in range(len(value)):
        value[index] = 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "inspect", "rotate", "set-state"))
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--key-id")
    parser.add_argument("--new-key-id")
    parser.add_argument("--state", choices=("retired", "revoked"))
    parser.add_argument("--expected-generation", type=int)
    parser.add_argument("--authorization", default="")
    args = parser.parse_args()
    bootstrap_key = bootstrap_key_from_environment()
    try:
        if args.command == "create":
            if not args.key_id:
                parser.error("create requires --key-id")
            report = create(args.path, key_id=args.key_id, bootstrap_key=bootstrap_key)
        elif args.command == "inspect":
            report = inspect(args.path, bootstrap_key=bootstrap_key)
        elif args.command == "rotate":
            if not args.new_key_id or args.expected_generation is None:
                parser.error("rotate requires --new-key-id and --expected-generation")
            report = rotate(
                args.path, new_key_id=args.new_key_id,
                expected_generation=args.expected_generation,
                bootstrap_key=bootstrap_key,
            )
        else:
            if not args.key_id or not args.state or args.expected_generation is None:
                parser.error("set-state requires --key-id, --state and --expected-generation")
            report = set_state(
                args.path, key_id=args.key_id, state=args.state,
                expected_generation=args.expected_generation,
                bootstrap_key=bootstrap_key, authorization=args.authorization,
            )
    finally:
        _zeroize(bootstrap_key)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
