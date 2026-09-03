import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "scan_phi_artifacts.py"


def _module():
    spec = importlib.util.spec_from_file_location("phi_artifact_scanner", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scanner_passes_ciphertext_and_fails_plaintext_without_disclosure(tmp_path) -> None:
    module = _module()
    sentinel = "PHI-CANARY-张三-20260902"
    sentinel_file = tmp_path / "sentinels.json"
    sentinel_file.write_text(json.dumps([sentinel], ensure_ascii=False), encoding="utf-8")
    safe = tmp_path / "backup-safe.sql"
    safe.write_text("v2:opaque-ciphertext", encoding="utf-8")
    passed = module.scan([safe], sentinel_file)
    assert passed["status"] == "passed" and passed["finding_count"] == 0

    unsafe = tmp_path / "wal-unsafe.bin"
    unsafe.write_bytes(b"prefix" + sentinel.encode("utf-8") + b"suffix")
    failed = module.scan([unsafe], sentinel_file)
    assert failed["status"] == "failed_plaintext_found"
    assert failed["finding_count"] == 1
    assert sentinel not in json.dumps(failed, ensure_ascii=False)


def test_scanner_detects_chunk_boundary_and_utf16(tmp_path, monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "CHUNK_SIZE", 32)
    sentinel = "PHI-CANARY-BOUNDARY"
    sentinel_file = tmp_path / "sentinels.json"
    sentinel_file.write_text(json.dumps([sentinel]), encoding="utf-8")
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"x" * 25 + sentinel.encode("utf-16le"))
    report = module.scan([artifact], sentinel_file)
    assert report["finding_count"] == 1
