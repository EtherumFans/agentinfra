# Token usage tracker — monitors LLM token consumption
import logging
import threading
from datetime import datetime, UTC
from typing import Optional

logger = logging.getLogger(__name__)


class TokenUsageTracker:
    """Thread-safe token usage accumulator with per-agent/session tracking."""

    def __init__(self):
        self._lock = threading.Lock()
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._call_count = 0
        self._last_call_at: Optional[datetime] = None

    def record(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        with self._lock:
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens
            self._total_tokens += total_tokens
            self._call_count += 1
            self._last_call_at = datetime.now(UTC)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._total_tokens,
                "call_count": self._call_count,
                "last_call_at": self._last_call_at.isoformat() if self._last_call_at else None,
            }

    def reset(self):
        with self._lock:
            self._prompt_tokens = 0
            self._completion_tokens = 0
            self._total_tokens = 0
            self._call_count = 0
            self._last_call_at = None


# Global tracker instance
global_tracker = TokenUsageTracker()
