"""Integrity-checked, image-owned Chinese clinical code catalogs.

The runtime must not depend on the sibling iCoDerA checkout.  These immutable
assets are copied into the backend Docker build context and verified before any
catalog content is exposed.  Missing, truncated, substituted, or malformed
assets fail application startup instead of silently falling back to sample
codes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CATALOG_ASSET_ROOT = Path(__file__).resolve().parent / "assets"
CATALOG_MANIFEST_PATH = CATALOG_ASSET_ROOT / "catalog_manifest.json"
CATALOG_SCHEMA_VERSION = "icoder.code-catalog-assets/v1"
CATALOG_RELEASE = "icoder-cn-runtime-2026-08-27.2"

# This code-owned trust anchor prevents an edited manifest from authorizing an
# edited catalog.  Updating a catalog is therefore an explicit reviewed code
# change, not a runtime filesystem substitution.
TRUSTED_CATALOG_FILES: dict[str, dict[str, int | str]] = {
    "icd10_opendrg_v1.json": {
        "size_bytes": 11_084_058,
        "sha256": "4b99940b192794c5807270d37788d23bec294aca93a3f76456651760f60a42ec",
        "record_count": 33_304,
        "valid_record_count": 33_304,
    },
    "icd10_cn_standard_names.json": {
        "size_bytes": 5_800_594,
        "sha256": "82a2e34db9f2199c1e993a48767a638cac1c5bd7fc06ba09e37163270f0aef43",
        "record_count": 37_897,
        "valid_record_count": 37_897,
        "merged_unique_code_count": 39_756,
    },
    "procedure_icd9cm3_knowledge_v8_with_opendrg.json": {
        "size_bytes": 4_499_282,
        "sha256": "408cda10f725d12326f1d810bfad7b32fe9a5d1f8c028d322bc20f47f5502f41",
        "record_count": 17_436,
        "valid_record_count": 16_561,
        "unique_code_count": 14_353,
    },
    "surgery_to_drg_mapping.json": {
        "size_bytes": 11_932_815,
        "sha256": "82a50967cebb1d1ecf01ac55d96169bda479715d6adc4314ed8be66be20c3923",
        "record_count": 23_165,
        "valid_record_count": 23_165,
    },
    "icd9cm3_code_catalog.json": {
        "size_bytes": 5_481_018,
        "sha256": "088ebeddc27e24ada0a1da4f46b1e33c8e1db3fe9c3bf8a7266709f5dde94590",
        "record_count": 13_617,
        "valid_record_count": 13_617,
        "merged_unique_code_count": 28_394,
    },
}


class CatalogIntegrityError(RuntimeError):
    """Raised when governed code catalog assets cannot be trusted."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_verified_assets(asset_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = asset_root / "catalog_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogIntegrityError("Code catalog manifest is missing or invalid") from exc

    declared = manifest.get("files")
    if (
        manifest.get("schema_version") != CATALOG_SCHEMA_VERSION
        or manifest.get("catalog_release") != CATALOG_RELEASE
        or not isinstance(declared, dict)
        or set(declared) != set(TRUSTED_CATALOG_FILES)
    ):
        raise CatalogIntegrityError("Code catalog manifest does not match the trusted release")

    loaded: dict[str, Any] = {}
    for filename, expected in TRUSTED_CATALOG_FILES.items():
        metadata = declared.get(filename)
        path = asset_root / filename
        if not isinstance(metadata, dict) or any(
            metadata.get(field) != value for field, value in expected.items()
        ):
            raise CatalogIntegrityError(f"Code catalog metadata mismatch: {filename}")
        try:
            if path.stat().st_size != expected["size_bytes"]:
                raise CatalogIntegrityError(f"Code catalog size mismatch: {filename}")
            if _sha256(path) != expected["sha256"]:
                raise CatalogIntegrityError(f"Code catalog digest mismatch: {filename}")
            loaded[filename] = json.loads(path.read_text(encoding="utf-8"))
        except CatalogIntegrityError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CatalogIntegrityError(f"Code catalog is missing or invalid: {filename}") from exc
    return manifest, loaded


ICD10_CN_CHAPTERS = {
    "A00-B99": "某些传染病和寄生虫病",
    "C00-D48": "肿瘤", "D50-D89": "血液及造血器官疾病",
    "E00-E90": "内分泌、营养和代谢疾病", "F00-F99": "精神和行为障碍",
    "G00-G99": "神经系统疾病", "H00-H59": "眼和附器疾病",
    "H60-H95": "耳和乳突疾病", "I00-I99": "循环系统疾病",
    "J00-J99": "呼吸系统疾病", "K00-K93": "消化系统疾病",
    "L00-L99": "皮肤和皮下组织疾病",
    "M00-M99": "肌肉骨骼系统和结缔组织疾病",
    "N00-N99": "泌尿生殖系统疾病", "O00-O99": "妊娠、分娩和产褥期",
    "P00-P96": "起源于围生期的某些情况",
    "Q00-Q99": "先天性畸形、变形和染色体异常",
    "R00-R99": "症状、体征和临床与实验室异常所见",
    "S00-T98": "损伤、中毒和外因的某些其他后果",
    "V01-Y98": "疾病和死亡的外因",
    "Z00-Z99": "影响健康状态和与保健机构接触的因素",
    "U00-U99": "用于特殊目的的编码",
}

