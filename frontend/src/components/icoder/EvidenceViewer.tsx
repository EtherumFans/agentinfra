// iCoDer M3-0 — EvidenceViewer (in-app, full chrome)
//
// Renders the per-diagnosis evidence chain returned by MedCodER Stage 1
// + Stage 5. Wraps the shared <EvidenceHighlighter /> from
// components/medical-coding/ to keep rendering consistent across the
// workbench and embed contexts.
//
// Key differences from <IcoderEvidenceViewer /> (embed variant):
//   - assumes app shell (Layout) is present
//   - does NOT auto-fetch (parent owns the run lifecycle)
//   - shows side panel listing (code, char range, doc_type) per span

import React from 'react';
import { EvidenceHighlighter } from '../medical-coding/EvidenceHighlighter';
import type { EvidenceSpan } from '../../types/runtime';
import type { EvidenceChainEntry } from '../../services/icoderCodingReviewApi';

// Re-export so embed callers can `import { EvidenceSpan } from '../icoder/EvidenceViewer'`.
export type { EvidenceSpan };

// Phase A A2 (2026-06-25): canonical evidence-kind enum (per
// M3_HOMEPAGE_CODING_REVIEW_AGENT_SPEC §6). M3-0 only auto-produces
// `auto_bootstrap`; `gold` is only created after a human reviewer marks
// a span as confirmed, and `rejected` after a reviewer marks a span as
// rejected. Frontend renders these distinctly.
export const EvidenceKind = {
  AutoBootstrap: 'auto_bootstrap',
  Gold: 'gold',
  Rejected: 'rejected',
} as const;
export type EvidenceKindValue = (typeof EvidenceKind)[keyof typeof EvidenceKind];

export interface EvidenceViewerProps {
  sourceText: Record<string, string>;
  /** Either the runtime-shaped spans (MedCodER) or the API response shape. */
  spans?: Array<EvidenceSpan | EvidenceChainEntry>;
  onMarkSpan?: (spanId: string, mark: string) => void;
  reviewer?: string;
  /** Compact embed mode (no side panel, no header). */
  compact?: boolean;
  className?: string;
}

const KIND_LABELS: Record<string, string> = {
  exact: '精确',
  fuzzy: '模糊',
  rapidfuzz: '模糊 (≥0.85)',
  auto_bootstrap: '自动派生',
};

export const EvidenceViewer: React.FC<EvidenceViewerProps> = ({
  sourceText,
  spans = [],
  onMarkSpan,
  reviewer,
  compact = false,
  className,
}) => {
  // Pick the first available field (most EMRs put text in present_illness)
  const fieldName = Object.keys(sourceText).find((k) => (sourceText[k] || '').length > 0) || 'present_illness';
  const text = sourceText[fieldName] || '';

  // Normalize to the EvidenceHighlighter shape
  const normSpans: EvidenceSpan[] = spans
    .filter((s) => typeof s.char_start === 'number' && typeof s.char_end === 'number' && s.char_end > s.char_start)
    .map((s) => ({
      text: s.text,
      char_start: s.char_start,
      char_end: s.char_end,
      doc_id: s.doc_id,
      doc_type: s.doc_type,
      confidence: s.confidence,
    }));

  if (compact) {
    return (
      <div className={className}>
        <EvidenceHighlighter sourceText={text} spans={normSpans} />
      </div>
    );
  }

  return (
    <div className={['rounded-lg border border-slate-200 bg-white p-3', className].filter(Boolean).join(' ')}>
      <div className="text-xs font-medium text-slate-700 mb-2 flex items-center justify-between">
        <span>证据回链 (M3-0 MedCodER)</span>
        {reviewer && (
          <span className="text-[10px] text-slate-400">
            审核人: <code className="text-[10px]">{reviewer}</code>
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Left: highlighted text */}
        <div className="md:col-span-2 max-h-80 overflow-y-auto rounded border border-slate-100 bg-slate-50/50 p-2 text-[12px] leading-relaxed text-slate-700">
          {text ? (
            <EvidenceHighlighter sourceText={text} spans={normSpans} />
          ) : (
            <span className="text-slate-400 italic">（无原文 — 请先运行 Agent）</span>
          )}
        </div>

        {/* Right: span list */}
        <div className="md:col-span-1 flex flex-col gap-1.5 max-h-80 overflow-y-auto">
          {normSpans.length === 0 && (
            <div className="text-[11px] text-slate-400 italic px-1">无证据链</div>
          )}
          {normSpans.map((s, i) => {
            const raw = spans[i] as EvidenceChainEntry | undefined;
            return (
              <div
                key={i}
                className="rounded border border-slate-200 bg-white px-2 py-1.5 text-[11px]"
              >
                <div className="flex items-center justify-between gap-1 mb-0.5">
                  <span className="font-mono text-slate-700 truncate" title={s.text}>
                    {s.text.slice(0, 24)}{s.text.length > 24 ? '…' : ''}
                  </span>
                  <span className="text-slate-400 text-[10px]">
                    [{s.char_start}–{s.char_end}]
                  </span>
                </div>
                <div className="flex items-center justify-between gap-1 text-[10px] text-slate-500">
                  <span>{(s.confidence * 100).toFixed(0)}%</span>
                  {raw?.match_method && (
                    <span className="text-slate-400">{KIND_LABELS[raw.match_method] || raw.match_method}</span>
                  )}
                </div>
                {raw?.supports_code && (
                  <div className="text-[10px] text-blue-700 mt-0.5">
                    → <code className="font-mono">{raw.supports_code}</code>
                  </div>
                )}
                {onMarkSpan && (
                  <div className="flex gap-1 mt-1">
                    <button
                      onClick={() => onMarkSpan(`span-${i}`, 'confirmed')}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100"
                    >
                      确认
                    </button>
                    <button
                      onClick={() => onMarkSpan(`span-${i}`, 'rejected')}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100"
                    >
                      驳回
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default EvidenceViewer;
