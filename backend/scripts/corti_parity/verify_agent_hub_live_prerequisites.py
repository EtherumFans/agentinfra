"""Fail closed on live-CI configuration, migrated schema and Registry health.

This preflight never invokes a model or writes to the application database.
Only bounded metadata is emitted; credentials and server error bodies are not.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import requests
from icoder_runtime.core.data_policy import RuntimeDataPolicy


def configuration_errors() -> list[str]:
    errors = []
    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        errors.append("live credential missing")
    for name in ("ICODER_ALLOW_DEGRADED_NO_KEY", "ICODER_DISABLE_AUTH_FOR_TESTS"):
        if os.environ.get(name) != "0":
            errors.append(f"{name} must be 0")
    provider = os.environ.get("LLM_PROVIDER", "deepseek")
    allowed, _ = RuntimeDataPolicy.from_env().can_use_provider(provider)
    if provider != "deepseek" or not allowed:
        errors.append("authorized DeepSeek egress is required")
    if not os.environ.get("DATABASE_URL", "").startswith("postgresql+asyncpg://"):
        errors.append("an isolated PostgreSQL asyncpg database is required")
    return errors


def runtime_errors(status: dict) -> list[str]:
    errors = []
    if status.get("started") is not True:
        errors.append("runtime not started")
    sync = status.get("registry_sync") or {}
    if sync.get("last_status") != "success" or sync.get("agents_failed") != 0:
        errors.append("Registry DB sync not successful")
    count = sync.get("total_in_registry")
    if not isinstance(count, int) or count < 26 or sync.get("total_in_db") != count:
        errors.append("Registry DB projection incomplete")
    return errors


async def schema_evidence() -> dict:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.database import PRODUCTION_SCHEMA_REVISION

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == [PRODUCTION_SCHEMA_REVISION], "cloud-start/head mismatch"
    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            revision = (await connection.execute(text(
                "SELECT version_num FROM alembic_version"
            ))).scalar_one()
            width = (await connection.execute(text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='agents' "
                "AND column_name='default_expert_id'"
            ))).scalar_one()
            runtime_width = (await connection.execute(text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='run_history' "
                "AND column_name='runtime_mode'"
            ))).scalar_one()
        assert revision == heads[0], "database/head mismatch"
        assert width == 128, "Pack expert identifier width mismatch"
        assert runtime_width == 128, "audit runtime identifier width mismatch"
        return {
            "revision": revision, "default_expert_id_width": width,
            "runtime_mode_width": runtime_width,
        }
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {"source_revision": os.environ.get("GITHUB_SHA", ""), "errors": []}
    errors = report["errors"]
    errors.extend(configuration_errors())
    if urlsplit(args.base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        errors.append("live preflight requires an isolated loopback API")
    if not errors:
        try:
            report["schema"] = asyncio.run(schema_evidence())
            response = requests.get(
                args.base_url.rstrip("/") + "/api/runtime-platform/status", timeout=15,
            )
            response.raise_for_status()
            status = response.json()
            errors.extend(runtime_errors(status))
            sync = status.get("registry_sync") or {}
            report["registry"] = {key: sync.get(key) for key in (
                "last_status", "agents_failed", "total_in_registry", "total_in_db",
            )}
        except Exception as exc:
            errors.append(f"live preflight failed: {type(exc).__name__}")
    report["passed"] = not errors
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
