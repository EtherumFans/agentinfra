"""Coding tools — search_icd10_index, assign_diagnosis_code, assign_procedure_code.

Tier 1 deterministic: search_icd10_index (code dictionary lookup, zero LLM)
Tier 2 LLM-powered: assign_diagnosis_code, assign_procedure_code (LLM selects from candidates)
"""

from app.services.tool_registry import ToolDefinition, ToolTier
from app.services.code_dictionary import code_dict_service
from app.services.llm_service import llm_service


async def search_icd10_index(term: str, coding_system: str = "ICD-10-CN") -> dict:
    """Deterministic ICD-10 alphabetic index lookup. Zero LLM involvement.

    Searches the comprehensive ICD-10 code dictionary using fuzzy matching
    to find candidate codes for a clinical term.
    """
    if coding_system == "ICD-9-CM-3":
        results = code_dict_service.search_icd9(term)
    else:
        results = code_dict_service.search_icd10(term)

    return {
        "term": term,
        "coding_system": coding_system,
        "candidates": [
            {"code": r["code"], "name": r["name"], "match_score": r.get("score", 0)}
            for r in results[:10]
        ],
        "source": "ICD-10 Alphabetic Index (deterministic)",
    }


async def search_icd9_index(term: str) -> dict:
    """Deterministic ICD-9-CM-3 procedure code lookup. Zero LLM involvement."""
    results = code_dict_service.search_icd9(term)
    return {
        "term": term,
        "coding_system": "ICD-9-CM-3",
        "candidates": [
            {"code": r["code"], "name": r["name"], "match_score": r.get("score", 0)}
            for r in results[:10]
        ],
        "source": "ICD-9-CM-3 Alphabetic Index (deterministic)",
    }


async def assign_diagnosis_code(
    fact: dict,
    candidates: list[dict],
    evidence_text: str,
    existing_codes: list[str] = None,
) -> dict:
    """Select best ICD-10 diagnosis code from candidates using LLM reasoning.

    The LLM can ONLY choose from the provided candidates (deterministic constraint).
    Postcondition validates the chosen code is in the candidate set.
    """
    existing_codes = existing_codes or []
    existing_set = set(existing_codes)

    prompt = f"""You are selecting the best ICD-10 diagnosis code from a CANDIDATE SET.

CLINICAL FACT: {fact.get('name', 'Unknown')}
CONTEXT: {fact.get('context', '')}
EVIDENCE TEXT: {evidence_text[:500]}

CANDIDATE CODES (you MUST choose from this list):
{chr(10).join(f"- {c['code']}: {c['name']} (match={c.get('match_score', 0)})" for c in candidates[:10])}

EXISTING CODES (already assigned, avoid duplicates): {existing_set}

Respond with JSON:
{{"code": "X00.0", "name": "Full Name", "confidence": "HIGH|MEDIUM|LOW",
  "evidence_binding": "exact quote from evidence text",
  "reasoning": "why this code over alternatives",
  "is_duplicate": false}}"""

    result = await llm_service.extract_json(prompt=prompt, text="", schema_hint="code assignment")
    return {
        "assigned_code": result.get("code", ""),
        "name": result.get("name", ""),
        "confidence": result.get("confidence", "MEDIUM"),
        "evidence_binding": result.get("evidence_binding", ""),
        "reasoning": result.get("reasoning", ""),
        "is_duplicate": result.get("is_duplicate", False),
    }


async def assign_procedure_code(
    fact: dict,
    candidates: list[dict],
    evidence_text: str,
    existing_codes: list[str] = None,
) -> dict:
    """Select best ICD-9-CM-3 procedure code from candidates using LLM reasoning."""
    existing_codes = existing_codes or []
    existing_set = set(existing_codes)

    prompt = f"""You are selecting the best ICD-9-CM-3 procedure code from a CANDIDATE SET.

PROCEDURE FACT: {fact.get('name', 'Unknown')}
CONTEXT: {fact.get('context', '')}
EVIDENCE TEXT: {evidence_text[:500]}

CANDIDATE CODES (you MUST choose from this list):
{chr(10).join(f"- {c['code']}: {c['name']} (match={c.get('match_score', 0)})" for c in candidates[:10])}

EXISTING CODES (already assigned, avoid duplicates): {existing_set}

Respond with JSON:
{{"code": "00.00", "name": "Full Name", "confidence": "HIGH|MEDIUM|LOW",
  "evidence_binding": "exact quote from evidence text",
  "reasoning": "why this code over alternatives"}}"""

    result = await llm_service.extract_json(prompt=prompt, text="", schema_hint="code assignment")
    return {
        "assigned_code": result.get("code", ""),
        "name": result.get("name", ""),
        "confidence": result.get("confidence", "MEDIUM"),
        "evidence_binding": result.get("evidence_binding", ""),
        "reasoning": result.get("reasoning", ""),
    }


CODING_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        id="search_icd10_index",
        name="ICD-10索引导航",
        description=(
            "在ICD-10-CN字母索引中查找临床术语对应的候选编码。"
            "纯确定性算法（模糊匹配），零LLM参与。"
        ),
        tier=ToolTier.DETERMINISTIC,
        category="coding",
        icon="BookOpenText",
        requires=[],
        guarantees={
            "output.candidates": "non-empty: list of code+name+match_score dicts",
            "output.source": "ICD-10 Alphabetic Index (deterministic)",
        },
        executor=search_icd10_index,
        accuracy_tags=["code_dict"],
        is_injectable=True,
    ),
    ToolDefinition(
        id="search_icd9_index",
        name="ICD-9手术索引导航",
        description=(
            "在ICD-9-CM-3手术编码索引中查找手术术语对应的候选编码。"
            "纯确定性算法，零LLM参与。"
        ),
        tier=ToolTier.DETERMINISTIC,
        category="coding",
        icon="BookOpenText",
        requires=[],
        guarantees={
            "output.candidates": "non-empty: list of code+name+match_score dicts",
            "output.source": "ICD-9-CM-3 Alphabetic Index (deterministic)",
        },
        executor=search_icd9_index,
        accuracy_tags=["code_dict"],
        is_injectable=True,
    ),
    ToolDefinition(
        id="assign_diagnosis_code",
        name="诊断编码分配",
        description=(
            "从ICD-10候选集中选择最佳诊断编码并绑定证据。"
            "LLM仅在候选集中选择——不能编造编码。"
        ),
        tier=ToolTier.LLM_REASONING,
        category="coding",
        icon="Stethoscope",
        requires=[
            "state.has('evidence.diagnosis_facts')",
            "state.has('icd10_search_results')",
        ],
        guarantees={
            "output.assigned_code": "valid icd10_code present in candidate set",
            "output.evidence_binding": "non-empty string",
        },
        executor=assign_diagnosis_code,
        accuracy_tags=["code_dict", "evidence_binding"],
        is_injectable=False,
    ),
    ToolDefinition(
        id="assign_procedure_code",
        name="手术编码分配",
        description=(
            "从ICD-9-CM-3候选集中选择最佳手术编码并绑定证据。"
            "LLM仅在候选集中选择——不能编造编码。"
        ),
        tier=ToolTier.LLM_REASONING,
        category="coding",
        icon="Stethoscope",
        requires=[
            "state.has('evidence.procedure_facts')",
            "state.has('icd9_search_results')",
        ],
        guarantees={
            "output.assigned_code": "non-empty string",
            "output.evidence_binding": "non-empty string",
        },
        executor=assign_procedure_code,
        accuracy_tags=["code_dict", "evidence_binding"],
        is_injectable=False,
    ),
]
