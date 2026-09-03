"""Governance gate for China clinical dictionaries and rule packs.

The manifest records what the repository actually knows about an asset.  It
does not turn an unverified heuristic or externally supplied dictionary into
an authoritative clinical or settlement source.  Cloud use fails closed until
authority, licence, effective-date and integrity gates are explicitly met.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA = "icoder.cn-clinical-assets/v1"
DRG_RISK_RULE_PACK_ID = "cn.drg_dip.risk_heuristics"
DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "china_clinical_assets_manifest.json"
)

_AUTHORITY_STATUSES = {
    "authoritative_verified",
    "experimental_unverified",
    "source_unverified",
}
_LICENSE_STATUSES = {"verified", "external_review_required", "unknown"}


class ClinicalAssetGovernanceError(RuntimeError):
    """Raised when a clinical asset cannot be used under the requested gate."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: str | Path | None = None) -> dict[str, Any]:
    """Load and structurally validate the immutable asset manifest."""
    manifest_path = Path(path) if path is not None else DEFAULT_MANIFEST_PATH
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClinicalAssetGovernanceError(
            f"clinical asset manifest unavailable or invalid: {manifest_path}"
        ) from exc

    if payload.get("schema_version") != MANIFEST_SCHEMA:
        raise ClinicalAssetGovernanceError("unsupported clinical asset manifest schema")
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ClinicalAssetGovernanceError("clinical asset manifest has no assets")

    seen: set[tuple[str, str]] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ClinicalAssetGovernanceError("clinical asset entry must be an object")
        required = {
            "asset_id",
            "version",
            "asset_type",
            "jurisdiction",
            "authority_status",
            "license_status",
            "billing_authoritative",
            "manual_review_required",
            "artifacts",
        }
        missing = sorted(required - set(asset))
        if missing:
            raise ClinicalAssetGovernanceError(
                f"clinical asset entry missing fields: {', '.join(missing)}"
            )
        key = (str(asset["asset_id"]), str(asset["version"]))
        if key in seen:
            raise ClinicalAssetGovernanceError(
                f"duplicate clinical asset version: {key[0]}@{key[1]}"
            )
        seen.add(key)
        if asset["authority_status"] not in _AUTHORITY_STATUSES:
            raise ClinicalAssetGovernanceError(
                f"invalid authority_status for {key[0]}@{key[1]}"
            )
        if asset["license_status"] not in _LICENSE_STATUSES:
            raise ClinicalAssetGovernanceError(
                f"invalid license_status for {key[0]}@{key[1]}"
            )
        if not isinstance(asset["billing_authoritative"], bool):
            raise ClinicalAssetGovernanceError("billing_authoritative must be boolean")
        if not isinstance(asset["manual_review_required"], bool):
            raise ClinicalAssetGovernanceError("manual_review_required must be boolean")
        if not isinstance(asset["artifacts"], list) or not asset["artifacts"]:
            raise ClinicalAssetGovernanceError(
                f"clinical asset {key[0]}@{key[1]} has no integrity artifacts"
            )
    return payload


