// Phase B — MethodTraceViewer
//
// Renders a per-method horizontal stage trace (MethodStageTraceEntry[])
// and a side-by-side comparison view across multiple methods. Drives
// the new Method Compare workbench (/method-compare).
//
// Backed by /api/icoder/coding-review/{compare, run-v2}.

import React, { useMemo } from 'react';
import {
  CheckCircle2, XCircle, MinusCircle, Loader2, Clock, Database, Cpu, ShieldCheck,
} from 'lucide-react';
import type {
  CompareResultEntry,
  MethodResult,
  MethodStageTraceEntry,
} from '../../types/runtime';

export interface MethodTraceViewerProps {
  result: MethodResult;
  className?: string;
}

const STATUS_ICON: Record<string, React.ElementType> = {
  ok: CheckCircle2,
  skipped: MinusCircle,
  failed: XCircle,
  noop: MinusCircle,
  unavailable: MinusCircle,
  error: XCircle,
};

const STATUS_COLOR: Record<string, string> = {
  ok: 'text-emerald-600 bg-emerald-50 border-emerald-200',
  skipped: 'text-slate-500 bg-slate-50 border-slate-200',
  failed: 'text-rose-600 bg-rose-50 border-rose-200',
  noop: 'text-slate-500 bg-slate-50 border-slate-200',
  unavailable: 'text-amber-700 bg-amber-50 border-amber-200',
  error: 'text-rose-700 bg-rose-50 border-rose-300',
};

const FAMILY_BADGE: Record<string, string> = {
  medcoder: 'bg-indigo-100 text-indigo-700',
  legacy: 'bg-slate-100 text-slate-700',
  noop: 'bg-amber-100 text-amber-700',
};

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function StatusDot({ status }: { status: string }) {
  const Icon = STATUS_ICON[status] ?? MinusCircle;
  const cls = STATUS_COLOR[status] ?? 'text-slate-500 bg-slate-50';
  return (
    <span
      className={`inline-flex h-5 w-5 items-center justify-center rounded-full border ${cls}`}
      title={status}
    >
      <Icon className="h-3 w-3" />
    </span>
  );
}

function StageBar({ stages }: { stages: MethodStageTraceEntry[] }) {
  if (!stages || stages.length === 0) {
    return (
      <div className="text-xs text-slate-400 italic py-1">
        no stage trace (method did not run)
      </div>
    );
  }
  const max = Math.max(1, ...stages.map((s) => s.latency_ms));
  return (
    <div className="space-y-1">
      {stages.map((stage, i) => (
        <div key={`${stage.stage_name}-${i}`} className="flex items-center gap-2 text-xs">
          <div className="w-32 truncate font-mono text-slate-600">
            {stage.stage_name}
          </div>
          <div className="flex-1 bg-slate-100 rounded h-3 overflow-hidden">
            <div
              className={
                stage.status === 'failed' || stage.status === 'error'
                  ? 'h-full bg-rose-400'
                  : stage.status === 'skipped' || stage.status === 'noop'
                    ? 'h-full bg-slate-300'
                    : 'h-full bg-emerald-400'
              }
              style={{ width: `${(stage.latency_ms / max) * 100}%` }}
            />
          </div>
          <div className="w-20 text-right font-mono text-slate-700">
            {formatMs(stage.latency_ms)}
          </div>
          <div className="w-8 text-right text-slate-500">
            {stage.output_size > 0 ? `×${stage.output_size}` : ''}
          </div>
        </div>
      ))}
    </div>
  );
}

function PrimaryCodeSummary({ entry }: { entry: CompareResultEntry | MethodResult }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-mono text-lg font-semibold text-slate-900">
        {entry.primary_code || '—'}
      </span>
      <span className="text-sm text-slate-600 truncate">
        {entry.primary_name || ''}
      </span>
      {entry.primary_confidence > 0 && (
        <span className="text-xs text-slate-500">
          {(entry.primary_confidence * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
}

export function MethodTraceViewer({ result, className = '' }: MethodTraceViewerProps) {
  const totalLatency = useMemo(
    () => (result.stage_trace || []).reduce((acc, s) => acc + s.latency_ms, 0),
    [result.stage_trace],
  );
  const family = result.method_family || 'unknown';
  return (
    <div
      className={`rounded-lg border border-slate-200 bg-white p-4 shadow-sm ${className}`}
    >
      <header className="mb-3 flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-900">
              {result.method_name || result.method_id}
            </h3>
            <span className={`rounded px-1.5 py-0.5 text-xs ${FAMILY_BADGE[family] ?? 'bg-slate-100 text-slate-600'}`}>
              {family}
            </span>
            <span className="font-mono text-xs text-slate-500">{result.method_id}</span>
          </div>
          <div className="mt-1">
            <PrimaryCodeSummary entry={result} />
          </div>
        </div>
        <div className="text-right text-xs text-slate-500">
          <div className="flex items-center justify-end gap-1">
            <Clock className="h-3 w-3" />
            {formatMs(result.processing_time_ms || totalLatency)}
          </div>
          <div className="mt-0.5">
            <StatusDot status={result.status} />
            <span className="ml-1">{result.status}</span>
          </div>
        </div>
      </header>

      {result.reason && (
        <div className="mb-3 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
          {result.reason}
        </div>
      )}

      <div className="border-t border-slate-100 pt-3">
        <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
          <span className="font-medium">Stage Trace ({result.stage_trace?.length ?? 0})</span>
          <span>total {formatMs(totalLatency)}</span>
        </div>
        <StageBar stages={result.stage_trace || []} />
      </div>

      {result.issues && result.issues.length > 0 && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <div className="mb-1 flex items-center gap-1 text-xs font-medium text-rose-700">
            <ShieldCheck className="h-3 w-3" />
            Issues ({result.issues.length})
          </div>
          <ul className="space-y-1 text-xs">
            {result.issues.slice(0, 3).map((issue, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="font-mono text-rose-600">{issue.code || '—'}</span>
                <span className="text-slate-700">{issue.message}</span>
              </li>
            ))}
            {result.issues.length > 3 && (
              <li className="text-slate-400 italic">+ {result.issues.length - 3} more…</li>
            )}
          </ul>
        </div>
      )}

      {result.secondary_codes && result.secondary_codes.length > 0 && (
        <div className="mt-3 border-t border-slate-100 pt-3">
          <div className="mb-1 text-xs font-medium text-slate-600">
            Secondary ({result.secondary_codes.length})
          </div>
          <div className="flex flex-wrap gap-1">
            {result.secondary_codes.slice(0, 5).map((c, i) => (
              <span
                key={i}
                className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-mono text-slate-700"
                title={c.name}
              >
                {c.code}
              </span>
            ))}
            {result.secondary_codes.length > 5 && (
              <span className="text-xs text-slate-400">+ {result.secondary_codes.length - 5}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export interface MethodComparisonGridProps {
  results: CompareResultEntry[];
  consensusCode?: string;
  className?: string;
}

export function MethodComparisonGrid({
  results,
  consensusCode,
  className = '',
}: MethodComparisonGridProps) {
  return (
    <div className={`grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 ${className}`}>
      {results.map((r) => {
        const isConsensus = consensusCode && r.primary_code === consensusCode;
        return (
          <div key={r.method_id} className={isConsensus ? 'ring-2 ring-emerald-400 rounded-lg' : ''}>
            <MethodTraceViewer result={r} />
            {isConsensus && (
              <div className="mt-1 text-center text-xs font-medium text-emerald-700">
                ✓ consensus
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default MethodTraceViewer;