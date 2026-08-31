"""Privacy boundary helpers for the CDI REST entry point."""

from app.api.cdi import _pseudonymize_reference


def test_reference_pseudonyms_are_stable_tenant_scoped_and_irreversible() -> None:
    raw_ref = "MRN-001"
    first = _pseudonymize_reference(raw_ref, kind="patient", tenant_id="org-a")
    same = _pseudonymize_reference(raw_ref, kind="patient", tenant_id="org-a")
    other_tenant = _pseudonymize_reference(
        raw_ref, kind="patient", tenant_id="org-b",
    )

    assert first == same
    assert first != other_tenant
    assert first.startswith("PSEUDO-PATIENT-")
    assert raw_ref not in first