def select_asset(
    asset_id: str,
    *,
    version: str | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Select one exact immutable asset version; never silently choose latest."""
    manifest = load_manifest(manifest_path)
    matches = [
        asset
        for asset in manifest["assets"]
        if asset["asset_id"] == asset_id
        and (version is None or asset["version"] == version)
    ]
    if not matches:
        suffix = f"@{version}" if version else ""
        raise ClinicalAssetGovernanceError(f"clinical asset not declared: {asset_id}{suffix}")
    if len(matches) != 1:
        raise ClinicalAssetGovernanceError(
            f"asset version must be selected explicitly: {asset_id}"
        )
    return dict(matches[0])


def _resolve_artifact(artifact: dict[str, Any], backend_root: Path) -> Path:
    kind = artifact.get("location_kind")
    if kind == "repository":
        relative_path = artifact.get("path")
        if not isinstance(relative_path, str) or not relative_path:
            raise ClinicalAssetGovernanceError("repository artifact path is missing")
        candidate = (backend_root / relative_path).resolve()
        try:
            candidate.relative_to(backend_root.resolve())
        except ValueError as exc:
            raise ClinicalAssetGovernanceError(
                "repository artifact escapes backend root"
            ) from exc
        return candidate
    if kind == "external_env_directory":
        env_name = artifact.get("directory_env")
        filename = artifact.get("filename")
        if not isinstance(env_name, str) or not isinstance(filename, str):
            raise ClinicalAssetGovernanceError("external artifact locator is incomplete")
        directory = os.environ.get(env_name) or artifact.get("development_default_directory")
        if not isinstance(directory, str) or not directory:
            raise ClinicalAssetGovernanceError(
                f"external clinical asset directory is not configured: {env_name}"
            )
        return Path(directory) / filename
    raise ClinicalAssetGovernanceError(f"unsupported artifact location_kind: {kind!r}")


def verify_asset_integrity(
    asset: dict[str, Any],
    *,
    backend_root: str | Path | None = None,
) -> None:
    """Verify every declared file using a pinned SHA-256 digest and size."""
    root = Path(backend_root) if backend_root is not None else Path(__file__).resolve().parents[2]
    for artifact in asset["artifacts"]:
        if not isinstance(artifact, dict):
            raise ClinicalAssetGovernanceError("clinical asset artifact must be an object")
        expected_hash = str(artifact.get("sha256", "")).lower()
        expected_size = artifact.get("size_bytes")
        if len(expected_hash) != 64 or any(ch not in "0123456789abcdef" for ch in expected_hash):
            raise ClinicalAssetGovernanceError("clinical asset artifact has invalid SHA-256")
        if not isinstance(expected_size, int) or expected_size < 0:
            raise ClinicalAssetGovernanceError("clinical asset artifact has invalid size")
        path = _resolve_artifact(artifact, root)
        if not path.is_file():
            raise ClinicalAssetGovernanceError(f"clinical asset artifact missing: {path.name}")
        if path.stat().st_size != expected_size:
            raise ClinicalAssetGovernanceError(
                f"clinical asset artifact size mismatch: {path.name}"
            )
        if _sha256(path) != expected_hash:
            raise ClinicalAssetGovernanceError(
                f"clinical asset artifact checksum mismatch: {path.name}"
            )


def assert_asset_use_allowed(
    asset_id: str,
    *,
    version: str | None = None,
    deployment_mode: str,
    usage: str,
    manifest_path: str | Path | None = None,
    verify_integrity: bool = True,
) -> dict[str, Any]:
    """Return the asset only when integrity and deployment policy allow use.

    Development may use explicitly marked experimental assets for risk review.
    Billing/settlement use and every cloud use require independently verified
    authority, licence and effective dates.
    """
    asset = select_asset(asset_id, version=version, manifest_path=manifest_path)
    if verify_integrity:
        verify_asset_integrity(asset)

    authoritative = (
        asset["authority_status"] == "authoritative_verified"
        and asset["license_status"] == "verified"
        and bool(asset.get("effective_from"))
    )
    if usage in {"billing", "settlement", "production_grouping"} and (
        not authoritative or not asset["billing_authoritative"]
    ):
        raise ClinicalAssetGovernanceError(
            f"{asset_id}@{asset['version']} is not authorized for {usage}"
        )
    if deployment_mode.strip().casefold() == "cloud" and not authoritative:
        raise ClinicalAssetGovernanceError(
            f"{asset_id}@{asset['version']} is not verified for cloud clinical use"
        )
    return asset


def public_governance(asset: dict[str, Any]) -> dict[str, Any]:
    """Expose audit-safe governance metadata without local filesystem paths."""
    return {
        "asset_id": asset["asset_id"],
        "version": asset["version"],
        "asset_type": asset["asset_type"],
        "jurisdiction": asset["jurisdiction"],
        "authority_status": asset["authority_status"],
        "license_status": asset["license_status"],
        "effective_from": asset.get("effective_from"),
        "effective_to": asset.get("effective_to"),
        "billing_authoritative": asset["billing_authoritative"],
        "manual_review_required": asset["manual_review_required"],
        "use_restriction": asset.get("use_restriction", ""),
    }


def get_drg_risk_governance(*, deployment_mode: str) -> dict[str, Any]:
    asset = assert_asset_use_allowed(
        DRG_RISK_RULE_PACK_ID,
        deployment_mode=deployment_mode,
        usage="risk_review",
    )
    return public_governance(asset)


__all__ = [
    "ClinicalAssetGovernanceError",
    "DEFAULT_MANIFEST_PATH",
    "DRG_RISK_RULE_PACK_ID",
    "assert_asset_use_allowed",
    "get_drg_risk_governance",
    "load_manifest",
    "public_governance",
    "select_asset",
    "verify_asset_integrity",
]
