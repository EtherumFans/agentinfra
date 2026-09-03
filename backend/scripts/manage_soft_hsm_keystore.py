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
from typing import Any, Callable


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
from app.services.soft_hsm_ops_audit import (  # noqa: E402
    append_event,
    audit_config_from_environment,
    audit_minimum_sequence_from_environment,
    audit_verification_keys_from_environment,
    key_store_identifier,
    parse_and_verify,
    read_audit_document,
    zeroize as zeroize_audit_key,
)
from app.services.soft_hsm_audit_archive import archive_from_environment  # noqa: E402


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


def rotate_bootstrap(
    path: Path, *, expected_generation: int, bootstrap_key: bytearray,
    new_bootstrap_key: bytearray,
) -> dict[str, Any]:
    """Reseal the same KEKs under a new bootstrap key; database DEKs are untouched."""
    if bootstrap_key == new_bootstrap_key:
        raise RuntimeError("new software HSM bootstrap key must differ from the current key")
    with _operator_lock(path):
        current = _load(path, bootstrap_key)
        _require_generation(current, expected_generation)
        payload = _payload(current)
        generation = current.generation + 1
        next_keyring = SoftwareHSMKeyring.from_payload(
            payload, generation=generation, source="encrypted_keystore",
        )
        _atomic_write(
            path,
            seal_keyring(
                payload, bootstrap_key=new_bootstrap_key, generation=generation,
            ),
            must_not_exist=False,
        )
    return {"operation": "rotate-bootstrap", **next_keyring.public_metadata()}


def inspect(path: Path, *, bootstrap_key: bytearray) -> dict[str, Any]:
    return {"operation": "inspect", **_load(path, bootstrap_key).public_metadata()}


def _zeroize(value: bytearray) -> None:
    for index in range(len(value)):
        value[index] = 0


def _audit_event(
    *, operation: str, phase: str, outcome: str, path: Path,
    expected_generation: int | None, report: dict[str, Any] | None,
    error_type: str | None, change_ticket: str,
) -> dict[str, Any]:
    deployment_mode = os.environ.get("ICODER_DEPLOYMENT_MODE", "local").strip().lower()
    operator_identity = os.environ.get("ICODER_OPERATOR_IDENTITY", "local-operator").strip()
    deployment_environment = os.environ.get(
        "ICODER_DEPLOYMENT_ENVIRONMENT", deployment_mode
    ).strip()
    release_version = os.environ.get("ICODER_RELEASE_VERSION", "development").strip()
    if deployment_mode == "cloud" and (
        not operator_identity or not deployment_environment or not release_version
    ):
        raise RuntimeError("cloud HSM audit requires operator, environment and release identity")
    return {
        "operation": operation,
        "phase": phase,
        "outcome": outcome,
        "key_store_id": key_store_identifier(path),
        "expected_generation": expected_generation,
        "resulting_generation": report.get("generation") if report else None,
        "active_key_id": report.get("active_key_id") if report else None,
        "key_states": report.get("key_states", {}) if report else {},
        "error_type": error_type,
        "change_ticket": change_ticket,
        "operator_identity": operator_identity,
        "deployment_environment": deployment_environment,
        "release_version": release_version,
    }


def _archive_is_required() -> bool:
    # Immutable/WORM archival is an optional advanced product capability, not
    # an implicit requirement of cloud mode. Keep the old variable as an
    # explicit backwards-compatible opt-in for existing deployments.
    enabled = os.environ.get(
        "ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED", "false"
    ).strip().lower()
    legacy_required = os.environ.get(
        "ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED", "false"
    ).strip().lower()
    accepted = {"1", "true", "yes", "on"}
    disabled = {"", "0", "false", "no", "off"}
    if enabled not in accepted | disabled or legacy_required not in accepted | disabled:
        raise RuntimeError("immutable audit archive feature flag is invalid")
    return enabled in accepted or legacy_required in accepted


def _replicate_audit_archive(
    *, audit_path: Path, audit_key: bytearray, audit_key_id: str,
    verification_keys: dict[str, bytearray], minimum_sequence: int,
    forbidden_checkpoint_keys: tuple[bytes | bytearray, ...] = (),
) -> dict[str, Any] | None:
    if not _archive_is_required():
        return None
    archive = archive_from_environment()
    if any(archive.uses_checkpoint_key(key) for key in forbidden_checkpoint_keys):
        raise RuntimeError("audit archive checkpoint key must be independently managed")
    document = read_audit_document(audit_path)
    records = parse_and_verify(
        document, audit_key=audit_key, signing_key_id=audit_key_id,
        verification_keys=verification_keys, minimum_sequence=minimum_sequence,
    )
    replication = archive.replicate_records(records)
    archive.verify(verification_keys=verification_keys, minimum_sequence=len(records))
    return replication


