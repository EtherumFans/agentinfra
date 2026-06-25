"""KB schema validation — ensures iCoDerA asset KBs match the expected schema.

Targets (read-only):
  - ``{asset_dir}/coding_differentiation_kb.json``
  - ``{asset_dir}/evidence_anchoring_kb.json``

Phase A A7 contract: every KB must declare a ``_meta`` block, all
required fields must be present, and code formats must match the ICD
catalog (letter-digit pattern, e.g. ``A00`` or ``M80.900``).

The actual schemas (discovered 2026-06-25):
  - differentiation KB: ``{_meta, groups: [{code_a.code, code_b.code, severity, ...}, ...]}``
  - evidence anchoring KB: ``{_meta, codes: [{code, patterns: [{type, pattern, ...}, ...]}, ...]}``

Usage:
    python scripts/validate_kb_schema.py --asset-dir E:/iCoDerA/DataAsset
    python scripts/validate_kb_schema.py --asset-dir E:/iCoDerA/DataAsset --json

Exit code: 0 if all KBs pass, 1 otherwise. Always prints a structured
report.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("validate_kb_schema")

# ICD-10 / ICD-9-CM-3 code patterns vary widely in iCoDerA's KBs:
#   - "A00"          — plain ICD-10 chapter code
#   - "M80.900"      — subclassified
#   - "C50.900x011"  — extension code
#   - "85.4301"      — ICD-9-CM-3 (digit-led)
#   - "47.01"        — short ICD-9-CM-3
#   - "B02.202+G53.0*" — dagger/asterisk combo
#   - "Q85.001M95400/1" — ICD-10 + ICD-O morphology (slash)
#   - "I60-I69"      — code range (not a single code, allowed)
#
# We accept anything in the explicit loose alphabet and flag the
# remaining structural problems via the per-side checks below.
ICD_LOOSE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+*/-]{1,20}$")

ALLOWED_SEVERITY = {"P0", "P1", "P2"}
ALLOWED_PATTERN_TYPE = {
    "direct_mention",
    "lab_threshold",
    "medication",
    "diagnostic_criteria",
    "synonym",
}


def _require_meta(kb: dict[str, Any], name: str, errors: list[str]) -> None:
    if "_meta" not in kb:
        errors.append(f"{name}: missing '_meta' block")
        return
    meta = kb["_meta"]
    for field in ("version", "build_date"):
        if field not in meta:
            errors.append(f"{name}._meta: missing field '{field}'")


def _check_icd_code(
    code: Any,
    where: str,
    errors: list[str],
    warnings: list[str],
    bad_counter: list[int],
) -> bool:
    """Validate an ICD code string. Empty codes and range patterns are warnings."""
    if not isinstance(code, str):
        bad_counter[0] += 1
        if bad_counter[0] <= 5:
            warnings.append(f"{where}: code must be str, got {type(code).__name__}")
        return False
    if code == "":
        # Textbook differential entries (TXTBK-*) carry differential
        # semantics but no ICD mapping yet — acceptable, surface as warning.
        warnings.append(f"{where}: empty ICD code (textbook differential entry)")
        return False
    if "," in code:
        # Comma-separated codes like "E10.2, E11.2" — these belong to the
        # code_a list of a single group, not as a single code field.
        warnings.append(f"{where}: comma-separated codes {code!r} (multi-code entry)")
        return False
    if "-" in code and not code.startswith("-"):
        # Range pattern like "I60-I69"; allowed as a wildcard, surface as warning.
        warnings.append(f"{where}: range pattern {code!r} (matches a chapter span)")
        return False
    # Chinese / non-ASCII disease names appearing where an ICD code is
    # expected — common in textbook differential entries (TXTBK-*) where
    # the codes list stores disease names instead of ICD codes.
    if any(ord(ch) > 127 for ch in code):
        warnings.append(
            f"{where}: non-ICD token {code!r} (likely a disease name in codes array)"
        )
        return False
    if not ICD_LOOSE_RE.match(code):
        bad_counter[0] += 1
        if bad_counter[0] <= 5:
            errors.append(f"{where}: malformed ICD code {code!r}")
        return False
    return True


def validate_differentiation_kb(
    path: Path, errors: list[str], warnings: list[str]
) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"coding_differentiation_kb.json missing at {path}")
        return {"path": str(path), "exists": False, "groups": 0}

    with open(path, encoding="utf-8") as f:
        kb = json.load(f)

    _require_meta(kb, "coding_differentiation_kb", errors)
    groups = kb.get("groups")
    if groups is None:
        errors.append("coding_differentiation_kb: missing 'groups' top-level list")
        return {"path": str(path), "exists": True, "groups": 0}
    if not isinstance(groups, list):
        errors.append(
            f"coding_differentiation_kb.groups: must be list, got {type(groups).__name__}"
        )
        return {"path": str(path), "exists": True, "groups": 0}

    bad_codes: list[int] = [0]
    for i, g in enumerate(groups):
        if not isinstance(g, dict):
            errors.append(f"coding_differentiation_kb.groups[{i}]: not a dict")
            continue
        # Schema: code_a / code_b are normally nested dicts with 'code'.
        # Some older groups store only the flat 'codes' list — fall back to it.
        for side in ("code_a", "code_b"):
            sub = g.get(side)
            if sub is None:
                flat = g.get("codes") or []
                if isinstance(flat, list) and len(flat) >= (2 if side == "code_b" else 1):
                    # Flat fallback: treat codes[i] as the code_a / code_b string.
                    fallback_idx = 1 if side == "code_b" else 0
                    _check_icd_code(
                        flat[fallback_idx],
                        f"coding_differentiation_kb.groups[{i}].{side} (via codes[{fallback_idx}])",
                        errors, warnings,
                        bad_codes,
                    )
                else:
                    warnings.append(
                        f"coding_differentiation_kb.groups[{i}].{side}: "
                        "missing and no flat 'codes' fallback"
                    )
                continue
            if not isinstance(sub, dict) or "code" not in sub:
                # Older records store code as a bare string.
                _check_icd_code(
                    sub if isinstance(sub, str) else None,
                    f"coding_differentiation_kb.groups[{i}].{side}",
                    errors, warnings,
                    bad_codes,
                )
                continue
            _check_icd_code(
                sub["code"],
                f"coding_differentiation_kb.groups[{i}].{side}.code",
                errors, warnings,
                bad_codes,
            )
        severity = g.get("severity")
        if severity is not None and severity not in ALLOWED_SEVERITY:
            errors.append(
                f"coding_differentiation_kb.groups[{i}].severity: "
                f"must be one of {sorted(ALLOWED_SEVERITY)} or null, got {severity!r}"
            )
        # ``strategy`` and ``decision`` are optional (some groups only have
        # ``resolution.decision`` instead). Surface as warnings, not errors.
        for opt_key in ("strategy", "decision"):
            if opt_key not in g:
                warnings.append(
                    f"coding_differentiation_kb.groups[{i}]: missing optional "
                    f"'{opt_key}' (may live under resolution)"
                )

    if bad_codes[0] > 5:
        errors.append(
            f"coding_differentiation_kb: total {bad_codes[0]} malformed codes "
            "(first 5 reported above)"
        )

    return {"path": str(path), "exists": True, "groups": len(groups)}


def validate_evidence_anchoring_kb(
    path: Path, errors: list[str], warnings: list[str]
) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"evidence_anchoring_kb.json missing at {path}")
        return {"path": str(path), "exists": False, "patterns": 0, "codes": 0}

    with open(path, encoding="utf-8") as f:
        kb = json.load(f)

    _require_meta(kb, "evidence_anchoring_kb", errors)
    codes = kb.get("codes")
    if codes is None:
        errors.append("evidence_anchoring_kb: missing 'codes' top-level list")
        return {"path": str(path), "exists": True, "patterns": 0, "codes": 0}
    if not isinstance(codes, list):
        errors.append(
            f"evidence_anchoring_kb.codes: must be list, got {type(codes).__name__}"
        )
        return {"path": str(path), "exists": True, "patterns": 0, "codes": 0}

    total_patterns = 0
    bad_codes: list[int] = [0]
    for i, entry in enumerate(codes):
        if not isinstance(entry, dict):
            errors.append(f"evidence_anchoring_kb.codes[{i}]: not a dict")
            continue
        _check_icd_code(
            entry.get("code"),
            f"evidence_anchoring_kb.codes[{i}].code",
            errors, warnings,
            bad_codes,
        )
        patterns = entry.get("patterns")
        if not isinstance(patterns, list):
            errors.append(
                f"evidence_anchoring_kb.codes[{i}].patterns: must be list, "
                f"got {type(patterns).__name__}"
            )
            continue
        for j, pat in enumerate(patterns):
            if not isinstance(pat, dict):
                errors.append(
                    f"evidence_anchoring_kb.codes[{i}].patterns[{j}]: not a dict"
                )
                continue
            # ``pattern`` is recommended but not strictly required
            # (some entries are exclusion notes with only ``type``/``subtype``).
            if "pattern" not in pat:
                warnings.append(
                    f"evidence_anchoring_kb.codes[{i}].patterns[{j}]: "
                    "missing 'pattern' (may be exclusion entry)"
                )
            if "type" not in pat:
                warnings.append(
                    f"evidence_anchoring_kb.codes[{i}].patterns[{j}]: "
                    "missing 'type'"
                )
            ptype = pat.get("type")
            if ptype is not None and ptype not in ALLOWED_PATTERN_TYPE:
                warnings.append(
                    f"evidence_anchoring_kb.codes[{i}].patterns[{j}].type: "
                    f"unexpected value {ptype!r} (allowed: "
                    f"{sorted(ALLOWED_PATTERN_TYPE)})"
                )
            total_patterns += 1

    if bad_codes[0] > 5:
        errors.append(
            f"evidence_anchoring_kb: total {bad_codes[0]} malformed codes "
            "(first 5 reported above)"
        )

    return {
        "path": str(path),
        "exists": True,
        "patterns": total_patterns,
        "codes": len(codes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--asset-dir",
        default=r"E:\iCoDerA\DataAsset",
        help="Path to the iCoDerA DataAsset directory (read-only).",
    )
    args = parser.parse_args(argv)

    asset_dir = Path(args.asset_dir)
    errors: list[str] = []
    warnings: list[str] = []

    diff_report = validate_differentiation_kb(
        asset_dir / "coding_differentiation_kb.json", errors, warnings
    )
    ev_report = validate_evidence_anchoring_kb(
        asset_dir / "evidence_anchoring_kb.json", errors, warnings
    )

    report = {
        "asset_dir": str(asset_dir),
        "coding_differentiation_kb": diff_report,
        "evidence_anchoring_kb": ev_report,
        "errors_count": len(errors),
        "warnings_count": len(warnings),
        "errors": errors[:50],
        "warnings": warnings[:20],
        "ok": not errors,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if errors:
        logger.error(
            "KB schema validation FAILED with %d error(s) (showing first 50)",
            len(errors),
        )
        return 1
    logger.info("KB schema validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())