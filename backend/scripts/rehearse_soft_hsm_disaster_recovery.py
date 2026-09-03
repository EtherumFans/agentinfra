"""Run a self-contained software-HSM disaster-recovery rehearsal.

The drill uses synthetic PHI and one-time keys in a temporary directory.  It
proves fail-closed behavior for a missing key store, missing bootstrap key,
generation rollback, and bootstrap-key rotation without database DEK rewrap.
Only metadata and pass/fail evidence are returned.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.phi_encryption import decrypt_phi, encrypt_phi  # noqa: E402
from app.services.soft_hsm import SoftwareHSMKeyring  # noqa: E402
from app.services.soft_hsm_ops_audit import verify_audit_file  # noqa: E402
from scripts.manage_soft_hsm_keystore import (  # noqa: E402
    _audited_mutation,
    create,
    inspect,
    rotate,
    rotate_bootstrap,
)


_ENV_KEYS = (
    "ICODER_DEPLOYMENT_MODE",
    "ICODER_PHI_KEY_PROVIDER",
    "ICODER_SOFT_HSM_KEYSTORE_PATH",
    "ICODER_SOFT_HSM_BOOTSTRAP_KEY",
    "ICODER_SOFT_HSM_MIN_GENERATION",
    "ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE",
    "ICODER_SOFT_HSM_OPS_AUDIT_PATH",
    "ICODER_SOFT_HSM_OPS_AUDIT_KEY",
    "ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID",
    "ICODER_SOFT_HSM_OPS_AUDIT_KEYS",
    "ICODER_SOFT_HSM_OPS_AUDIT_MIN_SEQUENCE",
    "ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED",
)


def _encoded(value: bytes | bytearray) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _expect_failure(callback, fragment: str) -> str:
    try:
        callback()
    except RuntimeError as exc:
        if fragment not in str(exc):
            raise AssertionError(f"unexpected fail-closed reason: {type(exc).__name__}") from exc
        return "passed"
    raise AssertionError("disaster scenario did not fail closed")


def run() -> dict:
    saved_environment = {key: os.environ.get(key) for key in _ENV_KEYS}
    old_bootstrap = bytearray(os.urandom(32))
    new_bootstrap = bytearray(os.urandom(32))
    audit_key = bytearray(os.urandom(32))
    try:
        with tempfile.TemporaryDirectory(prefix="icoder-soft-hsm-dr-") as directory:
            root = Path(directory).resolve()
            key_store = root / "software-hsm.keys"
            audit_path = root / "software-hsm-ops-audit.jsonl"
            os.environ.update({
                "ICODER_DEPLOYMENT_MODE": "local",
                "ICODER_PHI_KEY_PROVIDER": "software_hsm",
                "ICODER_SOFT_HSM_KEYSTORE_PATH": str(key_store),
                "ICODER_SOFT_HSM_BOOTSTRAP_KEY": _encoded(old_bootstrap),
                "ICODER_SOFT_HSM_MIN_GENERATION": "1",
                "ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE": "true",
                "ICODER_SOFT_HSM_OPS_AUDIT_PATH": str(audit_path),
                "ICODER_SOFT_HSM_OPS_AUDIT_KEY": _encoded(audit_key),
                "ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID": "drill-audit-v1",
                "ICODER_SOFT_HSM_OPS_AUDIT_KEYS": json.dumps({
                    "drill-audit-v1": _encoded(audit_key),
                }, separators=(",", ":")),
                "ICODER_SOFT_HSM_OPS_AUDIT_MIN_SEQUENCE": "0",
                "ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED": "false",
            })
            created = _audited_mutation(
                operation="create", path=key_store, expected_generation=0,
                change_ticket="DRILL-CREATE", bootstrap_key=old_bootstrap,
                callback=lambda: create(
                    key_store, key_id="drill-kek-v1", bootstrap_key=old_bootstrap,
                ),
            )
            generation_one = key_store.read_bytes()
            synthetic_envelope = encrypt_phi("SYNTHETIC-DR-PHI-NOT-A-PATIENT")
            if not synthetic_envelope:
                raise AssertionError("synthetic PHI encryption failed")

            rotated = _audited_mutation(
                operation="rotate", path=key_store, expected_generation=1,
                change_ticket="DRILL-KEK-ROTATE", bootstrap_key=old_bootstrap,
                callback=lambda: rotate(
                    key_store, new_key_id="drill-kek-v2", expected_generation=1,
                    bootstrap_key=old_bootstrap,
                ),
            )
            generation_two = key_store.read_bytes()
            os.environ["ICODER_SOFT_HSM_MIN_GENERATION"] = "2"

            missing_copy = root / "software-hsm.missing"
            os.replace(key_store, missing_copy)
            missing_store = _expect_failure(
                SoftwareHSMKeyring.from_environment, "cannot be inspected",
            )
            os.replace(missing_copy, key_store)

            del os.environ["ICODER_SOFT_HSM_BOOTSTRAP_KEY"]
            missing_bootstrap = _expect_failure(
                SoftwareHSMKeyring.from_environment,
                "ICODER_SOFT_HSM_BOOTSTRAP_KEY is required",
            )
            os.environ["ICODER_SOFT_HSM_BOOTSTRAP_KEY"] = _encoded(old_bootstrap)

            key_store.write_bytes(generation_one)
            os.chmod(key_store, 0o600)
            generation_rollback = _expect_failure(
                SoftwareHSMKeyring.from_environment, "rollback detected",
            )
            key_store.write_bytes(generation_two)
            os.chmod(key_store, 0o600)

            bootstrap_rotated = _audited_mutation(
                operation="rotate-bootstrap", path=key_store, expected_generation=2,
                change_ticket="DRILL-BOOTSTRAP-ROTATE", bootstrap_key=old_bootstrap,
                additional_secret_key=new_bootstrap,
                callback=lambda: rotate_bootstrap(
                    key_store, expected_generation=2, bootstrap_key=old_bootstrap,
                    new_bootstrap_key=new_bootstrap,
                ),
            )
            old_bootstrap_rejected = _expect_failure(
                lambda: inspect(key_store, bootstrap_key=old_bootstrap),
                "authentication failed",
            )
            os.environ["ICODER_SOFT_HSM_BOOTSTRAP_KEY"] = _encoded(new_bootstrap)
            os.environ["ICODER_SOFT_HSM_MIN_GENERATION"] = "3"
            recovered_plaintext = decrypt_phi(synthetic_envelope)
            if recovered_plaintext != "SYNTHETIC-DR-PHI-NOT-A-PATIENT":
                raise AssertionError("PHI envelope did not survive bootstrap rotation")

            audit_report = verify_audit_file(
                audit_path, audit_key=audit_key, signing_key_id="drill-audit-v1",
                minimum_sequence=6,
            )
            tampered_path = root / "tampered-audit.jsonl"
            tampered = bytearray(audit_path.read_bytes())
            tampered[len(tampered) // 2] ^= 1
            tampered_path.write_bytes(tampered)
            os.chmod(tampered_path, 0o600)
            audit_tamper = _expect_failure(
                lambda: verify_audit_file(
                    tampered_path, audit_key=audit_key,
                    signing_key_id="drill-audit-v1",
                ),
                "audit",
            )
            tail_path = root / "truncated-audit.jsonl"
            tail_path.write_bytes(b"\n".join(audit_path.read_bytes().splitlines()[:-1]) + b"\n")
            os.chmod(tail_path, 0o600)
            audit_tail_rollback = _expect_failure(
                lambda: verify_audit_file(
                    tail_path, audit_key=audit_key,
                    signing_key_id="drill-audit-v1", minimum_sequence=6,
                ),
                "tail rollback",
            )

            return {
                "schema_version": "icoder.software-hsm-dr-rehearsal/v1",
                "status": "passed",
                "synthetic_data_only": True,
                "scenarios": {
                    "key_store_missing": missing_store,
                    "bootstrap_key_missing": missing_bootstrap,
                    "generation_floor_rollback": generation_rollback,
                    "bootstrap_key_rotation": "passed",
                    "old_bootstrap_rejected": old_bootstrap_rejected,
                    "phi_envelope_preserved": "passed",
                    "audit_tamper_detected": audit_tamper,
                    "audit_tail_rollback_detected": audit_tail_rollback,
                },
                "generations": {
                    "created": created["generation"],
                    "kek_rotated": rotated["generation"],
                    "bootstrap_rotated": bootstrap_rotated["generation"],
                },
                "final_key_states": bootstrap_rotated["key_states"],
                "audit": audit_report,
            }
    finally:
        for value in (old_bootstrap, new_bootstrap, audit_key):
            for index in range(len(value)):
                value[index] = 0
        for key, value in saved_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main() -> int:
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
