"""Expert Runner — execute experts with System Prompt + MCP tools + LLM"""
import json
import logging
from app.services.llm_service import llm_service
from app.services.mcp_client import mcp_client
from app.models.expert import Expert, McpServer

logger = logging.getLogger(__name__)


class ExpertRunner:
    """Execute an Expert by composing system_prompt + MCP tools + LLM."""

    async def run(
        self,
        expert: Expert,
        user_input: str,
        conversation_history: list[dict] | None = None,
        mcp_servers: list[McpServer] | None = None,
    ) -> str:
        conversation_history = conversation_history or []
        mcp_servers = mcp_servers or []

        system_content = expert.system_prompt or f"You are {expert.name}. {expert.description}"
        messages = [{"role": "system", "content": system_content}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_input})

        tools = None
        if mcp_servers:
            tools = []
            for srv in mcp_servers:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": srv.name.replace(" ", "_").replace("-", "_").lower(),
                        "description": srv.description or f"Call {srv.name} at {srv.url}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": f"Query for {srv.name}"}
                            },
                            "required": ["query"],
                        },
                    },
                })

        try:
            if tools:
                result = await llm_service.chat_with_tools(messages=messages, tools=tools, temperature=0.1)
                if isinstance(result, dict) and result.get("tool_calls"):
                    output = await self._handle_tool_calls(result["tool_calls"], messages, mcp_servers)
                elif isinstance(result, dict) and result.get("content"):
                    output = result["content"]
                else:
                    output = str(result)
            else:
                result = await llm_service.chat(messages=messages, temperature=0.1)
                output = result.get("content", "") if isinstance(result, dict) else str(result)
                if not output:
                    output = "No output generated."
        except Exception as e:
            logger.error(f"ExpertRunner error for {expert.name}: {e}")
            output = f"Error running expert: {str(e)}"

        return output

    async def stream_run(
        self, expert: Expert, user_input: str,
        conversation_history: list[dict] | None = None,
    ):
        """Stream expert response token by token via DeepSeek stream."""
        history = conversation_history or []
        system_content = expert.system_prompt or f"You are {expert.name}."
        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})
        async for token in llm_service.chat_stream(messages=messages, temperature=0.1):
            yield token

    async def _handle_tool_calls(
        self, tool_calls: list[dict], messages: list[dict], mcp_servers: list[McpServer]
    ) -> str:
        """Execute real MCP tool calls and return final LLM response."""
        server_map = {}
        for srv in mcp_servers:
            tool_name = srv.name.replace(" ", "_").replace("-", "_").lower()
            server_map[tool_name] = srv

        for tc in tool_calls:
            func_name = tc.get("function", {}).get("name", "")
            func_args = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(func_args) if isinstance(func_args, str) else func_args
            except json.JSONDecodeError:
                args = {"query": str(func_args)}
            query = args.get("query", "")
            srv = server_map.get(func_name)
            if srv:
                tool_result = await self._real_mcp_call(srv, query)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call_1"),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

        try:
            result = await llm_service.chat(messages=messages, temperature=0.1)
            return result.get("content", "") if isinstance(result, dict) else str(result)
        except Exception as e:
            logger.error(f"_handle_tool_calls error: {e}")
            return f"Tool calls completed but final response failed: {e}"

    async def _real_mcp_call(self, srv: McpServer, query: str) -> dict:
        """Real MCP server call via McpClient. Falls back to mock for unknown services."""
        service = self._detect_service(srv)
        if service:
            return await mcp_client.call(service, "search", {"query": query})
        return self._mock_mcp_call(srv, query)

    def _detect_service(self, srv: McpServer) -> str | None:
        """Detect which MCP service a server connects to."""
        name_lower = srv.name.lower()
        url_lower = srv.url.lower() if srv.url else ""
        if "pubmed" in name_lower or "pubmed" in url_lower or "ncbi" in url_lower:
            return "pubmed"
        if "clinical" in name_lower and "trial" in name_lower:
            return "clinical_trials"
        if "drugbank" in name_lower or "drugbank" in url_lower:
            return "drugbank"
        if "posos" in name_lower:
            return "posos"
        if "web" in name_lower and "search" in name_lower:
            return "web_search"
        return None

    def _mock_mcp_call(self, srv: McpServer, query: str) -> dict:
        """Mock MCP call for services without real API access."""
        return {"source": srv.name, "query": query, "response": f"Mock response from {srv.name}: results for '{query}'"}


expert_runner = ExpertRunner()
