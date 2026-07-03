import { useCallback, useEffect, useState } from "react";
import { getRun, getRunAudit, listRuns, downloadReport } from "../services/api";
import type { AuditEvent, RunResult, RunSummary } from "../types";
import { Card, CardBody } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";
import { ErrorState } from "../components/ui/ErrorState";
import { EmptyState } from "../components/ui/EmptyState";
import { RunResultView } from "../components/RunResultView";
import { cn } from "../design/cn";

function fmtTime(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function pct(n: number, d: number): string {
  return d === 0 ? "—" : `${Math.round((n / d) * 100)}%`;
}

// Reviewer/QC triage: runs accumulate unboundedly, so the list needs a status filter.
// 待复核 = the actionable queue (needs review AND not yet reviewed); 拦截 = gate failed.
type Filter = "all" | "review" | "reviewed" | "blocked";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "review", label: "待复核" },
  { id: "reviewed", label: "已复核" },
  { id: "blocked", label: "拦截" },
];

const MATCH: Record<Filter, (r: RunSummary) => boolean> = {
  all: () => true,
  review: (r) => r.human_review_required === 1 && r.reviewed !== 1,
  reviewed: (r) => r.reviewed === 1,
  blocked: (r) => r.passed !== 1,
};

export function RunHistory({ agentId, token }: { agentId: string; token: string }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setRuns(null);
    setError(null);
    listRuns(token, { agentId, limit: 50 })
      .then((r) => alive && setRuns(r))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, [agentId, token, nonce]);

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  if (selected) {
    return <RunReplay runId={selected} token={token} onBack={() => setSelected(null)} />;
  }

  if (error) {
    return <ErrorState error={error} onRetry={retry} />;
  }

  if (!runs) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-muted">
        <Spinner /> 正在加载运行历史…
      </div>
    );
  }

  const total = runs.length;
  if (total === 0) {
    return (
      <EmptyState
        title="该智能体暂无运行记录"
        hint="在「试用」里跑一次编码审核，运行将出现在这里，可回放证据、门禁与审计时间线。"
      />
    );
  }

  const passed = runs.filter((r) => r.passed === 1).length;
  const needReview = runs.filter((r) => r.human_review_required === 1).length;
  const reviewed = runs.filter((r) => r.reviewed === 1).length;

  const counts: Record<Filter, number> = {
    all: total,
    review: runs.filter(MATCH.review).length,
    reviewed,
    blocked: runs.filter(MATCH.blocked).length,
  };
  const shown = runs.filter(MATCH[filter]);
  const activeLabel = FILTERS.find((f) => f.id === filter)?.label;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="运行数" value={String(total)} />
        <Stat label="门禁通过率" value={pct(passed, total)} />
        <Stat label="需人工复核率" value={pct(needReview, total)} />
        <Stat label="已复核" value={`${reviewed}/${total}`} />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {FILTERS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setFilter(id)}
            aria-pressed={filter === id}
            className={cn(
              "rounded-lg border px-3 py-1 text-xs font-medium transition-colors",
              filter === id
                ? "border-teal bg-teal/10 text-teal"
                : "border-line text-muted hover:bg-surface hover:text-ink",
            )}
          >
            {label}
            <span className={cn("ml-1.5 font-mono", filter === id ? "text-teal" : "text-faint")}>
              {counts[id]}
            </span>
          </button>
        ))}
      </div>

      <Card>
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[32rem] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-faint">
                <th className="px-4 py-2.5 font-medium">时间</th>
                <th className="px-4 py-2.5 font-medium">主诊断码</th>
                <th className="px-4 py-2.5 font-medium">DRG / DIP</th>
                <th className="px-4 py-2.5 font-medium">门禁</th>
                <th className="px-4 py-2.5 font-medium">复核</th>
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-faint">
                    无符合「{activeLabel}」的运行
                  </td>
                </tr>
              ) : (
                shown.map((r) => (
                <tr
                  key={r.run_id}
                  tabIndex={0}
                  role="button"
                  aria-label={`查看运行 ${r.primary_code ?? "无主诊断"} · ${fmtTime(r.created_at)}`}
                  onClick={() => setSelected(r.run_id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelected(r.run_id);
                    }
                  }}
                  className="cursor-pointer border-b border-line/60 last:border-0 hover:bg-surface focus-visible:bg-surface"
                >
                  <td className="px-4 py-2.5 text-muted">{fmtTime(r.created_at)}</td>
                  <td className="px-4 py-2.5 font-mono text-ink">{r.primary_code ?? "—"}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted">
                    {r.drg ?? "—"}
                    {r.dip_code ? ` · ${r.dip_code}` : ""}
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge tone={r.passed === 1 ? "teal" : "warn"}>
                      {r.passed === 1 ? "通过" : "拦截"}
                    </Badge>
                  </td>
                  <td className="px-4 py-2.5">
                    {r.reviewed === 1 ? (
                      <Badge tone="teal">已复核</Badge>
                    ) : r.human_review_required === 1 ? (
                      <Badge tone="warn">待复核</Badge>
                    ) : (
                      <span className="text-faint">—</span>
                    )}
                  </td>
                </tr>
                ))
              )}
            </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardBody className="py-3">
        <p className="text-xs text-faint">{label}</p>
        <p className="mt-1 text-xl font-semibold tracking-tight text-ink">{value}</p>
      </CardBody>
    </Card>
  );
}

