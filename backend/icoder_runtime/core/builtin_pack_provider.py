"""BuiltinAgentPackProvider — loads official Agent Packs from filesystem.

P1.1-B: uses ``agent_pack_loader`` to classify packs by status before
attempting registration.

Classification outcomes:

* ``INVALID``            → logged, never registered
* ``METADATA_ONLY``      → logged, never registered (Phase D stubs await
                            real expert wiring — surfaced in compat report)
* ``EXECUTABLE``         → forwarded to ``platform_runtime.install_agent``
                            (which still runs the legacy v1.1 validator
                            — packs with v1.2-only fields are accepted
                            via the loader's permissive validation)

Per-pack status is exposed via :func:`discover_all` for the Agent Hub,
Doctor, and CLI consumers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .agent_pack_loader import load_pack, discover_v1_files, load_packs_from_dir, why_not_executable
from .agent_pack_schema import NormalizedPack, PackStatus
from .registry_status import (
    AgentCompatibilityEntry,
    RegistryCompatibilityReport,
    compute_compatibility,
)

logger = logging.getLogger(__name__)


class BuiltinAgentPackProvider:
    """Discovers and registers built-in Agent Packs from the filesystem.

    Directory structure:
      official_agents/
        medical_coding/agent_pack.json
        a2a_experts/
          icd10_diagnosis_expert.json
          procedure_coding_expert.json
          ...
    """

    def __init__(self, agents_dir: str | Path):
        self._dir = Path(agents_dir)
        self._packs: list[dict] = []
        self._normalized: list[NormalizedPack] = []

    def discover(self) -> list[dict]:
        """Discover all agent pack files in the directory tree."""
        packs = []
        # Direct subdirectory packs (e.g., medical_coding/)
        for child in self._dir.iterdir():
            if child.is_dir():
                pack_file = child / "agent_pack.json"
                if pack_file.exists():
                    try:
                        pack = json.loads(pack_file.read_text(encoding="utf-8"))
                        packs.append(pack)
                        logger.info(f"Discovered agent pack: {child.name}")
                    except Exception as e:
                        logger.warning(f"Failed to load {pack_file}: {e}")
            elif child.suffix == ".json":
                try:
                    pack = json.loads(child.read_text(encoding="utf-8"))
                    packs.append(pack)
                except Exception as e:
                    logger.warning(f"Failed to load {child}: {e}")

        # A2A experts subdirectory
        a2a_dir = self._dir / "a2a_experts"
        if a2a_dir.exists():
            for pack_file in a2a_dir.glob("*.json"):
                try:
                    pack = json.loads(pack_file.read_text(encoding="utf-8"))
                    packs.append(pack)
                    logger.info(f"Discovered A2A expert pack: {pack_file.stem}")
                except Exception as e:
                    logger.warning(f"Failed to load {pack_file}: {e}")

        self._packs = packs
        return packs

    def discover_all(self) -> list[NormalizedPack]:
        """Discover + load via the new loader; return normalized views.

        Skips __pycache__ and hidden directories. Returns both valid and
        invalid packs (status=INVALID) so callers can surface them.
        """
        self._normalized = load_packs_from_dir(self._dir)
        # Also include a2a_experts/*.json
        a2a_dir = self._dir / "a2a_experts"
        if a2a_dir.exists():
            for pack_file in a2a_dir.glob("*.json"):
                try:
                    raw = json.loads(pack_file.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning(f"[builtin_pack_provider] failed to parse {pack_file}: {e}")
                    continue
                normalized = load_pack(raw, source_path=str(pack_file))
                self._normalized.append(normalized)
        return self._normalized

    def compatibility_report(self, registry=None) -> RegistryCompatibilityReport:
        """Run the loader on every pack + cross-ref registry.

        Returns a RegistryCompatibilityReport enumerating per-pack status
        (executable / metadata_only / invalid), production_ready flag,
        registry presence, and human-readable "why not executable" list.
        """
        return compute_compatibility(self._dir, registry=registry)

    def register_all(self, platform_runtime) -> int:
        """Register every EXECUTABLE pack into the PlatformRuntime.

        Returns the count of packs actually registered. METADATA_ONLY and
        INVALID packs are logged but skipped.

        Note: this method requires platform_runtime.install_agent() to
        succeed. For packs that are EXECUTABLE per the loader but still
        fail the legacy v1.1 validator (rare — the loader is permissive
        on tool shape), the legacy error is logged and the pack is left
        in METADATA_ONLY.
        """
        if not self._normalized:
            self.discover_all()

        count = 0
        for np in self._normalized:
            label = f"{np.name or np.agent_ref}@{np.version}"
            if np.status == PackStatus.INVALID:
                logger.warning(
                    f"Skipping {label}: INVALID — {len(np.validation_errors)} validation error(s)"
                )
                continue
            if np.status == PackStatus.METADATA_ONLY:
                reasons = why_not_executable(np)
                first_reason = reasons[0] if reasons else "see loader"
                logger.info(
                    f"Skipping {label}: METADATA_ONLY (no executable wiring). "
                    f"Reason: {first_reason}"
                )
                continue
            # EXECUTABLE — try to register
            try:
                platform_runtime.install_agent(
                    np.raw,
                    publisher_name=np.publisher_name or "iCoDer",
                    publisher_email=np.publisher_email or "hello@icoder.ai",
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to register pack {label}: {e}")
        return count