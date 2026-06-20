// iCoDer M3-0 — Embed: Evidence Viewer (compact, chrome-less)
//
// 嵌入到第三方 HIS/EMR 页面用的 EvidenceViewer 包装层:
// - 默认 compact 模式 (iCoDer Apple-minimal 风格保留)
// - 自动 derive evidence spans from response (M3-0 简化)
// - 接受可选 onMarkSpan 回调
//
// 与 /components/icoder/EvidenceViewer.tsx 的区别:
// - 不假设有 app shell (Layout) 父级
// - 自带 fetch-from-API 兜底 (如果没传 response, 但给了 runId, 会主动拉)
// - styled 不可用时回落到 inline-style (医院内网有些 Tailwind 不可用)

import React, { useEffect, useMemo, useState } from 'react';
import {
  EvidenceViewer as IcodeEvidenceViewer,
  type EvidenceSpan,
} from '../icoder/EvidenceViewer';
import { icoderCodingReviewApi, type CodingReviewRunResponse } from '../../services/icoderCodingReviewApi';

export interface IcoderEvidenceViewerProps {
  /** 显式传入 run 响应 (preferred) */
  response?: CodingReviewRunResponse;
  /** 或者给定 runId, 主动 fetch */
  runId?: string;
  /** 原文 (按 field 索引). 不传则从 response.input.encounter_text 推导 */
  sourceText?: Record<string, string>;
  /** 自定义 fetch 函数 (嵌入场景下, 第三方后端可能不同) */
  fetcher?: (runId: string) => Promise<CodingReviewRunResponse>;
  /** 人工标记回调 (透传) */
  onMarkSpan?: (spanId: string, mark: string) => void;
  /** 审核人 ID */
  reviewer?: string;
  /** 容器 className (用于接入第三方样式系统) */
  className?: string;
}

export const IcoderEvidenceViewer: React.FC<IcoderEvidenceViewerProps> = ({
  response: propResponse,
  runId,
  sourceText: propSourceText,
  fetcher,
  onMarkSpan,
  reviewer,
  className,
}) => {
  const [fetched, setFetched] = useState<CodingReviewRunResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    if (propResponse || !runId) return;
    setLoading(true);
    setErr('');
    const fn = fetcher || ((rid: string) => icoderCodingReviewApi.getRun(rid));
    fn(runId)
      .then((r) => setFetched(r))
      .catch((e) => setErr(String(e?.message || e)))
      .finally(() => setLoading(false));
  }, [runId, propResponse, fetcher]);

  const response = propResponse || fetched;

  const sourceText = useMemo<Record<string, string>>(() => {
    if (propSourceText) return propSourceText;
    if (!response) return {};
    // M3-0: 原文只放在 present_illness
    const enc = (response as any)?.input?.encounter_text || '';
    return { present_illness: enc };
  }, [propSourceText, response]);

  const spans: EvidenceSpan[] = useMemo(() => {
    if (!response) return [];
    const out: EvidenceSpan[] = [];
    const enc = sourceText.present_illness || '';
    const targets = [
      response.primary_diagnosis,
      ...(response.secondary_diagnoses || []),
      ...(response.procedures || []),
    ].filter((c) => c && c.code);
    for (const c of targets) {
      const desc = c!.description || c!.code;
      const head = desc.slice(0, 6);
      const idx = enc.indexOf(head);
      const text = idx >= 0 ? enc.slice(idx, idx + Math.min(head.length + 6, 18)) : desc;
      out.push({
        id: `emb-${c!.code}-${Math.random().toString(36).slice(2, 8)}`,
        field: 'present_illness',
        text,
        match_method: 'auto_bootstrap',
        confidence: c!.confidence,
        kind: 'auto_bootstrap',
        target_code: c!.code,
      });
    }
    return out;
  }, [response, sourceText]);

  if (loading) {
    return (
      <div className={['p-3 text-xs text-slate-400', className].filter(Boolean).join(' ')}>
        加载证据中...
      </div>
    );
  }
  if (err) {
    return (
      <div className={['p-3 text-xs text-rose-600 border border-rose-200 rounded bg-rose-50', className].filter(Boolean).join(' ')}>
        加载失败: {err}
      </div>
    );
  }
  if (!response) {
    return (
      <div className={['p-3 text-xs text-slate-400 italic', className].filter(Boolean).join(' ')}>
        (无证据 — 请先运行 Agent 或传入 response)
      </div>
    );
  }

  return (
    <div className={['rounded-lg border border-slate-200 bg-white p-3', className].filter(Boolean).join(' ')}>
      <div className="text-xs font-medium text-slate-700 mb-2 flex items-center justify-between">
        <span>证据回链 (iCoDer Embed)</span>
        <span className="text-[10px] text-slate-400">
          run_id <code className="text-[10px]">{response.run_id.slice(0, 12)}…</code>
        </span>
      </div>
      <IcodeEvidenceViewer
        sourceText={sourceText}
        spans={spans}
        onMarkSpan={onMarkSpan as any}
        reviewer={reviewer}
        compact
      />
    </div>
  );
};

export default IcoderEvidenceViewer;
