// Phase 3-D1 Task 4 - RunTrace Viewer.
// Phase 3-D2 Task 2 - empty-timeline guard + retry button.
// Phase 3-E Task 6 - enhanced dispatcher detail display.
//
// Route: /runs/:runId/trace
//
// Renders the 9-step timeline for a single run:
//   1. user_message_received
//   2. planner_selected_experts
//   3. tools_list          ┐
//   4. auth_resolved       │
//   5. scope_checked       ├─ Dispatcher (统一工具调度器)
//   6. tools_call          │
//   7. expert_response     ┘ (expert_response is emitted by InboundHandler
//   8. output_generated       for the orchestrator path, NOT by dispatcher)
//   9. completion
//
// Backend contract: app/api/run_trace.py GET /api/runtime/runs/{run_id}/trace
// Store contract: app/icoder/agent_runtime/orchestrator/run_trace.RunTraceStore
//
// Phase 3-E Task 6 enhancement: the 4 dispatcher steps (tools_list /
// auth_resolved / scope_checked / tools_call) are grouped under a
// "Dispatcher" visual header. Each step shows structured metadata
// (tool_name / handler_ref / scope diff / auth_type / arguments summary /
// result summary) instead of raw JSON. The agent→dispatcher→tool chain
// is now visually explicit.
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Loader2, AlertCircle, CheckCircle2, XCircle,
  ChevronDown, ChevronRight, Activity, Wrench, Shield, Key, Search, Cpu,
} from 'lucide-react';

import { runtimeAgentApi } from '../services/runtimeApi';
import { useToastStore } from '../store';
import type {
  RunTraceResponse, RunTraceEvent, RunTraceStatus,
} from '../types/runtime';
import { useT } from '../i18n';

const STEP_ORDER: string[] = [
  'user_message_received',
  'planner_selected_experts',
  'tools_list',
  'auth_resolved',
  'scope_checked',
  'tools_call',
  'expert_response',
  'output_generated',
  'completion',
];

const DISPATCHER_STEPS = new Set([
  'tools_list', 'auth_resolved', 'scope_checked', 'tools_call',
]);

function StatusIcon({ status }: { status?: RunTraceStatus }) {
  if (status === 'ok') return <CheckCircle2 size={14} className="text-green-600" />;
  if (status === 'failed') return <XCircle size={14} className="text-red-600" />;
  return <div className="w-3 h-3 rounded-full bg-muted-foreground/40" />;
}

function statusBadgeClass(status?: RunTraceStatus): string {
  if (status === 'ok') return 'bg-green-100 text-green-700';
  if (status === 'failed') return 'bg-red-100 text-red-700';
  if (status === 'skipped') return 'bg-amber-100 text-amber-700';
  return 'bg-muted text-muted-foreground';
}

function getStepIcon(step: string) {
  switch (step) {
    case 'tools_list': return Search;
    case 'auth_resolved': return Key;
    case 'scope_checked': return Shield;
    case 'tools_call': return Wrench;
    case 'completion': return CheckCircle2;
    default: return Activity;
  }
}

// ── Dispatcher detail renderers ──────────────────────────────────

// Phase 3-D2.5 Part A2 - Tool Dispatch Detail expandable.
// Renders the 15-field dispatch_detail dict emitted under
// TOOLS_CALL.safe_metadata.dispatch_detail. Default collapsed; failed
// dispatch auto-expands so the failure stage is visible immediately.
// Defense-in-depth: never render keys named token/secret/authorization/
// client_secret/secret_ref/password even if they appear (the backend
// already redacts, but this prevents any future emit-site mistake from
// leaking via the UI).
const SECRET_KEY_RE = /^(token|secret|authorization|client_secret|secret_ref|password|bearer_token|access_token|refresh_token|api_key)$/i;

interface DispatchDetail {
  tool_name?: string;
  dispatch_mode?: string;
  round_index?: number | null;
  caller?: string | null;
  handler_ref?: string;
  input_schema_validation?: string;
  phi_redaction?: string;
  auth_type?: string;
  auth_resolved?: boolean;
  required_scopes?: string[];
  granted_scopes?: string[];
  scope_check?: string;
  handler_status?: string;
  duration_ms?: number;
  result_shape?: string;
  error_code?: number | null;
  error_stage?: string | null;
}

