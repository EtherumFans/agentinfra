"""Symbolic State Engine — append-only decision log with SHA-256 chain.

Every Agent decision (tool call, state transition, human confirmation)
is recorded as an immutable entry with a hash chain for audit integrity.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _hash(data: dict | str) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str) if isinstance(data, dict) else str(data)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class SymbolicState:
    """Append-only state log with SHA-256 hash chain.

    Each entry is: {timestamp, step, actor, payload, prev_hash, entry_hash}
    - prev_hash: chain to previous entry (tamper-evident)
    - entry_hash: SHA-256 of this entry's content
    """

    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self.entries: list[dict] = []
        self._last_hash = "0" * 16  # genesis hash

    def record(self, step: str, actor: str = "", payload: dict | None = None) -> dict:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "actor": actor,
            "payload": payload or {},
            "prev_hash": self._last_hash,
        }
        entry["entry_hash"] = _hash(entry)
        self._last_hash = entry["entry_hash"]
        self.entries.append(entry)
        logger.debug(f"SymbolicState [{self.session_id[:8]}]: {step} — hash={entry['entry_hash']}")
        return entry

    def verify_chain(self) -> bool:
        """Verify the entire hash chain is intact."""
        prev = "0" * 16
        for e in self.entries:
            if e["prev_hash"] != prev:
                return False
            expected = _hash({k: e[k] for k in ("timestamp", "step", "actor", "payload", "prev_hash")})
            if e["entry_hash"] != expected:
                return False
            prev = e["entry_hash"]
        return True

    def export(self) -> dict:
        return {
            "session_id": self.session_id,
            "entry_count": len(self.entries),
            "chain_valid": self.verify_chain(),
            "last_hash": self._last_hash,
            "entries": self.entries,
        }
