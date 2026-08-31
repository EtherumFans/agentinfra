"""Deterministic security checks for managed A2A Artifact objects."""

from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfWriter

from app.api.agentic_context_resources import _actor_fingerprint_from_principal
from app.icoder.agent_runtime.a2a.v1 import artifact_object_store as store


def _pdf(*, javascript: bool = False) -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if javascript:
        writer.add_js("app.alert('blocked')")
    writer.write(output)
    return output.getvalue()


def test_canonical_upload_and_clean_media_detection() -> None:
    content = b'{"summary":"synthetic deidentified result"}'
    encoded = base64.b64encode(content).decode("ascii")
    assert store.decode_upload(encoded) == content
    result = store.scan_content(
        content,
        filename="result.json",
        declared_media_type="application/json",
        data_classification="deidentified",
    )
    assert result.detected_media_type == "application/json"
    assert result.malware_status == "clean"
    assert result.dlp_status == "clear"

    with pytest.raises(store.ArtifactObjectError) as malformed:
        store.decode_upload(encoded.rstrip("="))
    assert malformed.value.code == "INVALID_RAW_PAYLOAD"


def test_chinese_direct_identifiers_block_deidentified_but_restrict_clinical() -> None:
    content = "患者姓名：测试甲 身份证号：11010519491231002X".encode()
    with pytest.raises(Exception) as blocked:
        store.scan_content(
            content,
            filename="result.txt",
            declared_media_type="text/plain",
            data_classification="deidentified",
        )
    assert getattr(blocked.value, "code", None) == "DEIDENTIFICATION_POLICY_BLOCKED"
    assert getattr(blocked.value, "dlp_status", None) == "blocked"

    restricted = store.scan_content(
        content,
        filename="result.txt",
        declared_media_type="text/plain",
        data_classification="clinical-sensitive",
    )
    assert restricted.dlp_status == "restricted"
    assert "cn_resident_identity_number" in restricted.finding_types
    assert "explicit_patient_identifier" in restricted.finding_types


def test_eicar_executables_archives_and_media_spoofing_fail_closed() -> None:
    # Assemble the standardized test signature at runtime so source files do
    # not themselves look like malware to workstation antivirus software.
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    with pytest.raises(Exception) as infected:
        store.scan_content(
            eicar,
            filename="result.txt",
            declared_media_type="text/plain",
            data_classification="deidentified",
        )
    assert getattr(infected.value, "code", None) == "MALWARE_TEST_SIGNATURE"
    assert getattr(infected.value, "malware_status", None) == "infected"

    for content, code in ((b"MZpayload", "EXECUTABLE_CONTENT"), (b"PK\x03\x04data", "ARCHIVE_CONTENT_UNSCANNABLE")):
        with pytest.raises(Exception) as rejected:
            store.scan_content(
                content,
                filename="result.txt",
                declared_media_type="text/plain",
                data_classification="deidentified",
            )
        assert getattr(rejected.value, "code", None) == code

    with pytest.raises(Exception) as mismatch:
        store.scan_content(
            b'{"safe":true}',
            filename="result.txt",
            declared_media_type="text/plain",
            data_classification="deidentified",
        )
    assert getattr(mismatch.value, "code", None) == "MEDIA_TYPE_MISMATCH"


def test_pdf_parser_accepts_passive_pdf_and_rejects_active_content() -> None:
    passive = store.scan_content(
        _pdf(),
        filename="result.pdf",
        declared_media_type="application/pdf",
        data_classification="deidentified",
    )
    assert passive.detected_media_type == "application/pdf"
    assert passive.dlp_status == "clear"

    with pytest.raises(Exception) as active:
        store.scan_content(
            _pdf(javascript=True),
            filename="result.pdf",
            declared_media_type="application/pdf",
            data_classification="deidentified",
        )
    assert getattr(active.value, "code", None) == "PDF_ACTIVE_CONTENT"
    assert getattr(active.value, "malware_status", None) == "infected"


def test_machine_download_actor_is_bound_to_exact_client_not_shared_owner() -> None:
    class Owner:
        id = "owner-1"
        email = "owner@example.test"

    first_type, first_hash = _actor_fingerprint_from_principal(
        (Owner(), {"type": "oauth_client", "client_id": "client-1"})
    )
    second_type, second_hash = _actor_fingerprint_from_principal(
        (Owner(), {"type": "oauth_client", "client_id": "client-2"})
    )

    assert first_type == second_type == "oauth_client"
    assert first_hash != second_hash
