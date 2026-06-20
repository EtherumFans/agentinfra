// iCoDer M3-0 — 病案首页编码审核 Agent Workbench
//
// 3 列布局 (原文 / 编码建议 / 证据与风险) + 底部 14 阶段 RunTrace + 人工复核操作条
// 调 /api/icoder/coding-review/{run, {run_id}/human-review, {run_id}/report}

import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ChevronRight, Loader2, Sparkles, Download, ExternalLink, FileText,
  AlertTriangle, Check, X, ShieldAlert, Send, BookOpen, Home,
  ChevronLeft, RefreshCw, Activity, AlertCircle,
} from 'lucide-react';
import { useT } from '../i18n';
import { useToastStore } from '../store';
import {
  icoderCodingReviewApi,
  type CodingReviewRunRequest,
  type CodingReviewRunResponse,
  type HumanReviewAction,
  type DiagnosisCard as DxCard,
} from '../services/icoderCodingReviewApi';
import { EvidenceViewer, type EvidenceSpan } from '../components/icoder/EvidenceViewer';
import { HighRiskCodingPointPanel } from '../components/icoder/HighRiskCodingPointPanel';
import { RunTraceTimeline } from '../components/icoder/RunTraceTimeline';
import { AgentRuntimeConsole } from '../components/agent-console/AgentRuntimeConsole';
import { HumanReviewHistoryTimeline, type HumanReviewHistoryEntry } from '../components/icoder/HumanReviewHistoryTimeline';

const SAMPLE_INPUT = `主诉: 反复胸闷、心悸 3 年, 加重伴夜间呼吸困难 1 周。
现病史: 患者 3 年前无明显诱因出现胸闷心悸, 活动后明显, 休息后可缓解。
曾于外院诊断为 "冠心病", 长期口服阿司匹林、阿托伐他汀。
近 1 周症状加重, 伴夜间阵发性呼吸困难, 需高枕卧位。
既往史: 高血压病史 10 年, 最高 160/100mmHg, 口服氨氯地平 5mg qd。
2 型糖尿病史 5 年, 口服二甲双胍 0.5g tid。
体格检查: BP 138/86mmHg, 双肺呼吸音清, 心率 78 次/分, 律齐。
辅助检查: 心电图 V4-V6 ST 段下移 0.1mV。冠脉造影 LAD 中段狭窄 75%。
入院诊断:
1. 冠状动脉粥样硬化性心脏病 不稳定型心绞痛
2. 高血压病 2 级 (很高危)
3. 2 型糖尿病`;

// M3-0.1 修复: 复核 reason_code 不再硬编码, 改为下拉 + 必填校验
// 文档: 复核原因遵循 M3_HOMEPAGE_CODING_REVIEW_AGENT_SPEC.md §5
const REASON_CODES: Array<{ code: string; label: string; requireForReject: boolean }> = [
  { code: '', label: '— 请选择复核原因 —', requireForReject: false },
  { code: 'R001', label: 'R001 临床依据不足', requireForReject: true },
  { code: 'R002', label: 'R002 编码规则不符 (主诊断选择原则)', requireForReject: true },
  { code: 'R003', label: 'R003 病因 / 临床表现描述不清', requireForReject: true },
  { code: 'R004', label: 'R004 手术 / 操作与诊断不匹配', requireForReject: true },
  { code: 'R005', label: 'R005 漏报 / 错报合并症', requireForReject: true },
  { code: 'R006', label: 'R006 病案首页字段缺失', requireForReject: true },
  { code: 'R007', label: 'R007 医生确认 (accept 默认)', requireForReject: false },
  { code: 'R008', label: 'R008 编码细化 (subdivision)', requireForReject: true },
  { code: 'R009', label: 'R009 编码粗化 (合并)', requireForReject: true },
  { code: 'R010', label: 'R010 字典版本对齐', requireForReject: true },
];

// M3-0.1 修复: PHI 文本脱敏 (前端兜底, 后端也会 redact)
// 18 位身份证 / 11 位手机 / 患者姓名 (2-3 字) 等敏感信息替换为 ****
function redactPhiForView(text: string): string {
  if (!text) return '';
  return text
    .replace(/\d{17}[\dXx]/g, (m) => m.slice(0, 4) + '****' + m.slice(-2))
    .replace(/1[3-9]\d{9}/g, (m) => m.slice(0, 3) + '****' + m.slice(-2))
    .replace(/(患者|姓名|姓)[\s:：]?[一-龥]{2,4}/g, '$1: ****');
}

// M3-0.3: 错误归一化 — 后端 503 的 detail 是对象 {reason, hint}, 直接塞进 string state
// 会让 JSX {error} 渲染对象 → React 抛错 → ErrorBoundary 吞整页。统一转成可读中文字符串。
function friendlyRunError(e: unknown): string {
  if (!e) return 'run failed';
  const detail: any = (e as any)?.response?.data?.detail ?? (e as any)?.detail ?? e;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    if (detail.reason === 'llm_credential_missing') {
      return '后端未配置 LLM 凭证 (ICODER_CREDENTIAL_LLM)，无法运行真实审核。'
        + '本地开发可设 ICODER_ALLOW_DEGRADED_NO_KEY=1 返回降级回显（非真实模型结果）。';
    }
    if (detail.reason) return `运行失败 (${detail.reason})${detail.hint ? ': ' + detail.hint : ''}`;
    if (detail.hint) return detail.hint;
  }
  return (e as any)?.message || String(e);
}

