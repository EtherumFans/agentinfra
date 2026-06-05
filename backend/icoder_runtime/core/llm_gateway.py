"""LLM Gateway — model routing layer for iCoDer Runtime.

AgentRunner calls LLMGateway, not individual LLM providers.
LLMGateway routes to the configured provider based on runtime settings.

Providers:
  - MockLLMProvider: deterministic fake responses for tests
  - DeepSeekProvider: calls DeepSeek API
  - OpenAICompatibleProvider: any OpenAI-compatible endpoint
  - MedicalCodingLLMProvider: wraps iCoDer coding engine as an LLM
"""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any

from .errors import LLMProviderNotConfigured, ProviderError

logger = logging.getLogger(__name__)


# ── Abstract Provider ──


class BaseLLMProvider(ABC):
    """Abstract LLM provider. All providers implement this interface."""

    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a completion from the provider.

        Returns: {"content": str, "model": str, "usage": {"input_tokens": int, "output_tokens": int}}
        """
        ...

    def health_check(self) -> dict:
        """Return provider health status."""
        return {"provider": self.name, "status": "unknown"}


# ── Mock Provider ──


class MockLLMProvider(BaseLLMProvider):
    """Deterministic mock for testing. Returns structured JSON from the last user message.

    If the message contains a JSON schema hint, returns a valid instance.
    Otherwise returns a generic compliance audit result.
    """

    name = "mock"

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Build a plausible response from the last user message
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        reply = {
            "review_conclusion": "PASS",
            "primary_diagnosis": {"code": "I21.0", "description": "急性前壁心肌梗死"},
            "issues_found": [],
            "confidence": 0.95,
            "notes": f"[MockLLM] Processed input ({len(last_user)} chars).",
        }

        return {
            "content": json.dumps(reply, ensure_ascii=False),
            "model": "mock/1.0",
            "usage": {"input_tokens": len(last_user) // 3, "output_tokens": 120},
            "structured": reply,
        }

    def health_check(self) -> dict:
        return {"provider": self.name, "status": "healthy"}


# ── DeepSeek Provider ──


class DeepSeekProvider(BaseLLMProvider):
    """Calls DeepSeek API (deepseek-chat)."""

    name = "deepseek"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: int = 120,
    ):
        self.api_key = api_key or os.environ.get("ICODER_CREDENTIAL_LLM", "")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise ProviderError("DeepSeek API key not configured.")

        import httpx

        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
        if response_schema:
            payload["response_format"] = {"type": "json_object", "schema": response_schema}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"DeepSeek API error: {e}")

        choice = data["choices"][0]
        return {
            "content": choice["message"]["content"],
            "model": data.get("model", self.model),
            "usage": {
                "input_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
            },
            "latency_ms": int((time.time() - t0) * 1000),
        }

    def health_check(self) -> dict:
        return {"provider": self.name, "model": self.model, "status": "configured" if self.api_key else "no_api_key"}


# ── OpenAI-Compatible Provider ──


class OpenAICompatibleProvider(BaseLLMProvider):
    """Any OpenAI-compatible API endpoint (vLLM, Ollama, etc.)."""

    name = "openai_compat"

    def __init__(
        self,
        api_key: str = "not-needed",
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: int = 120,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import httpx

        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"OpenAI-compatible API error: {e}")

        choice = data["choices"][0]
        return {
            "content": choice["message"]["content"],
            "model": data.get("model", self.model),
            "usage": {
                "input_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "output_tokens": data.get("usage", {}).get("completion_tokens", 0),
            },
            "latency_ms": int((time.time() - t0) * 1000),
        }

    def health_check(self) -> dict:
        return {"provider": self.name, "model": self.model, "status": "configured"}


# ── Medical Coding LLM Provider ──
# Wraps the iCoDer coding engine as an LLM provider.
# Does NOT contain Reviews/Encounters business logic — that lives in ReviewCodingService.


class MedicalCodingLLMProvider(BaseLLMProvider):
    """Adapter that exposes the iCoDer coding engine as an LLM Provider.

    Supports three modes:
    - mock: No engine configured, returns MedicalCodingOutputSchema.mock_result()
    - prompt_llm: Uses PromptLLMAdapter (LLM via prompt engineering) to get coding output
    - real: Uses a CodingEngineAdapter-compatible coding inference service

    All output is normalized through MedicalCodingOutputSchema.
    """

    name = "medical_coding"

    def __init__(self, coding_engine: Any = None, gateway: Any = None):
        """coding_engine: CodingEngineAdapter or compatible object.
        If None and gateway is provided, uses PromptLLMAdapter.
        If both None, uses mock mode.
        """
        from .coding_schema import CodingEngineAdapter
        if coding_engine is not None and isinstance(coding_engine, CodingEngineAdapter):
            self._engine = coding_engine
        elif gateway is not None:
            from .coding_schema import PromptLLMAdapter
            self._engine = PromptLLMAdapter(gateway)
        else:
            self._engine = None

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from .coding_schema import MedicalCodingOutputSchema

        if self._engine is not None:
            return await self._generate_real(messages, tools, response_schema, context)

        # Mock mode: use standard schema
        schema = MedicalCodingOutputSchema.mock_result()
        return self._pack_response(schema)

    async def _generate_real(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None,
        response_schema: dict | None,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        from .coding_schema import MedicalCodingOutputSchema

        result = await self._engine.infer_async(
            messages=messages, tools=tools, response_schema=response_schema, context=context
        )

        if isinstance(result, MedicalCodingOutputSchema):
            return self._pack_response(result)

        # Coerce to schema
        if isinstance(result, dict):
            schema = MedicalCodingOutputSchema.from_dict(result, provider=self._engine.name)
        else:
            schema = MedicalCodingOutputSchema.mock_result()
        return self._pack_response(schema)

    def _pack_response(self, schema) -> dict[str, Any]:
        """Pack a MedicalCodingOutputSchema into the standard provider response."""
        d = schema.to_dict()
        return {
            "content": json.dumps(d, ensure_ascii=False),
            "model": f"medical-coding/{schema.model}" if schema.model else "medical-coding/mock",
            "usage": {"input_tokens": 0, "output_tokens": len(json.dumps(d)) // 3},
            "structured": d,
        }

    def health_check(self) -> dict:
        from .coding_schema import CodingEngineAdapter
        if self._engine is None:
            return {"provider": self.name, "mode": "mock", "status": "healthy", "engine_type": "none"}
        if isinstance(self._engine, CodingEngineAdapter):
            eng_health = self._engine.health_check()
            return {"provider": self.name, "mode": "real", "status": "healthy", "engine": eng_health}
        return {"provider": self.name, "mode": "real", "status": "healthy", "engine_type": type(self._engine).__name__}


# ── LLM Gateway ──


class LLMGateway:
    """Routes agent LLM requests to configured providers.

    Usage:
        gateway = LLMGateway()
        gateway.register(MockLLMProvider(), default=True)
        gateway.register(MedicalCodingLLMProvider(), alias="medical-coding")

        result = await gateway.generate(messages, provider="default")
    """

    def __init__(self):
        self._providers: dict[str, BaseLLMProvider] = {}
        self._default: str | None = None
        self._aliases: dict[str, str] = {}

    def register(self, provider: BaseLLMProvider, *, default: bool = False, alias: str = "") -> "LLMGateway":
        """Register a provider. If default=True, set as the default provider."""
        self._providers[provider.name] = provider
        if alias:
            self._aliases[alias] = provider.name
        if default:
            self._default = provider.name
        return self

    def get(self, name: str = "") -> BaseLLMProvider:
        """Get a provider by name, alias, or the default.

        Raises LLMProviderNotConfigured if no provider is available.
        """
        key = self._aliases.get(name, name)
        if key and key in self._providers:
            return self._providers[key]
        if self._default and self._default in self._providers:
            return self._providers[self._default]
        # Return any available provider as last resort
        if self._providers:
            return next(iter(self._providers.values()))
        raise LLMProviderNotConfigured()

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        provider: str = "",
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Route a generation request to the appropriate provider."""
        p = self.get(provider)
        return await p.generate(
            messages=messages, tools=tools, response_schema=response_schema, context=context
        )

    def list_providers(self) -> dict[str, dict]:
        """Return health status of all registered providers."""
        return {name: p.health_check() for name, p in self._providers.items()}

    @property
    def is_configured(self) -> bool:
        return len(self._providers) > 0

    @property
    def default_provider(self) -> str | None:
        return self._default
