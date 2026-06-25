// iCoDer M3-0 — RunTraceTimeline
//
// Vertical timeline of the 5 MedCodER pipeline stages observed during
// a coding-review run. The agent_ref + pipeline_stages_observed fields
// of the CodingReviewRunResponse drive this view. The 14-stage
// homepage-coding-review ordering is NOT rendered (deprecated).

import React, { useMemo } from 'react';
import type { LucideIcon } from 'lucide-react';
import {
  Search, ListChecks, GitMerge, ArrowUpDown, ShieldCheck, Circle, CircleCheck,
} from 'lucide-react';
import type { CodingReviewRunResponse } from '../../services/icoderCodingReviewApi';

export interface RunTraceTimelineProps {
  response: CodingReviewRunResponse;
  compact?: boolean;
  className?: string;
}

const STAGE_META: Record<string, { label: string; description: string; icon: LucideIcon }> = {
  extraction: {
    label: 'Stage 1 · 抽取',
    description: 'DeepSeek chat 抽取 {disease, evidence, llm_initial_code}',
    icon: Search,
  },
  retrieval: {
    label: 'Stage 2 · 检索',
    description: 'BGE-M3 + FAISS top-20, 通过 icd10cn_code_catalog 兜底',
    icon: ListChecks,
  },
  merge: {
    label: 'Stage 3 · 合并',
    description: '(LLM codes) ∪ (Retrieved top-20) → cap 30 + differentiation KB hints',
    icon: GitMerge,
  },
  rerank: {
    label: 'Stage 4 · Re-rank',
    description: 'DeepSeek RankGPT-style, per-disease final_confidence',
    icon: ArrowUpDown,
  },
  calibration: {
    label: 'Stage 5 · 合规 + 校准',
    description: 'MedCodERRetrievalRuleSet + per-diagnosis calibration',
    icon: ShieldCheck,
  },
};

export const RunTraceTimeline: React.FC<RunTraceTimelineProps> = ({
  response,
  compact = false,
  className,
}) => {
  const stages = useMemo(() => {
    const observed = new Set(response.pipeline_stages_observed || []);
    // Always render all 5 stages in canonical order; mark observed ones green.
    return Object.keys(STAGE_META).map((id) => ({
      id,
      ...STAGE_META[id],
      observed: observed.has(id),
    }));
  }, [response.pipeline_stages_observed]);

  if (compact) {
    return (
      <div className={['flex flex-col gap-1', className].filter(Boolean).join(' ')}>
        {stages.map((s) => {
          const Icon = s.observed ? CircleCheck : Circle;
          return (
            <div
              key={s.id}
              className="flex items-center gap-1.5 text-[11px]"
            >
              <Icon
                size={11}
                className={s.observed ? 'text-emerald-600' : 'text-slate-300'}
              />
              <span className={s.observed ? 'text-slate-700' : 'text-slate-400'}>
                {s.label}
              </span>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className={['rounded-lg border border-slate-200 bg-white p-3', className].filter(Boolean).join(' ')}>
      <div className="text-xs font-medium text-slate-700 mb-2 flex items-center justify-between">
        <span>MedCodER 5 阶段运行追踪</span>
        <span className="text-[10px] text-slate-400">
          run_id <code className="text-[10px]">{response.run_id.slice(0, 12)}…</code>
        </span>
      </div>

      <ol className="space-y-1.5">
        {stages.map((s) => {
          const Icon = s.icon;
          return (
            <li
              key={s.id}
              className={[
                'flex items-start gap-2 rounded-md border px-2 py-1.5',
                s.observed
                  ? 'border-emerald-200 bg-emerald-50/40'
                  : 'border-slate-200 bg-slate-50/30',
              ].join(' ')}
            >
              <div
                className={[
                  'shrink-0 w-5 h-5 rounded-full flex items-center justify-center',
                  s.observed ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-400',
                ].join(' ')}
              >
                <Icon size={11} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[12px] font-medium text-slate-800">{s.label}</div>
                <div className="text-[10px] text-slate-500 leading-snug">{s.description}</div>
              </div>
              {s.observed ? (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 border border-emerald-200">
                  已观察
                </span>
              ) : (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200">
                  未触发
                </span>
              )}
            </li>
          );
        })}
      </ol>

      <div className="mt-2 pt-2 border-t border-slate-100 text-[10px] text-slate-400 flex items-center justify-between">
        <span>agent_ref: <code>{response.agent_ref}</code></span>
        <span>
          started {response.started_at?.slice(11, 19)} · finished {response.finished_at?.slice(11, 19)}
        </span>
      </div>
    </div>
  );
};

export default RunTraceTimeline;
