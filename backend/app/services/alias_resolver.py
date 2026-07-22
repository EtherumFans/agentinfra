"""AliasResolver — resolves Agent/Expert alias keys to canonical keys.

A1B-AE.4 carries forward the A1B-AE.2 §3.4 canonical-name rule:

    For dual-named pairs, the dash-form is canonical (matches Corti
    public convention and Pack metadata). Legacy underscore-form is
    retained as an alias.

This service is the application-layer half of the clone-404 fix. The
data-layer half (Migration 023) populates ``agents.canonical_key`` +
``agents.aliases`` for the 3 known dual-named legacy Pack Agents.

The resolver is hermetic: it loads aliases.json + migrations.json
once at startup and serves from memory. No DB or network calls in
the hot path.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AliasResolver:
    """Resolves legacy names → canonical names for Agents and Experts.

    Sources of truth (in priority order):

    1. ``backend/agent_catalog/aliases.json`` (A1B-AE.2 §3.4 canonical)
    2. ``agents.canonical_key`` + ``agents.aliases`` (DB-row level)
    3. ``expert_catalog.json`` entries (Expert level)
    """

    def __init__(self) -> None:
        self._aliases: dict[str, str] = {}
        self._reasons: dict[str, str] = {}
        self._loaded = False

    def load(self, catalog_dir: Optional[Path] = None) -> None:
        """Eagerly load alias mappings from the A1B-AE.2 catalog.

        Safe to call multiple times — only the first call does work.
        """
        if self._loaded:
            return

        catalog_dir = catalog_dir or self._default_catalog_dir()
        aliases_path = catalog_dir / "aliases.json"
        if not aliases_path.exists():
            logger.warning(
                "AliasResolver: aliases.json not found at %s — "
                "resolver will be a no-op until rebuilt",
                aliases_path,
            )
            self._loaded = True
            return

        data = json.loads(aliases_path.read_text(encoding="utf-8"))
        for entry in data.get("entries", []):
            alias = entry.get("alias")
            canonical = entry.get("canonical")
            reason = entry.get("reason", "")
            if alias and canonical and alias != canonical:
                self._aliases[alias] = canonical
                self._reasons[alias] = reason

        self._loaded = True
        logger.info(
            "AliasResolver: loaded %d alias mappings from %s",
            len(self._aliases),
            aliases_path,
        )

    def _default_catalog_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "agent_catalog"

    def resolve_agent_key(self, key: str) -> str:
        """Resolve a possibly-aliased Agent key to its canonical form.

        Returns the input unchanged if no alias is known. This makes
        the resolver safe to use unconditionally on any user-provided
        key — unknown keys pass through, known aliases get rewritten.
        """
        if not key:
            return key
        self.load()
        return self._aliases.get(key, key)

    def resolve_expert_key(self, key: str) -> str:
        """Resolve a possibly-aliased Expert key.

        Currently identical to resolve_agent_key because the A1B-AE.2
        catalog uses a single aliases.json for both. Kept as a
        separate method for clarity at call sites and to allow
        Expert-specific aliasing in a future phase.
        """
        return self.resolve_agent_key(key)

    def is_alias(self, key: str) -> bool:
        """True iff ``key`` is a known legacy alias (not canonical)."""
        self.load()
        return key in self._aliases

    def canonical_for(self, alias: str) -> Optional[str]:
        """Return the canonical key for ``alias``, or None if unknown."""
        self.load()
        return self._aliases.get(alias)

    def all_aliases(self) -> dict[str, str]:
        """Return a copy of the full alias → canonical mapping."""
        self.load()
        return dict(self._aliases)

    def reason_for(self, alias: str) -> Optional[str]:
        """Return the human-readable reason for an alias, or None."""
        self.load()
        return self._reasons.get(alias)


# Module-level singleton — hermetic, no DB calls, safe to share.
alias_resolver = AliasResolver()
