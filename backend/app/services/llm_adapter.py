"""LLM Adapter — Structured output, validation, error handling.

Wraps llm_service with:
- Pydantic model validation for structured output
- Unified JSON parsing (single impl, no duplication)
- Typed error hierarchy (LLMError, LLMParseError, LLMValidationError)
- Auto-retry with exponential backoff
- Provider abstraction (swap DeepSeek → OpenAI without code changes)

Usage:
    from app.services.llm_adapter import llm_adapter

    class MySchema(BaseModel):
        code: str; name: str; score: float

    result = await llm_adapter.extract(prompt, text, response_model=MySchema)
    # Returns validated MySchema instance, not raw dict
"""

import json
import logging
import asyncio
from typing import Optional, Type, TypeVar, Any
from pydantic import BaseModel, ValidationError

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class LLMError(Exception):
    """Base error for LLM adapter failures."""
    pass


class LLMConnectionError(LLMError):
    """Network/provider connection failure after all retries."""
    pass


class LLMParseError(LLMError):
    """Response is not valid JSON and cannot be recovered."""
    pass


class LLMValidationError(LLMError):
    """Response parsed as JSON but failed Pydantic schema validation."""
    def __init__(self, message: str, raw_data: Any = None, validation_errors: list = None):
        super().__init__(message)
        self.raw_data = raw_data
        self.validation_errors = validation_errors or []


class LLMAdapter:
    """Structured LLM interface with output validation and error handling."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    async def extract(
        self,
        prompt: str,
        text: str,
        response_model: Type[T],
        schema_hint: Optional[str] = None,
        temperature: float = 0.05,
        system_prompt: Optional[str] = None,
    ) -> T:
        """Extract structured data from text using LLM.

        Args:
            prompt: What to extract
            text: Source text to extract from
            response_model: Pydantic model for validation
            schema_hint: Optional JSON schema hint for the LLM
            temperature: LLM temperature (default 0.05 for extraction)
            system_prompt: Override default system prompt

        Returns:
            Validated Pydantic model instance

        Raises:
            LLMConnectionError: LLM unavailable after retries
            LLMParseError: Response is not valid JSON
            LLMValidationError: Response doesn't match schema
        """
        default_system = (
            "You are a precise medical data extraction system. "
            "Extract the requested information from the medical text "
            "and output ONLY valid JSON. Do not add explanations. "
            "Follow the exact schema requested."
        )
        system = system_prompt or default_system
        if schema_hint:
            system += f"\n\nExpected JSON structure:\n{schema_hint}"

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = await llm_service.chat(
                    messages=[{"role": "user", "content": f"{prompt}\n\nText:\n{text}"}],
                    system_prompt=system,
                    temperature=temperature,
                    response_format="json",
                )
                content = response.get("content", "{}") if isinstance(response, dict) else "{}"
                parsed = self._parse_json(content)
                return self._validate(parsed, response_model)
            except (LLMParseError, LLMValidationError) as e:
                last_error = e
                logger.warning(f"LLM adapter attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.base_delay * (2 ** attempt))
            except Exception as e:
                last_error = e
                logger.warning(f"LLM adapter attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.base_delay * (2 ** attempt))

        if isinstance(last_error, (LLMParseError, LLMValidationError)):
            raise last_error
        raise LLMConnectionError(f"LLM call failed after {self.max_retries} attempts: {last_error}")

    def _parse_json(self, content: str) -> Any:
        """Unified JSON parsing with markdown fence stripping."""
        text = content.strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try stripping markdown fences
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMParseError(f"Failed to parse JSON after fence stripping: {e}")

    def _validate(self, data: Any, model: Type[T]) -> T:
        """Validate parsed data against Pydantic model."""
        if not isinstance(data, dict):
            raise LLMValidationError(
                f"Expected dict, got {type(data).__name__}",
                raw_data=data,
            )
        try:
            return model(**data)
        except ValidationError as e:
            raise LLMValidationError(
                f"Schema validation failed: {e.error_count()} error(s)",
                raw_data=data,
                validation_errors=e.errors(),
            )

    async def chat_structured(
        self,
        messages: list[dict],
        response_model: Type[T],
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        """Chat completion with structured output.

        Args:
            messages: Conversation messages
            response_model: Pydantic model for validation
            system_prompt: Optional system prompt override
            temperature: LLM temperature

        Returns:
            Validated Pydantic model instance
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = await llm_service.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    response_format="json",
                )
                content = response.get("content", "{}") if isinstance(response, dict) else "{}"
                parsed = self._parse_json(content)
                return self._validate(parsed, response_model)
            except (LLMParseError, LLMValidationError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.base_delay * (2 ** attempt))
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.base_delay * (2 ** attempt))

        if isinstance(last_error, (LLMParseError, LLMValidationError)):
            raise last_error
        raise LLMConnectionError(f"LLM chat failed after {self.max_retries} attempts: {last_error}")


# Singleton
llm_adapter = LLMAdapter()
