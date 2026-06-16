import { Fragment, useMemo, useRef, useState } from "react";
import type { CodeResult, RunResult } from "../types";
import { Card, CardBody } from "./ui/Card";
import { Badge } from "./ui/Badge";
import { cn } from "../design/cn";

export interface Mark {
  start: number;
  end: number;
  code: string;
}

export interface Segment {
  text: string;
  mark?: Mark;
}

// Merge evidence spans from all codes/candidates into non-overlapping segments,
// mirroring the vanilla widget's highlight() (start inclusive, end exclusive).
export function buildSegments(text: string, marks: Mark[]): Segment[] {
  const spans = [...marks].sort((a, b) => a.start - b.start || b.end - a.end);
  const segs: Segment[] = [];
  let cursor = 0;
  for (const s of spans) {
    if (s.start < cursor || s.start >= s.end || s.end > text.length) continue; // overlap/oob
    if (s.start > cursor) segs.push({ text: text.slice(cursor, s.start) });
    segs.push({ text: text.slice(s.start, s.end), mark: s });
    cursor = s.end;
  }
  if (cursor < text.length) segs.push({ text: text.slice(cursor) });
  return segs;
}

const sevClass: Record<string, string> = {
  Critical: "text-red-700 font-semibold dark:text-red-300",
  Moderate: "text-amber-700 dark:text-amber-300",
  Informational: "text-faint",
};

const STAGE_LABEL: Record<string, string> = {
  ingest: "摄入 · PHI 脱敏",
  extract: "实体抽取",
  submit: "提交事实",
  retrieve: "候选检索",
  verify: "编码核验",
  sequence: "诊断排序",
  group: "DRG/DIP 分组",
  compliance: "合规门禁",
};

// Research-phase tool names — the model's autonomous coding-expert calls. The migrated
// (with-key) coding-review path emits stage="tool" rows whose tool is one of these.
const TOOL_LABEL: Record<string, string> = {
  search: "索引检索",
  verify: "编码核验",
  guidelines: "编码指南",
  explore: "层级邻居",
  alternatives: "鉴别诊断",
};

// The Event Inspector shows two phases: the LLM's autonomous tool-calling research (only
// present with a key) and the deterministic coding/compliance pipeline. Offline runs carry
// no research stages, so the timeline self-degrades to the classic flat list (no headers).
function phaseOf(stage: string, hasResearch: boolean): "research" | "pipeline" {
  if (!hasResearch) return "pipeline";
  return stage === "ingest" || stage === "tool" || stage === "submit"
    ? "research"
    : "pipeline";
}

// ICD instructional notes (Verify tool). excludes1 is a hard mutual-exclusion —
// the strongest compliance signal — so it gets a warn tone; the rest are advisory.
const NOTE_LABEL: Record<string, string> = {
  includes: "包含",
  excludes1: "不可同时编码",
  excludes2: "可另编码",
  code_first: "先编码",
  use_additional: "附加编码",
};
const NOTE_WARN = new Set(["excludes1"]);

function markKey(start: number, end: number): string {
  return `${start}-${end}`;
}

