"""Unit tests for MedicalCodingOutputSchema.mode discriminator.

Covers Commit 8: default ``mode`` is ``Mode.UNSET`` (not ``"hybrid"``) so
``mock_result()`` and other unset paths don't falsely claim a real hybrid
pipeline ran. M2 (audit Part 7.4) upgrades ``mode`` to the ``Mode``
StrEnum SSOT; string-compat is preserved (``Mode.UNSET == ""`` is True).
"""
from official_agents.medical_coding.modes import Mode
from official_agents.medical_coding.schema import MedicalCodingOutputSchema


def test_mock_result_mode_is_unset():
    """mock_result() must NOT set mode='hybrid' — that would lie about provenance."""
    out = MedicalCodingOutputSchema.mock_result()
    assert out.mode == Mode.UNSET
    # String-compat preserved (StrEnum).
    assert out.mode == ""


def test_default_construction_mode_is_unset():
    """Plain MedicalCodingOutputSchema() also defaults to Mode.UNSET."""
    out = MedicalCodingOutputSchema()
    assert out.mode == Mode.UNSET
    assert out.mode == ""


def test_from_dict_defaults_mode_to_unset():
    """If a dict payload has no 'mode' key, from_dict defaults to UNSET."""
    payload = {
        "primary_diagnosis": {"code": "I50.900", "description": "心力衰竭"},
        "secondary_diagnoses": [],
        "procedures": [],
        "issues_found": [],
        "confidence": 0.9,
    }
    out = MedicalCodingOutputSchema.from_dict(payload, provider="test")
    assert out.mode == Mode.UNSET


def test_from_dict_preserves_explicit_mode():
    """from_dict honors an explicit mode string from the payload (str-coerced to Mode)."""
    payload = {
        "primary_diagnosis": {"code": "I50.900", "description": "心力衰竭"},
        "secondary_diagnoses": [],
        "procedures": [],
        "issues_found": [],
        "confidence": 0.9,
        "mode": "medcoder",
    }
    out = MedicalCodingOutputSchema.from_dict(payload, provider="test")
    assert out.mode == Mode.MEDCODER
    # String-compat preserved.
    assert out.mode == "medcoder"


def test_from_dict_unknown_mode_falls_back_to_unset():
    """Unknown / stale mode values fall back to Mode.UNSET (defensive R1)."""
    payload = {
        "primary_diagnosis": {"code": "I50.900", "description": "心力衰竭"},
        "mode": "stale_mode_from_older_version",
    }
    out = MedicalCodingOutputSchema.from_dict(payload, provider="test")
    assert out.mode == Mode.UNSET


def test_to_dict_serializes_empty_mode():
    """to_dict round-trips Mode.UNSET as the empty string."""
    out = MedicalCodingOutputSchema.mock_result()
    d = out.to_dict()
    assert d["mode"] == Mode.UNSET
    assert d["mode"] == ""