// ── Phase 4-A (2026-07-07): Agent Backend Provider summary ──
// Renders a one-line "Backend Provider" panel when safe_metadata
// carries backend_provider / backend_type (emitted by
// emit_backend_metadata_event in run_trace.py). The full metadata
// block still renders below for raw inspection.
export function BackendProviderSummary({
  meta,
}: {
  meta: Record<string, unknown>;
}) {
  const provider = (meta.backend_provider as string) || '';
  const backendType = (meta.backend_type as string) || '';
  const latency = (meta.provider_latency_ms as number) || 0;
  const status = (meta.provider_status as string) || '';
  const deterministic = (meta.provider_deterministic as boolean) ?? false;
  const supportsTools = (meta.supports_tool_calling as boolean) ?? false;
  const fallbackUsed = (meta.fallback_used as boolean) ?? false;
  const outputContract = (meta.output_contract as string) || '';
  const toolRounds = (meta.tool_rounds as number) || 0;

  if (!provider) return null;

  const statusColor =
    status === 'pass' || status === 'complete' || status === 'compliant'
      ? 'text-green-700 bg-green-50 border-green-200'
      : status === 'warning' || status === 'requires_review' || status === 'unclear' || status === 'incomplete'
      ? 'text-amber-700 bg-amber-50 border-amber-200'
      : 'text-red-700 bg-red-50 border-red-200';

  return (
    <div className="border border-border/40 rounded-md p-2 mb-2 bg-muted/20">
      <div className="flex flex-wrap items-center gap-2 mb-1.5">
        <span className="text-[10px] font-semibold text-primary">
          Backend Provider
        </span>
        <span className="font-mono text-xs font-semibold text-foreground">{provider}</span>
        {backendType && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono text-muted-foreground">
            {backendType}
          </span>
        )}
        {status && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono border ${statusColor}`}>
            {status}
          </span>
        )}
        {fallbackUsed && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-50 border border-orange-200 text-orange-700 font-mono">
            fallback
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-3 text-[10px] text-muted-foreground font-mono">
        {latency > 0 && (
          <span>latency: <span className="text-foreground font-semibold">{latency}ms</span></span>
        )}
        <span>
          deterministic: <span className="text-foreground">{deterministic ? 'yes' : 'no'}</span>
        </span>
        <span>
          tools: <span className="text-foreground">{supportsTools ? 'yes' : 'no'}</span>
        </span>
        {supportsTools && toolRounds > 0 && (
          <span>
            tool_rounds: <span className="text-foreground">{toolRounds}</span>
          </span>
        )}
        {outputContract && (
          <span>
            contract: <span className="text-foreground">{outputContract}</span>
          </span>
        )}
      </div>
    </div>
  );
}

export function ToolDispatchDetail({
  detail,
  t,
}: {
  detail: DispatchDetail;
  t: ReturnType<typeof useT>;
}) {
  const [open, setOpen] = useState(detail.handler_status === 'failed');
  const failed = detail.handler_status === 'failed';

  const rows: JSX.Element[] = [];
  const pushRow = (label: string, value: JSX.Element | string, keyId: string) => {
    rows.push(
      <div key={keyId} className="flex items-start gap-2 text-xs py-0.5">
        <span className="text-muted-foreground w-32 shrink-0">{label}:</span>
        <span className="font-mono text-foreground flex-1 break-all">{value}</span>
      </div>,
    );
  };

  pushRow(t.runTraceToolName, detail.tool_name || '-', 'tool');
  pushRow(t.runTraceDispatchMode, detail.dispatch_mode || '-', 'mode');
  pushRow(
    t.runTraceRoundIndex,
    typeof detail.round_index === 'number' ? String(detail.round_index) : '-',
    'ridx',
  );
  pushRow(t.runTraceCaller, detail.caller || '-', 'caller');
  pushRow(t.runTraceHandlerRef, detail.handler_ref || '-', 'href');
  pushRow(
    t.runTraceSchemaValidation,
    <span className={detail.input_schema_validation === 'failed' ? 'text-red-600' : ''}>
      {detail.input_schema_validation || '-'}
    </span>,
    'schema',
  );
  pushRow(
    t.runTracePhiRedaction,
    <span className={detail.phi_redaction === 'failed' ? 'text-red-600' : ''}>
      {detail.phi_redaction || '-'}
    </span>,
    'phi',
  );
  pushRow(t.runTraceAuthType, detail.auth_type || '-', 'auth');
  pushRow(
    t.runTraceAuthType === 'auth_type' ? 'auth_resolved' : 'auth_resolved',
    detail.auth_resolved === true ? 'true' : detail.auth_resolved === false ? 'false' : '-',
    'ar',
  );
  pushRow(
    t.runTraceScopeDiff.replace(/\s*\(.*\)$/, ''),
    detail.required_scopes && detail.required_scopes.length > 0
      ? detail.required_scopes.join(', ')
      : '-',
    'rs',
  );
  pushRow(
    t.runTraceGrantedScopes,
    detail.granted_scopes && detail.granted_scopes.length > 0
      ? detail.granted_scopes.join(', ')
      : '-',
    'gs',
  );
  pushRow(
    t.runTraceScopeCheck,
    <span className={detail.scope_check === 'failed' ? 'text-red-600' : ''}>
      {detail.scope_check || '-'}
    </span>,
    'sc',
  );
  pushRow(
    t.runTraceHandlerStatus,
    <span className={failed ? 'text-red-600 font-semibold' : 'text-green-700'}>
      {detail.handler_status || '-'}
    </span>,
    'hs',
  );
  pushRow(
    t.runTraceDurationMs,
    typeof detail.duration_ms === 'number' ? `${detail.duration_ms.toFixed(1)}ms` : '-',
    'dur',
  );
  pushRow(t.runTraceResultShape, detail.result_shape || '-', 'shape');
  pushRow(
    t.runTraceErrorStage,
    detail.error_stage || '-',
    'es',
  );
  pushRow(
    t.runTraceMcpErrorCode,
    detail.error_code !== null && detail.error_code !== undefined ? String(detail.error_code) : '-',
    'ec',
  );

  return (
    <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-1.5 px-2.5 py-1.5 hover:bg-amber-100/50 transition-colors text-left"
      >
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <span className="text-[10px] font-semibold text-amber-800">
          {t.runTraceToolDispatchDetail}
        </span>
        {failed && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 text-red-700 font-mono ml-auto">
            failed
          </span>
        )}
      </button>
      {open && (
        <div className="px-2.5 pb-2 pt-1 border-t border-amber-200/60 bg-background/60">
          {rows}
        </div>
      )}
    </div>
  );
}

function renderScopeDiff(
  required: string[] | undefined,
  granted: string[] | undefined,
  noRequiredLabel: string,
): JSX.Element {
  const req = required || [];
  const gran = granted || [];
  return (
    <div className="flex flex-wrap gap-1.5">
      {req.map((scope) => {
        const matched = gran.includes(scope);
        return (
          <span
            key={scope}
            className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
              matched ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
            }`}
          >
            {matched ? '✓' : '✗'} {scope}
          </span>
        );
      })}
      {req.length === 0 && (
        <span className="text-[10px] text-muted-foreground italic">{noRequiredLabel}</span>
      )}
    </div>
  );
}

