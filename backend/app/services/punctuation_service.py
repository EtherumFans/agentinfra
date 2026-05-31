"""Punctuation Restoration Service — CT-Transformer + Medical LLM pipeline.

Pipeline:
  1. CT-Transformer (FunASR punc_ct-transformer) — MacBERT-architecture
     Chinese punctuation model. Fast, no LLM cost. Handles 99% of cases.
  2. Medical LLM (DeepSeek) — Domain-specific correction pass. Fixes
     clinical terminology punctuation that the general model misses.

Usage:
    from app.services.punctuation_service import punctuation_service
    text = await punctuation_service.punctuate("raw text from any ASR")
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Singleton
_punc_model = None
_punc_model_loaded = False


def _get_device() -> str:
    """Determine best device for punc inference."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda:0"
    except ImportError:
        pass
    return "cpu"


async def _load_punc_model():
    """Load standalone CT-Transformer punctuation model.

    Model: iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch
    Architecture: MacBERT-based Chinese punctuation restoration transformer.
    Trained on 272K vocabulary of common Chinese text.
    """
    global _punc_model, _punc_model_loaded
    if _punc_model_loaded:
        return _punc_model

    try:
        from funasr import AutoModel

        device = _get_device()
        logger.info(f"Loading CT-Transformer punc model on {device}...")

        _punc_model = AutoModel(
            model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
            model_revision="v2.0.4",
            device=device,
            disable_update=True,
        )
        _punc_model_loaded = True
        logger.info(f"CT-Transformer punc model loaded on {device}")
        return _punc_model
    except ImportError:
        logger.warning("funasr not installed — punc model unavailable")
        _punc_model_loaded = True  # Mark as attempted
        return None
    except Exception as e:
        logger.error(f"Failed to load punc model: {e}")
        _punc_model_loaded = True
        return None


async def _llm_punctuate(text: str) -> Optional[str]:
    """Second pass: medical LLM correction for domain-specific punctuation."""
    from app.services.llm_service import llm_service

    prompt = f"""请为以下中文医疗文本添加正确的标点符号（。，！？：），不要修改任何文字内容，只添加或修正标点。

规则：
1. 根据语义判断句子边界，添加句号（。）
2. 从句、并列、转折处添加逗号（，）
3. 医学段落标题（主诉、现病史、查体、诊断等）后加冒号（：）
4. 临床数值与单位之间不要加标点
5. 直接返回加标点后的文本，不加解释

文本：
{text}"""

    try:
        result = await llm_service.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.05,
            max_tokens=min(len(text) * 2, 4000),
        )
        content = result.get("content", "") if isinstance(result, dict) else str(result)
        return content.strip()
    except Exception as e:
        logger.warning(f"LLM punctuation failed: {e}")
        return None


class PunctuationService:
    """Two-stage punctuation restoration: CT-Transformer → Medical LLM."""

    async def punctuate(self, text: str, use_llm: bool = True) -> str:
        """Restore Chinese punctuation in raw text.

        Args:
            text: Raw unpunctuated Chinese text
            use_llm: If True, run medical LLM correction as second pass

        Returns:
            Punctuated text
        """
        if not text or not text.strip():
            return text

        # Stage 1: CT-Transformer (fast, offline, no API cost)
        stage1 = await self._ct_punctuate(text)
        if not stage1:
            # CT-Transformer unavailable — fall through to LLM or return raw
            if use_llm:
                llm_result = await _llm_punctuate(text)
                return llm_result if llm_result else text
            return text

        # Stage 2: Medical LLM correction (optional, API cost)
        if use_llm:
            llm_result = await _llm_punctuate(stage1)
            if llm_result and len(llm_result) >= len(stage1) * 0.8:
                return llm_result
            return stage1

        return stage1

    async def _ct_punctuate(self, text: str) -> Optional[str]:
        """Run CT-Transformer punc model on text."""
        model = await _load_punc_model()
        if model is None:
            return None

        try:
            # CT-Transformer expects raw text, returns punctuated text
            result = model.generate(input=text)
            if result and len(result) > 0:
                output = result[0].get("text", "") if isinstance(result[0], dict) else str(result[0])
                if output and len(output) >= len(text) * 0.8:
                    return output
                if output:
                    return output
            return None
        except Exception as e:
            logger.warning(f"CT-Transformer inference failed: {e}")
            return None


punctuation_service = PunctuationService()
