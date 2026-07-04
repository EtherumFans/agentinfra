"""MedicalCodingOutputSchema — standard output format for medical coding agents.

Also defines CodingEngineAdapter — abstract interface for real coding engines.

v2.0: EvidenceSpan — span-level evidence linking (code ↔ char position in source doc)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .modes import Mode, MEDCODER_MODES, LEGACY_MODES, coerce  # noqa: F401


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
            "evidence": [_serialize_evidence_item(e) for e in self.evidence],
        }


def _serialize_evidence_item(e):
    """Serialize one evidence item to a dict for API/JSON consumers.

    Accepts EvidenceSpan, dict (already-serialized), or bare string.
    Strings are wrapped as {text, kind=auto_bootstrap} so consumers
    always see dicts.
    """
    if isinstance(e, EvidenceSpan):
        d = e.to_dict()
        d.setdefault("kind", "auto_bootstrap")
        return d
    if isinstance(e, dict):
        d = dict(e)
        d.setdefault("kind", "auto_bootstrap")
        return d
    if isinstance(e, str):
        return {"text": e, "kind": "auto_bootstrap"}
    return {"text": str(e), "kind": "auto_bootstrap"}


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
            "evidence": [_serialize_evidence_item(e) for e in self.evidence],
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
    LLM), ``retrieve`` (BGE-M3 + FAISS top-K), ``catalog`` (E1.6 ICD-9-CM-3
    exact substring match against the catalog, score=1.0),
    ``differentiation_kb`` (rule suggested by coding_differentiation_kb),
    or ``rerank`` (post RankGPT).
    """
    code: str = ""
    name: str = ""
    score: float = 0.0
    chapter: str = ""
    source: str = "retrieve"  # llm | retrieve | catalog | differentiation_kb | rerank

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
    # ``mode`` discriminates which adapter produced this output. Validated
    # against :class:`Mode` (M2 — StrEnum). String-compat preserved:
    # ``Mode.MEDCODER == "medcoder"`` is True, so JSON payloads round-trip
    # unchanged. See ``MEDCODER_CAPABILITY_AUDIT.md`` Part 7.4 (M2) for
    # the full vocabulary (5 MedCodER modes + 4 legacy + UNSET).
    #
    # ``extracted_diagnoses`` is only populated when ``mode`` is one of
    # the MedCodER modes (see ``MEDCODER_MODES``).
    mode: Mode = Mode.UNSET
    extracted_diagnoses: list = field(default_factory=list)  # list[ExtractedDiagnosis]

    # Phase B (Coding Method Runtime 骨架) — canonical method_id +
    # per-stage trace. ``method_id`` is the new SSOT (e.g. "medcoder.full",
    # "legacy.deepseek"); ``mode`` is preserved for back-compat with
    # persisted JSON. ``method_stage_trace`` is a list of MethodStageTraceEntry
    # dicts (typed as ``list[dict]`` here to avoid circular imports with
    # :mod:`icoder_runtime.methods.base`; the runtime always produces
    # properly-shaped dicts).
    method_id: str = ""
    method_name: str = ""
    method_family: str = ""  # medcoder | legacy | noop
    method_stage_trace: list = field(default_factory=list)  # list[dict]

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
            "method_id": self.method_id,
            "method_name": self.method_name,
            "method_family": self.method_family,
            "method_stage_trace": list(self.method_stage_trace),
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
            mode=coerce(data.get("mode", "")),
            extracted_diagnoses=[ExtractedDiagnosis.from_dict(d) if isinstance(d, dict) else d
                                 for d in data.get("extracted_diagnoses", [])],
            method_id=data.get("method_id", ""),
            method_name=data.get("method_name", ""),
            method_family=data.get("method_family", ""),
            method_stage_trace=list(data.get("method_stage_trace", []) or []),
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


@dataclass
class TraceRefs:
    """References to internal run/trace artifacts (Corti-style field 8).

    Lets a reviewer or downstream UI drill from the agent's output back to
    the run history, stage trace, and rule firings that produced it.
    """
    run_id: str = ""
    stage_trace: list = field(default_factory=list)  # list[StageTraceEntry dict]
    rule_fired: list = field(default_factory=list)  # list[str] rule codes
    mode: str = ""  # medcoder | legacy | noop (technical, not user-facing)
    method_id: str = ""  # medcoder.full | legacy.deepseek | ...
    provider: str = ""
    model: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "stage_trace": list(self.stage_trace),
            "rule_fired": list(self.rule_fired),
            "mode": self.mode,
            "method_id": self.method_id,
            "provider": self.provider,
            "model": self.model,
        }


