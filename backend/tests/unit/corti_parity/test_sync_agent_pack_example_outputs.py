from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.corti_parity.sync_agent_pack_example_outputs import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_REPORT,
    REQUIRED_SOURCE_CHECKS,
    sync_examples,
)


def _fixture_tree(tmp_path: Path) -> tuple[Path, Path]:
    agents_dir = tmp_path / "agents"
    report_dir = tmp_path / "evidence"
    responses_dir = report_dir / "responses"
    responses_dir.mkdir(parents=True)
    rows = []
    for index in range(26):
        agent_id = f"agent-{index:02d}"
        pack_dir = agents_dir / agent_id
        pack_dir.mkdir(parents=True)
        pack = {
            "agent_ref": f"icoder/{agent_id}@1.0.0",
            "manifest": {"hidden_from_hub": False},
            "output_contract": {
                "schema_ref": f"icoder/{agent_id}/v1",
                "required_fields": ["result", "manual_review_required", "trace_refs"],
            },
            "integrity": {"sha256": "0" * 64},
        }
        (pack_dir / "agent_pack.json").write_text(
            json.dumps(pack), encoding="utf-8",
        )
        checks = {name: True for name in REQUIRED_SOURCE_CHECKS}
        rows.append({
            "agent_id": agent_id,
            "evaluation": {"passed": True, "checks": checks},
        })
        (responses_dir / f"{agent_id}.json").write_text(
            json.dumps({
                "result": {
                    "result": f"validated-{index}",
                    "manual_review_required": True,
                    "trace_refs": {
                        "run_id": f"live-run-{index}",
                        "trace_id": f"live-trace-{index}",
                    },
                    "provider_only_field": "must-not-be-promoted",
                }
            }),
            encoding="utf-8",
        )
    report_path = report_dir / "report.json"
    report_path.write_text(
        json.dumps({"total": 26, "passed": 26, "failed": 0, "rows": rows}),
        encoding="utf-8",
    )
    return agents_dir, report_path


def test_sync_promotes_only_contract_fields_and_is_idempotent(tmp_path: Path) -> None:
    agents_dir, report_path = _fixture_tree(tmp_path)

    dry_run = sync_examples(
        agents_dir,
        report_path,
        write=False,
        reference_cases_path=None,
    )
    assert len(dry_run["changed_agents"]) == 26

    written = sync_examples(
        agents_dir,
        report_path,
        write=True,
        reference_cases_path=None,
    )
    assert len(written["changed_agents"]) == 26
    assert sync_examples(
        agents_dir,
        report_path,
        write=False,
        reference_cases_path=None,
    )["changed_agents"] == []

    pack = json.loads(
        (agents_dir / "agent-00" / "agent_pack.json").read_text(encoding="utf-8")
    )
    example = pack["example_outputs"][0]
    assert set(example) == {"result", "manual_review_required", "trace_refs"}
    assert example["trace_refs"] == {
        "run_id": "sample-run",
        "trace_id": "sample-trace",
    }
    assert pack["integrity"]["sha256"] != "0" * 64
    assert len(pack["integrity"]["sha256"]) == hashlib.sha256().digest_size * 2


def test_sync_rejects_source_evidence_with_a_failed_safety_check(tmp_path: Path) -> None:
    agents_dir, report_path = _fixture_tree(tmp_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["rows"][0]["evaluation"]["checks"]["content_safety"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")

    untouched_path = agents_dir / "agent-01" / "agent_pack.json"
    untouched = untouched_path.read_bytes()
    with pytest.raises(ValueError, match="content_safety"):
        sync_examples(
            agents_dir,
            report_path,
            write=True,
            reference_cases_path=None,
        )
    assert untouched_path.read_bytes() == untouched


def test_historical_repository_e2e_cannot_overwrite_current_semantic_references() -> None:
    with pytest.raises(ValueError, match="Pack-owned reference semantics"):
        sync_examples(DEFAULT_AGENTS_DIR, DEFAULT_REPORT, write=False)
