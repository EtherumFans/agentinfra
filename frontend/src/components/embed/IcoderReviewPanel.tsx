// iCoDer M3-0 — Embed: Review Panel (chrome-less card grid)
//
// 嵌入到第三方 HIS/EMR 系统的主组件:
// - 列出 primary / secondary dx + procedures
// - 接受 accept/reject/modify 回调 (不直接调 API, 由宿主决定)
// - 展示高风险易错编码点 (只读, 不嵌入 confirm 按钮)
// - 自带 fetch (给定 runId 时)
//
// 配套使用: <IcoderEvidenceViewer />, <IcoderTraceViewer />
//
// 设计原则:
// - 不假设父级 Layout, 自带白底圆角卡片
// - 字体/Tailwind className 可由 className 覆盖
// - 不引入 iCoDer 全局 store (useToast, useAuth 等都不依赖)

import React, { useEffect, useMemo, useState } from 'react';
import {
  Check, X, Send, AlertTriangle, Loader2, RefreshCw,
} from 'lucide-react';
import {
  icoderCodingReviewApi,
  type CodingReviewRunResponse,
  type DiagnosisCard as DxCard,
} from '../../services/icoderCodingReviewApi';
import { HighRiskCodingPointPanel } from '../icoder/HighRiskCodingPointPanel';

export type EmbedAction = 'accept' | 'reject' | 'modify' | 'insufficient_evidence' | 'escalate';

export interface IcoderReviewPanelProps {
  /** 显式传入 run 响应 (preferred) */
  response?: CodingReviewRunResponse;
  /** 或者给定 runId, 主动 fetch */
  runId?: string;
  /** 自定义 fetch 函数 (嵌入场景下, 第三方后端可能不同) */
  fetcher?: (runId: string) => Promise<CodingReviewRunResponse>;
  /** 点击"接受" / "驳回" / "修改" 时触发 (由宿主决定如何写回) */
  onAction?: (action: EmbedAction, code: string, role: string, newCode?: string) => void;
  /** 是否显示"修改"按钮 (某些嵌入场景下不允许) */
  allowModify?: boolean;
  /** 是否显示高风险易错编码点 (默认 true) */
  showHighRiskPanel?: boolean;
  /** 容器 className */
  className?: string;
  /** 标题 (默认 "iCoDer 编码审核") */
  title?: string;
  /** 是否展示"刷新"按钮 (默认 true) */
  showRefresh?: boolean;
  /** 刷新回调 (在父组件控制下重新 fetch) */
  onRefresh?: () => void;
}

const ROLE_BY_INDEX: Array<'primary_disease' | 'other_disease' | 'primary_surgery'> = [
  'primary_disease',
  'other_disease',
  'primary_surgery',
];

const ROLE_LABEL: Record<string, string> = {
  primary_disease: '主诊断',
  other_disease: '其他诊断',
  primary_surgery: '主手术',
};

