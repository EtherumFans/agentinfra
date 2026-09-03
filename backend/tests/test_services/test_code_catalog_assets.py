from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.code_dicts import icd_data


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_packaged_catalog_release_is_integrity_verified_and_complete() -> None:
    assert icd_data.CATALOG_ASSET_ROOT.is_relative_to(BACKEND_ROOT)
    assert icd_data.CODE_CATALOG_STATUS == {
        "schema_version": "icoder.code-catalog-assets/v1",
        "catalog_release": "icoder-cn-runtime-2026-08-27.2",
        "integrity_verified": True,
        "diagnosis_count": 39_756,
        "procedure_count": 28_394,
        "diagnosis_supplement_added": 6_452,
        "procedure_supplement_added": 5_229,
    }
    assert len(icd_data.ICD10_CN_CODES) == 39_756
    assert len(icd_data.ICD9_CM3_CODES) == 28_394


def test_catalog_loader_fails_closed_without_packaged_assets(tmp_path: Path) -> None:
    with pytest.raises(icd_data.CatalogIntegrityError, match="manifest"):
        icd_data.load_catalogs(tmp_path)


def test_catalog_loader_rejects_modified_release_manifest(tmp_path: Path) -> None:
    manifest = json.loads(icd_data.CATALOG_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["catalog_release"] = "unreviewed-replacement"
    (tmp_path / "catalog_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(icd_data.CatalogIntegrityError, match="trusted release"):
        icd_data.load_catalogs(tmp_path)


def test_backend_image_context_includes_catalog_assets() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (BACKEND_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "COPY --chown=icoder:icoder . ." in dockerfile
    assert "data/code_dicts" not in dockerignore
    assert "assets/" not in dockerignore