export function RunResultView({ run }: { run: RunResult }) {
  const [flash, setFlash] = useState<string | null>(null);
  const markRefs = useRef<Map<string, HTMLElement | null>>(new Map());

  const docText = run.redaction.text ?? "";
  const offline = run.versions.model_version === "deterministic-local";
  const segments = useMemo(() => {
    const marks: Mark[] = [];
    for (const c of [...run.codes, ...run.candidates]) {
      for (const ev of c.evidences ?? []) {
        marks.push({ start: ev.start, end: ev.end, code: c.code });
      }
    }
    return buildSegments(docText, marks);
  }, [run, docText]);

  function jumpTo(start: number, end: number) {
    const key = markKey(start, end);
    const el = markRefs.current.get(key);
    if (el) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    }
    setFlash(key);
    window.setTimeout(() => setFlash((f) => (f === key ? null : f)), 900);
  }

  return (
    <div className="space-y-4">
      {offline ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <span className="font-semibold">离线确定性模式</span> · 未配置外部 LLM；本结果由本地词典抽取生成（非 LLM 研究式抽取）。配置{" "}
          <code className="rounded bg-amber-100 px-1 font-mono dark:bg-amber-900/60">
            ICODER_CREDENTIAL_LLM
          </code>{" "}
          后启用完整的工具调用研究抽取。
        </div>
      ) : (
        <span className="inline-flex w-fit items-center gap-1 rounded-md border border-teal-100 bg-teal-50 px-2 py-0.5 text-[11px] font-medium text-teal-700 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-300">
          LLM 研究式抽取 · {run.versions.model_version}
        </span>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Left: redacted doc with evidence highlights */}
        <Card>
          <CardBody>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
                去标识化病历 · 证据回链
              </h3>
              {run.redaction.redacted && (
                <span className="rounded-md bg-surface px-1.5 py-0.5 text-[11px] text-muted">
                  PHI 脱敏 ·{" "}
                  {typeof run.redaction.spans === "number"
                    ? run.redaction.spans > 0
                      ? `已移除 ${run.redaction.spans} 处`
                      : "未检出"
                    : "已处理"}
                </span>
              )}
            </div>
            <div className="mt-3 whitespace-pre-wrap text-sm leading-[1.9] text-ink">
              {docText ? (
                segments.map((seg, i) =>
                  seg.mark ? (
                    <mark
                      key={i}
                      ref={(el) => {
                        const key = markKey(seg.mark!.start, seg.mark!.end);
                        if (el) markRefs.current.set(key, el);
                      }}
                      className={cn(
                        "rounded-sm border-b-2 border-teal px-px text-ink",
                        flash === markKey(seg.mark.start, seg.mark.end)
                          ? "bg-amber-200 dark:bg-amber-400/30"
                          : "bg-teal-50",
                      )}
                    >
                      {seg.text}
                    </mark>
                  ) : (
                    <span key={i}>{seg.text}</span>
                  ),
                )
              ) : (
                <span className="text-faint">无文本</span>
              )}
            </div>
          </CardBody>
        </Card>

        {/* Right: codes / candidates / gate / DRG */}
        <Card>
          <CardBody>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
              编码结果 · 合规门禁
            </h3>

            <p className="mt-3 text-xs text-muted">Codes（确信 · 可计费）</p>
            <div className="mt-2 space-y-2">
              {run.codes.length ? (
                run.codes.map((c) => <CodeCard key={c.code} c={c} onJump={jumpTo} />)
              ) : (
                <p className="text-sm text-faint">无</p>
              )}
            </div>

            <p className="mt-4 text-xs text-muted">
              Candidates（需人工复核 · 不与 codes 合并）
            </p>
            <div className="mt-2 space-y-2">
              {run.candidates.length ? (
                run.candidates.map((c) => <CodeCard key={c.code} c={c} onJump={jumpTo} />)
              ) : (
                <p className="text-sm text-faint">无</p>
              )}
            </div>

            <Gate run={run} />
            <Drg run={run} />
            {run.human_review && <ReviewPanel run={run} />}

            <p className="mt-3 font-mono text-[11px] leading-5 text-faint">
              runtime {run.versions.runtime_version} · ruleset {run.versions.ruleset_version} ·
              catalog {run.versions.catalog_version} · model {run.versions.model_version} ·
              writeback_blocked={String(run.production_writeback_blocked)}
            </p>
          </CardBody>
        </Card>
      </div>

      <PipelineTimeline run={run} />
    </div>
  );
}

