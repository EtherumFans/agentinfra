/**
 * CDIWorkbenchPage — Phase 5 Track D P0 Gate 5 (Real API closed loop).
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
 * Gate 5 changes (this commit):
 *   - Removed SAMPLE_CASE constant. Page calls real /api/v1/cdi/runs.
 *   - Chart input box with "Run CDI Analysis" button.
 *   - Loading / error / empty / degraded states per PDF §A8.
 *   - Role-aware action matrix (admin/qc=cdi_specialist/clinician/insurance).
 *   - Warning banner when response.degraded = true.
 *
 * Boundary: this page does NOT call medical-coding tools. CDI ≠ coding.
 */

import { useEffect, useState } from 'react';
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
  Loader2,
  PlayCircle,
  RefreshCw,
} from 'lucide-react';
import { useAuthStore } from '../store';
import {
  runCDI,
  getCDICase,
  transitionQuery,
  type CDIRunResponse,
  type ProviderQueryDTO,
  type LifecycleState,
  type NLQVerdict,
} from '../services/cdiApi';

// ---------------------------------------------------------------------------
// Role mapping — backend accepts admin/cdi_specialist/clinician/auditor
// ---------------------------------------------------------------------------

type CDIRole = 'admin' | 'cdi_specialist' | 'clinician' | 'auditor' | 'read_only';

function mapCDIRole(appRole: string): CDIRole {
  switch (appRole) {
    case 'admin':
      return 'admin';
    case 'qc':
      return 'cdi_specialist';
    case 'clinician':
      return 'clinician';
    case 'insurance':
      return 'auditor';
    default:
      return 'read_only';
  }
}

// ---------------------------------------------------------------------------
// Visual maps
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
// Default chart (placeholder for the empty state — NOT a fake result)
// ---------------------------------------------------------------------------

const DEFAULT_CHART_HINT =
  '患者男性,58岁,因咳嗽咳痰伴发热3天入院。查体:T 38.5℃。痰培养:肺炎链球菌。入院诊断:肺炎。';