export const IcoderReviewPanel: React.FC<IcoderReviewPanelProps> = ({
  response: propResponse,
  runId,
  fetcher,
  onAction,
  allowModify = true,
  showHighRiskPanel = true,
  className,
  title = 'iCoDer 编码审核',
  showRefresh = true,
  onRefresh,
}) => {
  const [fetched, setFetched] = useState<CodingReviewRunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string>('');

  const refetch = () => {
    if (!runId) return;
    setLoading(true);
    setErr('');
    const fn = fetcher || ((rid: string) => icoderCodingReviewApi.getRun(rid));
    fn(runId)
      .then((r) => setFetched(r))
      .catch((e) => setErr(String(e?.message || e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (propResponse || !runId) return;
    refetch();
  }, [runId, propResponse]);

  const response = propResponse || fetched;

  const groups = useMemo(() => {
    if (!response) return [] as { role: string; label: string; items: DxCard[] }[];
    return [
      { role: 'primary_disease', label: '主诊断', items: response.primary_diagnosis ? [response.primary_diagnosis] : [] },
      { role: 'other_disease', label: '其他诊断', items: response.secondary_diagnoses || [] },
      { role: 'primary_surgery', label: '手术操作', items: response.procedures || [] },
    ];
  }, [response]);

  if (loading) {
    return (
      <div className={['p-4 text-xs text-slate-400 flex items-center gap-2', className].filter(Boolean).join(' ')}>
        <Loader2 size={12} className="animate-spin" /> 加载审核结果中...
      </div>
    );
  }
  if (err) {
    return (
      <div className={['p-3 text-xs text-rose-600 border border-rose-200 rounded bg-rose-50', className].filter(Boolean).join(' ')}>
        加载失败: {err}
        {showRefresh && (
          <button onClick={refetch} className="ml-2 underline">重试</button>
        )}
      </div>
    );
  }
  if (!response) {
    return (
      <div className={['p-3 text-xs text-slate-400 italic', className].filter(Boolean).join(' ')}>
        (无审核结果)
      </div>
    );
  }

  return (
    <div className={['rounded-lg border border-slate-200 bg-white p-3 flex flex-col gap-3', className].filter(Boolean).join(' ')}>
      {/* Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-800">{title}</span>
          {response.status === 'ok' && <span className="text-[10px] px-1.5 py-0.5 rounded border bg-emerald-50 text-emerald-700 border-emerald-200">完成</span>}
          {response.status === 'unavailable' && <span className="text-[10px] px-1.5 py-0.5 rounded border bg-rose-50 text-rose-700 border-rose-200">不可用</span>}
          {response.degraded && <span className="text-[10px] px-1.5 py-0.5 rounded border bg-amber-50 text-amber-700 border-amber-200">degraded</span>}
          {response.manual_review_required && (
            <span className="text-[10px] text-rose-600 flex items-center gap-0.5">
              <AlertTriangle size={10} /> 需人工复核
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-400">
          <span>run_id <code>{response.run_id.slice(0, 12)}…</code></span>
          {showRefresh && (
            <button
              onClick={onRefresh || refetch}
              className="px-1.5 py-0.5 rounded border border-slate-200 hover:bg-slate-50"
              title="刷新"
            >
              <RefreshCw size={10} />
            </button>
          )}
        </div>
      </div>

      {/* Disclaimer (embed 场景尤其重要) */}
      {response.prediction_mode === 'link_validation' && (
        <div className="text-[10px] text-rose-700 bg-rose-50/50 border border-rose-200 rounded px-2 py-1.5 leading-relaxed">
          <strong>Pipeline Validation</strong> 模式 — 代表 iCoDer Runtime 全链路验证结果, 不代表模型效果, 不可用于生产写回 (production_writeback_blocked=true)。
        </div>
      )}

      {/* Code groups */}
      {groups.map((g) => g.items.length > 0 && (
        <div key={g.role}>
          <div className="text-[11px] text-slate-500 mb-1">{g.label} <span className="text-slate-400">({g.items.length})</span></div>
          <div className="flex flex-col gap-1.5">
            {g.items.map((c) => (
              <div key={c.code} className="rounded-md border border-slate-200 bg-slate-50/50 p-2">
                <div className="flex items-center gap-2 mb-1">
                  <code className="text-xs font-semibold text-slate-900 bg-white px-1.5 py-0.5 rounded border border-slate-200">{c.code}</code>
                  <span className="text-xs text-slate-700 flex-1 truncate">{c.description}</span>
                  {typeof c.confidence === 'number' && (
                    <span className="text-[10px] text-slate-500 font-mono">{(c.confidence * 100).toFixed(0)}%</span>
                  )}
                  {c.human_review_required && <span className="text-[10px] text-rose-600">需人工</span>}
                </div>
                {onAction && (
                  <div className="flex gap-1">
                    <button
                      onClick={() => onAction('accept', c.code, g.role)}
                      className="px-2 py-0.5 rounded text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 flex items-center gap-0.5"
                    >
                      <Check size={10} /> 接受
                    </button>
                    <button
                      onClick={() => onAction('reject', c.code, g.role)}
                      className="px-2 py-0.5 rounded text-[10px] bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 flex items-center gap-0.5"
                    >
                      <X size={10} /> 驳回
                    </button>
                    {allowModify && (
                      <button
                        onClick={() => {
                          const newCode = prompt('修改为 (ICD 码):', c.code);
                          if (newCode) onAction('modify', c.code, g.role, newCode);
                        }}
                        className="px-2 py-0.5 rounded text-[10px] bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 flex items-center gap-0.5"
                      >
                        <Send size={10} /> 修改
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* 高风险易错编码点 (只读) */}
      {showHighRiskPanel && response.high_risk_coding_points?.length > 0 && (
        <div>
          <HighRiskCodingPointPanel response={response} compact />
        </div>
      )}
    </div>
  );
};

export default IcoderReviewPanel;
