"""LLMGateway — provider routing for the extraction stage.

Two providers:
- DeterministicProvider: zero-dependency local extraction (lexicon scan). Lets the whole
  runtime run on-prem with no external model — used in tests and the offline demo.
- DeepSeekProvider: production seam. Requires ICODER_CREDENTIAL_LLM; the actual
  prompt/parse is intentionally left as a marked seam so the slice stays dependency-free.

The gateway is the only place that knows about LLMs; experts and the runner never call
a model directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@dataclass
class RawExtraction:
    """One extracted clinical entity (≈ MedCodER Stage 1 output)."""
    term: str
    evidence_text: str
    llm_initial_code: Optional[str] = None


class CredentialMissing(RuntimeError):
    """Raised when a credentialed provider is selected without credentials."""


@runtime_checkable
class Provider(Protocol):
    name: str

    def extract(self, text: str) -> list[RawExtraction]: ...


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


class DeepSeekProvider:
    name = "deepseek"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.deepseek.com"):
        if not api_key:
            raise CredentialMissing("ICODER_CREDENTIAL_LLM is required for the DeepSeek provider")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def extract(self, text: str) -> list[RawExtraction]:
        # Production seam: POST an extraction prompt to DeepSeek and parse
        # {disease, supporting_evidence, llm_initial_code} JSON (MedCodER Stage 1).
        # Left unwired so the slice has no external dependency.
        raise NotImplementedError(
            "DeepSeek extraction is the production seam — wire ICODER_CREDENTIAL_LLM and implement parse."
        )


class LLMGateway:
    def __init__(self, provider: Provider):
        self.provider = provider

    @classmethod
    def from_env(cls, lexicon: list[str]) -> "LLMGateway":
        key = os.environ.get("ICODER_CREDENTIAL_LLM")
        if key:
            model = os.environ.get("ICODER_DEEPSEEK_MODEL", "deepseek-v4-flash")
            return cls(DeepSeekProvider(key, model))
        return cls(DeterministicProvider(lexicon))

    def extract(self, text: str) -> list[RawExtraction]:
        return self.provider.extract(text)
