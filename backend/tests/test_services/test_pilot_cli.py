# Pilot CLI — smoke tests
import json
import os
import subprocess
import sys
import tempfile
import pytest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPT = BACKEND_DIR / "scripts" / "pilot_eval_runbook.py"


def _run_cli(*args):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True, text=True, cwd=str(BACKEND_DIR),
        timeout=60, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return result


class TestGenerateTemplate:
    def test_json_smoke(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp = f.name
        try:
            result = _run_cli("generate-template", "--department", "ortho", "--output", tmp)
            assert result.returncode == 0, f"stderr: {result.stderr}"
            content = Path(tmp).read_text(encoding="utf-8")
            data = json.loads(content)
            assert "_instructions" in data
            assert data["case_metadata"]["department"] == "ortho"
        finally:
            os.unlink(tmp)

    def test_markdown_smoke(self):
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            tmp = f.name
        try:
            result = _run_cli("generate-template", "--format", "markdown", "--output", tmp)
            assert result.returncode == 0
            content = Path(tmp).read_text(encoding="utf-8")
            assert "Gold Case Template" in content
        finally:
            os.unlink(tmp)


class TestValidateGold:
    def test_valid_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump([{"encounter_id": "T001", "expected_principal_diagnosis": "Z51.102", "department": "tumor"}], f)
            tmp = f.name
        try:
            result = _run_cli("validate-gold", tmp)
            assert result.returncode == 0, f"stderr: {result.stderr}"
        finally:
            os.unlink(tmp)

    def test_invalid_file_exit_code(self):
        result = _run_cli("validate-gold", "/nonexistent/file.json")
        assert result.returncode != 0

    def test_csv_file(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8-sig") as f:
            f.write("encounter_id,expected_principal_diagnosis,department\nT001,Z51.102,tumor\nT002,C20.x00,ortho\n")
            tmp = f.name
        try:
            result = _run_cli("validate-gold", tmp)
            assert result.returncode == 0, f"stderr: {result.stderr}"
        finally:
            os.unlink(tmp)


class TestImportGold:
    def test_dry_run(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as f:
            json.dump([{"encounter_id": "IMP001", "expected_principal_diagnosis": "Z51.102", "department": "tumor"}], f)
            tmp = f.name
        try:
            result = _run_cli("import-gold", tmp, "--dry-run")
            assert result.returncode == 0, f"stderr: {result.stderr}"
        finally:
            os.unlink(tmp)


class TestExportReport:
    def test_generates_report(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp = f.name
        try:
            result = _run_cli("export-report", "--output", tmp, "--pilot_name", "test_pilot")
            assert result.returncode == 0, f"stderr: {result.stderr}"
            data = json.loads(Path(tmp).read_text(encoding="utf-8"))
            assert "sections" in data
            assert data["pilot_name"] == "test_pilot"
        finally:
            os.unlink(tmp)
