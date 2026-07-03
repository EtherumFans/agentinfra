# DEPRECATED (P1.3 Stage 5, 2026-07-02) — Legacy 单体 Agent. Phase 2 切换到 app/icoder/agent_runtime/orchestrator/ 后删. 见 docs/architecture/MAINLINE_VS_LEGACY.md §3.1.
# iCoDer - Base Agent Class
import logging
import time
from typing import Optional
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class BaseExpert:
    """Base class for all coding experts."""
    name: str = "BaseExpert"
    description: str = ""

    def __init__(self):
        self.llm = llm_service

    async def run(self, context: dict) -> dict:
        """Run the expert. Override in subclasses."""
        raise NotImplementedError

    def _log_step(self, step_name: str, context: dict) -> None:
        logger.info(f"[{self.name}] {step_name} - encounter: {context.get('encounter_id', 'unknown')}")

    def _timed_result(self, start: float, result: dict) -> dict:
        elapsed_ms = int((time.time() - start) * 1000)
        result["processing_time_ms"] = elapsed_ms
        return result