function renderDispatcherDetail(
  step: string,
  meta: Record<string, unknown>,
  t: ReturnType<typeof useT>,
): JSX.Element {
  const toolName = (meta.tool_name as string) || '-';
  const handlerRef = (meta.handler_ref as string) || '';
  const stage = (meta.stage as string) || '';
  const authType = (meta.auth_type as string) || '';
  const redactedView = (meta.redacted_view as string) || '';
  const requiredScopes = meta.required_scopes as string[] | undefined;
  const grantedScopes = meta.granted_scopes as string[] | undefined;
  const argKeys = meta.arguments_key as string[] | undefined;
  const argSize = meta.arguments_size as number | undefined;
  const inputValidated = meta.input_validated as boolean | undefined;
  const resultType = (meta.result_type as string) || '';
  const resultKeys = meta.result_keys as string[] | undefined;
  const resultSize = meta.result_size as number | undefined;
  const totalDispatchMs = meta.total_dispatch_ms as number | undefined;
  const isError = meta.is_error as boolean | undefined;
  const error = (meta.error as string) || '';
  const mcpErrorCode = (meta.mcp_error_code as string) || '';
  const note = (meta.note as string) || '';

  const rows: JSX.Element[] = [];

  if (step === 'tools_list') {
    const toolCount = meta.tool_count as number | undefined;
    const toolNames = meta.tool_names as string[] | undefined;
    rows.push(
      <div key="tc" className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">{t.runTraceToolCount}:</span>
        <span className="font-mono font-semibold text-foreground">{toolCount ?? '-'}</span>
      </div>,
    );
    if (toolNames && toolNames.length > 0) {
      rows.push(
        <div key="tn" className="text-xs">
          <span className="text-muted-foreground">{t.runTraceToolNames}: </span>
          <div className="flex flex-wrap gap-1 mt-1">
            {toolNames.map((n) => (
              <span key={n} className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono">{n}</span>
            ))}
          </div>
        </div>,
      );
    }
    return <div className="space-y-1.5">{rows}</div>;
  }

  // For the other 3 dispatcher steps, show tool_name + handler_ref first.
  rows.push(
    <div key="tn" className="flex items-center gap-2 text-xs">
      <span className="text-muted-foreground">{t.runTraceToolName}:</span>
      <span className="font-mono font-semibold text-primary">{toolName}</span>
      {stage && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
          {t.runTraceStage}: {stage}
        </span>
      )}
    </div>,
  );

  if (handlerRef) {
    rows.push(
      <div key="hr" className="text-xs">
        <span className="text-muted-foreground">{t.runTraceHandlerRef}:</span>
        <code className="ml-1.5 text-[11px] font-mono text-foreground bg-muted/40 px-1.5 py-0.5 rounded break-all">
          {handlerRef}
        </code>
      </div>,
    );
  }

  if (step === 'auth_resolved') {
    if (authType) {
      rows.push(
        <div key="at" className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">{t.runTraceAuthType}:</span>
          <span className="font-mono font-semibold text-foreground">{authType}</span>
          {authType === 'in-process' && (
            <span className="text-[10px] text-amber-600">{t.runTraceInProcessBypass}</span>
          )}
        </div>,
      );
    }
    if (redactedView) {
      rows.push(
        <div key="rv" className="text-xs">
          <span className="text-muted-foreground">{t.runTraceRedactedView}:</span>
          <code className="ml-1.5 text-[11px] font-mono text-muted-foreground break-all">{redactedView}</code>
        </div>,
      );
    }
    if (grantedScopes && grantedScopes.length > 0) {
      rows.push(
        <div key="gs" className="text-xs">
          <span className="text-muted-foreground">{t.runTraceGrantedScopes}:</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {grantedScopes.map((s) => (
              <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-green-100 text-green-700 font-mono">
                {s}
              </span>
            ))}
          </div>
        </div>,
      );
    }
    if (note) {
      rows.push(
        <div key="nt" className="text-[11px] text-amber-600 italic">{note}</div>,
      );
    }
  }

  if (step === 'scope_checked') {
    rows.push(
      <div key="sd" className="text-xs">
        <span className="text-muted-foreground">{t.runTraceScopeDiff}:</span>
        <div className="mt-1.5">
          {renderScopeDiff(requiredScopes, grantedScopes, t.runTraceNoRequiredScopes)}
        </div>
      </div>,
    );
    if (redactedView) {
      rows.push(
        <div key="rv" className="text-xs">
          <span className="text-muted-foreground">{t.runTraceRedactedView}:</span>
          <code className="ml-1.5 text-[11px] font-mono text-muted-foreground break-all">{redactedView}</code>
        </div>,
      );
    }
  }

  if (step === 'tools_call') {
    if (argKeys && argKeys.length > 0) {
      rows.push(
        <div key="ak" className="text-xs">
          <span className="text-muted-foreground">
            {t.runTraceArguments} ({argKeys.length} {t.runTraceArgumentsKeysLabel}, {argSize ?? 0} {t.runTraceChars}
            {inputValidated ? `, ${t.runTraceValidated}` : ''}):
          </span>
          <div className="flex flex-wrap gap-1 mt-1">
            {argKeys.map((k) => (
              <span key={k} className="text-[10px] px-1.5 py-0.5 rounded bg-muted font-mono">{k}</span>
            ))}
          </div>
        </div>,
      );
    }
    // Phase 3-D2.5 Part A2 - Tool Dispatch Detail expandable
    const dispatchDetail = meta.dispatch_detail as DispatchDetail | undefined;
    if (dispatchDetail && typeof dispatchDetail === 'object') {
      rows.push(
        <ToolDispatchDetail key="tdd" detail={dispatchDetail} t={t} />,
      );
    }
    // Phase 4-A - Backend Provider summary (emitted by emit_backend_metadata_event)
    if (meta.backend_provider && typeof meta.backend_provider === 'string') {
      rows.push(
        <BackendProviderSummary key="bps" meta={meta} />,
      );
    }
  }

  if (step === 'completion') {
    if (isError === false) {
      rows.push(
        <div key="rs" className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">{t.runTraceResult}:</span>
          <span className="font-mono font-semibold text-green-700">{resultType}</span>
          {resultKeys && resultKeys.length > 0 && (
            <span className="text-[10px] text-muted-foreground">
              ({resultKeys.length} {t.runTraceResultKeysLabel}: {resultKeys.join(', ')})
            </span>
          )}
          {resultSize !== undefined && (
            <span className="text-[10px] text-muted-foreground font-mono">{resultSize} {t.runTraceChars}</span>
          )}
        </div>,
      );
    } else {
      if (error) {
        rows.push(
          <div key="er" className="text-xs">
            <span className="text-red-600">{t.runTraceError}:</span>
            <code className="ml-1.5 text-[11px] font-mono text-red-600 break-all">{error}</code>
          </div>,
        );
      }
      if (mcpErrorCode) {
        rows.push(
          <div key="ec" className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">{t.runTraceMcpErrorCode}:</span>
            <span className="font-mono font-semibold text-red-600">{mcpErrorCode}</span>
          </div>,
        );
      }
    }
    if (totalDispatchMs !== undefined) {
      rows.push(
        <div key="td" className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">{t.runTraceTotalDispatch}:</span>
          <span className="font-mono font-semibold text-foreground">{totalDispatchMs.toFixed(1)}ms</span>
          <span className="text-[10px] text-muted-foreground">{t.runTraceTotalDispatchBreakdown}</span>
        </div>,
      );
    }
  }

  return <div className="space-y-1.5">{rows}</div>;
}

