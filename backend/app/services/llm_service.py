# iCoDer - LLM Service (DeepSeek V4 Pro)
# *** DEPRECATED (LLM calling parts) — will be removed in v2.1 ***
# Migration: Use icoder_runtime.core.llm_gateway.LLMGateway instead.
# See MIGRATION_RUNTIME.md for details.
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


class LLMProviderCallError(RuntimeError):
    """Content-free provider failure safe for traces and user-facing logs."""

    def __init__(
        self,
        *,
        category: str,
        status_code: int | None,
        attempts: int,
        retryable: bool,
    ) -> None:
        self.category = category
        self.status_code = status_code
        self.attempts = attempts
        self.retryable = retryable
        super().__init__(
            f"LLM provider call failed ({category}) after {attempts} attempt(s)."
        )


def _classify_provider_error(exc: Exception) -> tuple[str, int | None]:
    """Return a bounded category/status without retaining provider content."""
    if isinstance(exc, LLMProviderCallError):
        return exc.category, exc.status_code
    status = getattr(exc, "status_code", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError, OverflowError):
        status = None
    if status == 429:
        return "rate_limit", status
    if status in {500, 502, 503, 504}:
        return "server_error", status
    if status in {408, 425}:
        return "timeout", status
    if status == 401:
        return "authentication", status
    if status == 403:
        return "permission", status
    if status in {400, 404, 413}:
        return "bad_request", status
    marker = f"{type(exc).__name__} {exc}".lower()
    if "timeout" in marker:
        return "timeout", status
    if "connection" in marker or "reset" in marker:
        return "connection", status
    return "unknown", status


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


def _ensure_llm_call_allowed() -> None:
    """Apply the same fail-closed egress policy as the unified LLMGateway."""

    from icoder_runtime.core.data_policy import (
        RuntimeDataPolicy,
        normalize_provider_name,
    )

    provider = normalize_provider_name(
        os.environ.get("LLM_PROVIDER", settings.LLM_PROVIDER or "mock")
    )
    if provider == "mock":
        raise RuntimeError("LLM provider unavailable: mock mode is development-only")
    allowed, reason = RuntimeDataPolicy.from_env().can_use_provider(provider)
    if not allowed:
        raise RuntimeError(f"LLM provider egress denied by data policy: {reason}")


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

    async def aclose(self) -> None:
        """Close the request-scoped async HTTP connection pool."""
        await self.client.close()

    async def chat(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
    ) -> dict:
        """Send chat completion and return result with token counts."""
        _ensure_llm_call_allowed()
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
            raise LLMProviderCallError(
                category="circuit_open",
                status_code=None,
                attempts=0,
                retryable=True,
            )

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
                retryable = _is_transient_error(e)
                category, status_code = _classify_provider_error(e)
                if not retryable:
                    logger.error(
                        "LLM call failed permanently: category=%s status=%s type=%s",
                        category, status_code, type(e).__name__,
                    )
                    raise LLMProviderCallError(
                        category=category,
                        status_code=status_code,
                        attempts=attempt + 1,
                        retryable=False,
                    ) from e
                logger.warning(
                    "LLM call failed transiently: attempt=%s category=%s status=%s type=%s",
                    attempt + 1, category, status_code, type(e).__name__,
                )
                if attempt < self.max_retries:
                    delay = (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)

        category, status_code = _classify_provider_error(last_error)
        raise LLMProviderCallError(
            category=category,
            status_code=status_code,
            attempts=self.max_retries + 1,
            retryable=True,
        ) from last_error

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
        _ensure_llm_call_allowed()
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
        _ensure_llm_call_allowed()
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        if llm_circuit_breaker.is_open:
            raise LLMProviderCallError(
                category="circuit_open",
                status_code=None,
                attempts=0,
                retryable=True,
            )

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
                retryable = _is_transient_error(e)
                category, status_code = _classify_provider_error(e)
                if not retryable:
                    logger.error(
                        "LLM tool call failed permanently: category=%s status=%s type=%s",
                        category, status_code, type(e).__name__,
                    )
                    raise LLMProviderCallError(
                        category=category,
                        status_code=status_code,
                        attempts=attempt + 1,
                        retryable=False,
                    ) from e
                logger.warning(
                    "LLM tool call failed transiently: attempt=%s category=%s status=%s type=%s",
                    attempt + 1, category, status_code, type(e).__name__,
                )
                if attempt < self.max_retries:
                    delay = (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(delay)

        category, status_code = _classify_provider_error(last_error)
        raise LLMProviderCallError(
            category=category,
            status_code=status_code,
            attempts=self.max_retries + 1,
            retryable=True,
        ) from last_error

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
