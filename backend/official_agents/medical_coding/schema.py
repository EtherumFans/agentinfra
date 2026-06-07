"""MedicalCodingOutputSchema — standard output format for medical coding agents.

Also defines CodingEngineAdapter — abstract interface for real coding engines.

v2.0: EvidenceSpan — span-level evidence linking (code ↔ char position in source doc)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── Span-level Evidence ──


@dataclass
class EvidenceSpan:
    """A single evidence citation with precise character-position linking to source text.

    Replaces bare evidence strings. Each span maps a code to the exact text
    in a specific document that supports it.
    """
    text: str = ""
    char_start: int = 0
    char_end: int = 0
    doc_id: str = ""
    doc_type: str = ""  # 入院记录 | 出院小结 | 手术记录 | 病程记录 | 检查报告
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict | str) -> "EvidenceSpan":
        if isinstance(data, str):
            return cls(text=data)
        return cls(
            text=data.get("text", data.get("evidence_text", "")),
            char_start=data.get("char_start", 0),
            char_end=data.get("char_end", 0),
            doc_id=data.get("doc_id", ""),
            doc_type=data.get("doc_type", ""),
            confidence=data.get("confidence", 1.0),
        )

    def validate(self, source_text: str) -> bool:
        """Verify that the span text matches the source at the given position."""
        if not source_text or self.char_start >= self.char_end:
            return False
        actual = source_text[self.char_start:self.char_end]
        return actual.strip() == self.text.strip()


# ── Standard Medical Coding Output Schema ──


def _parse_evidence(raw: list) -> list:
    """Parse evidence from mixed format (str or dict) → list of EvidenceSpan.

    Backward compatible: bare strings become EvidenceSpan with text only.
    """
    spans = []
    for item in raw or []:
        spans.append(EvidenceSpan.from_dict(item))
    return spans


def _serialize_evidence(spans: list[EvidenceSpan]) -> list[dict]:
    return [s.to_dict() for s in spans]


@dataclass
class DiagnosisEntry:
    code: str = ""
    description: str = ""
    confidence: float = 0.0
    category: str = ""  # principal | secondary | complication | comorbidity
    evidence: list = field(default_factory=list)  # list[EvidenceSpan] or backward compat list[str]

    def evidence_spans(self) -> list[EvidenceSpan]:
        """Get evidence as typed EvidenceSpan list."""
        return _parse_evidence(self.evidence)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "description": self.description,
            "confidence": self.confidence,
            "category": self.category,
            "evidence": [e.to_dict() if isinstance(e, EvidenceSpan) else e for e in self.evidence],
        }


@dataclass
class ProcedureEntry:
    code: str = ""
    description: str = ""
    confidence: float = 0.0
    category: str = ""  # principal | secondary | diagnostic | therapeutic
    evidence: list = field(default_factory=list)  # list[EvidenceSpan] or backward compat list[str]

    def evidence_spans(self) -> list[EvidenceSpan]:
        """Get evidence as typed EvidenceSpan list."""
        return _parse_evidence(self.evidence)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "description": self.description,
            "confidence": self.confidence,
            "category": self.category,
            "evidence": [e.to_dict() if isinstance(e, EvidenceSpan) else e for e in self.evidence],
        }


@dataclass
class CodingIssue:
    severity: str = "info"  # critical | high | medium | low | info
    code: str = ""
    message: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class CandidateCode:
    """A single ICD code candidate produced by the retriever / LLM.

    ``source`` discriminates provenance: ``llm`` (initial code from Stage 1
    LLM), ``retrieve`` (BGE-M3 + FAISS top-K), ``differentiation_kb`` (rule
    suggested by coding_differentiation_kb), or ``rerank`` (post RankGPT).
    """
    code: str = ""
    name: str = ""
    score: float = 0.0
    chapter: str = ""
    source: str = "retrieve"  # llm | retrieve | differentiation_kb | rerank

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "score": self.score,
            "chapter": self.chapter,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CandidateCode":
        return cls(
            code=data.get("code", ""),
            name=data.get("name", ""),
            score=float(data.get("score", 0.0)),
            chapter=data.get("chapter", ""),
            source=data.get("source", "retrieve"),
        )


@dataclass
class ExtractedDiagnosis:
    """One disease extracted from EMR text in the MedCodER pipeline.

    Carries the full provenance chain:
      - disease_text: the LLM's normalization of the disease mention
      - supporting_evidence: list[EvidenceSpan] pinpointing source text
      - llm_initial_code: the LLM's best ICD guess in Stage 1
      - retrieved_codes: top-K from BGE-M3 + FAISS in Stage 2
      - final_top_k: re-ranked top-K from Stage 4
      - final_confidence: per-diagnosis calibrated confidence
      - rerank_notes: short rationale from the re-ranker
    """
    disease_text: str = ""
    supporting_evidence: list = field(default_factory=list)  # list[EvidenceSpan]
    llm_initial_code: str = ""
    retrieved_codes: list = field(default_factory=list)  # list[CandidateCode]
    final_top_k: list = field(default_factory=list)  # list[CandidateCode]
    final_confidence: float = 0.0
    rerank_notes: str = ""

    def evidence_spans(self) -> list[EvidenceSpan]:
        return _parse_evidence(self.supporting_evidence)

    def to_dict(self) -> dict:
        return {
            "disease_text": self.disease_text,
            "supporting_evidence": [e.to_dict() if isinstance(e, EvidenceSpan) else e
                                    for e in self.supporting_evidence],
            "llm_initial_code": self.llm_initial_code,
            "retrieved_codes": [c.to_dict() if isinstance(c, CandidateCode) else c
                                for c in self.retrieved_codes],
            "final_top_k": [c.to_dict() if isinstance(c, CandidateCode) else c
                            for c in self.final_top_k],
            "final_confidence": self.final_confidence,
            "rerank_notes": self.rerank_notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractedDiagnosis":
        # Re-hydrate supporting_evidence (list of dicts) to EvidenceSpan list
        raw_evidence = data.get("supporting_evidence", [])
        spans: list = []
        for item in raw_evidence:
            if isinstance(item, EvidenceSpan):
                spans.append(item)
            elif isinstance(item, dict):
                spans.append(EvidenceSpan.from_dict(item))
            elif isinstance(item, str):
                spans.append(EvidenceSpan(text=item))
        return cls(
            disease_text=data.get("disease_text", ""),
            supporting_evidence=spans,
            llm_initial_code=data.get("llm_initial_code", ""),
            retrieved_codes=[CandidateCode.from_dict(c) if isinstance(c, dict) else c
                             for c in data.get("retrieved_codes", [])],
            final_top_k=[CandidateCode.from_dict(c) if isinstance(c, dict) else c
                         for c in data.get("final_top_k", [])],
            final_confidence=float(data.get("final_confidence", 0.0)),
            rerank_notes=data.get("rerank_notes", ""),
        )


@dataclass
class MedicalCodingOutputSchema:
    """Standard output for any medical coding agent execution."""

    review_conclusion: str = "PASS"  # PASS | WARNING | FAIL
    primary_diagnosis: DiagnosisEntry = field(default_factory=DiagnosisEntry)
    secondary_diagnoses: list[DiagnosisEntry] = field(default_factory=list)
    procedures: list[ProcedureEntry] = field(default_factory=list)
    issues_found: list[CodingIssue] = field(default_factory=list)
    drg_suggestion: str = ""
    dip_suggestion: str = ""
    manual_review_required: bool = False
    confidence: float = 0.0
    notes: str = ""

    # Metadata
    provider: str = ""  # Which provider produced this
    model: str = ""
    is_mock: bool = False

    # Repair-loop tracking (Phase 2 of F1 0.76 → 0.85+)
    # Defaults preserve backward compatibility — old callers that construct
    # the schema directly don't need to know about these.
    repair_attempted: bool = False
    repair_success: bool = False
    repair_rounds: int = 0

    # MedCodER pipeline output (NAACL 2025 Industry Track 3-stage).
    # ``mode`` discriminates which adapter produced this output:
    #   "deepseek"    — DeepSeek prompt only (legacy)
    #   "prompt_llm"  — generic LLM via prompt (legacy)
    #   "hybrid"      — DeepSeek + trigger RAG + repair (default)
    #   "no_repair"   — Hybrid without repair loop (ablation)
    #   "medcoder"    — Full 5-stage MedCodER pipeline (BGE-M3 + FAISS + RankGPT)
    # ``extracted_diagnoses`` is only populated when ``mode == "medcoder"``.
    mode: str = "hybrid"
    extracted_diagnoses: list = field(default_factory=list)  # list[ExtractedDiagnosis]

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_conclusion": self.review_conclusion,
            "primary_diagnosis": self.primary_diagnosis.to_dict(),
            "secondary_diagnoses": [d.to_dict() for d in self.secondary_diagnoses],
            "procedures": [p.to_dict() for p in self.procedures],
            "issues_found": [i.to_dict() for i in self.issues_found],
            "drg_suggestion": self.drg_suggestion,
            "dip_suggestion": self.dip_suggestion,
            "manual_review_required": self.manual_review_required,
            "confidence": self.confidence,
            "notes": self.notes,
            "provider": self.provider,
            "model": self.model,
            "is_mock": self.is_mock,
            "repair_attempted": self.repair_attempted,
            "repair_success": self.repair_success,
            "repair_rounds": self.repair_rounds,
            "mode": self.mode,
            "extracted_diagnoses": [d.to_dict() if isinstance(d, ExtractedDiagnosis) else d
                                    for d in self.extracted_diagnoses],
        }

    @classmethod
    def from_dict(cls, data: dict, provider: str = "", is_mock: bool = False) -> "MedicalCodingOutputSchema":
        pd_data = data.get("primary_diagnosis", {})
        if isinstance(pd_data, dict):
            pd = DiagnosisEntry(
                code=pd_data.get("code", ""),
                description=pd_data.get("description", ""),
                confidence=pd_data.get("confidence", 0.0),
                category=pd_data.get("category", "principal"),
                evidence=pd_data.get("evidence", []),
            )
        else:
            pd = DiagnosisEntry()

        sds = [DiagnosisEntry(**d) if isinstance(d, dict) else DiagnosisEntry() for d in data.get("secondary_diagnoses", [])]
        procs = [ProcedureEntry(**p) if isinstance(p, dict) else ProcedureEntry() for p in data.get("procedures", [])]
        issues = [CodingIssue(**i) if isinstance(i, dict) else CodingIssue() for i in data.get("issues_found", [])]

        return cls(
            review_conclusion=data.get("review_conclusion", "PASS"),
            primary_diagnosis=pd,
            secondary_diagnoses=sds,
            procedures=procs,
            issues_found=issues,
            drg_suggestion=data.get("drg_suggestion", ""),
            dip_suggestion=data.get("dip_suggestion", ""),
            manual_review_required=data.get("manual_review_required", False),
            confidence=data.get("confidence", 0.0),
            notes=data.get("notes", ""),
            provider=provider,
            model=data.get("model", data.get("_meta", {}).get("provider", "")),
            is_mock=is_mock,
            repair_attempted=data.get("repair_attempted", False),
            repair_success=data.get("repair_success", False),
            repair_rounds=data.get("repair_rounds", 0),
            mode=data.get("mode", "hybrid"),
            extracted_diagnoses=[ExtractedDiagnosis.from_dict(d) if isinstance(d, dict) else d
                                 for d in data.get("extracted_diagnoses", [])],
        )

    @classmethod
    def mock_result(cls, provider_name: str = "MedicalCodingLLMProvider") -> "MedicalCodingOutputSchema":
        """Produce an explicitly-marked mock result for testing."""
        return cls(
            review_conclusion="PASS",
            primary_diagnosis=DiagnosisEntry(code="I21.0", description="急性前壁心肌梗死", confidence=0.95, category="principal"),
            secondary_diagnoses=[
                DiagnosisEntry(code="I10", description="原发性高血压", confidence=0.88, category="comorbidity"),
            ],
            procedures=[
                ProcedureEntry(code="00.66", description="经皮冠状动脉介入治疗", confidence=0.92, category="therapeutic"),
            ],
            issues_found=[],
            drg_suggestion="F60A",
            manual_review_required=False,
            confidence=0.93,
            notes="Mock medical coding result.",
            provider=provider_name,
            model="medical-coding/mock",
            is_mock=True,
        )


# ── CodingEngineAdapter — abstract interface for real coding engines ──


class CodingEngineAdapter(ABC):
    """Abstract adapter for a real coding engine.

    Implementations wrap actual medical coding inference services
    and expose them through a standard async interface.
    """

    name: str = "coding_engine_adapter"

    @abstractmethod
    async def infer_async(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> MedicalCodingOutputSchema:
        """Run inference on the coding engine and return structured output."""
        ...

    @abstractmethod
    def health_check(self) -> dict:
        """Return engine health status."""
        ...


class PromptLLMAdapter(CodingEngineAdapter):
    """Adapter that wraps a generic LLM as a coding engine via prompt engineering.

    This is a bridge between "we have a real LLM but no dedicated coding model"
    and "we have a specialized coding inference service."
    """

    name = "prompt_llm_adapter"

    def __init__(self, llm_gateway=None, coding_system_prompt: str = ""):
        self._gateway = llm_gateway
        self._system_prompt = coding_system_prompt or (
            "You are a medical coding auditor. Review the patient encounter "
            "and return a JSON object with: review_conclusion (PASS|WARNING|FAIL), "
            "primary_diagnosis ({code, description, confidence}), "
            "secondary_diagnoses (list of {code, description, confidence}), "
            "procedures (list of {code, description, confidence}), "
            "issues_found (list of {severity, code, message, suggestion}), "
            "drg_suggestion, dip_suggestion, manual_review_required (bool), confidence (float)."
        )

    async def infer_async(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        context: dict[str, Any] | None = None,
    ) -> MedicalCodingOutputSchema:
        if not self._gateway:
            return MedicalCodingOutputSchema.mock_result("prompt_llm_adapter")

        full_messages = [{"role": "system", "content": self._system_prompt}] + list(messages)
        try:
            result = await self._gateway.generate(full_messages, provider="default")
            output = result.get("content", "")
            import json
            data = json.loads(output) if isinstance(output, str) else output
            return MedicalCodingOutputSchema.from_dict(data, provider="prompt_llm_adapter")
        except Exception:
            return MedicalCodingOutputSchema.mock_result("prompt_llm_adapter")

    def health_check(self) -> dict:
        return {"engine": self.name, "status": "configured" if self._gateway else "no_gateway"}