@dataclass
class EncounterSummary:
    """Corti-style field 1 — high-level encounter synthesis.

    Pulls the headline facts (主诉 / 诊疗经过 / 关键发现) plus the source
    document list so the reviewer can see what was fed in.
    """
    chief_complaint: str = ""
    treatment_course: str = ""
    key_findings: list = field(default_factory=list)  # list[str]
    document_sources: list = field(default_factory=list)  # list[dict]: {doc_id, doc_type}
    encounter_date: str = ""

    def to_dict(self) -> dict:
        return {
            "chief_complaint": self.chief_complaint,
            "treatment_course": self.treatment_course,
            "key_findings": list(self.key_findings),
            "document_sources": list(self.document_sources),
            "encounter_date": self.encounter_date,
        }


@dataclass
class DocumentationAnalysis:
    """Corti-style field 2 — evidence extracted from the source documents.

    All four buckets must be populated (even if empty) so consumers can
    trust the shape. Each evidence item is an :class:`EvidenceSpan`.
    """
    diagnosis_evidence: list = field(default_factory=list)  # list[EvidenceSpan]
    procedure_evidence: list = field(default_factory=list)  # list[EvidenceSpan]
    negated_findings: list = field(default_factory=list)  # list[EvidenceSpan]
    historical_conditions: list = field(default_factory=list)  # list[EvidenceSpan]

    def to_dict(self) -> dict:
        def _ser(items):
            out = []
            for e in items or []:
                if isinstance(e, EvidenceSpan):
                    out.append(e.to_dict())
                elif isinstance(e, dict):
                    out.append(e)
                elif isinstance(e, str):
                    out.append({"text": e})
            return out
        return {
            "diagnosis_evidence": _ser(self.diagnosis_evidence),
            "procedure_evidence": _ser(self.procedure_evidence),
            "negated_findings": _ser(self.negated_findings),
            "historical_conditions": _ser(self.historical_conditions),
        }


@dataclass
class CodeAssignment:
    """Corti-style field 3 — final code assignment with evidence.

    Each code MUST carry an evidence span linking back to the source. No
    evidence = no code (Corti red line).
    """
    primary_diagnosis: DiagnosisEntry = field(default_factory=DiagnosisEntry)
    secondary_diagnoses: list = field(default_factory=list)  # list[DiagnosisEntry]
    procedures: list = field(default_factory=list)  # list[ProcedureEntry]

    def to_dict(self) -> dict:
        return {
            "primary_diagnosis": self.primary_diagnosis.to_dict(),
            "secondary_diagnoses": [d.to_dict() if isinstance(d, DiagnosisEntry) else d
                                    for d in self.secondary_diagnoses],
            "procedures": [p.to_dict() if isinstance(p, ProcedureEntry) else p
                           for p in self.procedures],
        }


@dataclass
class DocumentationGap:
    """Corti-style field 4a — a single documentation gap.

    Gaps are evidence shortages, candidate conflicts, negated findings
    that should be coded elsewhere, or historical dx that weren't coded.
    """
    gap_type: str = ""  # insufficient_evidence | candidate_conflict | negated_uncoded | historical_uncoded
    description: str = ""
    related_code: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "gap_type": self.gap_type,
            "description": self.description,
            "related_code": self.related_code,
            "suggestion": self.suggestion,
        }


@dataclass
class UncodableItem:
    """Corti-style field 5a — a single uncodable finding.

    Different from DocumentationGap: gaps are 'need more evidence', while
    uncodable items are 'cannot assign a code at all' (e.g. negated
    findings, historical conditions, deferred diagnoses).
    """
    item_type: str = ""  # negated_finding | historical_condition | deferred_diagnosis | other
    text: str = ""
    reason: str = ""  # why this can't be coded

    def to_dict(self) -> dict:
        return {
            "item_type": self.item_type,
            "text": self.text,
            "reason": self.reason,
        }


@dataclass
class ValidationSummary:
    """Corti-style field 6 — rule_set pass/fail + issues.

    Wraps the issues_found list with a top-level pass bool and the
    manual_review flag derived from issue severity.
    """
    passed: bool = True
    issues_found: list = field(default_factory=list)  # list[CodingIssue]
    manual_review_required: bool = False
    rule_set: str = ""  # e.g. "MedCodERRetrievalRuleSet"
    fired_rules: list = field(default_factory=list)  # list[str]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "issues_found": [i.to_dict() if isinstance(i, CodingIssue) else i
                             for i in self.issues_found],
            "manual_review_required": self.manual_review_required,
            "rule_set": self.rule_set,
            "fired_rules": list(self.fired_rules),
        }


