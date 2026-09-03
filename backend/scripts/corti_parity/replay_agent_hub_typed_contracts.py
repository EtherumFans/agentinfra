"""Replay captured provider outputs through the current typed Pack boundary.

This is an offline development E2E gate: it uses previously captured, already
redacted successful provider results and executes the current structured
projector, Pack validation, human-review enforcement, and public response
mapping.  It does not call an LLM, database, browser, or network service.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.agent_run import map_backend_response
from icoder_runtime.backends.contracts import BackendResponse
from icoder_runtime.backends.structured_output_projector import project


DEFAULT_AGENTS_DIR = BACKEND_ROOT / "official_agents"
DEFAULT_SOURCE_DIR = REPO_ROOT / "reports" / "agent_hub" / "examples_e2e_20260813"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "agent_hub" / "typed_contract_replay_20260815"


def _agent_id(pack: dict[str, Any]) -> str:
    return str(pack.get("agent_ref") or "").rsplit("/", 1)[-1].split("@", 1)[0]


def replay(agents_dir: Path, source_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for pack_path in sorted(agents_dir.glob("*/agent_pack.json")):
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        agent_id = _agent_id(pack)
        source_path = source_dir / "responses" / f"{agent_id}.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source_result = source.get("result") or {}
        contract = pack.get("output_contract") or {}
        required = list(contract.get("required_fields") or [])
        optional = list(contract.get("optional_fields") or [])
        domain = {
            field: source_result[field]
            for field in required + optional
            if field in source_result
        }
        captured_markdown = source_result.get("markdown")
        replay_markdown = json.dumps(domain, ensure_ascii=False)
        if isinstance(captured_markdown, str) and captured_markdown.strip():
            projected = project(
                captured_markdown,
                str(contract.get("schema_ref") or ""),
                agent_id,
            ).result
            runtime_owned = {"trace_refs", "manual_review_required"}
            provider_required = [
                field for field in required if field not in runtime_owned
            ]
            if all(field in projected for field in provider_required):
                replay_markdown = captured_markdown
        public = map_backend_response(
            agent_id=agent_id,
            run_id=f"run-replay-{agent_id}",
            trace_id=f"trace-replay-{agent_id}",
            runtime_mode="offline_typed_contract_replay",
            resp=BackendResponse(
                status="requires_review",
                summary=str(source.get("summary") or source_result.get("summary") or "replay"),
                markdown=replay_markdown,
                backend_provider=str(source_result.get("backend_provider") or "captured.provider"),
                backend_type=str(source_result.get("backend_type") or "captured_replay"),
                finish_state="completed",
            ),
            include_trace=False,
            include_evidence=False,
            agent_pack=pack,
            t0=time.perf_counter(),
        )
        extraction = public.result.get("structured_extraction") or {}
        checks = {
            "source_required_fields_complete": all(field in source_result for field in required),
            "field_type_declarations_complete": all(
                field in (contract.get("field_types") or {})
                for field in required + optional
            ),
            "public_required_fields_complete": all(
                field in public.result for field in required
            ),
            "structured_extraction_valid": extraction.get("valid") is True,
            "invalid_field_types_empty": extraction.get("invalid_field_types") == [],
            "invalid_field_schemas_empty": extraction.get("invalid_field_schemas") == [],
            "undeclared_output_fields_empty": (
                extraction.get("undeclared_output_fields") == []
            ),
            "public_error_false": public.error is False,
            "manual_review_enforced": public.manual_review_required is True,
        }
        rows.append({
            "agent_id": agent_id,
            "contract": contract.get("schema_ref"),
            "required_field_count": len(required),
            "checks": checks,
            "passed": all(checks.values()),
            "missing_required_fields": extraction.get("missing_required_fields") or [],
            "invalid_field_types": extraction.get("invalid_field_types") or [],
            "invalid_field_schemas": extraction.get("invalid_field_schemas") or [],
            "undeclared_output_fields": extraction.get("undeclared_output_fields") or [],
        })
    passed = sum(row["passed"] for row in rows)
    return {
        "schema_version": "icoder.agent-hub-typed-contract-replay/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    report = replay(args.agents_dir.resolve(), args.source_dir.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "agent_hub_typed_contract_replay.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total", "passed", "failed")}, ensure_ascii=False))
    print(path)
    return 0 if report["total"] == 26 and report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
