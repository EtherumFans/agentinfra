"""Medical Coding Providers — adapters for coding inference.

Usage:
    from icoder_runtime.providers.medical_coding import (
        MockCodingAdapter, PromptLLMAdapter, RuleEngineAdapter, HybridCodingAdapter
    )
    adapter = HybridCodingAdapter(gateway=my_gateway)
    result = await adapter.infer_async(messages)
"""

from .mock_adapter import MockCodingAdapter
from .prompt_llm_adapter import PromptLLMAdapter
from .rule_engine_adapter import RuleEngineAdapter
from .hybrid_adapter import HybridCodingAdapter
from .deepseek_coding_adapter import DeepSeekCodingAdapter

__all__ = [
    "MockCodingAdapter",
    "PromptLLMAdapter",
    "RuleEngineAdapter",
    "HybridCodingAdapter",
    "DeepSeekCodingAdapter",
]