function CodeCard({
  c,
  onJump,
}: {
  c: CodeResult;
  onJump: (start: number, end: number) => void;
}) {
  return (
    <div className="rounded-lg border border-line p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold text-ink">{c.code}</span>
        <span className="text-xs text-muted">{c.display}</span>
        {c.is_primary && <Badge tone="teal">主要诊断</Badge>}
        {c.high_risk && <Badge tone="warn">高风险/易错</Badge>}
        <Badge>{c.system}</Badge>
        <Badge>conf {c.confidence.toFixed(2)}</Badge>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {(c.evidences ?? []).length ? (
          c.evidences.map((ev, i) => (
            <button
              key={i}
              onClick={() => onJump(ev.start, ev.end)}
              className="rounded-md border border-teal-100 bg-teal-50 px-1.5 py-0.5 text-[11px] text-teal-600 hover:bg-teal-100"
            >
              「{ev.text}」 [{ev.start},{ev.end})
            </button>
          ))
        ) : (
          <span className="text-xs text-faint">无证据</span>
        )}
      </div>

      {(c.notes ?? []).length > 0 && (
        <div className="mt-2 space-y-1">
          {c.notes.map((n, i) => (
            <div key={i} className="flex items-start gap-1.5 text-[11px] leading-5">
              <span
                className={cn(
                  "shrink-0 rounded px-1 py-px font-medium",
                  NOTE_WARN.has(n.kind)
                    ? "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300"
                    : "bg-surface text-muted",
                )}
              >
                {NOTE_LABEL[n.kind] ?? n.kind}
              </span>
              <span className="text-muted">{n.text}</span>
            </div>
          ))}
        </div>
      )}

      {(c.alternatives ?? []).length > 0 && (
        <div className="mt-2 rounded-md border border-dashed border-line bg-surface/40 p-2">
          <p className="text-[11px] font-medium text-faint">鉴别诊断 · 未采纳</p>
          <div className="mt-1 space-y-0.5">
            {c.alternatives.map((a, i) => (
              <div key={i} className="text-[11px] leading-5">
                <span className="font-mono text-muted">{a.code}</span>{" "}
                <span className="text-muted">{a.display}</span>
                {a.reason && <span className="text-faint"> · {a.reason}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Gate({ run }: { run: RunResult }) {
  const g = run.compliance;
  return (
    <div
      className={cn(
        "mt-4 rounded-lg border p-2.5 text-sm",
        g.passed
          ? "border-green-200 bg-green-50 text-green-700 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300"
          : "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300",
      )}
    >
      门禁：{g.passed ? "通过" : "拦截"} · 需人工复核：{g.human_review_required ? "是" : "否"}
      {g.hits.map((h, i) => (
        <div key={i} className="mt-1.5 text-xs">
          <span className={sevClass[h.severity] ?? "text-muted"}>
            [{h.severity}] {h.rule_id}
          </span>{" "}
          {h.message}
        </div>
      ))}
    </div>
  );
}

function Drg({ run }: { run: RunResult }) {
  const drg = run.drg_route;
  if (!drg || !drg.drg) {
    return (
      <div className="mt-3 rounded-lg border border-line bg-surface p-2.5 text-xs text-faint">
        DRG：{drg?.note || "未分组"}
      </div>
    );
  }
  const sev = drg.cc_mcc ? drg.cc_mcc : "无 CC/MCC";
  const kind = drg.surgical ? "外科组" : "内科组";
  return (
    <div className="mt-3 rounded-lg border border-teal-100 bg-teal-50/40 p-2.5 text-xs leading-6 text-ink">
      <div>
        <span className="font-semibold">DRG/DIP 分组</span> · {kind} · 严重度 {sev}
        {drg.mdc ? (
          <span title={drg.mdc_name ?? undefined}> · MDC {drg.mdc}</span>
        ) : (
          ""
        )}
      </div>
      <div>
        ADRG <span className="font-mono">{drg.adrg || "-"}</span> → DRG{" "}
        <span className="font-mono">{drg.drg || "-"}</span> · {drg.group_name || ""}
      </div>
      {drg.dip_code && (
        <div>
          DIP <span className="font-mono">{drg.dip_code}</span> {drg.dip_name || ""} · 分值{" "}
          {drg.dip_score}
        </div>
      )}
      {(drg.rationale ?? []).length > 0 && (
        <div className="mt-1.5 border-t border-teal-100 pt-1.5 dark:border-teal-900">
          <p className="text-[11px] font-medium text-faint">分组理由</p>
          <ul className="mt-0.5 space-y-0.5">
            {drg.rationale.map((r, i) => (
              <li key={i} className="text-[11px] leading-5 text-muted">
                · {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ReviewPanel({ run }: { run: RunResult }) {
  const hr = run.human_review!;
  return (
    <div className="mt-3 rounded-lg border border-line bg-surface p-2.5 text-xs leading-6 text-muted">
      <span className="font-semibold text-ink">人工复核</span> · 角色 {hr.reviewer_role} · 决定{" "}
      {hr.decision}
      {hr.code ? ` · 编码 ${hr.code}` : ""}
      {hr.override_code ? ` · 覆盖为 ${hr.override_code}` : ""}
      {hr.note ? ` · 备注：${hr.note}` : ""}
    </div>
  );
}

// Event Inspector: the tool-orchestration timeline behind a run — iCoDer's signature
// differentiation (every code traces back through the stages that produced it). With a
// key it splits into two phases — the LLM's autonomous tool-calling research, then the
// deterministic coding/compliance pipeline; offline it degrades to the classic flat list.
function PipelineTimeline({ run }: { run: RunResult }) {
  const [open, setOpen] = useState(true);
  const stages = run.stages ?? [];
  if (!stages.length) return null;
  const total = stages.reduce((sum, st) => sum + st.duration_ms, 0);
  const max = Math.max(...stages.map((st) => st.duration_ms), 1);
  const usageEntries = Object.entries(run.usage ?? {});
  const hasResearch = stages.some((st) => st.stage === "tool" || st.stage === "submit");

  return (
    <Card>
      <CardBody>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full flex-wrap items-baseline justify-between gap-2 text-left"
        >
          <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
            运行事件 · Event Inspector
          </h3>
          <span className="font-mono text-[11px] tabular-nums text-faint">
            {stages.length} 事件 · 总耗时 {total.toFixed(1)}ms · {open ? "收起" : "展开"}
          </span>
        </button>

        {open && (
          <>
            <ol className="mt-3.5 space-y-3">
              {stages.map((st, i) => {
                const phase = phaseOf(st.stage, hasResearch);
                const prevPhase =
                  i > 0 ? phaseOf(stages[i - 1].stage, hasResearch) : null;
                const showHeader = hasResearch && phase !== prevPhase;
                const label =
                  st.stage === "tool"
                    ? TOOL_LABEL[st.tool] ?? st.tool
                    : STAGE_LABEL[st.stage] ?? st.stage;
                return (
                  <Fragment key={st.tool_run_id || i}>
                    {showHeader && (
                      <li className="list-none pt-1 first:pt-0">
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
                          {phase === "research"
                            ? "研究阶段 · LLM 自主工具调用"
                            : "确定性管线 · 编码与合规"}
                        </p>
                      </li>
                    )}
                    <li>
                      <div className="grid grid-cols-[1.25rem_7.5rem_1fr_auto] items-center gap-2.5">
                        <span className="font-mono text-[11px] text-faint">{i + 1}</span>
                        <span className="truncate text-sm text-ink" title={st.tool}>
                          {label}
                        </span>
                        <div className="h-1.5 overflow-hidden rounded-full bg-surface">
                          <div
                            className="h-full rounded-full bg-teal transition-[width] duration-base"
                            style={{ width: `${Math.max(4, (st.duration_ms / max) * 100)}%` }}
                          />
                        </div>
                        <span className="font-mono text-[11px] tabular-nums text-muted">
                          {st.duration_ms.toFixed(1)}ms
                        </span>
                      </div>
                      {st.summary && (
                        <p className="ml-[1.75rem] mt-1 text-xs leading-5 text-faint">
                          {st.summary}
                        </p>
                      )}
                    </li>
                  </Fragment>
                );
              })}
            </ol>

            {usageEntries.length > 0 && (
              <p className="mt-4 font-mono text-[11px] leading-5 text-faint">
                {usageEntries.map(([k, v]) => `${k}=${String(v)}`).join(" · ")}
              </p>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}