function renderSafeMetadata(
  step: string,
  meta: Record<string, unknown> | undefined,
  noMetadataLabel: string,
): JSX.Element {
  if (!meta || Object.keys(meta).length === 0) {
    return <span className="text-[11px] text-muted-foreground italic">{noMetadataLabel}</span>;
  }

  // Defense-in-depth: for the auth_resolved step, only surface
  // redacted_view + granted_scopes + auth_type + tool_name + note. Hide
  // everything else (the store contract already guarantees no raw tokens,
  // but this belt-and-braces measure prevents a future emit site from
  // leaking).
  if (step === 'auth_resolved') {
    const allowed = ['tool_name', 'auth_type', 'redacted_view', 'granted_scopes', 'note', 'mcp_error_code'];
    const filtered: Record<string, unknown> = {};
    for (const k of allowed) {
      if (k in meta) filtered[k] = meta[k];
    }
    return (
      <pre className="text-[11px] bg-muted/30 rounded p-2 overflow-x-auto font-mono leading-relaxed">
        {JSON.stringify(filtered, null, 2)}
      </pre>
    );
  }

  return (
    <pre className="text-[11px] bg-muted/30 rounded p-2 overflow-x-auto font-mono leading-relaxed">
      {JSON.stringify(meta, null, 2)}
    </pre>
  );
}

