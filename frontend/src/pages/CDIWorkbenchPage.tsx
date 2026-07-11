/**
 * CDIWorkbenchPage — Phase 5 Track D Gate 7
 *
 * 3-pane CDI workbench for CORE_ENTRY_AGENT #1 (Clinical Documentation
 * Improvement). Layout:
 *
 *   ┌──────────────┬────────────────────────┬─────────────────────┐
 *   │ Case         │ Documentation Gaps &   │ Physician Response  │
 *   │ context      │ Provider Queries        │ Panel               │
 *   │ (L, 320px)   │ (Center, flex-1)        │ (R, 420px)          │
 *   └──────────────┴────────────────────────┴─────────────────────┘
 *
 * Beyond Corti (which is single-pane chat): iCoDer adds the digital
 * physician response loop with NLQ gate enforcement + 9-state
 * clarification lifecycle.
 *
 * Phase 5 Track D Gate 7 (this commit):
 *   - 3-pane layout
 *   - Renders CDICase state (6 sections per Corti-compatible spec)
 *   - Shows NLQ gate verdict per query
 *   - Shows clarification lifecycle state per query
 *   - Physician Response Panel mock (real API arrives Gate 9)
 *
 * Boundary: this page does NOT call medical-coding tools. CDI ≠ coding.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ClipboardCheck,
  AlertTriangle,
  HelpCircle,
  Activity,
  ShieldCheck,
  FileText,
  Send,
  Eye,
  CheckCircle2,
  XCircle,
  Clock,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types — mirror backend domain models
// ---------------------------------------------------------------------------

type LifecycleState =
  | 'DRAFT'
  | 'PENDING_CDI_REVIEW'
  | 'APPROVED'
  | 'SENT_TO_CLINICIAN'
  | 'VIEWED'
  | 'RESPONDED'
  | 'DOCUMENTATION_UPDATED'
  | 'REVALIDATED'
  | 'CLOSED'
  | 'CANCELLED'
  | 'ESCALATED'
  | 'EXPIRED';

type NLQVerdict = 'PASS' | 'BLOCK' | 'PENDING';

interface EvidenceSpan {
  document_id: string;
  quote: string;
  char_start: number;
  char_end: number;
}

interface DocumentationGap {
  gap_id: string;
  gap_type: string;
  description: string;
  why_it_matters: string;
  evidence_span: EvidenceSpan;
  minimal_clarification_needed: string;
  priority: 'routine' | 'urgent';
  status: string;
}

interface ProviderQuery {
  query_id: string;
  gap_id: string;
  topic: string;
  reason: string;
  evidence_span: EvidenceSpan;
  query_text: string;
  response_options: string[];
  priority: 'routine' | 'urgent';
  lifecycle_state: LifecycleState;
  nlq_gate_verdict: NLQVerdict;
  nlq_gate_block_reasons: string[];
}

interface CDICase {
  case_id: string;
  patient_ref: string;
  encounter_ref: string;
  chart_excerpt: string;
  encounter_summary: { key_points: string[] };
  documentation_gaps: DocumentationGap[];
  proposed_provider_queries: ProviderQuery[];
  risk_flags: { category: string; description: string }[];
  specialist_trace: {
    expert_id: string;
    consulted: boolean;
    rationale: string;
  }[];
  completion_state: string;
}

// ---------------------------------------------------------------------------
// Sample case — matches Phase 5 Track D §8.3 compliant example
// ---------------------------------------------------------------------------

const SAMPLE_CASE: CDICase = {
  case_id: 'cdi_demo_001',
  patient_ref: 'p_001',
  encounter_ref: 'e_2026_0711_001',
  chart_excerpt:
    '入院记录: 诊断: 肺炎。痰培养: 肺炎链球菌 (3+)。既往: 高血压 5 年。',
  encounter_summary: {
    key_points: [
      '患者因肺炎入院',
      '痰培养示肺炎链球菌 3+',
      '既往高血压史',
    ],
  },
  documentation_gaps: [
    {
      gap_id: 'gap_diagnostic_specificity_pneumonia',
      gap_type: 'diagnostic_specificity',
      description: '肺炎诊断未记录病原体',
      why_it_matters:
        'J18.9 (肺炎, 未特指) vs J13 (肺炎链球菌性肺炎) — 编码特异性差异',
      evidence_span: {
        document_id: '入院记录',
        quote: '诊断: 肺炎',
        char_start: 5,
        char_end: 11,
      },
      minimal_clarification_needed: '病原体',
      priority: 'routine',
      status: 'OPEN',
    },
  ],
  proposed_provider_queries: [
    {
      query_id: 'q_cdi_demo_001',
      gap_id: 'gap_diagnostic_specificity_pneumonia',
      topic: '肺炎病原体',
      reason: '痰培养结果阳性但诊断未记录病原体, 影响编码特异性',
      evidence_span: {
        document_id: '入院记录',
        quote: '诊断: 肺炎',
        char_start: 5,
        char_end: 11,
      },
      query_text:
        "入院记录诊断为'肺炎', 痰培养结果为'肺炎链球菌'. 请根据您的临床判断回答:",
      response_options: [
        'A. 肺炎病原体为肺炎链球菌 (J13)',
        'B. 肺炎病原体为其他已知病原体 (请在自由文本中说明)',
        'C. 痰培养结果为定植菌, 不作为病原体',
        'D. 无法确定 (unable to determine)',
        'E. 临床不支持 (痰培养结果与临床表现不符)',
      ],
      priority: 'routine',
      lifecycle_state: 'DRAFT',
      nlq_gate_verdict: 'PASS',
      nlq_gate_block_reasons: [],
    },
  ],
  risk_flags: [],
  specialist_trace: [
    {
      expert_id: 'coding-expert',
      consulted: true,
      rationale: 'J18.9 vs J13 编码特异性缺口已确认',
    },
  ],
  completion_state: 'REVIEW_REQUIRED',
};

// ---------------------------------------------------------------------------
// Lifecycle state helpers
// ---------------------------------------------------------------------------

const LIFECYCLE_COLOR: Record<LifecycleState, string> = {
  DRAFT: 'bg-gray-100 text-gray-700',
  PENDING_CDI_REVIEW: 'bg-yellow-100 text-yellow-800',
  APPROVED: 'bg-blue-100 text-blue-800',
  SENT_TO_CLINICIAN: 'bg-indigo-100 text-indigo-800',
  VIEWED: 'bg-cyan-100 text-cyan-800',
  RESPONDED: 'bg-purple-100 text-purple-800',
  DOCUMENTATION_UPDATED: 'bg-emerald-100 text-emerald-800',
  REVALIDATED: 'bg-teal-100 text-teal-800',
  CLOSED: 'bg-green-100 text-green-800',
  CANCELLED: 'bg-gray-200 text-gray-600 line-through',
  ESCALATED: 'bg-red-100 text-red-800',
  EXPIRED: 'bg-red-100 text-red-800 line-through',
};

const NLQ_COLOR: Record<NLQVerdict, string> = {
  PASS: 'bg-green-100 text-green-800 border-green-300',
  BLOCK: 'bg-red-100 text-red-800 border-red-300',
  PENDING: 'bg-yellow-100 text-yellow-800 border-yellow-300',
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function CDIWorkbenchPage() {
  const navigate = useNavigate();
  const [selectedCase] = useState<CDICase>(SAMPLE_CASE);
  const [selectedQueryId, setSelectedQueryId] = useState<string | null>(
    SAMPLE_CASE.proposed_provider_queries[0]?.query_id ?? null
  );

  const selectedQuery =
    selectedCase.proposed_provider_queries.find(
      (q) => q.query_id === selectedQueryId
    ) ?? null;

  return (
    <div className="min-h-dvh bg-mono-surface-subtle">
      {/* Header */}
      <div className="border-b bg-white px-6 py-4">
        <div className="mx-auto max-w-[1600px]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <ClipboardCheck className="h-7 w-7 text-mono-primary" />
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-mono-text-primary">
                  CDI 工作台
                </h1>
                <p className="text-xs text-mono-text-secondary">
                  Clinical Documentation Improvement · Core Entry Agent #1
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="rounded-full bg-mono-surface px-3 py-1 text-mono-text-secondary">
                Case: <span className="font-mono">{selectedCase.case_id}</span>
              </span>
              <span className="rounded-full bg-mono-surface px-3 py-1 text-mono-text-secondary">
                Patient: <span className="font-mono">{selectedCase.patient_ref}</span>
              </span>
              <span className="rounded-full bg-yellow-100 px-3 py-1 text-yellow-800">
                {selectedCase.completion_state}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 3-pane body */}
      <div className="mx-auto max-w-[1600px] grid grid-cols-[320px_1fr_420px] gap-0">
        {/* ─── Pane 1: Case Context ─── */}
        <aside className="border-r bg-white p-5 space-y-5 min-h-dvh">
          <section>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
              Chart 节选
            </h2>
            <div className="rounded-md bg-mono-surface p-3 text-xs text-mono-text-primary leading-relaxed">
              {selectedCase.chart_excerpt}
            </div>
          </section>

          <section>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
              就诊摘要
            </h2>
            <ul className="space-y-1.5 text-xs text-mono-text-primary">
              {selectedCase.encounter_summary.key_points.map((p, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-mono-text-secondary">·</span>
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
              Specialist Trace
            </h2>
            <div className="space-y-2">
              {selectedCase.specialist_trace.map((t) => (
                <div
                  key={t.expert_id}
                  className="rounded-md border border-mono-border p-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-mono-text-primary">
                      {t.expert_id}
                    </span>
                    {t.consulted ? (
                      <CheckCircle2 className="h-3 w-3 text-green-600" />
                    ) : (
                      <XCircle className="h-3 w-3 text-mono-text-secondary" />
                    )}
                  </div>
                  <p className="mt-1 text-mono-text-secondary">{t.rationale}</p>
                </div>
              ))}
            </div>
          </section>

          {selectedCase.risk_flags.length > 0 && (
            <section>
              <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
                Risk Flags
              </h2>
              <div className="space-y-2">
                {selectedCase.risk_flags.map((r, i) => (
                  <div
                    key={i}
                    className="rounded-md bg-red-50 p-2 text-xs text-red-900"
                  >
                    <div className="font-semibold">{r.category}</div>
                    <div className="mt-0.5">{r.description}</div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </aside>

        {/* ─── Pane 2: Gaps & Queries ─── */}
        <main className="p-5 space-y-5">
          {/* Documentation Gaps */}
          <section>
            <header className="flex items-center justify-between mb-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-mono-text-primary">
                <AlertTriangle className="h-4 w-4 text-yellow-600" />
                文档缺口 ({selectedCase.documentation_gaps.length})
              </h2>
              <span className="text-xs text-mono-text-secondary">
                PDF §6.2 — 8 gap types
              </span>
            </header>
            <div className="space-y-3">
              {selectedCase.documentation_gaps.map((g) => (
                <div
                  key={g.gap_id}
                  className="rounded-lg border border-mono-border bg-white p-4"
                >
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div>
                      <span className="inline-block rounded-full bg-mono-surface px-2 py-0.5 text-[10px] font-mono text-mono-text-secondary">
                        {g.gap_type}
                      </span>
                      <h3 className="mt-1 text-sm font-medium text-mono-text-primary">
                        {g.description}
                      </h3>
                    </div>
                    <span
                      className={`shrink-0 rounded px-2 py-0.5 text-[10px] ${
                        g.priority === 'urgent'
                          ? 'bg-red-100 text-red-800'
                          : 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {g.priority}
                    </span>
                  </div>
                  <p className="text-xs text-mono-text-secondary mb-2">
                    {g.why_it_matters}
                  </p>
                  <div className="rounded bg-mono-surface p-2 text-xs">
                    <div className="text-mono-text-secondary">
                      evidence ({g.evidence_span.document_id}, chars{' '}
                      {g.evidence_span.char_start}-{g.evidence_span.char_end}):
                    </div>
                    <div className="mt-1 font-mono text-mono-text-primary">
                      "{g.evidence_span.quote}"
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Provider Queries */}
          <section>
            <header className="flex items-center justify-between mb-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-mono-text-primary">
                <HelpCircle className="h-4 w-4 text-mono-primary" />
                临床澄清任务 ({selectedCase.proposed_provider_queries.length})
              </h2>
              <span className="text-xs text-mono-text-secondary">
                Non-leading Query Gate: NLQ-001..009
              </span>
            </header>
            <div className="space-y-3">
              {selectedCase.proposed_provider_queries.map((q) => {
                const selected = q.query_id === selectedQueryId;
                return (
                  <button
                    key={q.query_id}
                    onClick={() => setSelectedQueryId(q.query_id)}
                    className={`w-full text-left rounded-lg border p-4 transition-colors ${
                      selected
                        ? 'border-mono-primary ring-1 ring-mono-primary/30 bg-mono-primary/5'
                        : 'border-mono-border bg-white hover:border-mono-primary/50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex-1">
                        <h3 className="text-sm font-medium text-mono-text-primary">
                          {q.topic}
                        </h3>
                        <p className="mt-0.5 text-xs text-mono-text-secondary">
                          {q.reason}
                        </p>
                      </div>
                      <span
                        className={`shrink-0 rounded border px-2 py-0.5 text-[10px] font-semibold ${NLQ_COLOR[q.nlq_gate_verdict]}`}
                      >
                        NLQ: {q.nlq_gate_verdict}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-mono ${LIFECYCLE_COLOR[q.lifecycle_state]}`}
                      >
                        {q.lifecycle_state}
                      </span>
                      <span className="text-[10px] text-mono-text-secondary">
                        {q.response_options.length} options
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        </main>

        {/* ─── Pane 3: Physician Response Panel ─── */}
        <aside className="border-l bg-white p-5 space-y-4 min-h-dvh">
          <header className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-mono-primary" />
            <h2 className="text-sm font-semibold text-mono-text-primary">
              临床澄清任务详情
            </h2>
          </header>

          {selectedQuery ? (
            <>
              <div className="space-y-3">
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-mono-text-secondary">
                    Lifecycle
                  </div>
                  <div
                    className={`mt-1 inline-block rounded-full px-3 py-1 text-xs font-mono ${LIFECYCLE_COLOR[selectedQuery.lifecycle_state]}`}
                  >
                    {selectedQuery.lifecycle_state}
                  </div>
                </div>

                <div>
                  <div className="text-[11px] uppercase tracking-wider text-mono-text-secondary">
                    Query
                  </div>
                  <p className="mt-1 text-xs text-mono-text-primary leading-relaxed">
                    {selectedQuery.query_text}
                  </p>
                </div>

                <div>
                  <div className="text-[11px] uppercase tracking-wider text-mono-text-secondary mb-2">
                    Response Options
                  </div>
                  <div className="space-y-1.5">
                    {selectedQuery.response_options.map((opt, idx) => (
                      <label
                        key={idx}
                        className="flex items-start gap-2 rounded border border-mono-border p-2 text-xs hover:bg-mono-surface cursor-pointer"
                      >
                        <input
                          type="radio"
                          name="response-option"
                          className="mt-0.5"
                          disabled={selectedQuery.lifecycle_state !== 'SENT_TO_CLINICIAN' && selectedQuery.lifecycle_state !== 'VIEWED'}
                        />
                        <span className="text-mono-text-primary">{opt}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* NLQ Gate detail */}
                <div className="rounded-md bg-mono-surface p-3 text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldCheck className="h-3 w-3 text-green-700" />
                    <span className="font-semibold text-mono-text-primary">
                      Non-leading Query Gate
                    </span>
                  </div>
                  <div className="text-mono-text-secondary">
                    Verdict: <span className="font-mono">{selectedQuery.nlq_gate_verdict}</span>
                  </div>
                  {selectedQuery.nlq_gate_verdict === 'BLOCK' &&
                    selectedQuery.nlq_gate_block_reasons.length > 0 && (
                      <ul className="mt-1 space-y-0.5 text-red-700">
                        {selectedQuery.nlq_gate_block_reasons.map((r, i) => (
                          <li key={i} className="font-mono text-[10px]">
                            {r}
                          </li>
                        ))}
                      </ul>
                    )}
                </div>

                {/* Action buttons (state-aware) */}
                <div className="flex flex-col gap-2 pt-2">
                  {selectedQuery.lifecycle_state === 'DRAFT' && (
                    <button
                      disabled
                      className="rounded bg-mono-text-secondary/30 px-3 py-2 text-xs text-white"
                    >
                      <Clock className="mr-1 inline h-3 w-3" />
                      NLQ gate 通过后才能提交审核
                    </button>
                  )}
                  {selectedQuery.lifecycle_state === 'PENDING_CDI_REVIEW' && (
                    <button className="rounded bg-mono-primary px-3 py-2 text-xs text-white">
                      <CheckCircle2 className="mr-1 inline h-3 w-3" />
                      CDI Specialist: 审核通过
                    </button>
                  )}
                  {selectedQuery.lifecycle_state === 'APPROVED' && (
                    <button className="rounded bg-mono-primary px-3 py-2 text-xs text-white">
                      <Send className="mr-1 inline h-3 w-3" />
                      发送给医生
                    </button>
                  )}
                  {selectedQuery.lifecycle_state === 'SENT_TO_CLINICIAN' && (
                    <button className="rounded bg-mono-text-secondary px-3 py-2 text-xs text-white">
                      <Eye className="mr-1 inline h-3 w-3" />
                      等待医生查看
                    </button>
                  )}
                  {(selectedQuery.lifecycle_state === 'VIEWED' ||
                    selectedQuery.lifecycle_state === 'RESPONDED') && (
                    <button className="rounded bg-mono-primary px-3 py-2 text-xs text-white">
                      <FileText className="mr-1 inline h-3 w-3" />
                      提交答复
                    </button>
                  )}
                  {selectedQuery.lifecycle_state === 'DOCUMENTATION_UPDATED' && (
                    <button className="rounded bg-mono-primary px-3 py-2 text-xs text-white">
                      <ShieldCheck className="mr-1 inline h-3 w-3" />
                      CDI 复核
                    </button>
                  )}
                  {selectedQuery.lifecycle_state === 'CLOSED' && (
                    <div className="rounded bg-green-50 p-2 text-center text-xs text-green-800">
                      <CheckCircle2 className="mr-1 inline h-3 w-3" />
                      已关闭 (CLOSED)
                    </div>
                  )}
                  {selectedQuery.lifecycle_state === 'ESCALATED' && (
                    <div className="rounded bg-red-50 p-2 text-center text-xs text-red-800">
                      <AlertTriangle className="mr-1 inline h-3 w-3" />
                      已升级 (ESCALATED) — 医生无法确定, 需人工跟进
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <p className="text-xs text-mono-text-secondary">
              选择一个临床澄清任务以查看详情
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
