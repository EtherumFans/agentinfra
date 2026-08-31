"""Small public adapter for the managed Artifact JSON scanner."""

from __future__ import annotations

from app.icoder.agent_runtime.a2a.v1.artifact_object_store import scan_content


def scan_deidentified_json(content: bytes, *, filename: str) -> None:
    """Fail unless bounded bytes are clean, JSON and deidentified.

    The underlying development scanner deliberately rejects executables,
    archives, malformed/binary content, media mismatches and known CN/identity
    patterns.  Production still requires an independently operated AV/DLP
    service.
    """

    result = scan_content(
        content,
        filename=filename,
        declared_media_type="application/json",
        data_classification="deidentified",
    )
    if result.malware_status != "clean" or result.dlp_status != "clear":
        raise ValueError("artifact content scan did not return clean/clear")


__all__ = ["scan_deidentified_json"]
