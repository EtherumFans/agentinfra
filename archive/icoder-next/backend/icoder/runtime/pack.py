"""AgentPackageV1 — the ``.icoder-agent`` pack format + a local Marketplace.

Phase 4 of the slice: Agent 打包/分发. A thin Agent is just an ``AgentDefinition`` (role +
mounted Experts + declared rule sets); packing it makes it *distributable* — the ISV/operator
lifecycle the full product runs as ``pack → Marketplace publish → install → AgentRunner``.

Pack format (stdlib ``zipfile`` only — a real container, zero external deps):
  ``<id>-<version>.icoder-agent``  is a zip holding one ``manifest.json``::

      {"schema": "icoder-agent/v1",
       "digest": "sha256:…",          # over the CANONICAL json of "agent"
       "packed_at": <epoch>, "packer": "…",
       "agent": { …the 9 AgentDefinition fields… }}

The digest is computed over the canonical (sorted-key, UTF-8) serialization of the ``agent``
body, so any post-pack edit to the manifest is caught on install — install of a tampered or
wrong-schema pack *refuses* rather than silently registering a mutated agent. A zip (not a bare
json) keeps the contract open: a pack can later carry experts/assets without changing callers.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import zipfile
from dataclasses import asdict, fields
from pathlib import Path

from .registry import AgentDefinition, AgentRegistry

PACK_SCHEMA = "icoder-agent/v1"
MARKET_SCHEMA = "icoder-marketplace/v1"
PACKER = "icoder-next-pack@0.1.0"
PACK_SUFFIX = ".icoder-agent"
_MANIFEST = "manifest.json"


class PackError(RuntimeError):
    """Base for pack/marketplace failures."""


class PackSchemaError(PackError):
    """The pack is malformed or its schema is unknown."""


class PackIntegrityError(PackError):
    """The manifest digest does not match the agent body — the pack was tampered with."""


# --- canonicalization + digest -------------------------------------------------------------

_AGENT_FIELDS = {f.name for f in fields(AgentDefinition)}


def _canonical(agent_body: dict) -> bytes:
    # sorted keys + UTF-8 (ensure_ascii=False keeps the Chinese system_prompt stable) so the
    # digest is reproducible across packs of the same agent.
    return json.dumps(
        agent_body, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _digest(agent_body: dict) -> str:
    return "sha256:" + hashlib.sha256(_canonical(agent_body)).hexdigest()


def _safe_stem(agent_id: str, version: str) -> str:
    # icoder/homepage-coding-review-agent -> icoder__homepage-coding-review-agent-1.0.0
    return f"{agent_id.replace('/', '__')}-{version}"


# --- agent <-> manifest --------------------------------------------------------------------

def agent_to_manifest(agent: AgentDefinition) -> dict:
    body = asdict(agent)
    return {
        "schema": PACK_SCHEMA,
        "digest": _digest(body),
        "packed_at": time.time(),
        "packer": PACKER,
        "agent": body,
    }


def manifest_to_agent(manifest: dict) -> AgentDefinition:
    body = manifest["agent"]
    # tolerate forward-compat extra keys: keep only the known dataclass fields
    kw = {k: v for k, v in body.items() if k in _AGENT_FIELDS}
    return AgentDefinition(**kw)


# --- pack / read / verify ------------------------------------------------------------------

def pack(agent: AgentDefinition, out_dir: str) -> str:
    """Write ``<out_dir>/<id>-<version>.icoder-agent`` and return its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{_safe_stem(agent.id, agent.version)}{PACK_SUFFIX}"
    manifest = agent_to_manifest(agent)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(_MANIFEST, payload)
    return str(path)


def read_manifest(pack_path: str) -> dict:
    p = Path(pack_path)
    if not zipfile.is_zipfile(p):
        raise PackSchemaError(f"{p.name} 不是合法的 .icoder-agent 包（非 zip 容器）")
    with zipfile.ZipFile(p) as z:
        if _MANIFEST not in z.namelist():
            raise PackSchemaError(f"{p.name} 缺少 {_MANIFEST}")
        manifest = json.loads(z.read(_MANIFEST).decode("utf-8"))
    if manifest.get("schema") != PACK_SCHEMA:
        raise PackSchemaError(f"未知的包 schema: {manifest.get('schema')!r}")
    if "agent" not in manifest or "digest" not in manifest:
        raise PackSchemaError("manifest 缺少 agent / digest 字段")
    return manifest


def verify_pack(pack_path: str) -> dict:
    """Read + integrity-check a pack. Raises on schema/digest failure; returns the manifest."""
    manifest = read_manifest(pack_path)
    expected = manifest["digest"]
    actual = _digest(manifest["agent"])
    if actual != expected:
        raise PackIntegrityError(
            f"包完整性校验失败：manifest digest={expected} 但内容 digest={actual}（疑似被篡改）"
        )
    return manifest


def install(pack_path: str, registry: AgentRegistry) -> AgentDefinition:
    """Verify a pack then register its agent into ``registry``. Returns the agent."""
    manifest = verify_pack(pack_path)
    agent = manifest_to_agent(manifest)
    registry.register(agent)
    return agent


# --- version helpers -----------------------------------------------------------------------

def _version_key(v: str) -> tuple:
    parts = []
    for seg in str(v).split("."):
        parts.append((0, int(seg)) if seg.isdigit() else (1, seg))
    return tuple(parts)


# --- Marketplace ---------------------------------------------------------------------------

class Marketplace:
    """A directory-backed marketplace: ``packs/`` + ``index.json``.

    ``publish`` verifies a pack and copies it in (idempotent per id+version); ``install``
    resolves an id (latest version unless pinned) and registers it into a runtime registry.
    """

    def __init__(self, root: str):
        self.root = Path(root)
        self.packs_dir = self.root / "packs"
        self.index_path = self.root / "index.json"

    def _load_index(self) -> dict:
        if self.index_path.is_file():
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        return {"schema": MARKET_SCHEMA, "packs": []}

    def _save_index(self, index: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def publish(self, pack_path: str) -> dict:
        manifest = verify_pack(pack_path)
        agent = manifest["agent"]
        self.packs_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{_safe_stem(agent['id'], agent['version'])}{PACK_SUFFIX}"
        dest = self.packs_dir / filename
        if Path(pack_path).resolve() != dest.resolve():
            shutil.copyfile(pack_path, dest)
        entry = {
            "id": agent["id"], "version": agent["version"], "name": agent["name"],
            "category": agent["category"], "digest": manifest["digest"],
            "filename": filename, "published_at": time.time(),
        }
        index = self._load_index()
        # upsert by (id, version): re-publishing the same coordinates replaces the entry
        index["packs"] = [
            e for e in index["packs"]
            if not (e["id"] == entry["id"] and e["version"] == entry["version"])
        ]
        index["packs"].append(entry)
        self._save_index(index)
        return entry

    def list(self) -> list[dict]:
        return self._load_index()["packs"]

    def _resolve(self, agent_id: str, version: str | None) -> dict:
        candidates = [e for e in self.list() if e["id"] == agent_id]
        if version is not None:
            candidates = [e for e in candidates if e["version"] == version]
        if not candidates:
            raise PackError(f"marketplace 中未找到 agent {agent_id!r}"
                            + (f"@{version}" if version else ""))
        return max(candidates, key=lambda e: _version_key(e["version"]))

    def install(self, agent_id: str, registry: AgentRegistry,
                version: str | None = None) -> AgentDefinition:
        entry = self._resolve(agent_id, version)
        return install(str(self.packs_dir / entry["filename"]), registry)
