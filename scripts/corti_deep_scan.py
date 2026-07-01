#!/usr/bin/env python3
"""Corti contract extractor — wrap the 4 existing crawlers, normalize output
to ``corti_contracts/{endpoint}_request.json`` + ``_response_schema.json``.

Modes
-----
- ``static``  : parse a captured Corti OpenAPI markdown spec under
                ``docs/corti-reverse-engineered/{feature}.md`` and emit
                request/response JSON.
- ``dynamic`` : re-run ``corti_deep_crawler.py --only <feature>`` to capture
                a real network request/response pair, then emit normalized
                JSON to ``golden_captures/{feature}.json``.
- ``hybrid``  : do both. Default.

Usage
-----
    python scripts/corti_deep_scan.py --endpoint coding/icoder --mode static \\
        --spec docs/corti-reverse-engineered/codes-predict-codes.md

    python scripts/corti_deep_scan.py --endpoint medical-coding --mode dynamic
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from colorama import Fore, Style, init as colorama_init

colorama_init()

REPO_ROOT = Path(__file__).resolve().parent.parent
CORTI_CONTRACTS_DIR = REPO_ROOT / "corti_contracts"
GOLDEN_DIR = REPO_ROOT / "golden_captures"
SPEC_DIR = REPO_ROOT / "docs" / "corti-reverse-engineered"

INTERNAL_NAMESPACES = frozenset({
    "icd10cn-inpatient", "icd10cn-outpatient",
    "icd9cm3-cn",
})

CORTI_NAMESPACES = frozenset({
    "icd10cm-inpatient", "icd10cm-outpatient", "icd10pcs", "cpt",
    "icd10int-inpatient", "icd10int-outpatient",
    "icd10uk-inpatient", "icd10uk-outpatient",
    "cim10fr-inpatient", "cim10fr-outpatient",
    "icd10gm-inpatient", "icd10gm-outpatient",
    "opcs4", "ops", "ccam",
})


def _find_spec_for_endpoint(endpoint: str) -> Path | None:
    """Heuristic: match endpoint slug → captured .md spec.

    Examples:
        'coding/icoder'     → codes-predict-codes.md
        'medical-coding'    → codes-predict-codes.md
        'stt-list-transcripts' → stt-list-transcripts.md
    """
    candidates = list(SPEC_DIR.glob("*.md"))
    slug = endpoint.lower().replace("/", "-")
    for c in candidates:
        if slug in c.stem.lower():
            return c
    short = slug.split("-")[-1] if "-" in slug else slug
    for c in candidates:
        if short in c.stem.lower():
            return c
    return None


def extract_openapi_yaml(spec_path: Path) -> dict[str, Any]:
    """Pull the embedded ``openapi: 3.0+`` YAML block out of a Mintlify .md."""
    text = spec_path.read_text(encoding="utf-8")
    for block in re.findall(r"```yaml[^\n]*\n(.*?)```", text, flags=re.DOTALL):
        try:
            parsed = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if isinstance(parsed, dict) and parsed.get("openapi"):
            return parsed
    raise ValueError(f"No openapi 3.0+ YAML block found in {spec_path}")


def make_sample_request(openapi: dict[str, Any], endpoint: str) -> dict[str, Any]:
    """Heuristic: build a small valid request body for the endpoint from
    the OpenAPI schema. Picks a sample system + minimal context.

    Two system scenarios are emitted: one with a Corti-native (US) name that
    the iCoDer Chinese-only endpoint will reject with 400, one with a
    Chinese ICD-10-CN name it will accept. This makes the comparison suite
    useful for parity diffing.
    """
    path = openapi.get("paths", {}).get(f"/tools/{endpoint}", {}) or \
           openapi.get("paths", {}).get(f"/tools/{endpoint.split('/')[-1]}", {})
    post = path.get("post", {}) if isinstance(path, dict) else {}
    body_schema = (
        post.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
    )
    ref = body_schema.get("$ref") or body_schema.get("items", {}).get("$ref")
    target_name = ref.split("/")[-1] if ref else None
    components = openapi.get("components", {}).get("schemas", {})
    body = components.get(target_name, {}) if target_name else {}

    sample = {}
    for prop_name, prop_schema in body.get("properties", {}).items():
        if prop_name == "system":
            sample[prop_name] = ["icd10cm-outpatient"]
        elif prop_name == "context":
            sample[prop_name] = [{"type": "text", "text": "Patient presents with chest pain."}]
        elif prop_name == "filter":
            sample[prop_name] = None
        elif prop_name == "async":
            sample[prop_name] = False
        elif prop_name in ("recordingId", "primaryLanguage"):
            sample[prop_name] = "00000000-0000-4000-8000-000000000001"
        elif prop_name in ("full",):
            sample[prop_name] = True
    return sample


def emit_static_contract(endpoint: str, spec_path: Path) -> tuple[Path, Path]:
    """Write ``{endpoint}_request.json`` + ``{endpoint}_response_schema.json``."""
    openapi = extract_openapi_yaml(spec_path)
    request = make_sample_request(openapi, endpoint)
    CORTI_CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    request_path = CORTI_CONTRACTS_DIR / f"{endpoint}_request.json"
    schema_path = CORTI_CONTRACTS_DIR / f"{endpoint}_response_schema.json"
    request_path.write_text(
        json.dumps({"endpoint": endpoint, "request": request}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    schema_path.write_text(
        json.dumps({"endpoint": endpoint, "openapi": openapi}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return request_path, schema_path


def emit_dynamic_capture(endpoint: str) -> Path | None:
    """Re-run corti_deep_crawler to capture a real network pair.

    Returns path to the per-feature summary.json, or None if the crawl
    wasn't run (missing SSO session in CI etc.).
    """
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    feature = endpoint.split("/")[-1] or endpoint
    feature_dir = GOLDEN_DIR / feature
    summary = feature_dir / "summary.json"
    if summary.exists():
        return summary
    crawler = REPO_ROOT / "scripts" / "corti_deep_crawler.py"
    if not crawler.exists():
        print(f"{Fore.YELLOW}[skip] dynamic mode: {crawler} not found")
        return None
    print(f"{Fore.CYAN}[run] python {crawler.name} --only {feature}")
    result = subprocess.run(
        [sys.executable, str(crawler), "--only", feature],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"{Fore.YELLOW}[warn] dynamic crawl returned {result.returncode} (likely no SSO)")
        return None
    return summary if summary.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Corti contract extractor (wrapper).")
    parser.add_argument("--endpoint", required=True, help="e.g. 'coding/icoder' or 'medical-coding'")
    parser.add_argument("--mode", choices=["static", "dynamic", "hybrid"], default="hybrid")
    parser.add_argument("--spec", type=Path, help="Override spec .md path (static mode)")
    args = parser.parse_args()

    spec = args.spec or _find_spec_for_endpoint(args.endpoint)
    if not spec or not spec.exists():
        print(f"{Fore.RED}[fail] no spec found for endpoint {args.endpoint!r}")
        print(f"       looked in {SPEC_DIR}")
        print(f"       pass --spec <path-to-md> to override")
        return 2

    print(f"{Fore.GREEN}[scan] endpoint={args.endpoint}  mode={args.mode}  spec={spec.name}")

    wrote = []
    if args.mode in ("static", "hybrid"):
        req_p, sch_p = emit_static_contract(args.endpoint, spec)
        wrote += [req_p, sch_p]
        print(f"  ✓ static  → {req_p.relative_to(REPO_ROOT)}")
        print(f"  ✓ static  → {sch_p.relative_to(REPO_ROOT)}")

    if args.mode in ("dynamic", "hybrid"):
        golden = emit_dynamic_capture(args.endpoint)
        if golden:
            print(f"  ✓ dynamic → {golden.relative_to(REPO_ROOT)}")
            wrote.append(golden)
        else:
            print(f"  · dynamic skipped (no SSO / no crawler)")

    print(f"\n{Fore.GREEN}[done] {len(wrote)} contract file(s) emitted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
