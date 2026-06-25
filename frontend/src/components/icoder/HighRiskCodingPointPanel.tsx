// iCoDer M3-0 — HighRiskCodingPointPanel
//
// Read-only panel for displaying the 62 high-risk coding points hit
// by a MedCodER run. These are ICD codes that have a history of
// over-coding / under-coding and require mandatory human confirmation
// before production write-back.
//
// Wired to the CodingReviewRunResponse.high_risk_coding_points list
// returned by POST /api/icoder/coding-review/run.

import React from 'react';
import { AlertTriangle } from 'lucide-react';
import type { HighRiskCodingPoint, CodingReviewRunResponse } from '../../services/icoderCodingReviewApi';

export interface HighRiskCodingPointPanelProps {
  /** Either pass the full response (preferred) or a bare list. */
  response?: CodingReviewRunResponse;
  points?: HighRiskCodingPoint[];
  compact?: boolean;
  className?: string;
}

export const HighRiskCodingPointPanel: React.FC<HighRiskCodingPointPanelProps> = ({
  response,
  points: propPoints,
  compact = false,
  className,
}) => {
  const points = propPoints || response?.high_risk_coding_points || [];

  if (points.length === 0) {
    if (compact) return null;
    return (
      <div className={['text-[11px] text-slate-400 italic', className].filter(Boolean).join(' ')}>
        未命中 62 高风险易错编码点
      </div>
    );
  }

  return (
    <div className={['rounded-lg border border-rose-200 bg-rose-50/40 p-2', className].filter(Boolean).join(' ')}>
      <div className="flex items-center gap-1 text-[11px] font-medium text-rose-700 mb-1.5">
        <AlertTriangle size={12} />
        <span>高风险易错编码点 ({points.length})</span>
        <span className="text-[10px] text-rose-500 font-normal">— 须人工确认 (M2b-2 §6 硬性)</span>
      </div>
      <ul className="space-y-1">
        {points.map((p) => (
          <li
            key={p.code}
            className="rounded border border-rose-200 bg-white px-2 py-1 text-[11px] flex items-start gap-2"
          >
            <code className="font-mono text-rose-800 bg-rose-50 px-1 py-0.5 rounded border border-rose-200 shrink-0">
              {p.code}
            </code>
            <div className="flex-1 min-w-0">
              <div className="text-slate-700 leading-snug">{p.reason}</div>
              <div className="flex items-center gap-2 mt-0.5 text-[10px]">
                {p.is_priority && (
                  <span className="px-1 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200">
                    ★ 5 重点码
                  </span>
                )}
                <span className="text-slate-500">
                  状态: <code>{p.current_status}</code>
                </span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default HighRiskCodingPointPanel;
