# iCoDer - LLM Service (DeepSeek V4 Pro)
import asyncio
import json
import logging
import os
import random
from typing import Optional, AsyncIterator
from openai import AsyncOpenAI
from app.config import settings
from app.services.token_tracker import global_tracker
from app.services.circuit_breaker import llm_circuit_breaker

logger = logging.getLogger(__name__)


def _is_transient_error(exc: Exception) -> bool:
    """Return True if the error is transient and worth retrying.
    Permanent errors (auth, bad request, context length) skip retry entirely.
    """
    status = getattr(exc, "status_code", None)
    # Transient: rate-limit, server errors, network issues
    if status in (429, 500, 502, 503, 504):
        return True
    # Permanent: auth, bad request, not found, context too long
    if status in (401, 403, 400, 404, 413):
        return False
    msg = str(exc).lower()
    permanent_indicators = [
        "invalid_api_key", "insufficient_quota", "context_length_exceeded",
        "invalid_request_error", "account_deactivated", "invalid model",
    ]
    if any(ind in msg for ind in permanent_indicators):
        return False
    # Network-level errors are transient
    if "connection" in msg or "timeout" in msg or "reset" in msg:
        return True
    # Default: assume transient for safety
    return True


def _resolve_api_key() -> str:
    """Resolve LLM API key from Credential Vault or environment.
    Priority: env var > config file. Never log the key value.
    """
    key = os.environ.get("ICODER_CREDENTIAL_LLM", "")
    if key:
        return key
    # Fallback: config value (for dev environments)
    if settings.LLM_API_KEY:
        return settings.LLM_API_KEY
    # Legacy: check old env var name
    return os.environ.get("DEEPSEEK_API_KEY", "")


class LLMService:
    """Unified LLM interface. Defaults to DeepSeek V4 Pro.

    API key is resolved from Credential Vault (env var ICODER_CREDENTIAL_LLM)
    at initialization time. The key is never logged or serialized.
    """

    def __init__(self):
        api_key = _resolve_api_key()
        if not api_key:
            logger.warning("LLM API key not configured. Set ICODER_CREDENTIAL_LLM environment variable.")
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT,
        )
        self.model = settings.LLM_MODEL
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.temperature = settings.LLM_TEMPERATURE
        self.max_retries = settings.AGENT_MAX_RETRIES

    async def chat(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
    ) -> dict:
        """Send chat completion and return result with token counts."""
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        if llm_circuit_breaker.is_open:
            raise RuntimeError("LLM circuit breaker is OPEN — provider appears unhealthy")

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(**kwargs)
                llm_circuit_breaker.record_success()
                choice = response.choices[0]
                prompt_tokens = response.usage.prompt_tokens if response.usage else 0
                completion_tokens = response.usage.completion_tokens if response.usage else 0
                total_tokens = response.usage.total_tokens if response.usage else 0
                global_tracker.record(prompt_tokens, completion_tokens, total_tokens)
                return {
                    "content": choice.message.content or "",
                    "role": choice.message.role,
                    "finish_reason": choice.finish_reason,
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                }
            except Exception as e:
                last_error = e
                llm_circuit_breaker.record_failure()
                if not _is_transient_error(e):
                    logger.error(f"LLM call failed with permanent error: {type(e).__name__}: {e}")
                    raise RuntimeError(f"LLM call failed (permanent): {e}") from e
                logger.warning(f"LLM call attempt {attempt + 1} failed (transient): {e}")
                if attempt < self.max_retries:
                    delay = (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)

        raise RuntimeError(f"LLM call failed after {self.max_retries + 1} attempts: {last_error}")

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Stream chat completion tokens via async generator.

        Usage:
            async for chunk in llm_service.chat_stream(messages):
                yield chunk  # Each chunk is a text fragment
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            yield f"\n[Stream error: {e}]"

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> dict:
        """Chat with function/tool calling support."""
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        if llm_circuit_breaker.is_open:
            raise RuntimeError("LLM circuit breaker is OPEN — provider appears unhealthy")

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    tools=tools,
                    temperature=temperature or self.temperature,
                    max_tokens=self.max_tokens,
                )
                llm_circuit_breaker.record_success()
                choice = response.choices[0]
                msg = choice.message
                prompt_tokens = response.usage.prompt_tokens if response.usage else 0
                completion_tokens = response.usage.completion_tokens if response.usage else 0
                total_tokens = response.usage.total_tokens if response.usage else 0
                global_tracker.record(prompt_tokens, completion_tokens, total_tokens)
                result = {
                    "content": msg.content or "",
                    "role": msg.role,
                    "finish_reason": choice.finish_reason,
                    "tool_calls": [],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                }
                if msg.tool_calls:
                    result["tool_calls"] = [
                        {
                            "id": tc.id,
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ]
                return result
            except Exception as e:
                last_error = e
                llm_circuit_breaker.record_failure()
                if not _is_transient_error(e):
                    logger.error(f"LLM tool call failed with permanent error: {type(e).__name__}: {e}")
                    raise RuntimeError(f"LLM tool call failed (permanent): {e}") from e
                logger.warning(f"LLM tool call attempt {attempt + 1} failed (transient): {e}")
                if attempt < self.max_retries:
                    delay = (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)

        raise RuntimeError(f"LLM tool call failed after {self.max_retries + 1} attempts: {last_error}")

    async def extract_json(self, prompt: str, text: str, schema_hint: Optional[str] = None) -> dict:
        """Extract structured JSON from text using LLM."""
        system = f"""You are a precise medical data extraction system.
Extract the requested information from the medical text and output ONLY valid JSON.
Do not add explanations. Follow the exact schema requested."""

        if schema_hint:
            system += f"\n\nExpected JSON structure:\n{schema_hint}"

        result = await self.chat(
            messages=[{"role": "user", "content": f"{prompt}\n\nText:\n{text}"}],
            system_prompt=system,
            temperature=0.05,
            response_format="json",
        )
        try:
            return json.loads(result["content"])
        except json.JSONDecodeError:
            content = result["content"]
            # Try to extract JSON from markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content.strip())


# Singleton
llm_service = LLMService()
