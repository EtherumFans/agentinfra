"""Unit tests for MedicalCodingOutputSchema.mode discriminator.

Covers Commit 8: default ``mode`` is "" (not "hybrid") so mock_result
and other unset paths don't falsely claim a real hybrid pipeline ran.
"""
from official_agents.medical_coding.schema import MedicalCodingOutputSchema


def test_mock_result_mode_is_empty_string():
    """mock_result() must NOT set mode='hybrid' — that would lie about provenance."""
    out = MedicalCodingOutputSchema.mock_result()
    assert out.mode == "", f"expected mode='' (unset), got {out.mode!r}"


def test_default_construction_mode_is_empty_string():
    """Plain MedicalCodingOutputSchema() also defaults mode=''."""
    out = MedicalCodingOutputSchema()
    assert out.mode == ""


def test_from_dict_defaults_mode_to_empty_string():
    """If a dict payload has no 'mode' key, from_dict defaults to '' (not 'hybrid')."""
    payload = {
        "primary_diagnosis": {"code": "I50.900", "description": "心力衰竭"},
        "secondary_diagnoses": [],
        "procedures": [],
        "issues_found": [],
        "confidence": 0.9,
    }
    out = MedicalCodingOutputSchema.from_dict(payload, provider="test")
    assert out.mode == ""


def test_from_dict_preserves_explicit_mode():
    """from_dict honors an explicit mode string from the payload."""
    payload = {
        "primary_diagnosis": {"code": "I50.900", "description": "心力衰竭"},
        "secondary_diagnoses": [],
        "procedures": [],
        "issues_found": [],
        "confidence": 0.9,
        "mode": "medcoder",
    }
    out = MedicalCodingOutputSchema.from_dict(payload, provider="test")
    assert out.mode == "medcoder"


def test_to_dict_serializes_empty_mode():
    """to_dict round-trips the empty mode as an empty string."""
    out = MedicalCodingOutputSchema.mock_result()
    d = out.to_dict()
    assert d["mode"] == ""
