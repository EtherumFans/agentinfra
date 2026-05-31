"""MCP Wrapper — wrap external MCP servers as iCoDer Experts.

iCoDer Agentic Framework equivalent: "Bring Your Own Expert — expose an MCP
server and iCoDer wraps it in a custom LLM agent with a system prompt."

Difficulty: HIGH — implements MCP protocol (tools/list, tools/call), auto-discovers
tool schemas, converts JSON Schema to OpenAI function format, wraps as full Expert.
"""
import json
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)


class McpWrapper:
    """Wraps external MCP servers as iCoDer Experts.

    When a user registers an MCP server, this wrapper:
    1. Auto-discovers available tools from the MCP server
    2. Converts MCP tool schemas to OpenAI function calling format
    3. Creates an LLM agent with a user-provided system prompt
    4. Routes tool calls to the MCP server
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def discover_tools(self, mcp_url: str, auth_header: str | None = None) -> list[dict]:
        """Discover available tools from an MCP server.

        Calls the MCP tools/list endpoint to get available tools with their schemas.
        """
        client = await self._get_client()
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header

        try:
            # MCP JSON-RPC: tools/list
            resp = await client.post(
                mcp_url.rstrip("/") + "/tools/list",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", {}).get("tools", [])
            # Try REST-style endpoint as fallback
            resp2 = await client.get(mcp_url.rstrip("/") + "/tools", headers=headers)
            if resp2.status_code == 200:
                data = resp2.json()
                return data if isinstance(data, list) else data.get("tools", [])
        except Exception as e:
            logger.warning(f"MCP tool discovery failed for {mcp_url}: {e}")

        return []

    def tools_to_openai_format(self, mcp_tools: list[dict]) -> list[dict]:
        """Convert MCP tool schemas to OpenAI function calling format.

        MCP Schema → OpenAI Function:
        {
          "name": "tool_name",
          "description": "...",
          "inputSchema": {"type": "object", "properties": {...}}
        }
        →
        {
          "type": "function",
          "function": {
            "name": "tool_name",
            "description": "...",
            "parameters": {"type": "object", "properties": {...}}
          }
        }
        """
        openai_tools = []
        for tool in mcp_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", "unknown_tool"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Query parameter"}
                        }
                    }),
                },
            })
        return openai_tools

    async def call_tool(
        self, mcp_url: str, tool_name: str, arguments: dict, auth_header: str | None = None
    ) -> dict:
        """Call a tool on an MCP server.

        Uses MCP JSON-RPC tools/call endpoint.
        """
        client = await self._get_client()
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header

        try:
            # MCP JSON-RPC: tools/call
            resp = await client.post(
                mcp_url.rstrip("/") + "/tools/call",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                    "id": 1,
                },
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", {})
            # Fallback: REST-style
            resp2 = await client.post(
                mcp_url.rstrip("/") + f"/tools/{tool_name}",
                json=arguments,
                headers=headers,
            )
            if resp2.status_code == 200:
                return resp2.json()
        except Exception as e:
            logger.error(f"MCP tool call failed: {mcp_url}/{tool_name}: {e}")
            return {"error": str(e)}

        return {"error": f"MCP call returned {resp.status_code if 'resp' in dir() else 'unknown'}"}

    async def create_expert_config(
        self, mcp_url: str, system_prompt: str, name: str = "Custom MCP Expert"
    ) -> dict:
        """Create a complete expert configuration from an MCP server.

        Discovers tools, converts schemas, and returns a full expert config
        ready to be saved and used like any other Expert.
        """
        tools = await self.discover_tools(mcp_url)
        openai_tools = self.tools_to_openai_format(tools)

        return {
            "name": name,
            "description": f"Custom expert wrapping MCP server at {mcp_url}",
            "system_prompt": system_prompt or f"You are {name}. Use available tools to assist the user.",
            "category": "custom",
            "mcp_server_url": mcp_url,
            "tools": openai_tools,
            "tool_count": len(openai_tools),
            "tool_names": [t["function"]["name"] for t in openai_tools],
        }

    async def close(self):
        if self._client:
            await self._client.aclose()


mcp_wrapper = McpWrapper()
