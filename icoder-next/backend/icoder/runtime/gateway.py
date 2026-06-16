"""LLMGateway — provider routing for extraction and the tool-calling executor.

Two providers:
- DeterministicProvider: zero-dependency local extraction (lexicon scan). Lets the whole
  runtime run on-prem with no external model — used in tests and the offline demo. It has
  no ``chat`` method, so the executor falls back to deterministic extraction without a key.
- OpenAICompatibleProvider: any OpenAI-compatible /chat/completions endpoint. The product
  is NOT bound to DeepSeek — base_url / model / name are all env-configurable so a hospital
  can point at its own in-house model (vLLM / Ollama / local Qwen-DeepSeek) and keep
  de-identified text on-prem. DeepSeek is only the default endpoint.

The gateway is the only place that knows about LLMs; experts and the runner never call
a model directly.
"""
from __future__ import annotations

import json
import os
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class RawExtraction:
    """One extracted clinical entity (≈ MedCodER Stage 1 output)."""
    term: str
    evidence_text: str
    llm_initial_code: Optional[str] = None


@dataclass
class ToolCall:
    """One function/tool call requested by the model (OpenAI tool-calling shape)."""
    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class ChatResult:
    """One assistant turn: free-text content and/or a batch of tool calls."""
    content: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    usage: dict = field(default_factory=dict)


class CredentialMissing(RuntimeError):
    """Raised when a credentialed provider is selected without credentials."""


class ProviderError(RuntimeError):
    """An LLM endpoint call failed (unreachable / non-2xx). Carries NO credentials."""


@runtime_checkable
class Provider(Protocol):
    name: str

    def extract(self, text: str) -> list[RawExtraction]: ...


@runtime_checkable
class ChatProvider(Protocol):
    """A provider that can drive the tool-calling executor."""
    name: str
    model: str

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None,
             tool_choice: Optional[dict | str] = None) -> ChatResult: ...


class DeterministicProvider:
    name = "deterministic-local"

    def __init__(self, lexicon: list[str]):
        # longest-first so the most specific term wins and nested terms don't double-count
        self._lexicon = sorted({t for t in lexicon if t}, key=len, reverse=True)

    def extract(self, text: str) -> list[RawExtraction]:
        out: list[RawExtraction] = []
        claimed: list[tuple[int, int]] = []
        for term in self._lexicon:
            idx = text.find(term)
            if idx == -1:
                continue
            end = idx + len(term)
            if any(s <= idx and end <= e for s, e in claimed):
                continue  # contained within an already-matched longer term
            claimed.append((idx, end))
            out.append(RawExtraction(term=term, evidence_text=term))
        return out


class OpenAICompatibleProvider:
    """Calls any OpenAI-compatible /chat/completions endpoint (default: DeepSeek)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        name: str = "deepseek",
    ):
        if not api_key:
            raise CredentialMissing("ICODER_CREDENTIAL_LLM is required for the external LLM provider")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.name = name

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None,
             tool_choice: Optional[dict | str] = None) -> ChatResult:
        import httpx  # lazy: the deterministic / offline path needs no HTTP client

        payload: dict = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            # default to free choice; the executor forces submit_findings on the final round
            payload["tool_choice"] = tool_choice or "auto"
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=httpx.Timeout(60.0),
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # message carries status + endpoint, never the api_key
            raise ProviderError(
                f"LLM endpoint {self.base_url} returned HTTP {e.response.status_code}"
            ) from None
        except httpx.HTTPError as e:
            raise ProviderError(
                f"LLM endpoint {self.base_url} is unreachable: {type(e).__name__}"
            ) from None

        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_calls: list[ToolCall] = []
        for c in message.get("tool_calls") or []:
            fn = c.get("function") or {}
            raw_args = fn.get("arguments")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(ToolCall(id=c.get("id", ""), name=fn.get("name", ""), arguments=args))
        return ChatResult(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", ""),
            usage=data.get("usage") or {},
        )

    # extraction seam retained: the executor (tool-calling) supersedes it, but the
    # deterministic single-shot extract contract stays defined for the no-key path symmetry.
    def extract(self, text: str) -> list[RawExtraction]:
        raise NotImplementedError(
            "single-shot extract is superseded by the tool-calling executor (use AgentExecutor)"
        )


def _provider_name_from_url(base_url: str) -> str:
    host = urllib.parse.urlparse(base_url).hostname or base_url
    if host.endswith("deepseek.com"):
        return "deepseek"
    return host


class LLMGateway:
    def __init__(self, provider: Provider):
        self.provider = provider

    @classmethod
    def from_env(cls, lexicon: list[str]) -> "LLMGateway":
        key = os.environ.get("ICODER_CREDENTIAL_LLM")
        if key:
            base_url = os.environ.get("ICODER_LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
            model = os.environ.get("ICODER_LLM_MODEL") or os.environ.get(
                "ICODER_DEEPSEEK_MODEL", "deepseek-v4-flash"
            )
            name = os.environ.get("ICODER_LLM_PROVIDER") or _provider_name_from_url(base_url)
            return cls(OpenAICompatibleProvider(key, model, base_url=base_url, name=name))
        return cls(DeterministicProvider(lexicon))

    def extract(self, text: str) -> list[RawExtraction]:
        return self.provider.extract(text)