const ACTION_LABEL: Record<string, string> = {
  "run.created": "运行创建",
  "report.viewed": "查看报告",
  human_review: "人工复核",
};

export function RunReplay({
  runId,
  token,
  onBack,
}: {
  runId: string;
  token: string;
  onBack: () => void;
}) {
  const [run, setRun] = useState<RunResult | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setRun(null);
    setError(null);
    Promise.all([getRun(token, runId), getRunAudit(token, runId)])
      .then(([r, a]) => {
        if (!alive) return;
        setRun(r);
        setAudit(a);
      })
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, [runId, token, nonce]);

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  const [exporting, setExporting] = useState<"html" | "json" | null>(null);
  const [exportErr, setExportErr] = useState<string | null>(null);
  const exportReport = useCallback(
    async (format: "html" | "json") => {
      setExportErr(null);
      setExporting(format);
      try {
        await downloadReport(token, runId, format);
      } catch (e) {
        setExportErr(e instanceof Error ? e.message : "导出失败");
      } finally {
        setExporting(null);
      }
    },
    [token, runId],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          ← 返回列表
        </Button>
        <div className="flex items-center gap-2">
          {exportErr && (
            <span className="text-xs text-red-600 dark:text-red-400">{exportErr}</span>
          )}
          <span className="font-mono text-xs text-faint">{runId}</span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!run || exporting !== null}
            onClick={() => exportReport("json")}
          >
            {exporting === "json" ? "导出中…" : "导出 JSON"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={!run || exporting !== null}
            onClick={() => exportReport("html")}
          >
            {exporting === "html" ? "导出中…" : "导出 HTML"}
          </Button>
        </div>
      </div>

      {error ? (
        <ErrorState error={error} onRetry={retry} />
      ) : !run ? (
        <div className="flex items-center gap-2 py-10 text-sm text-muted">
          <Spinner /> 正在加载运行…
        </div>
      ) : (
        <>
          <RunResultView run={run} />
          <Card>
            <CardBody>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
                审计时间线（append-only）
              </h3>
              <ol className="mt-3 space-y-2">
                {audit.map((ev) => (
                  <li key={ev.id} className="flex items-start gap-3 text-sm">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal" />
                    <div className="min-w-0">
                      <span className="text-ink">{ACTION_LABEL[ev.action] ?? ev.action}</span>
                      <span className="ml-2 text-xs text-faint">
                        {fmtTime(ev.ts)} · {ev.actor_role ?? "—"}
                      </span>
                      {Object.keys(ev.detail).length > 0 && (
                        <span className="mt-0.5 block break-all font-mono text-xs text-muted">
                          {JSON.stringify(ev.detail)}
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}
