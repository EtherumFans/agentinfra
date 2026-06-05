"""Runtime configuration — controls execution mode and feature flags.

Read from environment variables or a runtime.yaml file.
Default to 'legacy' mode for safe rollout.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ExecutionMode = Literal["legacy", "platform_runtime", "shadow"]


@dataclass
class RuntimeConfig:
    """Feature flags controlling how the Runtime is used.

    execution_mode:
      - "legacy": All APIs use old orchestrator/agent_runner paths
      - "platform_runtime": All APIs use PlatformRuntime via LLMGateway
      - "shadow": Old path returns, new path runs in background, diff is logged

    review_coding_mode:
      Same as execution_mode, but scoped to Reviews/Encounters specifically.

    fallback_to_legacy:
      When true, if PlatformRuntime fails, fall back to the old path.
    """

    execution_mode: ExecutionMode = "legacy"
    review_coding_mode: ExecutionMode = "legacy"
    fallback_to_legacy: bool = True
    registry_dir: str = ".icoder"
    log_shadow_diff: bool = True

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        """Load config from environment variables.

        ICODER_REVIEW_CODING_MODE follows ICODER_EXECUTION_MODE when not explicitly set.
        """
        exec_mode = _env_mode("ICODER_EXECUTION_MODE", "legacy")
        review_env = os.environ.get("ICODER_REVIEW_CODING_MODE")
        review_mode = _env_mode("ICODER_REVIEW_CODING_MODE", exec_mode) if review_env is not None else exec_mode
        return cls(
            execution_mode=exec_mode,
            review_coding_mode=review_mode,
            fallback_to_legacy=os.environ.get("ICODER_FALLBACK_TO_LEGACY", "true").lower() == "true",
            registry_dir=os.environ.get("ICODER_REGISTRY_DIR", ".icoder"),
            log_shadow_diff=os.environ.get("ICODER_LOG_SHADOW_DIFF", "true").lower() == "true",
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RuntimeConfig":
        """Load config from a YAML file (if PyYAML is available)."""
        path = Path(path)
        if not path.exists():
            return cls.from_env()

        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except ImportError:
            # Fall back to JSON
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}

        rt = data.get("runtime", data)
        return cls(
            execution_mode=_valid_mode(rt.get("execution_mode", "legacy")),
            review_coding_mode=_valid_mode(rt.get("review_coding_mode", "legacy")),
            fallback_to_legacy=rt.get("fallback_to_legacy", True),
            registry_dir=rt.get("registry_dir", ".icoder"),
            log_shadow_diff=rt.get("log_shadow_diff", True),
        )

    def is_legacy(self, mode: str = "execution") -> bool:
        val = self.execution_mode if mode == "execution" else self.review_coding_mode
        return val == "legacy"

    def is_shadow(self, mode: str = "execution") -> bool:
        val = self.execution_mode if mode == "execution" else self.review_coding_mode
        return val == "shadow"

    def is_platform_runtime(self, mode: str = "execution") -> bool:
        val = self.execution_mode if mode == "execution" else self.review_coding_mode
        return val == "platform_runtime"

    def should_shadow_run(self, mode: str = "execution") -> bool:
        """Shadow mode: old path returns, new path runs in background."""
        return self.is_shadow(mode)

    def should_use_new_path(self, mode: str = "execution") -> bool:
        """New path is primary: platform_runtime mode."""
        return self.is_platform_runtime(mode)


def _env_mode(key: str, default: str) -> ExecutionMode:
    val = os.environ.get(key, default).lower()
    try:
        return _valid_mode(val)
    except ValueError:
        return default  # type: ignore[return-value]


def _valid_mode(val: str) -> ExecutionMode:
    if val in ("legacy", "platform_runtime", "shadow"):
        return val  # type: ignore[return-value]
    raise ValueError(f"Invalid mode: {val!r}. Must be legacy, platform_runtime, or shadow.")
