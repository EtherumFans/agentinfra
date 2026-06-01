"""Evidence Pack — assemble auditable evidence from Agent execution results.

Works with Runtime output dicts (no DB dependency).
"""

import hashlib
import json
from datetime import datetime, timezone


def _hash(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def build_evidence_pack(run_result: dict) -> dict:
    """Build audit evidence pack from an AgentRunner.run() result dict."""
    now = datetime.now(timezone.utc).isoformat()

    pack = {
        "metadata": {
            "review_id": run_result.get("review_id", ""),
            "agent_name": run_result.get("agent_name", ""),
            "agent_version": run_result.get("agent_version", ""),
            "exported_at": now,
            "processing_time_ms": run_result.get("processing_time_ms", 0),
        },
        "primary_diagnosis": run_result.get("primary_diagnosis", {}),
        "output": run_result.get("output", ""),
        "contract_valid": run_result.get("contract_valid", True),
        "state_log": run_result.get("state_log", {}),
    }

    content_hash = _hash(pack)

    return {
        **pack,
        "integrity": {
            "content_hash": f"sha256:{content_hash}",
            "unsigned_hash": content_hash,
            "exported_at": now,
        },
    }
