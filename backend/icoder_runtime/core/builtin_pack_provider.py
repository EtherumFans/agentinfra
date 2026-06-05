"""BuiltinAgentPackProvider — loads official Agent Packs from filesystem.

Used at startup to register official agents into the RuntimeAgentRegistry.
Replaces hardcoded A2A expert registration with file-based discovery.

Migration path:
  Phase 1 (current): Load official_agents/medical_coding/agent_pack.json
  Phase 2 (v2.0): Load all official_agents/a2a_experts/*.json
  Phase 3 (v2.1): Remove hardcoded a2a_registry.register_all_experts()
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

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

    def register_all(self, platform_runtime) -> int:
        """Register all discovered packs into the PlatformRuntime. Returns count."""
        count = 0
        for pack in self._packs:
            try:
                platform_runtime.install_agent(
                    pack,
                    publisher_name=pack.get("publisher_name", "iCoDer"),
                    publisher_email=pack.get("publisher_email", "hello@icoder.ai"),
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to register pack {pack.get('manifest',{}).get('name','?')}: {e}")
        return count
