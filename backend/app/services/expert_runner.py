"""Expert Runner — execute experts with System Prompt + MCP tools + LLM"""
import json
import logging
from app.services.llm_service import llm_service
from app.services.mcp_client import mcp_client
from app.models.expert import Expert, McpServer
from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload

logger = logging.getLogger(__name__)


class ExpertRunnerError(RuntimeError):
    """Safe, caller-visible failure from the legacy Expert runtime."""


class ExpertExecutionError(ExpertRunnerError):
    """The Expert could not produce a valid response."""


class MCPToolExecutionError(ExpertRunnerError):
    """A configured MCP tool call failed closed."""


class UnsupportedMCPServiceError(MCPToolExecutionError):
    """The requested MCP server has no production connector."""


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

        try:
            safe_payload = redact_payload({
                "user_input": user_input,
                "conversation_history": conversation_history,
            }).value
        except Exception:
            logger.warning("ExpertRunner PHI boundary failed")
            raise ExpertExecutionError(
                "Expert input could not be safely de-identified"
            ) from None

        user_input = safe_payload["user_input"]
        conversation_history = safe_payload["conversation_history"]

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
                elif isinstance(result, dict) and isinstance(result.get("content"), str):
                    output = result["content"].strip()
                else:
                    raise ExpertExecutionError("LLM returned an invalid Expert response")
            else:
                result = await llm_service.chat(messages=messages, temperature=0.1)
                output = result.get("content", "").strip() if isinstance(result, dict) else ""
            if not output:
                raise ExpertExecutionError("LLM returned an empty Expert response")
        except ExpertRunnerError:
            raise
        except Exception as exc:
            logger.error(
                "ExpertRunner failed expert_id=%s error_type=%s",
                getattr(expert, "id", ""),
                type(exc).__name__,
            )
            raise ExpertExecutionError("Expert execution failed") from None

        return output

    async def stream_run(
        self, expert: Expert, user_input: str,
        conversation_history: list[dict] | None = None,
    ):
        """Stream expert response token by token via DeepSeek stream."""
        try:
            safe_payload = redact_payload({
                "user_input": user_input,
                "conversation_history": conversation_history or [],
            }).value
        except Exception:
            logger.warning("ExpertRunner streaming PHI boundary failed")
            raise ExpertExecutionError(
                "Expert input could not be safely de-identified"
            ) from None
        history = safe_payload["conversation_history"]
        user_input = safe_payload["user_input"]
        system_content = expert.system_prompt or f"You are {expert.name}."
        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})
        try:
            async for token in llm_service.chat_stream(messages=messages, temperature=0.1):
                yield token
        except Exception as exc:
            logger.error(
                "ExpertRunner stream failed expert_id=%s error_type=%s",
                getattr(expert, "id", ""),
                type(exc).__name__,
            )
            raise ExpertExecutionError("Expert streaming failed") from None

    async def _handle_tool_calls(
        self, tool_calls: list[dict], messages: list[dict], mcp_servers: list[McpServer]
    ) -> str:
        """Execute real MCP tool calls and return final LLM response."""
        server_map = {}
        for srv in mcp_servers:
            tool_name = srv.name.replace(" ", "_").replace("-", "_").lower()
            server_map[tool_name] = srv

        messages.append({"role": "assistant", "content": "", "tool_calls": tool_calls})
        for tc in tool_calls:
            func_name = tc.get("function", {}).get("name", "")
            func_args = tc.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(func_args) if isinstance(func_args, str) else func_args
            except json.JSONDecodeError:
                raise MCPToolExecutionError("MCP tool arguments are invalid") from None
            if not isinstance(args, dict):
                raise MCPToolExecutionError("MCP tool arguments must be an object")
            query = args.get("query", "")
            srv = server_map.get(func_name)
            if srv is None:
                raise UnsupportedMCPServiceError(
                    "LLM requested an MCP tool outside the configured server set"
                )
            if not isinstance(query, str) or not query.strip():
                raise MCPToolExecutionError("MCP tool query must be a non-empty string")
            tool_result = await self._real_mcp_call(srv, query)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", "call_1"),
                "content": json.dumps(tool_result, ensure_ascii=False),
            })

        try:
            result = await llm_service.chat(messages=messages, temperature=0.1)
        except Exception as exc:
            logger.error(
                "ExpertRunner final synthesis failed error_type=%s",
                type(exc).__name__,
            )
            raise ExpertExecutionError("Expert final synthesis failed") from None
        output = result.get("content", "").strip() if isinstance(result, dict) else ""
        if not output:
            raise ExpertExecutionError("Expert final synthesis returned no content")
        return output

    async def _real_mcp_call(self, srv: McpServer, query: str) -> dict:
        """Call a supported production MCP connector or fail closed."""
        service = self._detect_service(srv)
        if not service:
            raise UnsupportedMCPServiceError(
                "Configured MCP server has no production connector"
            )
        result = await mcp_client.call(service, "search", {"query": query})
        if not isinstance(result, dict) or result.get("error"):
            raise MCPToolExecutionError("MCP connector call failed")
        return result

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

expert_runner = ExpertRunner()


__all__ = [
    "ExpertExecutionError",
    "ExpertRunner",
    "ExpertRunnerError",
    "MCPToolExecutionError",
    "UnsupportedMCPServiceError",
    "expert_runner",
]
