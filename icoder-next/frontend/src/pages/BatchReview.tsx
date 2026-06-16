import { useCallback, useMemo, useState } from "react";
import { runBatch } from "../services/api";
import type { BatchResult } from "../types";
import { Card, CardBody } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Textarea } from "../components/ui/Textarea";
import { Spinner } from "../components/ui/Spinner";
import { ErrorState } from "../components/ui/ErrorState";
import { RunReplay } from "./RunHistory";

// Batch worklist for a 病案编码员: paste several records (one per "---" separator line),
// run them through the same single-run pipeline server-side, triage the rows, then drill
// into any run to inspect evidence / gate / audit — identical to the run-history replay.

const BATCH_SAMPLE = `主要诊断：慢性心力衰竭，心功能Ⅲ级。其他诊断：高血压病，2型糖尿病。
---
主要诊断：脑梗死后遗症。其他诊断：高血压病3级。手术操作：胃镜检查及活检。
---
主要诊断：闭合性胫腓骨骨折。手术操作：骨折切开复位内固定术。`;

const BATCH_MAX = 20;

function parseRecords(text: string): string[] {
  return text
    .split(/^\s*-{3,}\s*$/m)
    .map((r) => r.trim())
    .filter(Boolean);
}

function preview(text: string | undefined): string {
  if (!text) return "—";
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > 42 ? `${oneLine.slice(0, 42)}…` : oneLine;
}

export function BatchReview({
  agentId,
  token,
  codingSystem,
}: {
  agentId: string;
  token: string;
  codingSystem: string;
}) {
  const [text, setText] = useState(BATCH_SAMPLE);
  const [submitted, setSubmitted] = useState<string[]>([]);
  const [result, setResult] = useState<BatchResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const records = useMemo(() => parseRecords(text), [text]);
  const tooMany = records.length > BATCH_MAX;

  const run = useCallback(async () => {
    const recs = parseRecords(text);
    if (recs.length === 0 || recs.length > BATCH_MAX) return;
    setRunning(true);
    setError(null);
    setSubmitted(recs);
    try {
      setResult(await runBatch(token, recs, { codingSystem, agentId }));
    } catch (e) {
      setError(e);
      setResult(null);
    } finally {
      setRunning(false);
    }
  }, [text, token, codingSystem, agentId]);

  if (selected) {
    return <RunReplay runId={selected} token={token} onBack={() => setSelected(null)} />;
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardBody>
          <div className="flex items-center justify-between">
            <h3 id="batch-doc-heading" className="text-sm font-semibold text-ink">
              批量病历（每条以单独一行 <span className="font-mono text-muted">---</span> 分隔 · PHI 在服务端脱敏）
            </h3>
            <span className="text-xs text-faint">体系 {codingSystem}</span>
          </div>
          <Textarea
            aria-labelledby="batch-doc-heading"
            className="mt-3 h-56"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button onClick={run} disabled={running || records.length === 0 || tooMany}>
              {running ? "运行中…" : `运行批量审核（${records.length} 条）`}
            </Button>
            {running ? (
              <span className="flex items-center gap-2 text-xs text-muted">
                <Spinner /> 正在逐条执行编码管线…
              </span>
            ) : tooMany ? (
              <span className="text-xs text-amber-600 dark:text-amber-400">
                单次最多 {BATCH_MAX} 条，请减少后重试。
              </span>
            ) : (
              <span className="text-xs text-faint">
                每条作为独立运行持久化，可在「运行历史」回放；本切片同步执行，生产将异步排队。
              </span>
            )}
          </div>
        </CardBody>
      </Card>

      {error ? <ErrorState error={error} onRetry={run} /> : null}

      {result && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Stat label="提交条数" value={String(result.total)} />
            <Stat label="门禁通过" value={`${result.passed}/${result.total}`} />
            <Stat label="待人工复核" value={`${result.needs_review}/${result.total}`} />
          </div>

          <Card>
            <CardBody className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[36rem] text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-xs text-faint">
                      <th className="px-4 py-2.5 font-medium">#</th>
                      <th className="px-4 py-2.5 font-medium">病历摘要</th>
                      <th className="px-4 py-2.5 font-medium">主诊断码</th>
                      <th className="px-4 py-2.5 font-medium">DRG / DIP</th>
                      <th className="px-4 py-2.5 font-medium">门禁</th>
                      <th className="px-4 py-2.5 font-medium">复核</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.results.map((r) => (
                      <tr
                        key={r.run_id}
                        tabIndex={0}
                        role="button"
                        aria-label={`查看第 ${r.index + 1} 条运行 ${r.primary_code ?? "无主诊断"}`}
                        onClick={() => setSelected(r.run_id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setSelected(r.run_id);
                          }
                        }}
                        className="cursor-pointer border-b border-line/60 last:border-0 hover:bg-surface focus-visible:bg-surface"
                      >
                        <td className="px-4 py-2.5 font-mono text-faint">{r.index + 1}</td>
                        <td className="px-4 py-2.5 text-muted">{preview(submitted[r.index])}</td>
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
                    ))}
                  </tbody>
                </table>
              </div>
            </CardBody>
          </Card>
        </>
      )}
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