// Defensive normalizer so a backend response missing optional lists never
// crashes the renderer. Backend Gate 5 includes all fields, but we keep
// this guard so a partial/degraded response still renders.
function normalizeCase(c: CDIRunResponse): CDIRunResponse {
  return {
    ...c,
    documentation_gaps: c.documentation_gaps ?? [],
    proposed_provider_queries: c.proposed_provider_queries ?? [],
    risk_flags: c.risk_flags ?? [],
    specialist_trace: c.specialist_trace ?? [],
    stage_traces: c.stage_traces ?? [],
    stage_run_ids: c.stage_run_ids ?? {},
    stage_trace_ids: c.stage_trace_ids ?? {},
    encounter_summary: c.encounter_summary ?? undefined,
    chart_excerpt_preview: c.chart_excerpt_preview ?? '',
    patient_ref: c.patient_ref ?? 'DEID',
    encounter_ref: c.encounter_ref ?? 'DEID',
    completion_state: c.completion_state ?? 'REVIEW_REQUIRED',
    degraded: c.degraded ?? false,
    runtime_mode: c.runtime_mode ?? 'real',
  };
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

type LoadState = 'idle' | 'loading' | 'success' | 'error';

export default function CDIWorkbenchPage() {
  const user = useAuthStore((s) => s.user);
  const role = mapCDIRole(user?.role ?? '');

  const [chartInput, setChartInput] = useState<string>(DEFAULT_CHART_HINT);
  const [caseData, setCaseData] = useState<CDIRunResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [caseIdInput, setCaseIdInput] = useState<string>('');
  const [selectedQueryId, setSelectedQueryId] = useState<string | null>(null);

  // Auto-load case if URL has ?case_id=...
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const cid = params.get('case_id');
    if (cid) {
      setCaseIdInput(cid);
      void loadCase(cid);
    }
  }, []);

  async function runAnalysis() {
    if (!chartInput.trim()) {
      setErrorMsg('请输入病历文本');
      setLoadState('error');
      return;
    }
    setLoadState('loading');
    setErrorMsg('');
    try {
      const result = await runCDI({ chart_excerpt: chartInput });
      setCaseData(normalizeCase(result));
      setLoadState('success');
      setSelectedQueryId(
        result.proposed_provider_queries?.[0]?.query_id ?? null,
      );
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setErrorMsg(
        typeof detail === 'string'
          ? detail
          : detail?.error || e?.message || 'CDI 分析失败',
      );
      setLoadState('error');
    }
  }

  async function loadCase(caseId: string) {
    setLoadState('loading');
    setErrorMsg('');
    try {
      const result = await getCDICase(caseId);
      setCaseData(normalizeCase(result));
      setLoadState('success');
      setSelectedQueryId(
        result.proposed_provider_queries?.[0]?.query_id ?? null,
      );
    } catch (e: any) {
      const status = e?.response?.status;
      setErrorMsg(
        status === 404
          ? `Case ${caseId} 不存在`
          : e?.response?.data?.detail?.error || e?.message || '加载失败',
      );
      setLoadState('error');
    }
  }

  async function onTransition(q: ProviderQueryDTO, toState: LifecycleState) {
    try {
      await transitionQuery(q.query_id, {
        to_state: toState,
        // DRAFT → PENDING_CDI_REVIEW runs the NLQ gate, which needs the
        // query payload to validate (PDF §A4 three-layer gate).
        query_text: toState === 'PENDING_CDI_REVIEW' ? q.query_text : undefined,
        response_options:
          toState === 'PENDING_CDI_REVIEW' ? q.response_options : undefined,
        evidence_quote:
          toState === 'PENDING_CDI_REVIEW'
            ? (q.evidence_span?.quote ?? undefined)
            : undefined,
        topic: toState === 'PENDING_CDI_REVIEW' ? q.topic : undefined,
        priority: q.priority,
      });
      // Reload case to reflect new state
      if (caseData?.case_id) await loadCase(caseData.case_id);
    } catch (e: any) {
      setErrorMsg(e?.response?.data?.detail?.error || e?.message || '状态转换失败');
      setLoadState('error');
    }
  }

  const selectedQuery =
    caseData?.proposed_provider_queries.find(
      (q) => q.query_id === selectedQueryId,
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
                Role: <span className="font-mono">{role}</span>
              </span>
              {caseData && (
                <>
                  <span className="rounded-full bg-mono-surface px-3 py-1 text-mono-text-secondary">
                    Case: <span className="font-mono">{caseData.case_id}</span>
                  </span>
                  <span className="rounded-full bg-yellow-100 px-3 py-1 text-yellow-800">
                    {caseData.completion_state}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Chart input bar */}
      <div className="border-b bg-mono-surface/40 px-6 py-3">
        <div className="mx-auto max-w-[1600px] flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <label className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary shrink-0">
              病历文本
            </label>
            <textarea
              value={chartInput}
              onChange={(e) => setChartInput(e.target.value)}
              placeholder="粘贴病历文本 (1-32000 字符)..."
              className="flex-1 rounded border border-mono-border bg-white px-3 py-2 text-xs text-mono-text-primary focus:outline-none focus:ring-1 focus:ring-mono-primary min-h-[60px] max-h-[120px]"
              maxLength={32000}
            />
            <button
              onClick={runAnalysis}
              disabled={loadState === 'loading'}
              className="shrink-0 rounded bg-mono-primary px-4 py-2 text-xs font-semibold text-white hover:bg-mono-primary/90 disabled:opacity-50 inline-flex items-center gap-1"
            >
              {loadState === 'loading' ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <PlayCircle className="h-3 w-3" />
              )}
              运行 CDI 分析
            </button>
          </div>
          <div className="flex items-center gap-2 text-[11px]">
            <span className="text-mono-text-secondary">或加载已有 Case:</span>
            <input
              value={caseIdInput}
              onChange={(e) => setCaseIdInput(e.target.value)}
              placeholder="CASE-..."
              className="rounded border border-mono-border bg-white px-2 py-1 text-[11px] font-mono w-64"
            />
            <button
              onClick={() => caseIdInput && loadCase(caseIdInput)}
              disabled={loadState === 'loading' || !caseIdInput}
              className="rounded border border-mono-border bg-white px-3 py-1 text-[11px] text-mono-text-primary hover:bg-mono-surface disabled:opacity-50 inline-flex items-center gap-1"
            >
              <RefreshCw className="h-3 w-3" />
              加载
            </button>
          </div>
        </div>
      </div>

      {/* Degraded banner */}
      {caseData?.degraded && (
        <div className="border-b bg-yellow-50 border-yellow-200 px-6 py-2">
          <div className="mx-auto max-w-[1600px] flex items-center gap-2 text-xs text-yellow-900">
            <AlertTriangle className="h-3 w-3" />
            <span>
              部分 LLM 阶段降级 (degraded) — 输出可能不完整, 请审核后使用
            </span>
          </div>
        </div>
      )}

      {/* Error banner */}
      {loadState === 'error' && (
        <div className="border-b bg-red-50 border-red-200 px-6 py-2">
          <div className="mx-auto max-w-[1600px] flex items-center gap-2 text-xs text-red-900">
            <XCircle className="h-3 w-3" />
            <span>{errorMsg}</span>
          </div>
        </div>
      )}

      {/* Loading state */}
      {loadState === 'loading' && (
        <div className="mx-auto max-w-[1600px] py-20 flex flex-col items-center gap-3 text-mono-text-secondary">
          <Loader2 className="h-6 w-6 animate-spin text-mono-primary" />
          <p className="text-sm">正在调用 RealCDIRunner + DeepSeek...</p>
          <p className="text-[11px]">
            encounter_synthesis → gap_identification → expert_consultation →
            query_generation → specialist_trace_emit
          </p>
        </div>
      )}

      {/* Empty state */}
      {loadState === 'idle' && !caseData && (
        <div className="mx-auto max-w-[1600px] py-20 flex flex-col items-center gap-3 text-mono-text-secondary">
          <ClipboardCheck className="h-10 w-10 text-mono-text-secondary/40" />
          <p className="text-sm">输入病历文本, 运行 CDI 分析</p>
          <p className="text-[11px]">
            Phase 5 Track D P0 · 真实 LLM · NLQ-001..010 gate · 9-state lifecycle
          </p>
        </div>
      )}

      {/* 3-pane body — only when case loaded */}
      {caseData && loadState === 'success' && (
        <div className="mx-auto max-w-[1600px] grid grid-cols-[320px_1fr_420px] gap-0">
          {/* ─── Pane 1: Case Context ─── */}
          <aside className="border-r bg-white p-5 space-y-5 min-h-dvh">
            <section>
              <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
                Chart 节选
              </h2>
              <div className="rounded-md bg-mono-surface p-3 text-xs text-mono-text-primary leading-relaxed max-h-[200px] overflow-y-auto">
                {caseData.chart_excerpt_preview}
              </div>
            </section>

            {caseData.encounter_summary && (
              <section>
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
                  就诊摘要
                </h2>
                <ul className="space-y-1.5 text-xs text-mono-text-primary">
                  {caseData.encounter_summary.key_points.map((p, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-mono-text-secondary">·</span>
                      <span>{p}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {caseData.specialist_trace.length > 0 && (
              <section>
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
                  Specialist Trace
                </h2>
                <div className="space-y-2">
                  {caseData.specialist_trace.map((t) => (
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
                      <p className="mt-1 text-mono-text-secondary">
                        {t.rationale}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {caseData.risk_flags.length > 0 && (
              <section>
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
                  Risk Flags
                </h2>
                <div className="space-y-2">
                  {caseData.risk_flags.map((r, i) => (
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

            {caseData.stage_traces.length > 0 && (
              <section>
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
                  Stage Traces ({caseData.stage_traces.length})
                </h2>
                <div className="space-y-1">
                  {caseData.stage_traces.map((t, i) => (
                    <div
                      key={i}
                      className={`rounded border p-1.5 text-[10px] font-mono ${
                        t.degraded
                          ? 'border-yellow-300 bg-yellow-50'
                          : 'border-mono-border bg-white'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-mono-text-primary">
                          {t.expert_id ? `${t.expert_id}` : t.stage}
                        </span>
                        <span className="text-mono-text-secondary">
                          {t.latency_ms}ms · {t.total_tokens}tok
                        </span>
                      </div>
                      <div className="text-mono-text-secondary mt-0.5 truncate">
                        {t.run_id}
                      </div>
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
                  文档缺口 ({caseData.documentation_gaps.length})
                </h2>
                <span className="text-xs text-mono-text-secondary">
                  PDF §6.2 — 9 gap types (incl. unknown)
                </span>
              </header>
              <div className="space-y-3">
                {caseData.documentation_gaps.length === 0 ? (
                  <div className="rounded-lg border border-mono-border bg-white p-4 text-xs text-mono-text-secondary">
                    无文档缺口 (auto_pass 或 LLM 阶段降级)
                  </div>
                ) : (
                  caseData.documentation_gaps.map((g) => (
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
                      </div>
                      <p className="text-xs text-mono-text-secondary mb-2">
                        {g.why_it_matters}
                      </p>
                      <div className="rounded bg-mono-surface p-2 text-xs">
                        <div className="text-mono-text-secondary">
                          evidence ({g.evidence_span.document_id}):
                        </div>
                        <div className="mt-1 font-mono text-mono-text-primary">
                          "{g.evidence_span.quote}"
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* Provider Queries */}
            <section>
              <header className="flex items-center justify-between mb-3">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-mono-text-primary">
                  <HelpCircle className="h-4 w-4 text-mono-primary" />
                  临床澄清任务 ({caseData.proposed_provider_queries.length})
                </h2>
                <span className="text-xs text-mono-text-secondary">
                  Non-leading Query Gate: NLQ-001..010
                </span>
              </header>
              <div className="space-y-3">
                {caseData.proposed_provider_queries.length === 0 ? (
                  <div className="rounded-lg border border-mono-border bg-white p-4 text-xs text-mono-text-secondary">
                    无临床澄清任务 (auto_pass 或 NLQ gate 阻塞全部)
                  </div>
                ) : (
                  caseData.proposed_provider_queries.map((q) => {
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
                  })
                )}
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
                            disabled={
                              role === 'clinician' &&
                              selectedQuery.lifecycle_state !== 'SENT_TO_CLINICIAN' &&
                              selectedQuery.lifecycle_state !== 'VIEWED'
                            }
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
                      Verdict:{' '}
                      <span className="font-mono">
                        {selectedQuery.nlq_gate_verdict}
                      </span>
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

                  {/* Role-aware action matrix */}
                  <div className="flex flex-col gap-2 pt-2">
                    <ActionButtons
                      query={selectedQuery}
                      role={role}
                      onTransition={onTransition}
                    />
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
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Role-aware action buttons
// ---------------------------------------------------------------------------

function ActionButtons({
  query,
  role,
  onTransition,
}: {
  query: ProviderQueryDTO;
  role: CDIRole;
  onTransition: (q: ProviderQueryDTO, to: LifecycleState) => void;
}) {
  const s = query.lifecycle_state;

  // read_only users can only view, no actions
  if (role === 'read_only') {
    return (
      <div className="rounded bg-gray-50 p-2 text-center text-xs text-mono-text-secondary">
        <Eye className="mr-1 inline h-3 w-3" />
        只读权限 (read_only)
      </div>
    );
  }

  // cdi_specialist + admin: drive the DRAFT → PENDING_CDI_REVIEW → APPROVED path
  const canReviewCDI = role === 'cdi_specialist' || role === 'admin';
  // clinician: respond to SENT_TO_CLINICIAN/VIEWED queries
  const canRespondClinician = role === 'clinician' || role === 'admin';
  // auditor: read-only oversight (same as read_only for actions)
  const isAuditor = role === 'auditor';

  if (isAuditor) {
    return (
      <div className="rounded bg-blue-50 p-2 text-center text-xs text-blue-900">
        <Eye className="mr-1 inline h-3 w-3" />
        审计员只读 (auditor)
      </div>
    );
  }

  if (s === 'DRAFT') {
    return (
      <div className="rounded bg-mono-text-secondary/10 p-2 text-center text-xs text-mono-text-secondary">
        <Clock className="mr-1 inline h-3 w-3" />
        CDI Specialist 提交后进入 PENDING_CDI_REVIEW
        {canReviewCDI && (
          <button
            onClick={() => onTransition(query, 'PENDING_CDI_REVIEW')}
            className="mt-1 block w-full rounded bg-mono-primary px-3 py-2 text-xs text-white"
          >
            提交 CDI 审核
          </button>
        )}
      </div>
    );
  }

  if (s === 'PENDING_CDI_REVIEW' && canReviewCDI) {
    return (
      <button
        onClick={() => onTransition(query, 'APPROVED')}
        className="rounded bg-mono-primary px-3 py-2 text-xs text-white"
      >
        <CheckCircle2 className="mr-1 inline h-3 w-3" />
        CDI Specialist: 审核通过
      </button>
    );
  }

  if (s === 'APPROVED' && canReviewCDI) {
    return (
      <button
        onClick={() => onTransition(query, 'SENT_TO_CLINICIAN')}
        className="rounded bg-mono-primary px-3 py-2 text-xs text-white"
      >
        <Send className="mr-1 inline h-3 w-3" />
        发送给医生
      </button>
    );
  }

  if (s === 'SENT_TO_CLINICIAN') {
    return (
      <div className="rounded bg-mono-text-secondary/10 p-2 text-center text-xs text-mono-text-secondary">
        <Eye className="mr-1 inline h-3 w-3" />
        等待医生查看
        {canRespondClinician && (
          <button
            onClick={() => onTransition(query, 'VIEWED')}
            className="mt-1 block w-full rounded bg-mono-text-secondary px-3 py-2 text-xs text-white"
          >
            标记为已查看
          </button>
        )}
      </div>
    );
  }

  if ((s === 'VIEWED' || s === 'RESPONDED') && canRespondClinician) {
    return (
      <button
        onClick={() => onTransition(query, 'RESPONDED')}
        className="rounded bg-mono-primary px-3 py-2 text-xs text-white"
      >
        <FileText className="mr-1 inline h-3 w-3" />
        提交答复
      </button>
    );
  }

  if (s === 'DOCUMENTATION_UPDATED' && canReviewCDI) {
    return (
      <button
        onClick={() => onTransition(query, 'REVALIDATED')}
        className="rounded bg-mono-primary px-3 py-2 text-xs text-white"
      >
        <ShieldCheck className="mr-1 inline h-3 w-3" />
        CDI 复核
      </button>
    );
  }

  if (s === 'CLOSED') {
    return (
      <div className="rounded bg-green-50 p-2 text-center text-xs text-green-800">
        <CheckCircle2 className="mr-1 inline h-3 w-3" />
        已关闭 (CLOSED)
      </div>
    );
  }

  if (s === 'ESCALATED') {
    return (
      <div className="rounded bg-red-50 p-2 text-center text-xs text-red-800">
        <AlertTriangle className="mr-1 inline h-3 w-3" />
        已升级 (ESCALATED) — 医生无法确定, 需人工跟进
      </div>
    );
  }

  return null;
}
