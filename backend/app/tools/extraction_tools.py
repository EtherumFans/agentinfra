"""Extraction tools — extract_evidence, reconstruct_timeline.

Tier 2 LLM-powered tools. Use LLM for natural language understanding,
but output structured data with postcondition validation.
"""

from app.services.tool_registry import ToolDefinition, ToolTier
from app.agents.experts.evidence_expert import EvidenceExtractionExpert
from app.agents.experts.timeline_expert import TimelineReconstructionExpert

_evidence_expert = EvidenceExtractionExpert()
_timeline_expert = TimelineReconstructionExpert()


async def extract_evidence(documents: list[dict], admission_reason: str = "") -> dict:
    """Extract structured clinical facts from medical documents.

    Runs EvidenceExtractionExpert which uses LLM for NLP extraction
    with structured JSON output.
    """
    context = {
        "documents": documents,
        "admission_reason": admission_reason,
    }
    result = await _evidence_expert.run(context)
    return {
        "evidence": result.get("evidence", {}),
        "raw_text_length": result.get("raw_text_length", 0),
        "extraction_metadata": result.get("metadata", {}),
    }


async def reconstruct_timeline(documents: list[dict], evidence: dict = None) -> dict:
    """Reconstruct clinical timeline from documents and evidence.

    Runs TimelineReconstructionExpert to build an ordered timeline of events.
    """
    context = {
        "documents": documents,
        "evidence": evidence or {},
    }
    result = await _timeline_expert.run(context)
    return {
        "timeline": result.get("timeline", {}),
        "event_count": result.get("event_count", 0),
    }


EXTRACTION_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        id="extract_evidence",
        name="证据提取",
        description="从病历文档中提取结构化临床事实（诊断事实、手术事实、主诉等）。",
        tier=ToolTier.LLM_REASONING,
        category="extraction",
        icon="FileSearch",
        requires=[],
        guarantees={
            "output.evidence": "dict with diagnosis_facts, procedure_facts, chief_complaint",
            "output.raw_text_length": "non-negative int",
        },
        executor=extract_evidence,
        accuracy_tags=["evidence_binding"],
        is_injectable=False,
        input_schema={
            "type": "object",
            "properties": {
                "documents": {"type": "array", "items": {"type": "object"}},
                "admission_reason": {"type": "string"},
            },
            "required": ["documents"],
        },
    ),
    ToolDefinition(
        id="reconstruct_timeline",
        name="时间线重建",
        description="从病历中重建临床事件时间线，标记未解决事件。",
        tier=ToolTier.LLM_REASONING,
        category="extraction",
        icon="Clock",
        requires=[],
        guarantees={
            "output.timeline": "dict with events list and summary",
            "output.event_count": "non-negative int",
        },
        executor=reconstruct_timeline,
        accuracy_tags=[],
        is_injectable=False,
    ),
]
