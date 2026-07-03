"""Optional real coding-asset loader — the read-only ICD-10-CN (37,897) + ICD-9-CM-3
(13,617) national catalogs at ``E:\\iCoDerA\\DataAsset``.

Enabled by the ``ICODER_ICD_CATALOG_DIR`` env var. When set, ``catalog.py`` overlays the
curated sample *on top of* the real base (``overlay`` below) so the demonstrable codes keep
their high-risk routing / instructional notes / differentiation, while membership (R003),
search, and verify gain the full national breadth.

Default-off: with the env unset the slice runs on the 13-code sample exactly as before, so
the test suite stays offline + deterministic and never depends on the asset dir existing.
This module is pure (every function takes/derives its dir) and read-only — it never writes
to the asset dir.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ICD10CN = "ICD-10-CN"
ICD9CM3 = "ICD-9-CM-3"

_ICD10CN_FILE = "icd10cn_code_catalog.json"
_ICD9CM3_FILE = "icd9cm3_code_catalog.json"

ENV_VAR = "ICODER_ICD_CATALOG_DIR"


def asset_dir() -> str | None:
    """The configured real-catalog directory, or None when the slice runs on the sample."""
    return os.environ.get(ENV_VAR)


def available(dir_: str | None = None) -> bool:
    """True only when both national catalog files are present under ``dir_``."""
    dir_ = dir_ or asset_dir()
    if not dir_:
        return False
    p = Path(dir_)
    return (p / _ICD10CN_FILE).is_file() and (p / _ICD9CM3_FILE).is_file()


def _entry(rec: dict, system: str, code_type: str) -> dict:
    """Shape one real catalog record into the curated-sample entry contract.

    The national catalog has no instructional notes / guideline / differentiation /
    high_risk — those stay the curated overlay's job; here we fill display + synonyms +
    system + code_type so search / verify / membership work over the full code space.
    """
    name = rec.get("name_cn") or rec.get("name_en") or rec["code"]
    return {
        "display": name,
        "system": system,
        "code_type": code_type,
        "synonyms": list(rec.get("synonyms_cn") or []),
        "notes": [],
        "guideline": "",
        "parent": rec.get("category_code"),
        "siblings": [],
        "children": [],
        "high_risk": False,
        "differentiation": [],
    }


def load(dir_: str | None = None) -> dict[str, dict]:
    """Return ``{code -> sample-shaped entry}`` for the real national catalogs.

    Pure function of ``dir_`` (falls back to the env var). Returns ``{}`` when no dir is
    configured so the caller can cheaply no-op. ICD-9-CM-3 codes are tagged ``procedure``;
    ICD-10-CN codes ``diagnosis``.
    """
    dir_ = dir_ or asset_dir()
    if not dir_:
        return {}
    p = Path(dir_)
    out: dict[str, dict] = {}
    with open(p / _ICD10CN_FILE, encoding="utf-8") as f:
        for rec in json.load(f)["codes"]:
            out[rec["code"]] = _entry(rec, ICD10CN, "diagnosis")
    with open(p / _ICD9CM3_FILE, encoding="utf-8") as f:
        for rec in json.load(f)["codes"]:
            out[rec["code"]] = _entry(rec, ICD9CM3, "procedure")
    return out


def overlay(real: dict[str, dict], curated: dict[str, dict]) -> dict[str, dict]:
    """Merge the curated sample *over* the real base — curated entries win on conflict.

    This is the one load-bearing merge in Phase 3: the curated codes carry the high-risk
    flags, instructional notes, and differentiation hints the demo relies on, so they must
    take precedence over the (flag-less) national records for the same code.
    """
    merged = dict(real)
    merged.update(curated)
    return merged
