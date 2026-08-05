/**
 * CDIWorkbenchPage — 临床文档改进 (CDI) 工作台.
 *
 * 3-pane CDI workbench layout:
 *   ┌──────────────┬────────────────────────┬─────────────────────┐
 *   │ 病例摘要     │ 文档缺口 / 临床澄清任务 │ 临床答复与状态分层  │
 *   │ (L, 320px)   │ (Center, flex-1)        │ (R, 420px)          │
 *   └──────────────┴────────────────────────┴─────────────────────┘
 *
 * Phase 5 Track D P0.5 Gate 6 changes (this commit):
 *   - 业务界面统一使用中文业务标签 (cdiLabels.ts).
 *   - 状态分层: 病例状态 / 缺口状态 / 澄清任务状态 / 非诱导检查 /
 *     必要性检查 / 证据支持状态 分别展示.
 *   - 技术与审计详情默认折叠, 仅 Admin/Auditor 可见. 临床医生界面
 *     不再展示 Token / run_id / trace_id / 原始 enum.
 *   - 删除所有 "Phase 5 Track D / PDF § / NLQ-001 / Core Entry Agent /
 *     RealCDIRunner" 等技术暴露.
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
  ChevronDown,
  ChevronRight,
  Lock,
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
import {
  LIFECYCLE_LABELS,
  labelCompletion,
  labelGapType,
  labelNLQVerdict,
  labelExpert,
  labelExecutionMode,
  labelRole,
  labelRuleIds,
  labelRiskCategory,
} from '../services/cdiLabels';

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

/** Roles allowed to see 技术与审计详情 (tokens, run_id, trace_id, raw enums). */
function canSeeTechDetails(role: CDIRole): boolean {
  return role === 'admin' || role === 'auditor';
}