export default function CodingReviewWorkbenchPage() {
  const t = useT();
  const navigate = useNavigate();
  const { runId: routeRunId } = useParams<{ runId?: string }>();
  const toast = useToastStore((s) => s.addToast);

  // 1. 输入
  const [encounterText, setEncounterText] = useState<string>(SAMPLE_INPUT);
  const [primaryCodes, setPrimaryCodes] = useState('I20.000');
  const [otherDiseaseCodes, setOtherDiseaseCodes] = useState('I10.x00, E11.900');
  const [primarySurgeryCodes, setPrimarySurgeryCodes] = useState('');
  const [otherSurgeryCodes, setOtherSurgeryCodes] = useState('');
  const [caseId, setCaseId] = useState('c-' + Date.now().toString(36));
  const [inputSource, setInputSource] = useState('manual');

  // 2. Run 状态
  const [response, setResponse] = useState<CodingReviewRunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [centerError, setCenterError] = useState<string>('');
  const [rightError, setRightError] = useState<string>('');
  const [currentRunId, setCurrentRunId] = useState<string | undefined>(routeRunId);

  // 3. Human review 状态
  const [reviewerName, setReviewerName] = useState('dr.li');
  const [reviewerRole, setReviewerRole] = useState('medical_insurance_reviewer');
  const [humanLoading, setHumanLoading] = useState(false);
  const [humanResult, setHumanResult] = useState<any>(null);
  // M3-0.2 P5: 人工复核历史 timeline (本会话内累计, 不持久化)
  const [humanHistory, setHumanHistory] = useState<HumanReviewHistoryEntry[]>([]);
  // M3-0.2: 底部 trace 视图切换 (Simple Trace / Agent Runtime Console)
  const [traceView, setTraceView] = useState<'simple' | 'console'>('simple');
  // M3-0.2 P4: 点击 candidate → 高亮证据 (scrollIntoView in EvidenceViewer)
  const [highlightAnchor, setHighlightAnchor] = useState<string | undefined>(undefined);
  // M3-0.1: 当前操作的 reason code + review note (弹层用)
  const [pendingReview, setPendingReview] = useState<{
    action: HumanReviewAction['action']; code: string; role: string;
  } | null>(null);
  const [pendingReason, setPendingReason] = useState<string>('');
  const [pendingNote, setPendingNote] = useState<string>('');
  const [pendingNewCode, setPendingNewCode] = useState<string>('');

  // ── route: 加载既有 run ────────────────────────────────
  useEffect(() => {
    if (!routeRunId) return;
    setCurrentRunId(routeRunId);
    icoderCodingReviewApi.getRun(routeRunId)
      .then((r) => setResponse(r))
      .catch((e) => setError(`${t.cr.runFailed}: ${friendlyRunError(e)}`));
  }, [routeRunId, t.cr.runFailed]);

  // ── run 提交 ──────────────────────────────────────────
  async function handleRun() {
    setLoading(true);
    setError('');
    setCenterError('');
    setRightError('');
    setHumanResult(null);
    try {
      const req: CodingReviewRunRequest = {
        encounter_text: encounterText,
        case_id: caseId,
        input_source: inputSource,
        mode: 'link_validation',
        primary_disease_codes: primaryCodes,
        other_disease_codes: otherDiseaseCodes,
        primary_surgery_codes: primarySurgeryCodes,
        other_surgery_codes: otherSurgeryCodes,
      };
      const r = await icoderCodingReviewApi.run(req);
      setResponse(r);
      setCurrentRunId(r.run_id);
      navigate(`/runtime/coding-review/${r.run_id}`, { replace: true });
    } catch (e: any) {
      const msg = friendlyRunError(e);
      setError(msg);
      setCenterError(msg);
      toast(t.cr.runFailed, 'error');
    } finally {
      setLoading(false);
    }
  }

  // ── human review: 打开弹层 (M3-0.1 修复: 显式 reason code + 全 5 actions) ──
  function openReview(
    action: HumanReviewAction['action'],
    code: string,
    role: string,
    presetReason: string = '',
  ) {
    if (!currentRunId) {
      toast(t.cr.pleaseRunFirst, 'error');
      return;
    }
    setPendingReview({ action, code, role });
    setPendingReason(presetReason);
    setPendingNote('');
    setPendingNewCode(code); // modify 默认填原码
  }

  // ── human review: 弹层提交 (含 reason code 校验) ─────────
  async function handleHumanReview() {
    if (!pendingReview || !currentRunId) return;
    // reason_code 强校验: reject / modify / insufficient_evidence 必填非空
    const requireReason = ['reject', 'modify', 'insufficient_evidence', 'escalate'].includes(pendingReview.action);
    if (requireReason && !pendingReason) {
      toast('请选择复核原因 (reason_code)', 'error');
      return;
    }
    if (pendingReview.action === 'modify' && !pendingNewCode.trim()) {
      toast('modify 必须填写新码', 'error');
      return;
    }
    setHumanLoading(true);
    setRightError('');
    try {
      const payload: HumanReviewAction = {
        action: pendingReview.action,
        target_code: pendingReview.code,
        target_role: pendingReview.role,
        reason_code: pendingReason || 'R007', // accept 允许默认 R007
        review_note: pendingNote,
        reviewer: reviewerName,
        reviewer_role: reviewerRole,
        ...(pendingReview.action === 'modify' ? { new_code: pendingNewCode } : {}),
      };
      const r = await icoderCodingReviewApi.humanReview(currentRunId, payload);
      setHumanResult(r);
      if (r.accepted) {
        // M3-0.2 P5: 记录到 timeline
        setHumanHistory((prev) => [
          {
            record_id: r.record_id,
            recorded_at: r.recorded_at,
            action: pendingReview.action,
            target_code: pendingReview.code,
            target_role: pendingReview.role,
            new_code: pendingReview.action === 'modify' ? pendingNewCode : undefined,
            reason_code: pendingReason,
            review_note: pendingNote,
            reviewer: reviewerName,
            reviewer_role: reviewerRole,
            accepted: true,
          },
          ...prev,
        ]);
        toast(`${t.cr.reviewRecorded} (action=${pendingReview.action} code=${pendingReview.code})`, 'success');
        setPendingReview(null);
      } else {
        // 即使 validation 不通过, 也记录到 timeline (用于审计)
        setHumanHistory((prev) => [
          {
            record_id: r.record_id || `failed-${Date.now()}`,
            recorded_at: r.recorded_at || new Date().toISOString(),
            action: pendingReview.action,
            target_code: pendingReview.code,
            target_role: pendingReview.role,
            new_code: pendingReview.action === 'modify' ? pendingNewCode : undefined,
            reason_code: pendingReason,
            review_note: pendingNote,
            reviewer: reviewerName,
            reviewer_role: reviewerRole,
            accepted: false,
            validation_errors: r.validation_errors,
          },
          ...prev,
        ]);
        toast(`${t.cr.reviewNotPassed}: ${r.validation_errors.join('; ')}`, 'error');
      }
    } catch (e: any) {
      const msg = friendlyRunError(e);
      setRightError(msg);
      toast(`${t.cr.reviewFailed}: ${msg}`, 'error');
    } finally {
      setHumanLoading(false);
    }
  }

  // ── 报告下载 + 顶部 disclaimer 浮层 (M3-0.1 修复) ─────────
  const [reportNotice, setReportNotice] = useState<{
    format: 'html' | 'json'; filename: string; disclaimer: string;
  } | null>(null);
  async function handleReport(format: 'html' | 'json' = 'html') {
    if (!currentRunId) return;
    try {
      const r = await icoderCodingReviewApi.report(currentRunId, format);
      if (format === 'json') {
        const blob = new Blob([r.content], { type: 'application/json' });
        triggerDownload(blob, r.filename);
      } else {
        const blob = new Blob([r.content], { type: 'text/html' });
        triggerDownload(blob, r.filename);
      }
      setReportNotice({ format, filename: r.filename, disclaimer: r.disclaimer });
      toast(`${t.cr.downloadReport}: ${r.filename}`, 'success');
    } catch (e: any) {
      toast(`${t.cr.downloadFailed}: ${friendlyRunError(e)}`, 'error');
    }
  }

  // ── sourceText 来自 encounterText (M3-0 简化, 全归 present_illness) ──
  const sourceText = useMemo<Record<string, string>>(() => {
    return { present_illness: encounterText };
  }, [encounterText]);

  // ── evidence span (M3-0 阶段, 简单 substring 锚定主诊断码) ──
  const evidenceSpans = useMemo<EvidenceSpan[]>(() => {
    if (!response) return [];
    const spans: EvidenceSpan[] = [];
    const targets: { code: string; card?: DxCard | null }[] = [
      { code: response.primary_diagnosis?.code || '', card: response.primary_diagnosis },
      ...(response.secondary_diagnoses || []).map((c) => ({ code: c.code, card: c })),
      ...(response.procedures || []).map((c) => ({ code: c.code, card: c })),
    ].filter((t) => t.code);
    for (const t of targets) {
      // 找 code 描述中前 6 字作为证据 text
      const desc = t.card?.description || t.code;
      const head = desc.slice(0, 6);
      const idx = encounterText.indexOf(head);
      const text = idx >= 0 ? encounterText.slice(idx, idx + Math.min(head.length + 6, 18)) : desc;
      spans.push({
        id: `span-${t.code}-${Math.random().toString(36).slice(2, 8)}`,
        field: 'present_illness',
        text,
        match_method: 'auto_bootstrap',
        confidence: t.card?.confidence,
        kind: 'auto_bootstrap',
        target_code: t.code,
      });
    }
    return spans;
  }, [response, encounterText]);

  return (
    <div className="flex flex-col h-full bg-background">
      {/* ── Header (面包屑) ───────────────────────────── */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-border/20 shrink-0 text-xs">
        <Link to="/studio" className="text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1">
          <Home size={12} /> iCoDer
        </Link>
        <ChevronRight size={12} className="text-muted-foreground/50" />
        <Link to="/studio/agents" className="text-muted-foreground hover:text-foreground transition-colors">
          {t.cr.pageTitle}
        </Link>
        <ChevronRight size={12} className="text-muted-foreground/50" />
        <span className="text-foreground font-medium truncate">{t.cr.pageTitle} Agent</span>
        <div className="ml-auto flex items-center gap-3 text-muted-foreground">
          <a href="/docs" className="hover:text-foreground transition-colors">{t.documentation}</a>
        </div>
      </div>

      {/* M3-0.2 Premium: 顶部关键状态 bar (Agent + Status + 红线必显) ── */}
      <div
        data-testid="workbench-status-bar"
        className="px-4 py-1.5 border-b border-border/20 bg-slate-50/40 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] shrink-0"
      >
        {/* Agent 名 + 版本 */}
        <span className="inline-flex items-center gap-1 font-mono text-slate-700">
          <Activity size={11} className="text-slate-500" />
          icoder/homepage-coding-review-agent@1.0.0
        </span>
        <span className="text-slate-300">|</span>

        {/* Status pill (M3-0 红线 — 不可省略) */}
        <span
          data-testid="workbench-status-pill"
          data-status={response?.status || 'idle'}
          className={[
            'inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-medium',
            response?.status === 'ok' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
            response?.status === 'unavailable' ? 'bg-rose-50 text-rose-700 border-rose-200' :
            response?.status === 'degraded' ? 'bg-amber-50 text-amber-700 border-amber-200' :
            'bg-slate-50 text-slate-500 border-slate-200',
          ].join(' ')}
        >
          {response?.status === 'ok' ? <Check size={10} /> : <AlertTriangle size={10} />}
          {response?.status || 'idle'}
        </span>

        {/* production_writeback_blocked (M3-0 红线 — 永远 true) */}
        <span
          data-testid="workbench-writeback-blocked"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-rose-200 bg-rose-50 text-rose-700 text-[10px] font-medium"
          title="永真 — 任何路径都不会写回 HIS/EMR"
        >
          <ShieldAlert size={10} />
          writeback_blocked=true
        </span>

        {/* human_review_required (依赖 response) */}
        {response?.manual_review_required && (
          <span
            data-testid="workbench-human-review-required"
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-amber-200 bg-amber-50 text-amber-700 text-[10px] font-medium"
          >
            <AlertCircle size={10} />
            human_review_required
          </span>
        )}

        {/* DRG bundled KB (M3-0 红线) */}
        <span
          data-testid="workbench-drg-bundled"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-amber-200 bg-amber-50 text-amber-700 text-[10px] font-medium"
          title="当前为 bundled CHS-DRG 1.1 KB 内置分组器, 不等于医院内网 OpenDRG"
        >
          DRG bundled KB
        </span>

        {/* PHI 脱敏提示 (永远显示) */}
        <span
          data-testid="workbench-phi-badge"
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-blue-200 bg-blue-50 text-blue-700 text-[10px] font-medium"
          title="已对 18 位身份证 / 11 位手机号 / 患者姓名做前端脱敏 (与后端 PHI 脱敏一致)"
        >
          <ShieldAlert size={10} />
          PHI redacted
        </span>

        {/* 右侧 — disclaimer 永远可见 (M3-0 红线) */}
        <span
          data-testid="workbench-disclaimer-pill"
          className="ml-auto inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-blue-200 bg-blue-50 text-blue-800 text-[10px] font-medium"
          title="本报告为样板 Agent 输出, 不代表模型效果, 不接 EMR 生产写回"
        >
          <BookOpen size={10} />
          Pipeline Validation Disclaimer
        </span>
      </div>

      {/* ── 顶部介绍条 ────────────────────────────────── */}
      <div className="px-4 py-2 border-b border-border/20 bg-blue-50/40 text-[11px] text-slate-600 leading-relaxed shrink-0">
        <span className="inline-flex items-center gap-1 font-medium text-blue-700">
          <BookOpen size={12} />
          iCoDer 第一个官方样板 Agent
        </span>
        <span className="ml-2">
          pipeline validation 模式 — 验证 iCoDer Runtime / 14 阶段工具编排 / 证据回链 / 风险路由 / 医学安全门禁 / 人工复核 / 审计 / 嵌入 端到端能力,
          <strong className="text-rose-700">不代表模型效果</strong>, 不可用于生产写回 (production_writeback_blocked 永远为 true)。
        </span>
      </div>

      {/* ── 三列工作区 ────────────────────────────────── */}
      <div className="flex-1 grid grid-cols-12 gap-3 p-3 overflow-hidden min-h-0">
        {/* 左列: 原文 + 输入 */}
        <div
          className="col-span-3 flex flex-col gap-3 overflow-y-auto min-h-0"
          tabIndex={0}
          role="region"
          aria-label="输入参数与病历原文"
        >
          <div className="rounded-lg border border-border/40 bg-white p-3 flex flex-col gap-2">
            <div className="text-xs font-medium text-slate-700">输入参数</div>
            <Field label={t.cr.caseId}>
              <input
                value={caseId}
                onChange={(e) => setCaseId(e.target.value)}
                className="w-full text-xs px-2 py-1 border border-border/40 rounded"
                placeholder={t.cr.caseIdPlaceholder}
                aria-label={t.cr.caseId}
              />
            </Field>
            <Field label={t.cr.inputSource}>
              <input
                value={inputSource}
                onChange={(e) => setInputSource(e.target.value)}
                className="w-full text-xs px-2 py-1 border border-border/40 rounded"
                aria-label={t.cr.inputSource}
              />
            </Field>
            <Field label={t.cr.primaryDiseaseCodes}>
              <input
                value={primaryCodes}
                onChange={(e) => setPrimaryCodes(e.target.value)}
                className="w-full text-xs px-2 py-1 border border-border/40 rounded font-mono"
                placeholder={t.cr.primaryDiseaseCodesPlaceholder}
              />
            </Field>
            <Field label={t.cr.otherDiseaseCodes}>
              <input
                value={otherDiseaseCodes}
                onChange={(e) => setOtherDiseaseCodes(e.target.value)}
                className="w-full text-xs px-2 py-1 border border-border/40 rounded font-mono"
                placeholder={t.cr.otherDiseaseCodesPlaceholder}
              />
            </Field>
            <Field label={t.cr.primarySurgeryCodes}>
              <input
                value={primarySurgeryCodes}
                onChange={(e) => setPrimarySurgeryCodes(e.target.value)}
                className="w-full text-xs px-2 py-1 border border-border/40 rounded font-mono"
                placeholder={t.cr.primarySurgeryCodesPlaceholder}
              />
            </Field>
            <Field label={t.cr.otherSurgeryCodes}>
              <input
                value={otherSurgeryCodes}
                onChange={(e) => setOtherSurgeryCodes(e.target.value)}
                className="w-full text-xs px-2 py-1 border border-border/40 rounded font-mono"
                placeholder={t.cr.otherSurgeryCodesPlaceholder}
              />
            </Field>
          </div>

          <div className="rounded-lg border border-border/40 bg-white p-3 flex flex-col gap-2 flex-1 min-h-0">
            <div className="text-xs font-medium text-slate-700 flex items-center gap-1">
              <FileText size={12} /> 病历原文
            </div>
            {/* M3-0.1 修复: PHI 脱敏说明 + textarea 内的展示文本脱敏 */}
            <div className="text-[10px] text-slate-500 flex items-center gap-1" data-testid="phi-notice">
              <ShieldAlert size={10} className="text-amber-500" />
              已对 18 位身份证 / 11 位手机号 / 患者姓名做前端脱敏（与后端 PHI 脱敏一致）
            </div>
            <textarea
              value={encounterText}
              onChange={(e) => setEncounterText(e.target.value)}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !loading && encounterText.trim()) {
                  e.preventDefault();
                  handleRun();
                }
              }}
              className="flex-1 min-h-[200px] w-full text-[11px] leading-relaxed px-2 py-1.5 border border-border/40 rounded font-mono resize-none"
              placeholder={t.cr.encounterTextPlaceholder}
            />
            <div className="flex gap-1.5">
              <button
                onClick={handleRun}
                disabled={loading || !encounterText.trim()}
                aria-busy={loading}
                className="flex-1 px-3 py-1.5 rounded-md bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1"
              >
                {loading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                {loading ? t.cr.running : t.cr.runButton}
              </button>
              <button
                onClick={() => setEncounterText(SAMPLE_INPUT)}
                className="px-2 py-1.5 rounded-md border border-border/40 text-xs hover:bg-slate-50"
                title={t.cr.loadSample}
              >
                <RefreshCw size={12} />
              </button>
            </div>
            {!encounterText.trim() ? (
              <p data-testid="empty-input-hint" className="text-[10px] text-slate-400">请输入病历原文后运行</p>
            ) : (
              <p className="text-[10px] text-slate-400">⌘/Ctrl + Enter 运行</p>
            )}
            {error && (
              <div className="text-[11px] text-rose-600 bg-rose-50 border border-rose-200 rounded p-1.5 flex items-center justify-between gap-2">
                <span className="flex-1 break-all">{error}</span>
                <button
                  onClick={handleRun}
                  disabled={loading}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-rose-100 hover:bg-rose-200 text-rose-700 shrink-0"
                >
                  {t.cr.inlineErrorRetry}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* 中列: 编码建议 */}
        <div
          className="col-span-5 flex flex-col gap-3 overflow-y-auto min-h-0"
          tabIndex={0}
          role="region"
          aria-label="编码建议与诊断"
        >
          {centerError && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 text-rose-700 p-2.5 text-xs flex items-center justify-between gap-2">
              <span className="flex-1 break-all">
                <AlertTriangle size={12} className="inline-block mr-1 -mt-0.5" />
                {centerError}
              </span>
              <button
                onClick={handleRun}
                disabled={loading}
                className="text-[10px] px-1.5 py-0.5 rounded bg-rose-100 hover:bg-rose-200 text-rose-700 shrink-0"
              >
                {t.cr.inlineErrorRetry}
              </button>
            </div>
          )}
          {loading && !response ? (
            <div
              data-testid="center-loading-panel"
              role="status"
              aria-live="polite"
              className="rounded-lg border border-blue-200 bg-blue-50/40 p-8 text-center text-slate-600 text-sm flex-1 flex items-center justify-center"
            >
              <div>
                <Loader2 size={24} className="mx-auto mb-2 animate-spin text-blue-600" />
                <div className="font-medium text-slate-700">{t.cr.running}</div>
                <div className="text-xs text-slate-500 mt-1">正在执行 14 阶段管线审核…</div>
              </div>
            </div>
          ) : !response ? (
            <div className="rounded-lg border border-dashed border-border/40 bg-slate-50/30 p-8 text-center text-slate-500 text-sm flex-1 flex items-center justify-center">
              <div>
                <Sparkles size={24} className="mx-auto mb-2 opacity-40" />
                {t.cr.runFirstHint}
              </div>
            </div>
          ) : (
            <>
              {/* Status banner */}
              <div className={[
                'rounded-lg border p-2.5 text-xs flex items-center gap-2',
                response.status === 'ok' ? 'bg-emerald-50 border-emerald-200 text-emerald-700' :
                response.status === 'unavailable' ? 'bg-rose-50 border-rose-200 text-rose-700' :
                'bg-amber-50 border-amber-200 text-amber-700',
              ].join(' ')}>
                {response.status === 'ok' ? <Check size={14} /> : <AlertTriangle size={14} />}
                <span className="font-medium">
                  {response.status === 'ok' && t.cr.reviewComplete}
                  {response.status === 'unavailable' && t.cr.noResult}
                  {response.status === 'degraded' && t.cr.reviewDegraded}
                </span>
                <span className="ml-auto text-[10px] opacity-70">
                  {response.prediction_mode} · {response.business_result_generated ? t.cr.businessResultGenerated : t.cr.businessResultNotGenerated}
                  {response.manual_review_required && ` · ${t.cr.manualReviewRequired}`}
                </span>
              </div>

              {/* 编码卡片 — M3-0.1 修复: 全 5 actions + reason code 强校验 */}
              <CodeCardGroup
                title="Primary"
                color="blue"
                items={response.primary_diagnosis ? [response.primary_diagnosis] : []}
                spans={evidenceSpans}
                onClickCard={setHighlightAnchor}
                onAccept={(code) => openReview('accept', code, 'primary_disease', 'R007')}
                onReject={(code) => openReview('reject', code, 'primary_disease')}
                onModify={(code) => openReview('modify', code, 'primary_disease')}
                onInsufficient={(code) => openReview('insufficient_evidence', code, 'primary_disease')}
                onEscalate={(code) => openReview('escalate', code, 'primary_disease')}
              />
              <CodeCardGroup
                title="Secondary"
                color="slate"
                items={response.secondary_diagnoses || []}
                spans={evidenceSpans}
                onClickCard={setHighlightAnchor}
                onAccept={(code) => openReview('accept', code, 'other_disease', 'R007')}
                onReject={(code) => openReview('reject', code, 'other_disease')}
                onInsufficient={(code) => openReview('insufficient_evidence', code, 'other_disease')}
                onEscalate={(code) => openReview('escalate', code, 'other_disease')}
              />
              <CodeCardGroup
                title="Procedures"
                color="purple"
                items={response.procedures || []}
                spans={evidenceSpans}
                onClickCard={setHighlightAnchor}
                onAccept={(code) => openReview('accept', code, 'primary_surgery', 'R007')}
                onReject={(code) => openReview('reject', code, 'primary_surgery')}
                onModify={(code) => openReview('modify', code, 'primary_surgery')}
                onInsufficient={(code) => openReview('insufficient_evidence', code, 'primary_surgery')}
                onEscalate={(code) => openReview('escalate', code, 'primary_surgery')}
              />
            </>
          )}
        </div>

        {/* 右列: 证据与风险 */}
        <div
          className="col-span-4 flex flex-col gap-3 overflow-y-auto min-h-0"
          tabIndex={0}
          role="region"
          aria-label="证据、风险与人工复核"
        >
          {rightError && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 text-rose-700 p-2.5 text-xs flex items-center justify-between gap-2">
              <span className="flex-1 break-all">
                <AlertTriangle size={12} className="inline-block mr-1 -mt-0.5" />
                {rightError}
              </span>
              <button
                onClick={() => setRightError('')}
                className="text-[10px] px-1.5 py-0.5 rounded bg-rose-100 hover:bg-rose-200 text-rose-700 shrink-0"
              >
                {t.dismiss}
              </button>
            </div>
          )}
          {response && (
            <>
              {/* 高风险易错编码点 */}
              <Section title={t.cr.highRisk}>
                <HighRiskCodingPointPanel response={response} />
              </Section>

              {/* 风险路由 + 医学安全门禁 */}
              <Section title={t.cr.riskRoute}>
                <RiskRouteBar risk={response.risk_route} />
              </Section>
              <Section title={t.cr.safetyGate}>
                <SafetyGateBar gate={response.safety_gate} />
              </Section>

              {/* M3-0.2 P5: 人工复核历史时间线 */}
              <Section title={t.cr.humanReviewHistory}>
                <HumanReviewHistoryTimeline entries={humanHistory} />
              </Section>

              {/* DRG 分组 */}
              {response.drg_route && (
                <Section title={t.cr.drgRoute}>
                  <DRGRouteBar drg={response.drg_route} />
                  <div className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded p-1.5 mt-1.5" data-testid="drg-bundled-notice">
                    ⓘ 当前为 <strong>bundled CHS-DRG 1.1 KB</strong> 内置分组器；
                    不等于医院内网 <code>OpenDRG</code> 实际分组结果。
                    医院正式部署需对接真实 DRG/DIP 分组器。
                  </div>
                </Section>
              )}

              {/* 证据回链 */}
              <Section title={t.cr.evidenceChain}>
                <EvidenceViewer
                  sourceText={sourceText}
                  spans={evidenceSpans}
                  highlightAnchor={highlightAnchor}
                  compact
                />
                {/* M3-0.2 P4: 无证据时提示 */}
                {evidenceSpans.length === 0 && (
                  <div className="mt-2 text-[10px] text-slate-500 italic" data-testid="evidence-empty-state">
                    ⓘ 当前 run 未返回 evidence_chain — 请检查 LLM 输出或切换更高 rank 模型
                  </div>
                )}
              </Section>
            </>
          )}
        </div>
      </div>

      {/* ── 底部: RunTrace + 操作条 (M3-0.2 修复: 始终渲染 tabs, 无 response 时空态) ── */}
      <div className="border-t border-border/20 bg-slate-50/30 shrink-0">
        {/* M3-0.2: Tab 切换 — Simple Trace / Agent Runtime Console (always visible) */}
        <div className="flex items-center gap-1 px-3 pt-2" role="tablist" aria-label="Trace 视图切换">
          <button
            type="button"
            role="tab"
            data-testid="tab-simple-trace"
            aria-selected={traceView === 'simple'}
            aria-controls="trace-panel-simple"
            onClick={() => setTraceView('simple')}
            className={[
              'px-3 py-1 text-[11px] rounded-t border-b-0 border transition-colors',
              traceView === 'simple'
                ? 'bg-white border-border/40 text-slate-800 font-medium'
                : 'bg-transparent border-transparent text-slate-500 hover:text-slate-700',
            ].join(' ')}
          >
            Simple Trace
          </button>
          <button
            type="button"
            role="tab"
            data-testid="tab-agent-console"
            aria-selected={traceView === 'console'}
            aria-controls="trace-panel-console"
            onClick={() => setTraceView('console')}
            className={[
              'px-3 py-1 text-[11px] rounded-t border-b-0 border transition-colors flex items-center gap-1',
              traceView === 'console'
                ? 'bg-white border-border/40 text-slate-800 font-medium'
                : 'bg-transparent border-transparent text-slate-500 hover:text-slate-700',
            ].join(' ')}
          >
            Agent Console
            <span className="text-[9px] text-amber-700 bg-amber-50 border border-amber-200 px-1 rounded">TUI</span>
          </button>
        </div>
        <div className="grid grid-cols-12 gap-3 px-3 pb-3">
          <div className="col-span-8 bg-white border border-border/40 rounded-b-lg rounded-tr-lg p-3">
            {/* M3-0.2 P9: 两个 tabpanel 始终渲染 (hidden by default), 保证 aria-controls 永远指向存在的 element */}
            <div
              id="trace-panel-simple"
              role="tabpanel"
              aria-labelledby="tab-simple-trace"
              hidden={traceView !== 'simple'}
            >
              {response
                ? <RunTraceTimeline response={response} compact />
                : <div className="text-[11px] text-slate-500 italic flex items-center justify-center min-h-[80px]" data-testid="trace-empty-state">(尚无运行结果 — 请先点击 "运行 14 阶段审核")</div>
              }
            </div>
            <div
              id="trace-panel-console"
              role="tabpanel"
              aria-labelledby="tab-agent-console"
              hidden={traceView !== 'console'}
            >
              {response
                ? <AgentRuntimeConsole response={response} />
                : <div className="text-[11px] text-slate-500 italic flex items-center justify-center min-h-[80px]" data-testid="trace-empty-state">(尚无运行结果 — 请先点击 "运行 14 阶段审核")</div>
              }
            </div>
          </div>
          <div className="col-span-4 flex flex-col gap-2">
            <div className="text-[11px] text-slate-500">
              <label htmlFor="human-review-reviewer-name">Reviewer:</label>
              <input
                id="human-review-reviewer-name"
                value={reviewerName}
                onChange={(e) => setReviewerName(e.target.value)}
                className="ml-1 w-20 text-[11px] px-1.5 py-0.5 border border-border/40 rounded"
                aria-label="Reviewer name"
              />
              <select
                value={reviewerRole}
                onChange={(e) => setReviewerRole(e.target.value)}
                className="ml-1 text-[11px] px-1.5 py-0.5 border border-border/40 rounded"
                aria-label="Reviewer role"
              >
                <option value="medical_insurance_reviewer">Medical Insurance Reviewer</option>
                <option value="coder">Coder</option>
                <option value="attending">Attending</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            {response && (
              <>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => handleReport('html')}
                    disabled={!currentRunId}
                    className="flex-1 px-2.5 py-1.5 rounded-md border border-border/40 text-xs hover:bg-white flex items-center justify-center gap-1"
                  >
                    <Download size={12} /> HTML
                  </button>
                  <button
                    onClick={() => handleReport('json')}
                    disabled={!currentRunId}
                    className="flex-1 px-2.5 py-1.5 rounded-md border border-border/40 text-xs hover:bg-white flex items-center justify-center gap-1"
                  >
                    <Download size={12} /> JSON
                  </button>
                  <a
                    href={response.trace_url}
                    target="_blank"
                    rel="noreferrer"
                    className="px-2.5 py-1.5 rounded-md border border-border/40 text-xs hover:bg-white flex items-center gap-1"
                    title={t.cr.openTrace}
                  >
                    <ExternalLink size={12} /> Trace
                  </a>
                </div>
                {humanResult && (
                  <div className={[
                    'text-[11px] rounded p-1.5 border',
                    humanResult.accepted ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-rose-50 border-rose-200 text-rose-700',
                  ].join(' ')}>
                    {humanResult.accepted
                      ? `✓ ${t.cr.reviewRecorded} (action=${humanResult.action}, target=${humanResult.target_code}) — production_writeback_blocked=true`
                      : `✗ ${t.cr.reviewNotPassed}: ${(humanResult.validation_errors || []).join('; ')}`}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* M3-0.1 修复: 报告下载后顶部 disclaimer 浮层 (production_writeback_blocked + AI 需人工复核) */}
      {reportNotice && (
        <div className="fixed top-3 left-1/2 -translate-x-1/2 z-40 max-w-2xl w-full px-3" data-testid="report-disclaimer-banner" role="status">
          <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 shadow-lg text-[11px] text-slate-800">
            <div className="flex items-start gap-2">
              <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />
              <div className="flex-1 space-y-1">
                <div className="font-semibold text-amber-900">
                  已下载报告 {reportNotice.format.toUpperCase()} — {reportNotice.filename}
                </div>
                <div className="text-amber-800 leading-relaxed">{reportNotice.disclaimer}</div>
                <div className="text-rose-700 font-medium">
                  ⓘ production_writeback_blocked=true (永真) — 报告不写回 HIS/EMR, AI 建议需人工复核
                </div>
              </div>
              <button onClick={() => setReportNotice(null)} aria-label="关闭" data-testid="report-notice-close"
                className="text-amber-700 hover:text-amber-900 text-base leading-none shrink-0">×</button>
            </div>
          </div>
        </div>
      )}

      {/* M3-0.1 修复: 复核原因弹层 (reason code 必填) */}
      <ReviewReasonDialog
        pending={pendingReview}
        pendingReason={pendingReason}
        setPendingReason={setPendingReason}
        pendingNote={pendingNote}
        setPendingNote={setPendingNote}
        pendingNewCode={pendingNewCode}
        setPendingNewCode={setPendingNewCode}
        onSubmit={handleHumanReview}
        onCancel={() => setPendingReview(null)}
        humanLoading={humanLoading}
      />
    </div>
  );
}

