"""Tests for the iCoDer 201 fixture and its build script.

Covers Commit 9: 201-case sample of ccl2026_train_gold.json (seed=42),
source field, byte-equal across re-runs.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_PATH = _BACKEND_ROOT / "tests" / "fixtures" / "icoder_201.json"
BUILDER_SCRIPT = _BACKEND_ROOT / "scripts" / "build_icoder_201_fixture.py"


def test_fixture_exists_and_has_201_cases():
    """The committed fixture must have exactly 201 cases."""
    assert FIXTURE_PATH.exists(), f"Missing fixture: {FIXTURE_PATH}"
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert data.get("source") == "icoder_201_subset"
    assert data.get("sampled_at_seed") == 42
    cases = data.get("gold_cases")
    assert isinstance(cases, list)
    assert len(cases) == 201


def test_every_case_is_tagged_with_source():
    """Each case in the fixture carries the source='icoder_201_subset' marker."""
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for c in data["gold_cases"]:
        assert c.get("source") == "icoder_201_subset", (
            f"Case {c.get('encounter_id')} missing source tag"
        )


def test_fixture_is_compatible_with_extract_gold_codes():
    """Every case has the flat CCL fields extract_gold_codes() reads."""
    # Importing the e2e helper — its _norm_code is also imported in
    # combine_medcoder_reports.py. Mirrors what eval scripts do.
    sys.path.insert(0, str(_BACKEND_ROOT))
    from scripts.e2e_medcoder_validation import extract_gold_codes

    with open(FIXTURE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for c in data["gold_cases"]:
        gold = extract_gold_codes(c)
        # Every case should yield at least one gold code (otherwise
        # the eval F1 is undefined for that case).
        assert len(gold) > 0, (
            f"Case {c.get('encounter_id')} has no extractable gold codes"
        )


def test_fixture_loads_via_load_gold_cases_helper():
    """load_gold_cases() returns the 201 cases (it handles the wrapper)."""
    sys.path.insert(0, str(_BACKEND_ROOT))
    from scripts.e2e_medcoder_validation import load_gold_cases

    cases = load_gold_cases(str(FIXTURE_PATH))
    assert len(cases) == 201
    # First case has the expected principal_diagnosis field
    assert "expected_principal_diagnosis" in cases[0]


def test_builder_is_idempotent():
    """Re-running the builder with default args produces a byte-equal output.

    Catches silent changes in random sampling (e.g., someone bumps
    the seed by accident or switches to a different RNG).
    """
    with open(FIXTURE_PATH, "rb") as f:
        original = f.read()

    result = subprocess.run(
        [sys.executable, str(BUILDER_SCRIPT), "--output", str(FIXTURE_PATH)],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "201 cases" in result.stdout

    with open(FIXTURE_PATH, "rb") as f:
        rewritten = f.read()

    assert original == rewritten, (
        "Builder is non-idempotent — re-run produced a different byte stream"
    )


def test_builder_rejects_undersized_source():
    """If the source has fewer cases than the sample size, the builder errors."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump([{"a": 1}, {"a": 2}], f)
        small_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, str(BUILDER_SCRIPT),
             "--input", small_path,
             "--output", str(FIXTURE_PATH) + ".tmp"],
            cwd=_BACKEND_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "can't sample" in (result.stderr + result.stdout)
    finally:
        tmp_out = Path(str(FIXTURE_PATH) + ".tmp")
        if tmp_out.exists():
            tmp_out.unlink()
        Path(small_path).unlink()