// ---------------------------------------------------------------------------
// Visual maps (Chinese labels keyed by enum)
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
  const showTech = canSeeTechDetails(role);

  const [chartInput, setChartInput] = useState<string>(DEFAULT_CHART_HINT);
  const [caseData, setCaseData] = useState<CDIRunResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [caseIdInput, setCaseIdInput] = useState<string>('');
  const [selectedQueryId, setSelectedQueryId] = useState<string | null>(null);
  const [techDetailsOpen, setTechDetailsOpen] = useState<boolean>(false);

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
      setSelectedQueryId(result.proposed_provider_queries?.[0]?.query_id ?? null);
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
      setSelectedQueryId(result.proposed_provider_queries?.[0]?.query_id ?? null);
    } catch (e: any) {
      const status = e?.response?.status;
      setErrorMsg(
        status === 404
          ? `病例 ${caseId} 不存在`
          : e?.response?.data?.detail?.error || e?.message || '加载失败',
      );
      setLoadState('error');
    }
  }

  async function onTransition(q: ProviderQueryDTO, toState: LifecycleState) {
    try {
      await transitionQuery(q.query_id, {
        to_state: toState,
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

  // -------------------------------------------------------------------------
  // Derived state-layering labels (Master Task §7.3)
  // -------------------------------------------------------------------------
  const caseStatusLabel = caseData ? labelCompletion(caseData.completion_state) : '';
  const hasGapIssues = (caseData?.documentation_gaps.length ?? 0) > 0;
  const hasQueryIssues = (caseData?.proposed_provider_queries.length ?? 0) > 0;
  const firstQuery = caseData?.proposed_provider_queries[0];
  // Non-leading (NLQ) verdict: PASS unless any query is BLOCK.
  const anyNlqBlock =
    caseData?.proposed_provider_queries.some(
      (q) => q.nlq_gate_verdict === 'BLOCK',
    ) ?? false;
  const nlqStatusLabel = !hasQueryIssues
    ? '—'
    : anyNlqBlock
      ? '未通过 (部分任务被阻断)'
      : '通过';

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
                  临床文档改进 · 临床事实被写清楚
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="rounded-full bg-mono-surface px-3 py-1 text-mono-text-secondary">
                当前角色: <span className="font-medium">{labelRole(role)}</span>
              </span>
              {caseData && (
                <span className="rounded-full bg-mono-surface px-3 py-1 text-mono-text-secondary">
                  病例: <span className="font-mono">{caseData.case_id}</span>
                </span>
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
            <span className="text-mono-text-secondary">或加载已有病例:</span>
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

      {/* Degraded banner — kept (operational warning, not a tech leak) */}
      {caseData?.degraded && (
        <div className="border-b bg-yellow-50 border-yellow-200 px-6 py-2">
          <div className="mx-auto max-w-[1600px] flex items-center gap-2 text-xs text-yellow-900">
            <AlertTriangle className="h-3 w-3" />
            <span>
              部分模型调用降级, 输出可能不完整, 请审核后使用
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
          <p className="text-sm">正在分析病历...</p>
          <p className="text-[11px]">CDI 流水线运行中, 预计 20-30 秒</p>
        </div>
      )}

      {/* Empty state */}
      {loadState === 'idle' && !caseData && (
        <div className="mx-auto max-w-[1600px] py-20 flex flex-col items-center gap-3 text-mono-text-secondary">
          <ClipboardCheck className="h-10 w-10 text-mono-text-secondary/40" />
          <p className="text-sm">输入病历文本, 运行 CDI 分析</p>
          <p className="text-[11px]">
            工作台将识别文档缺口并生成临床澄清任务
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
                病历节选
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

            {/* ─── Status layering (Master Task §7.3) ─── */}
            <section>
              <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
                状态分层
              </h2>
              <div className="space-y-1.5 text-xs">
                <StatusRow label="病例状态" value={caseStatusLabel} />
                <StatusRow
                  label="缺口状态"
                  value={hasGapIssues ? `发现 ${caseData.documentation_gaps.length} 项` : '未发现缺口'}
                />
                <StatusRow
                  label="澄清任务状态"
                  value={
                    hasQueryIssues
                      ? `${caseData.proposed_provider_queries.length} 个任务`
                      : '无任务'
                  }
                />
                <StatusRow
                  label="非诱导检查"
                  value={hasQueryIssues ? nlqStatusLabel : '—'}
                />
                <StatusRow
                  label="必要性检查"
                  value={hasQueryIssues ? '已通过结构检查' : '—'}
                />
                <StatusRow
                  label="证据支持状态"
                  value={
                    hasGapIssues || hasQueryIssues
                      ? '已校验 (每个关键声明均有病历证据)'
                      : '—'
                  }
                />
              </div>
            </section>

            {caseData.specialist_trace.length > 0 && (
              <section>
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
                  专家协作
                </h2>
                <div className="space-y-2">
                  {caseData.specialist_trace.map((t) => {
                    const mode = t.execution_mode ?? '';
                    const invoked = mode === 'REAL_TOOL' || mode === 'LLM_KNOWLEDGE_ONLY';
                    return (
                      <div
                        key={t.expert_id}
                        className="rounded-md border border-mono-border p-2 text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-mono-text-primary">
                            {labelExpert(t.expert_id)}
                          </span>
                          {invoked ? (
                            <CheckCircle2 className="h-3 w-3 text-green-600" />
                          ) : (
                            <XCircle className="h-3 w-3 text-mono-text-secondary" />
                          )}
                        </div>
                        <p className="mt-1 text-[11px] text-mono-text-secondary">
                          {mode ? labelExecutionMode(mode) : (t.consulted ? '已调用' : '未调用')}
                        </p>
                        {invoked && t.rationale && (
                          <p className="mt-1 text-[11px] text-mono-text-secondary leading-relaxed">
                            {t.rationale}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {caseData.risk_flags.length > 0 && (
              <section>
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2">
                  风险提示
                </h2>
                <div className="space-y-2">
                  {caseData.risk_flags.map((r, i) => (
                    <div
                      key={i}
                      className="rounded-md bg-red-50 p-2 text-xs text-red-900"
                    >
                      <div className="font-semibold">{labelRiskCategory(r.category)}</div>
                      <div className="mt-0.5">{r.description}</div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* ─── 技术与审计详情 (collapsed; admin/auditor only) ─── */}
            {showTech && caseData.stage_traces.length > 0 && (
              <section>
                <button
                  onClick={() => setTechDetailsOpen((v) => !v)}
                  className="flex w-full items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-mono-text-secondary mb-2 hover:text-mono-text-primary"
                >
                  <span className="flex items-center gap-1">
                    <Lock className="h-3 w-3" />
                    技术与审计详情 ({caseData.stage_traces.length})
                  </span>
                  {techDetailsOpen ? (
                    <ChevronDown className="h-3 w-3" />
                  ) : (
                    <ChevronRight className="h-3 w-3" />
                  )}
                </button>
                {techDetailsOpen && (
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
                            {t.expert_id ? labelExpert(t.expert_id) : t.stage}
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
                )}
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
              </header>
              <div className="space-y-3">
                {caseData.documentation_gaps.length === 0 ? (
                  <div className="rounded-lg border border-mono-border bg-white p-4 text-xs text-mono-text-secondary">
                    未发现文档缺口
                  </div>
                ) : (
                  caseData.documentation_gaps.map((g) => (
                    <div
                      key={g.gap_id}
                      className="rounded-lg border border-mono-border bg-white p-4"
                    >
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div>
                          <span className="inline-block rounded-full bg-mono-surface px-2 py-0.5 text-[10px] text-mono-text-secondary">
                            {labelGapType(g.gap_type)}
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
                        <div className="text-mono-text-secondary">病历证据:</div>
                        <div className="mt-1 text-mono-text-primary">
                          &ldquo;{g.evidence_span.quote}&rdquo;
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
              </header>
              <div className="space-y-3">
                {caseData.proposed_provider_queries.length === 0 ? (
                  <div className="rounded-lg border border-mono-border bg-white p-4 text-xs text-mono-text-secondary">
                    无临床澄清任务
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
                            非诱导: {labelNLQVerdict(q.nlq_gate_verdict)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] ${LIFECYCLE_COLOR[q.lifecycle_state]}`}
                          >
                            {LIFECYCLE_LABELS[q.lifecycle_state]}
                          </span>
                          <span className="text-[10px] text-mono-text-secondary">
                            {q.response_options.length} 个选项
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
                      任务状态
                    </div>
                    <div
                      className={`mt-1 inline-block rounded-full px-3 py-1 text-xs ${LIFECYCLE_COLOR[selectedQuery.lifecycle_state]}`}
                    >
                      {LIFECYCLE_LABELS[selectedQuery.lifecycle_state]}
                    </div>
                  </div>

                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-mono-text-secondary">
                      澄清问句
                    </div>
                    <p className="mt-1 text-xs text-mono-text-primary leading-relaxed">
                      {selectedQuery.query_text}
                    </p>
                  </div>

                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-mono-text-secondary mb-2">
                      可选答复
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

                  {/* 非诱导检查 summary (no raw NLQ-XXX codes) */}
                  <div className="rounded-md bg-mono-surface p-3 text-xs">
                    <div className="flex items-center gap-2 mb-1">
                      <ShieldCheck className="h-3 w-3 text-green-700" />
                      <span className="font-semibold text-mono-text-primary">
                        非诱导检查
                      </span>
                    </div>
                    <div className="text-mono-text-secondary">
                      结果:{' '}
                      <span className="font-medium">
                        {labelNLQVerdict(selectedQuery.nlq_gate_verdict)}
                      </span>
                    </div>
                    {selectedQuery.nlq_gate_verdict === 'BLOCK' &&
                      selectedQuery.nlq_gate_block_reasons.length > 0 && (
                        <ul className="mt-1 space-y-0.5 text-red-700">
                          {labelRuleIds(selectedQuery.nlq_gate_block_reasons).map((r, i) => (
                            <li key={i} className="text-[10px]">{r}</li>
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
// Status row helper (Master Task §7.3)
// ---------------------------------------------------------------------------

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-mono-text-secondary">{label}</span>
      <span className="text-mono-text-primary text-right">{value}</span>
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

  if (role === 'read_only') {
    return (
      <div className="rounded bg-gray-50 p-2 text-center text-xs text-mono-text-secondary">
        <Eye className="mr-1 inline h-3 w-3" />
        只读权限
      </div>
    );
  }

  const canReviewCDI = role === 'cdi_specialist' || role === 'admin';
  const canRespondClinician = role === 'clinician' || role === 'admin';
  const isAuditor = role === 'auditor';

  if (isAuditor) {
    return (
      <div className="rounded bg-blue-50 p-2 text-center text-xs text-blue-900">
        <Eye className="mr-1 inline h-3 w-3" />
        审计员只读
      </div>
    );
  }

  if (s === 'DRAFT') {
    return (
      <div className="rounded bg-mono-text-secondary/10 p-2 text-center text-xs text-mono-text-secondary">
        <Clock className="mr-1 inline h-3 w-3" />
        CDI 专员提交后进入审核
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
        CDI 专员: 审核通过
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
        已关闭
      </div>
    );
  }

  if (s === 'ESCALATED') {
    return (
      <div className="rounded bg-red-50 p-2 text-center text-xs text-red-800">
        <AlertTriangle className="mr-1 inline h-3 w-3" />
        已升级 — 医生无法确定, 需人工跟进
      </div>
    );
  }

  return null;
}
