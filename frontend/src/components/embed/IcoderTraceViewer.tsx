// iCoDer M3-0 — Embed: Trace Viewer (compact, chrome-less)
//
// 嵌入到第三方页面用的 RunTraceTimeline 包装层:
// - 自动 fetch (给定 runId 时)
// - 风格紧凑, 自带边框 + 卡片背景
// - 不依赖 app shell
//
// 与 /components/icoder/RunTraceTimeline.tsx 的区别:
// - 自动 fetch + loading/error 状态
// - 自带 "回到审核 / 报告下载" 链接 (embed 上下文)

import React, { useEffect, useState } from 'react';
import { RunTraceTimeline } from '../icoder/RunTraceTimeline';
import { icoderCodingReviewApi, type CodingReviewRunResponse } from '../../services/icoderCodingReviewApi';

export interface IcoderTraceViewerProps {
  /** 显式传入 run 响应 (preferred) */
  response?: CodingReviewRunResponse;
  /** 或者给定 runId, 主动 fetch */
  runId?: string;
  /** 自定义 fetch 函数 */
  fetcher?: (runId: string) => Promise<CodingReviewRunResponse>;
  /** 是否显示顶部 header (默认 true) */
  showHeader?: boolean;
  /** 容器 className */
  className?: string;
}

export const IcoderTraceViewer: React.FC<IcoderTraceViewerProps> = ({
  response: propResponse,
  runId,
  fetcher,
  showHeader = true,
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

  if (loading) {
    return (
      <div className={['p-3 text-xs text-slate-400', className].filter(Boolean).join(' ')}>
        加载运行追踪中...
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
        (无运行追踪 — 请先运行 Agent 或传入 response)
      </div>
    );
  }

  return (
    <div className={['rounded-lg border border-slate-200 bg-white p-3', className].filter(Boolean).join(' ')}>
      {showHeader && (
        <div className="text-xs font-medium text-slate-700 mb-2 flex items-center justify-between">
          <span>运行追踪 (iCoDer Embed)</span>
          <a
            href={response.trace_url}
            target="_blank"
            rel="noreferrer"
            className="text-[10px] text-blue-600 hover:underline"
          >
            打开 M2a Trace ↗
          </a>
        </div>
      )}
      <RunTraceTimeline response={response} compact />
    </div>
  );
};

export default IcoderTraceViewer;
