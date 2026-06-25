"""MCP handlers — one module per tool, each a thin wrapper.

Each handler signature is ``async def handle(arguments: dict, request: Request) -> dict``.
The server resolves the dotted-path ``handler_ref`` from
:data:`app.icoder.mcp.tool_registry.TOOL_REGISTRY` and dispatches here.
"""

from __future__ import annotations