function TimelineRow({
  event, index, t,
}: { event: RunTraceEvent; index: number; t: ReturnType<typeof useT> }) {
  const [expanded, setExpanded] = useState(false);
  const stepLabels: Record<string, string> = {
    user_message_received: t.runTraceStepUserMessageReceived,
    planner_selected_experts: t.runTraceStepPlannerSelectedExperts,
    tools_list: t.runTraceStepToolsList,
    auth_resolved: t.runTraceStepAuthResolved,
    scope_checked: t.runTraceStepScopeChecked,
    tools_call: t.runTraceStepToolsCall,
    expert_response: t.runTraceStepExpertResponse,
    output_generated: t.runTraceStepOutputGenerated,
    completion: t.runTraceStepCompletion,
  };
  const label = stepLabels[event.step] || event.step;
  const hasMeta = event.safe_metadata && Object.keys(event.safe_metadata).length > 0;
  const isDispatcher = DISPATCHER_STEPS.has(event.step);
  const Icon = getStepIcon(event.step);
  // Rich subtitle for dispatcher steps: tool_name + handler_ref
  const meta = event.safe_metadata || {};
  const toolName = (meta.tool_name as string) || '';
  const handlerRef = (meta.handler_ref as string) || '';
  const subtitle = isDispatcher && toolName
    ? `${toolName}${handlerRef ? `  →  ${handlerRef}` : ''}`
    : '';

  return (
    <div className={`border rounded-lg overflow-hidden bg-background ${
      isDispatcher ? 'border-primary/30' : 'border-border/40'
    }`}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-accent/30 transition-colors text-left"
      >
        <span className="text-[10px] font-mono text-muted-foreground w-6 text-right shrink-0">
          {index + 1}
        </span>
        <StatusIcon status={event.status} />
        <Icon size={14} className={isDispatcher ? 'text-primary' : 'text-muted-foreground'} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-foreground truncate">{label}</div>
          {subtitle && (
            <div className="text-[11px] text-muted-foreground font-mono truncate mt-0.5">
              {subtitle}
            </div>
          )}
        </div>
        {event.status && (
          <span className={`text-[10px] px-2 py-0.5 rounded font-mono ${statusBadgeClass(event.status)}`}>
            {event.status}
          </span>
        )}
        {event.duration_ms !== undefined && event.duration_ms > 0 && (
          <span className="text-[10px] text-muted-foreground font-mono">
            {event.duration_ms.toFixed(1)}ms
          </span>
        )}
        <span className="text-[10px] text-muted-foreground font-mono">
          ts={event.ts.toFixed(3)}
        </span>
        {hasMeta ? (
          expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
        ) : null}
      </button>
      {expanded && hasMeta && (
        <div className="px-3 pb-3 pt-1 border-t border-border/20">
          {isDispatcher ? (
            <>
              <p className="text-[10px] font-semibold text-primary mb-1.5 flex items-center gap-1">
                <Cpu size={10} /> {t.runTraceDispatcherDetail}
              </p>
              {renderDispatcherDetail(event.step, meta, t)}
              <p className="text-[10px] font-semibold text-muted-foreground mt-3 mb-1.5">
                {t.runTraceRawSafeMetadata}
              </p>
              {renderSafeMetadata(event.step, meta, t.runTraceNoMetadata)}
            </>
          ) : (
            <>
              {/* Phase 4-A: Backend Provider summary on non-dispatcher steps */}
              {meta.backend_provider && typeof meta.backend_provider === 'string' && (
                <BackendProviderSummary meta={meta} />
              )}
              <p className="text-[10px] font-semibold text-muted-foreground mb-1.5">
                {t.runTraceSafeMetadata}
              </p>
              {renderSafeMetadata(event.step, meta, t.runTraceNoMetadata)}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function RunTracePage() {
  const { runId = '' } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const toast = useToastStore((s) => s.addToast);
  const t = useT();

  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [trace, setTrace] = useState<RunTraceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);

  useEffect(() => {
    if (!runId) {
      setNotFound(true);
      setLoading(false);
      return;
    }
    setLoading(true);
    runtimeAgentApi
      .getRunTrace(runId)
      .then((data) => {
        setTrace(data);
        setNotFound(false);
        setError(null);
      })
      .catch((err) => {
        const status = err?.response?.status;
        if (status === 404) {
          setNotFound(true);
          setError(err?.response?.data?.detail || t.runTraceNotFound);
        } else {
          toast(`${t.runTraceLoadFailed}: ${err?.message || 'unknown'}`, 'error');
          setError(err?.message || t.runTraceLoadError);
        }
      })
      .finally(() => setLoading(false));
  }, [runId, toast, retryNonce, t]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-muted/20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-muted/20 p-6 gap-3">
        <AlertCircle className="h-10 w-10 text-amber-500" />
        <p className="text-sm font-medium text-foreground">{t.runTraceNotFound}</p>
        <p className="text-xs text-muted-foreground max-w-md text-center">
          {error || t.runTraceNotFoundHint}
        </p>
        <button
          onClick={() => navigate(-1)}
          className="mt-2 text-xs text-primary hover:underline"
        >
          {t.runTraceBackToHub}
        </button>
      </div>
    );
  }

  // Sort timeline by step order then ts for stable display.
  const timeline = (trace?.timeline || []).slice().sort((a, b) => {
    const ai = STEP_ORDER.indexOf(a.step);
    const bi = STEP_ORDER.indexOf(b.step);
    if (ai !== -1 && bi !== -1 && ai !== bi) return ai - bi;
    if (ai !== -1 && bi === -1) return -1;
    if (bi !== -1 && ai === -1) return 1;
    return (a.ts || 0) - (b.ts || 0);
  });

  const okCount = timeline.filter((e) => e.status === 'ok').length;
  const failedCount = timeline.filter((e) => e.status === 'failed').length;
  const totalDuration = timeline.reduce(
    (acc, e) => acc + (typeof e.duration_ms === 'number' ? e.duration_ms : 0), 0,
  );

  // Group timeline into segments: pre-dispatcher / dispatcher / post-dispatcher.
  // The dispatcher group is the 4 MCP steps (tools_list / auth_resolved /
  // scope_checked / tools_call). expert_response / output_generated /
  // completion come after.
  type Segment = { kind: 'pre' | 'dispatcher' | 'post'; events: RunTraceEvent[] };
  const segments: Segment[] = [];
  let current: Segment = { kind: 'pre', events: [] };
  for (const ev of timeline) {
    if (ev.step === 'tools_list') {
      if (current.events.length > 0) segments.push(current);
      current = { kind: 'dispatcher', events: [ev] };
    } else if (DISPATCHER_STEPS.has(ev.step)) {
      if (current.kind !== 'dispatcher') {
        if (current.events.length > 0) segments.push(current);
        current = { kind: 'dispatcher', events: [] };
      }
      current.events.push(ev);
    } else {
      if (current.kind === 'dispatcher') {
        if (current.events.length > 0) segments.push(current);
        current = { kind: 'post', events: [ev] };
      } else {
        current.events.push(ev);
      }
    }
  }
  if (current.events.length > 0) segments.push(current);

  // Global index counter for stable numbering across segments.
  let globalIdx = 0;

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-muted/20">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border/40 bg-background flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="p-1.5 rounded-lg hover:bg-accent transition-colors text-muted-foreground"
          title={t.runTraceBack}
        >
          <ArrowLeft size={16} />
        </button>
        <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
          <Activity size={15} className="text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-foreground">{t.runTraceTitle}</p>
          <p className="text-xs text-muted-foreground font-mono truncate">
            {t.runTraceRunId}: {runId}
          </p>
        </div>
        {trace && (
          <div className="flex items-center gap-2 text-[11px]">
            <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground font-mono">
              {trace.step_count} {t.runTraceSteps}
            </span>
            <span className="px-2 py-0.5 rounded bg-green-100 text-green-700 font-mono">
              {okCount} {t.runTraceOk}
            </span>
            {failedCount > 0 && (
              <span className="px-2 py-0.5 rounded bg-red-100 text-red-700 font-mono">
                {failedCount} {t.runTraceFailed}
              </span>
            )}
            <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground font-mono">
              {totalDuration.toFixed(0)}ms {t.runTraceTotal}
            </span>
          </div>
        )}
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl mx-auto space-y-2">
          <p className="text-xs text-muted-foreground mb-4">
            {t.runTraceIntro}
            <span className="block mt-1">
              {t.runTraceAuthFilter}
            </span>
          </p>

          {timeline.length === 0 ? (
            <div className="text-center py-12 text-sm text-muted-foreground flex flex-col items-center gap-3">
              <p>{t.runTraceEmpty}</p>
              <p className="text-xs text-muted-foreground/80 max-w-md">
                {t.runTraceEmptyHint}
              </p>
              <button
                type="button"
                onClick={() => setRetryNonce((n) => n + 1)}
                className="mt-1 px-3 py-1.5 text-xs rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
              >
                {t.runTraceRetry}
              </button>
            </div>
          ) : (
            segments.map((seg, segIdx) => {
              return (
                <div key={`seg-${segIdx}`} className="space-y-2">
                  {seg.kind === 'dispatcher' && (
                    <div className="flex items-center gap-2 px-3 py-1.5 mt-4 rounded-lg bg-primary/5 border border-primary/20">
                      <Cpu size={12} className="text-primary" />
                      <span className="text-[11px] font-semibold text-primary">
                        {t.runTraceDispatcherHeader}
                      </span>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        {seg.events.length} {t.runTraceSteps}
                      </span>
                    </div>
                  )}
                  {seg.events.map((event) => {
                    const idx = globalIdx++;
                    return (
                      <TimelineRow
                        key={`${event.step}-${idx}`}
                        event={event}
                        index={idx}
                        t={t}
                      />
                    );
                  })}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

