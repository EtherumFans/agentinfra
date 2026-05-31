"""Test MCP Client + Wrapper"""
import pytest
from app.services.mcp_client import mcp_client
from app.services.mcp_wrapper import mcp_wrapper


@pytest.mark.asyncio
async def test_mcp_client_unknown_service():
    result = await mcp_client.call("unknown_service", "test", {"query": "test"})
    assert "error" in result


@pytest.mark.asyncio
async def test_mcp_client_pubmed_search():
    result = await mcp_client.call("pubmed", "search", {"query": "ICD-10 coding", "max_results": 2})
    assert result["source"] == "PubMed"
    assert "results" in result
    assert isinstance(result["results"], list)


def test_mcp_wrapper_tools_to_openai_format():
    mcp_tools = [
        {"name": "search_pubmed", "description": "Search PubMed", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}}
    ]
    openai_tools = mcp_wrapper.tools_to_openai_format(mcp_tools)
    assert len(openai_tools) == 1
    assert openai_tools[0]["type"] == "function"
    assert openai_tools[0]["function"]["name"] == "search_pubmed"


def test_mcp_wrapper_tools_to_openai_empty():
    openai_tools = mcp_wrapper.tools_to_openai_format([])
    assert openai_tools == []


@pytest.mark.asyncio
async def test_mcp_wrapper_discover_tools_invalid_url():
    tools = await mcp_wrapper.discover_tools("http://localhost:99999/nonexistent")
    assert tools == []  # gracefully handles unreachable servers
