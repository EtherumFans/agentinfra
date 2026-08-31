from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release" / "build_development_baseline.py"
SPEC = importlib.util.spec_from_file_location("build_development_baseline", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_baseline_buckets_keep_tests_and_evidence_out_of_product_source() -> None:
    assert MODULE.classify("backend/app/main.py") == "product_source"
    assert MODULE.classify("backend/tests/test_main.py") == "tests"
    assert MODULE.classify("frontend/src/x.test.ts") == "tests"
    assert MODULE.classify("reports/audit/result.json") == "documentation_evidence"
    assert MODULE.classify("screen.png") == "generated_binary_or_evidence"


def test_local_environment_files_are_never_product_source() -> None:
    assert MODULE.classify("backend/.env") == "unsafe_local"
    assert MODULE.classify(".env.cloud") == "unsafe_local"
    assert MODULE.classify(".env.cloud.example") == "product_source"