def _audited_mutation(
    *, operation: str, path: Path, expected_generation: int | None,
    change_ticket: str, bootstrap_key: bytearray,
    callback: Callable[[], dict[str, Any]],
    additional_secret_key: bytearray | None = None,
) -> dict[str, Any]:
    if not change_ticket or len(change_ticket) > 128 or any(
        character in change_ticket for character in "\r\n"
    ):
        raise RuntimeError("mutating software HSM operations require a valid change ticket")
    audit_minimum_sequence = audit_minimum_sequence_from_environment()
    audit_path, audit_key, audit_key_id = audit_config_from_environment()
    verification_keys = audit_verification_keys_from_environment()
    try:
        if audit_key == bootstrap_key or (
            additional_secret_key is not None and audit_key == additional_secret_key
        ):
            raise RuntimeError("software HSM operations audit key must differ from bootstrap key")
        if os.path.normcase(os.path.abspath(audit_path)) == os.path.normcase(os.path.abspath(path)):
            raise RuntimeError("software HSM key store and operations audit paths must differ")
        forbidden_checkpoint_keys = tuple(
            key for key in (audit_key, bootstrap_key, additional_secret_key) if key is not None
        )
        append_event(
            audit_path,
            _audit_event(
                operation=operation, phase="started", outcome="pending", path=path,
                expected_generation=expected_generation, report=None,
                error_type=None, change_ticket=change_ticket,
            ),
            audit_key=audit_key, signing_key_id=audit_key_id,
            minimum_sequence=audit_minimum_sequence, verification_keys=verification_keys,
        )
        _replicate_audit_archive(
            audit_path=audit_path, audit_key=audit_key, audit_key_id=audit_key_id,
            verification_keys=verification_keys, minimum_sequence=audit_minimum_sequence,
            forbidden_checkpoint_keys=forbidden_checkpoint_keys,
        )
        try:
            report = callback()
        except Exception as exc:
            append_event(
                audit_path,
                _audit_event(
                    operation=operation, phase="failed", outcome="failure", path=path,
                    expected_generation=expected_generation, report=None,
                    error_type=type(exc).__name__, change_ticket=change_ticket,
                ),
                audit_key=audit_key, signing_key_id=audit_key_id,
                minimum_sequence=audit_minimum_sequence, verification_keys=verification_keys,
            )
            _replicate_audit_archive(
                audit_path=audit_path, audit_key=audit_key, audit_key_id=audit_key_id,
                verification_keys=verification_keys, minimum_sequence=audit_minimum_sequence,
                forbidden_checkpoint_keys=forbidden_checkpoint_keys,
            )
            raise
        completed = append_event(
            audit_path,
            _audit_event(
                operation=operation, phase="completed", outcome="success", path=path,
                expected_generation=expected_generation, report=report,
                error_type=None, change_ticket=change_ticket,
            ),
            audit_key=audit_key, signing_key_id=audit_key_id,
            minimum_sequence=audit_minimum_sequence, verification_keys=verification_keys,
        )
        archive_report = _replicate_audit_archive(
            audit_path=audit_path, audit_key=audit_key, audit_key_id=audit_key_id,
            verification_keys=verification_keys, minimum_sequence=audit_minimum_sequence,
            forbidden_checkpoint_keys=forbidden_checkpoint_keys,
        )
        return {
            **report,
            "audit_sequence": completed["sequence"],
            "audit_chain_hash": completed["chain_hash"],
            "audit_archive": archive_report,
        }
    finally:
        zeroize_audit_key(audit_key)
        for verifier_key in verification_keys.values():
            zeroize_audit_key(verifier_key)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("create", "inspect", "rotate", "rotate-bootstrap", "set-state")
    )
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--key-id")
    parser.add_argument("--new-key-id")
    parser.add_argument("--state", choices=("retired", "revoked"))
    parser.add_argument("--expected-generation", type=int)
    parser.add_argument("--authorization", default="")
    parser.add_argument("--change-ticket", default="")
    args = parser.parse_args()
    bootstrap_key = bootstrap_key_from_environment()
    try:
        if args.command == "create":
            if not args.key_id:
                parser.error("create requires --key-id")
            report = _audited_mutation(
                operation="create", path=args.path, expected_generation=0,
                change_ticket=args.change_ticket, bootstrap_key=bootstrap_key,
                callback=lambda: create(
                    args.path, key_id=args.key_id, bootstrap_key=bootstrap_key,
                ),
            )
        elif args.command == "inspect":
            report = inspect(args.path, bootstrap_key=bootstrap_key)
        elif args.command == "rotate":
            if not args.new_key_id or args.expected_generation is None:
                parser.error("rotate requires --new-key-id and --expected-generation")
            report = _audited_mutation(
                operation="rotate", path=args.path,
                expected_generation=args.expected_generation,
                change_ticket=args.change_ticket, bootstrap_key=bootstrap_key,
                callback=lambda: rotate(
                    args.path, new_key_id=args.new_key_id,
                    expected_generation=args.expected_generation,
                    bootstrap_key=bootstrap_key,
                ),
            )
        elif args.command == "rotate-bootstrap":
            if args.expected_generation is None:
                parser.error("rotate-bootstrap requires --expected-generation")
            new_bootstrap_key = bootstrap_key_from_environment(
                "ICODER_SOFT_HSM_NEW_BOOTSTRAP_KEY"
            )
            try:
                report = _audited_mutation(
                    operation="rotate-bootstrap", path=args.path,
                    expected_generation=args.expected_generation,
                    change_ticket=args.change_ticket, bootstrap_key=bootstrap_key,
                    additional_secret_key=new_bootstrap_key,
                    callback=lambda: rotate_bootstrap(
                        args.path, expected_generation=args.expected_generation,
                        bootstrap_key=bootstrap_key,
                        new_bootstrap_key=new_bootstrap_key,
                    ),
                )
            finally:
                _zeroize(new_bootstrap_key)
        else:
            if not args.key_id or not args.state or args.expected_generation is None:
                parser.error("set-state requires --key-id, --state and --expected-generation")
            report = _audited_mutation(
                operation="set-state", path=args.path,
                expected_generation=args.expected_generation,
                change_ticket=args.change_ticket, bootstrap_key=bootstrap_key,
                callback=lambda: set_state(
                    args.path, key_id=args.key_id, state=args.state,
                    expected_generation=args.expected_generation,
                    bootstrap_key=bootstrap_key, authorization=args.authorization,
                ),
            )
    finally:
        _zeroize(bootstrap_key)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
