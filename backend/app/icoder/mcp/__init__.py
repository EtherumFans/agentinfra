"""MCP server package (M2).

Re-exports the public surface so callers can ``from app.icoder.mcp import mount_mcp``.
"""

from .errors import MCPError, MCPErrorCode
from .server import mount_mcp
from .tool_registry import TOOL_REGISTRY

__all__ = ["mount_mcp", "TOOL_REGISTRY", "MCPError", "MCPErrorCode"]