def load_catalogs(
    asset_root: Path = CATALOG_ASSET_ROOT,
) -> tuple[
    list[tuple[str, str, str]],
    list[tuple[str, str, str]],
    dict[str, Any],
]:
    """Load one trusted catalog release or fail closed."""

    manifest, assets = _load_verified_assets(asset_root)
    diagnosis_rows = assets["icd10_opendrg_v1.json"]
    diagnosis_standard_names = assets["icd10_cn_standard_names.json"]
    procedure_name_rows = assets[
        "procedure_icd9cm3_knowledge_v8_with_opendrg.json"
    ]
    procedure_mapping = assets["surgery_to_drg_mapping.json"]
    procedure_catalog = assets["icd9cm3_code_catalog.json"]
    mapping_rows = (
        procedure_mapping.get("surgery_to_drg")
        if isinstance(procedure_mapping, dict)
        else None
    )
    if (
        not isinstance(diagnosis_rows, list)
        or len(diagnosis_rows) != 33_304
        or not isinstance(diagnosis_standard_names, dict)
        or not isinstance(diagnosis_standard_names.get("code_names"), dict)
        or len(diagnosis_standard_names["code_names"]) != 37_897
        or not isinstance(procedure_name_rows, list)
        or len(procedure_name_rows) != 17_436
        or not isinstance(mapping_rows, list)
        or len(mapping_rows) != 23_165
        or not isinstance(procedure_catalog, dict)
        or not isinstance(procedure_catalog.get("codes"), list)
        or len(procedure_catalog["codes"]) != 13_617
    ):
        raise CatalogIntegrityError(
            "Code catalog record counts do not match the trusted release"
        )

    diagnosis_codes = [
        (
            str(item.get("icd10_code") or ""),
            str(item.get("disease_name") or ""),
            str(item.get("chapter_name") or ""),
        )
        for item in diagnosis_rows
        if isinstance(item, dict)
        and item.get("icd10_code")
        and item.get("disease_name")
    ]
    diagnosis_code_set = {code for code, _name, _chapter in diagnosis_codes}
    diagnosis_codes.extend(
        (str(code).strip(), str(name).strip(), "")
        for code, name in diagnosis_standard_names["code_names"].items()
        if str(code).strip()
        and str(name).strip()
        and str(code).strip() not in diagnosis_code_set
    )
    valid_procedure_name_rows = [
        item
        for item in procedure_name_rows
        if isinstance(item, dict)
        and str(item.get("icd9cm3_code") or "").strip()
        and str(item.get("procedure_name") or "").strip()
    ]
    procedure_names = {
        str(item.get("icd9cm3_code") or "").strip(): str(
            item.get("procedure_name") or ""
        ).strip()
        for item in valid_procedure_name_rows
    }
    procedure_codes: list[tuple[str, str, str]] = []
    for item in mapping_rows:
        if not isinstance(item, dict):
            continue
        code = str(item.get("icd9cm3_code") or "").strip()
        if not code:
            continue
        drg_groups = item.get("drg_groups")
        first_drg = (
            str(drg_groups[0])
            if isinstance(drg_groups, list) and drg_groups
            else ""
        )
        procedure_codes.append((code, procedure_names.get(code, ""), first_drg))

    procedure_code_set = {code for code, _name, _drg in procedure_codes}
    procedure_codes.extend(
        (
            str(item.get("code") or "").strip(),
            str(item.get("name_cn") or item.get("name_en") or "").strip(),
            str(item.get("chapter_name") or "").strip(),
        )
        for item in procedure_catalog["codes"]
        if isinstance(item, dict)
        and str(item.get("code") or "").strip()
        and str(item.get("name_cn") or item.get("name_en") or "").strip()
        and str(item.get("code") or "").strip() not in procedure_code_set
    )

    if (
        len(diagnosis_codes) != 39_756
        or len(valid_procedure_name_rows) != 16_561
        or len(procedure_names) != 14_353
        or len(procedure_codes) != 28_394
    ):
        raise CatalogIntegrityError(
            "Code catalog valid-record counts do not match the trusted release"
        )

    status = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_release": manifest["catalog_release"],
        "integrity_verified": True,
        "diagnosis_count": len(diagnosis_codes),
        "procedure_count": len(procedure_codes),
        "diagnosis_supplement_added": 6_452,
        "procedure_supplement_added": 5_229,
    }
    logger.info(
        "Loaded integrity-verified catalog release %s (%d diagnoses, %d procedures)",
        status["catalog_release"],
        status["diagnosis_count"],
        status["procedure_count"],
    )
    return diagnosis_codes, procedure_codes, status


ICD10_CN_CODES, ICD9_CM3_CODES, CODE_CATALOG_STATUS = load_catalogs()
