"""China clinical asset authority, licence, integrity and rollout gates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.clinical_asset_governance import (
    ClinicalAssetGovernanceError,
    DRG_RISK_RULE_PACK_ID,
    assert_asset_use_allowed,
    load_manifest,
    public_governance,
    select_asset,
    verify_asset_integrity,
)


def _write_manifest(path: Path, assets: list[dict]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "icoder.cn-clinical-assets/v1",
                "manifest_version": "test",
                "assets": assets,
            }
        ),
        encoding="utf-8",
    )
    return path


def _asset(*, version: str = "1", sha256: str = "0" * 64) -> dict:
    return {
        "asset_id": "test.asset",
        "version": version,
        "asset_type": "rule_pack",
        "jurisdiction": "CN_GENERIC_DEVELOPMENT",
        "authority_status": "experimental_unverified",
        "license_status": "external_review_required",
        "effective_from": None,
        "effective_to": None,
        "billing_authoritative": False,
        "manual_review_required": True,
        "use_restriction": "development_only",
        "artifacts": [
            {
                "location_kind": "repository",
                "path": "sample.bin",
                "size_bytes": 1,
                "sha256": sha256,
            }
        ],
    }


def test_repository_drg_rule_pack_integrity_is_pinned():
    manifest = load_manifest()
    assert manifest["schema_version"] == "icoder.cn-clinical-assets/v1"
    asset = select_asset(DRG_RISK_RULE_PACK_ID)
    verify_asset_integrity(asset)
    public = public_governance(asset)
    assert public["authority_status"] == "experimental_unverified"
    assert public["license_status"] == "external_review_required"
    assert public["billing_authoritative"] is False
    assert public["manual_review_required"] is True
    assert "directory" not in repr(public).casefold()


def test_agent_pack_exposes_non_authoritative_governance_constants():
    pack_path = Path(__file__).resolve().parents[2] / "official_agents" / "drg-analyzer" / "agent_pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    schemas = pack["output_contract"]["field_schemas"]
    governance = schemas["governance"]["properties"]
    assert governance["authority_status"]["const"] == "experimental_unverified"
    assert schemas["billing_authoritative"]["const"] is False
    assert governance["rule_pack_id"]["const"] == DRG_RISK_RULE_PACK_ID
    assert governance["jurisdiction"]["const"] == "CN_GENERIC_DEVELOPMENT"
    example = pack["example_outputs"][0]
    assert example["governance"]["authority_status"] == "experimental_unverified"
    assert example["manual_review_required"] is True
    assert example["billing_authoritative"] is False
    assert (
        "不得输出官方分组、权重、CMI、DIP 分值、支付或结算金额"
        in pack["system_prompt"]
    )


def test_development_risk_review_is_allowed_but_not_authoritative():
    asset = assert_asset_use_allowed(
        DRG_RISK_RULE_PACK_ID,
        deployment_mode="development",
        usage="risk_review",
    )
    assert asset["billing_authoritative"] is False


@pytest.mark.parametrize("usage", ["billing", "settlement", "production_grouping"])
def test_payment_and_grouping_use_fail_closed_even_in_development(usage):
    with pytest.raises(ClinicalAssetGovernanceError, match="not authorized"):
        assert_asset_use_allowed(
            DRG_RISK_RULE_PACK_ID,
            deployment_mode="development",
            usage=usage,
        )


def test_cloud_use_of_unverified_asset_fails_closed():
    with pytest.raises(ClinicalAssetGovernanceError, match="not verified"):
        assert_asset_use_allowed(
            DRG_RISK_RULE_PACK_ID,
            deployment_mode="cloud",
            usage="risk_review",
        )


def test_duplicate_asset_versions_are_rejected(tmp_path):
    manifest_path = _write_manifest(tmp_path / "manifest.json", [_asset(), _asset()])
    with pytest.raises(ClinicalAssetGovernanceError, match="duplicate"):
        load_manifest(manifest_path)


def test_rollback_requires_explicit_version_selection(tmp_path):
    manifest_path = _write_manifest(
        tmp_path / "manifest.json",
        [_asset(version="1"), _asset(version="2")],
    )
    with pytest.raises(ClinicalAssetGovernanceError, match="explicitly"):
        select_asset("test.asset", manifest_path=manifest_path)
    assert select_asset(
        "test.asset", version="1", manifest_path=manifest_path
    )["version"] == "1"


def test_checksum_mismatch_is_rejected(tmp_path):
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"x")
    asset = _asset(sha256="0" * 64)
    with pytest.raises(ClinicalAssetGovernanceError, match="checksum mismatch"):
        verify_asset_integrity(asset, backend_root=tmp_path)


def test_repository_path_escape_is_rejected(tmp_path):
    outside = tmp_path.parent / "outside.bin"
    outside.write_bytes(b"x")
    asset = _asset()
    asset["artifacts"][0]["path"] = "../outside.bin"
    try:
        with pytest.raises(ClinicalAssetGovernanceError, match="escapes"):
            verify_asset_integrity(asset, backend_root=tmp_path)
    finally:
        outside.unlink(missing_ok=True)