@dataclass
class HumanReview:
    """Corti-style field 7 — explicit human review requirement.

    Even when validation passes, MVP maturity means human review is always
    required. The review_focus list highlights the top items the coder
    should look at first.
    """
    review_conclusion: str = "PASS"  # PASS | WARNING | FAIL
    review_required: bool = True
    review_focus: list = field(default_factory=list)  # list[str] — top items to check
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "review_conclusion": self.review_conclusion,
            "review_required": self.review_required,
            "review_focus": list(self.review_focus),
            "notes": self.notes,
        }


@dataclass
class MedicalCodingAgentOutputV2:
    """Corti-style 8-field output for the Medical Coding Agent (MVP).

    This is the user-facing contract. The legacy ``MedicalCodingOutputSchema``
    (v1) carries the MedCodER 5-stage technical fields; this v2 wraps it
    and projects to the Corti 8 fields. Both can coexist — the runtime
    produces a v1 internally and the A2A / API layer projects to v2 for
    external consumers.

    MVP maturity: production_ready=false, human_review=required. Every
    field must be present in the output, even if empty (no field may be
    omitted — that's the Corti contract).
    """

    encounter_summary: EncounterSummary = field(default_factory=EncounterSummary)
    documentation_analysis: DocumentationAnalysis = field(default_factory=DocumentationAnalysis)
    code_assignment: CodeAssignment = field(default_factory=CodeAssignment)
    documentation_gaps: list = field(default_factory=list)  # list[DocumentationGap]
    uncodable_items: list = field(default_factory=list)  # list[UncodableItem]
    validation_summary: ValidationSummary = field(default_factory=ValidationSummary)
    human_review: HumanReview = field(default_factory=HumanReview)
    trace_refs: TraceRefs = field(default_factory=TraceRefs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "encounter_summary": self.encounter_summary.to_dict(),
            "documentation_analysis": self.documentation_analysis.to_dict(),
            "code_assignment": self.code_assignment.to_dict(),
            "documentation_gaps": [g.to_dict() if isinstance(g, DocumentationGap) else g
                                   for g in self.documentation_gaps],
            "uncodable_items": [i.to_dict() if isinstance(i, UncodableItem) else i
                                for i in self.uncodable_items],
            "validation_summary": self.validation_summary.to_dict(),
            "human_review": self.human_review.to_dict(),
            "trace_refs": self.trace_refs.to_dict(),
        }

    @classmethod
    def from_legacy_v1(
        cls,
        legacy: "MedicalCodingOutputSchema",
        *,
        run_id: str = "",
    ) -> "MedicalCodingAgentOutputV2":
        """Project a v1 ``MedicalCodingOutputSchema`` to the v2 Corti-style 8 fields.

        Used by the A2A / API layer to expose Corti-style output to external
        consumers. The v1 schema is the runtime's internal representation
        (carrying MedCodER 5-stage technical fields); the v2 is the user
        contract.
        """
        # documentation_analysis: gather evidence from extracted_diagnoses
        diag_evidence: list = []
        proc_evidence: list = []
        for dx in getattr(legacy, "extracted_diagnoses", []) or []:
            if isinstance(dx, ExtractedDiagnosis):
                diag_evidence.extend(dx.evidence_spans())
            elif isinstance(dx, dict):
                diag_evidence.extend(_parse_evidence(dx.get("supporting_evidence", [])))

        # validation_summary: project from issues_found + manual_review_required
        validation = ValidationSummary(
            passed=not legacy.issues_found,
            issues_found=list(legacy.issues_found),
            manual_review_required=legacy.manual_review_required,
            rule_set="MedCodERRetrievalRuleSet",
            fired_rules=[i.code for i in legacy.issues_found if i.code],
        )

        # human_review: always required in MVP
        review = HumanReview(
            review_conclusion=legacy.review_conclusion,
            review_required=True,
            review_focus=[i.message for i in legacy.issues_found
                          if i.severity in ("critical", "high")],
            notes=legacy.notes,
        )

        # code_assignment: pass-through (codes already carry evidence)
        assignment = CodeAssignment(
            primary_diagnosis=legacy.primary_diagnosis,
            secondary_diagnoses=list(legacy.secondary_diagnoses),
            procedures=list(legacy.procedures),
        )

        # trace_refs: runtime metadata
        trace = TraceRefs(
            run_id=run_id,
            stage_trace=list(legacy.method_stage_trace),
            rule_fired=[i.code for i in legacy.issues_found if i.code],
            mode=str(legacy.mode),
            method_id=legacy.method_id,
            provider=legacy.provider,
            model=legacy.model,
        )

        return cls(
            encounter_summary=EncounterSummary(),
            documentation_analysis=DocumentationAnalysis(
                diagnosis_evidence=diag_evidence,
                procedure_evidence=proc_evidence,
            ),
            code_assignment=assignment,
            documentation_gaps=[],
            uncodable_items=[],
            validation_summary=validation,
            human_review=review,
            trace_refs=trace,
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