// ── 小工具组件 ────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] text-slate-500 mb-0.5">{label}</div>
      {children}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/40 bg-white p-3">
      <div className="text-xs font-medium text-slate-700 mb-2">{title}</div>
      {children}
    </div>
  );
}

function CodeCardGroup({
  title, color, items, spans, onClickCard, onAccept, onReject, onModify, onInsufficient, onEscalate,
}: {
  title: string;
  color: 'blue' | 'slate' | 'purple';
  items: DxCard[];
  spans?: { target_code?: string; kind?: string }[];
  onClickCard?: (code: string) => void;
  onAccept?: (code: string) => void;
  onReject?: (code: string) => void;
  onModify?: (code: string) => void;
  onInsufficient?: (code: string) => void;
  onEscalate?: (code: string) => void;
}) {
  const t = useT();
  if (items.length === 0) return null;
  const colorMap = {
    blue: 'border-blue-200 bg-blue-50/30',
    slate: 'border-slate-200 bg-slate-50/30',
    purple: 'border-purple-200 bg-purple-50/30',
  } as const;
  return (
    <div className="rounded-lg border border-border/40 bg-white p-3">
      <div className="text-xs font-medium text-slate-700 mb-2">
        {title} <span className="text-slate-400">({items.length})</span>
      </div>
      <div className="flex flex-col gap-2">
        {items.map((c) => {
          // M3-0.2 P4: 计算 evidence trust — auto-only / has-gold / no-evidence
          const codeSpans = (spans || []).filter((s) => s.target_code === c.code);
          const hasGold = codeSpans.some((s) => s.kind === 'gold');
          const trustLevel: 'no-evidence' | 'auto-only' | 'has-gold' =
            codeSpans.length === 0 ? 'no-evidence' :
            hasGold ? 'has-gold' :
            'auto-only';
          return (
          <div key={c.code}
            className={['rounded-md border p-2 cursor-pointer transition-colors', colorMap[color]].join(' ')}
            data-testid={`code-card-${c.code}`}
            data-trust={trustLevel}
            onClick={() => onClickCard?.(c.code)}
            title={onClickCard ? `点击查看 ${c.code} 的证据` : undefined}
          >
            <div className="flex items-center gap-2 mb-1">
              <code className="text-sm font-semibold text-slate-900 bg-white px-1.5 py-0.5 rounded border border-slate-200">
                {c.code}
              </code>
              <span className="text-xs text-slate-700 flex-1 truncate">{c.description}</span>
              {typeof c.confidence === 'number' && (
                <span className="text-[10px] text-slate-500 font-mono" title="AI 置信度, 不代表编码正确性">
                  {(c.confidence * 100).toFixed(0)}%
                </span>
              )}
              {c.human_review_required && (
                <span className="text-[10px] text-rose-600" data-testid="manual-review-required">{t.cr.manualReviewRequired}</span>
              )}
            </div>
            {/* M3-0.2 P4: Trust indicator */}
            <div className="flex items-center gap-1 text-[10px] mb-1" data-testid={`trust-indicator-${c.code}`}>
              {trustLevel === 'has-gold' && (
                <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                  ● has-gold (人工确认)
                </span>
              )}
              {trustLevel === 'auto-only' && (
                <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                  ○ auto-only ({codeSpans.length} 条)
                </span>
              )}
              {trustLevel === 'no-evidence' && (
                <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
                  ⚠ no-evidence
                </span>
              )}
            </div>
            {/* M3-0.1 修复: 全 5 actions, 不用 window.prompt() — onClick 阻止冒泡以免触发 card 点击 */}
            <div className="flex flex-wrap gap-1" data-testid={`code-actions-${c.code}`} onClick={(e) => e.stopPropagation()}>
              {onAccept && (
                <button onClick={() => onAccept(c.code)} data-testid="action-accept"
                  className="px-2 py-0.5 rounded text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 flex items-center gap-0.5">
                  <Check size={10} /> accept
                </button>
              )}
              {onReject && (
                <button onClick={() => onReject(c.code)} data-testid="action-reject"
                  className="px-2 py-0.5 rounded text-[10px] bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 flex items-center gap-0.5">
                  <X size={10} /> reject
                </button>
              )}
              {onModify && (
                <button onClick={() => onModify(c.code)} data-testid="action-modify"
                  className="px-2 py-0.5 rounded text-[10px] bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 flex items-center gap-0.5">
                  <Send size={10} /> modify
                </button>
              )}
              {onInsufficient && (
                <button onClick={() => onInsufficient(c.code)} data-testid="action-insufficient"
                  className="px-2 py-0.5 rounded text-[10px] bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 flex items-center gap-0.5">
                  <AlertTriangle size={10} /> insufficient
                </button>
              )}
              {onEscalate && (
                <button onClick={() => onEscalate(c.code)} data-testid="action-escalate"
                  className="px-2 py-0.5 rounded text-[10px] bg-purple-50 text-purple-700 border border-purple-200 hover:bg-purple-100 flex items-center gap-0.5">
                  <ShieldAlert size={10} /> escalate
                </button>
              )}
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}

// M3-0.1 修复: 复核原因弹层 (reason code 必填 + review note 可选)
function ReviewReasonDialog({
  pending, pendingReason, setPendingReason, pendingNote, setPendingNote,
  pendingNewCode, setPendingNewCode, onSubmit, onCancel, humanLoading,
}: {
  pending: { action: string; code: string; role: string } | null;
  pendingReason: string;
  setPendingReason: (s: string) => void;
  pendingNote: string;
  setPendingNote: (s: string) => void;
  pendingNewCode: string;
  setPendingNewCode: (s: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  humanLoading: boolean;
}) {
  if (!pending) return null;
  const isModify = pending.action === 'modify';
  const requireReason = ['reject', 'modify', 'insufficient_evidence', 'escalate'].includes(pending.action);
  const actionLabel: Record<string, string> = {
    accept: '接受 (accept)', reject: '拒绝 (reject)', modify: '修改 (modify)',
    insufficient_evidence: '证据不足 (insufficient_evidence)', escalate: '升级 (escalate)',
  };
  return (
    <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center" data-testid="review-reason-dialog" role="dialog" aria-modal="true" aria-labelledby="review-dialog-title">
      <div className="bg-white rounded-lg border border-border shadow-lg w-full max-w-md p-4">
        <h3 id="review-dialog-title" className="text-sm font-semibold text-slate-800 mb-1">
          {actionLabel[pending.action] || pending.action}
        </h3>
        <p className="text-[11px] text-slate-500 mb-3">
          编码 <code className="bg-slate-100 px-1 rounded">{pending.code}</code> · 角色 {pending.role}
        </p>
        {isModify && (
          <div className="mb-3">
            <label className="text-[11px] text-slate-600 block mb-1" htmlFor="review-new-code">新编码 (必填)</label>
            <input id="review-new-code" data-testid="review-new-code" value={pendingNewCode}
              onChange={(e) => setPendingNewCode(e.target.value)}
              className="w-full text-xs px-2 py-1 border border-border/40 rounded font-mono" />
          </div>
        )}
        <div className="mb-3">
          <label className="text-[11px] text-slate-600 block mb-1" htmlFor="review-reason">
            复核原因 {requireReason && <span className="text-rose-600">*</span>}
          </label>
          <select id="review-reason" data-testid="review-reason" value={pendingReason}
            onChange={(e) => setPendingReason(e.target.value)}
            className="w-full text-xs px-2 py-1 border border-border/40 rounded">
            {REASON_CODES.map((r) => (
              <option key={r.code} value={r.code}>{r.label}</option>
            ))}
          </select>
        </div>
        <div className="mb-3">
          <label className="text-[11px] text-slate-600 block mb-1" htmlFor="review-note">复核备注 (可选, 不写入 EMR)</label>
          <textarea id="review-note" data-testid="review-note" value={pendingNote}
            onChange={(e) => setPendingNote(e.target.value)} rows={2}
            className="w-full text-xs px-2 py-1 border border-border/40 rounded resize-none" />
        </div>
        <div className="text-[10px] text-slate-500 bg-amber-50 border border-amber-200 rounded p-1.5 mb-3">
          ⓘ 复核记录仅用于人工留痕, <strong className="text-rose-600">不会写回 HIS/EMR</strong>。
          <code>production_writeback_blocked=true</code> 永真。
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} data-testid="review-cancel"
            className="px-3 py-1 text-xs border border-border/40 rounded hover:bg-slate-50">取消</button>
          <button onClick={onSubmit} disabled={humanLoading} data-testid="review-submit"
            className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-40">
            {humanLoading ? '提交中...' : '确认提交'}
          </button>
        </div>
      </div>
    </div>
  );
}

function RiskRouteBar({ risk }: { risk: any }) {
  const level = (risk?.level || 'unknown') as string;
  const color = {
    low: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    medium: 'bg-amber-50 text-amber-700 border-amber-200',
    high: 'bg-rose-50 text-rose-700 border-rose-200',
    critical: 'bg-purple-50 text-purple-700 border-purple-200',
    unknown: 'bg-slate-50 text-slate-500 border-slate-200',
  }[level] || 'bg-slate-50 text-slate-500 border-slate-200';
  return (
    <div className="text-xs space-y-1">
      <div className="flex items-center gap-2">
        <span className={['px-2 py-0.5 rounded border text-[10px]', color].join(' ')}>
          {level}
        </span>
        {risk?.sample_rejected && (
          <span className="text-[10px] text-rose-600">sample rejected</span>
        )}
      </div>
      {Array.isArray(risk?.reasons) && risk.reasons.length > 0 && (
        <ul className="text-[11px] text-slate-600 list-disc pl-4 space-y-0.5">
          {risk.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}
        </ul>
      )}
    </div>
  );
}

function SafetyGateBar({ gate }: { gate: any }) {
  const ruleCount = gate?.rule_count ?? 0;
  const blockCount = gate?.block_count ?? 0;
  const rules: any[] = gate?.rules || [];
  return (
    <div className="text-xs space-y-1">
      <div className="flex items-center gap-2">
        <ShieldAlert size={12} className="text-slate-500" />
        <span>rules <code>{ruleCount}</code></span>
        <span>· blocks <code className={blockCount > 0 ? 'text-rose-600' : 'text-emerald-600'}>{blockCount}</code></span>
      </div>
      {rules.length > 0 && (
        <ul className="text-[11px] text-slate-600 space-y-0.5">
          {rules.map((r, i) => (
            <li key={i} className="flex items-center gap-1">
              <code className="text-slate-700">{r.rule}</code>
              <span className={[
                'text-[10px] px-1 rounded',
                r.status === 'block' ? 'bg-rose-100 text-rose-700' :
                r.status === 'warning' ? 'bg-amber-100 text-amber-700' :
                'bg-emerald-100 text-emerald-700',
              ].join(' ')}>{r.status}</span>
              <span className="text-slate-500 truncate flex-1">{r.reason}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DRGRouteBar({ drg }: { drg: any }) {
  if (!drg) return null;
  if (drg.status === 'error') {
    return (
      <div className="text-[11px] text-rose-600 italic">
        error: {drg.reason || 'unknown'}
      </div>
    );
  }
  return (
    <div className="text-xs space-y-1">
      <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-[11px]">
        {drg.mdc && (
          <div>
            <span className="text-slate-400">MDC</span>
            <code className="ml-1 font-semibold">{drg.mdc}</code>
            {drg.mdc_name && <span className="ml-1 text-slate-500">{drg.mdc_name}</span>}
          </div>
        )}
        {drg.adrg && (
          <div>
            <span className="text-slate-400">ADRG</span>
            <code className="ml-1">{drg.adrg}</code>
          </div>
        )}
        {drg.drg && (
          <div>
            <span className="text-slate-400">DRG</span>
            <code className="ml-1 font-semibold text-blue-700">{drg.drg}</code>
          </div>
        )}
        {drg.cc_level && (
          <div>
            <span className="text-slate-400">CC</span>
            <code className="ml-1">{drg.cc_level}</code>
          </div>
        )}
        {drg.is_medical_or_surgical && (
          <div>
            <span className="text-slate-400">type</span>
            <span className="ml-1">{drg.is_medical_or_surgical}</span>
          </div>
        )}
        {drg.coverage !== undefined && (
          <div>
            <span className="text-slate-400">coverage</span>
            <span className={['ml-1', drg.coverage ? 'text-emerald-600' : 'text-amber-600'].join(' ')}>
              {drg.coverage ? 'full' : 'partial'}
            </span>
          </div>
        )}
      </div>
      {drg.drg_name && (
        <div className="text-[11px] text-slate-600 italic">{drg.drg_name}</div>
      )}
    </div>
  );
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
