"""Prevent SDK resources from advertising ordinary REST paths that cannot exist."""

from __future__ import annotations

import re
from pathlib import Path


_PATH_LITERAL = re.compile(r"[f]?(['\"`])(/api/.*?)(?<!\\)\1")

# These routes are intentionally mounted inside app.main's lifespan after the
# executable Agent registry is ready, so they do not appear in import-time
# OpenAPI. Dedicated A2A integration suites exercise their HTTP contracts.
_LIFESPAN_A2A_PATHS = {
    "/api/icoder/agents/{}/card",
    # First literal fragment of Python's adjacent f-string Context path.
    "/api/icoder/agents/{}/v1/contexts",
    "/api/icoder/agents/{}/v1/contexts/{}",
    "/api/icoder/agents/{}/v1/message:send",
    "/api/icoder/agents/{}/v1/message:stream",
    "/api/icoder/contexts/{}",
    "/api/v2/agentic/agents/{}",
    "/api/v2/agentic/agents/{}/message:send",
    "/api/v2/agentic/agents/{}/message:stream",
    "/api/v2/agentic/agents/{}/tasks",
    "/api/v2/agentic/agents/{}/tasks/{}",
    "/api/v2/agentic/agents/{}/tasks/{}:cancel",
}

# SDKs validate this fixed prefix before accepting a server-issued, same-origin
# one-time grant URL. The concrete FastAPI route adds the opaque grant id.
_STATIC_ROUTE_PREFIXES = {
    "/api/v2/agentic/artifact-objects/download",
}


def _normalized(path: str) -> str:
    normalized = re.sub(r"\$?\{[^}]+\}", "{}", path)
    normalized = normalized.split("?", 1)[0].rstrip("/")
    # Python's hub resource appends an already-encoded query string variable.
    return normalized.replace("/hub{}", "/hub")


def test_public_sdk_resource_paths_are_real_or_lifespan_mounted():
    from app.main import app

    repository = Path(__file__).resolve().parents[3]
    static_paths = {
        _normalized(path)
        for path in app.openapi()["paths"]
    }
    missing: list[str] = []
    roots = (
        repository / "packages" / "icoder-sdk" / "src" / "resources",
        repository / "packages" / "icoder-python" / "icoder_sdk" / "resources",
    )
    for root in roots:
        for source in sorted((*root.rglob("*.ts"), *root.rglob("*.py"))):
            text = source.read_text(encoding="utf-8")
            for match in _PATH_LITERAL.finditer(text):
                raw_path = match.group(2)
                normalized = _normalized(raw_path)
                prefix_is_real = (
                    normalized in _STATIC_ROUTE_PREFIXES
                    and any(path.startswith(f"{normalized}/{{}}") for path in static_paths)
                )
                if (
                    normalized in static_paths
                    or normalized in _LIFESPAN_A2A_PATHS
                    or prefix_is_real
                ):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                missing.append(
                    f"{source.relative_to(repository)}:{line}: {raw_path}"
                )

    assert missing == [], (
        "SDK resource paths have no FastAPI or approved lifespan A2A route:\n"
        + "\n".join(missing)
    )


def test_removed_legacy_sdk_surfaces_do_not_reappear():
    repository = Path(__file__).resolve().parents[3]
    js_index = (repository / "packages" / "icoder-sdk" / "src" / "index.ts").read_text(
        encoding="utf-8"
    )
    py_init = (
        repository / "packages" / "icoder-python" / "icoder_sdk" / "__init__.py"
    ).read_text(encoding="utf-8")
    py_client = (
        repository / "packages" / "icoder-python" / "icoder_sdk" / "client.py"
    ).read_text(encoding="utf-8")

    for legacy in ("ReviewsResource", "MarketplaceResource"):
        assert legacy not in js_index
        assert legacy not in py_init
        assert legacy not in py_client
