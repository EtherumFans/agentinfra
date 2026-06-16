import { useCallback, useMemo, useRef, useState } from "react";
import { extractFacts } from "../services/api";
import type { ExtractResult, ExtractedEntity } from "../types";
import { Card, CardBody } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Textarea } from "../components/ui/Textarea";
import { Spinner } from "../components/ui/Spinner";
import { ErrorState } from "../components/ui/ErrorState";
import { buildSegments, type Mark } from "../components/RunResultView";
import { cn } from "../design/cn";

// Fact Extraction — pipeline stages 1–2 (ingest → extract) surfaced standalone: paste a
// record, get structured clinical facts (诊断/手术操作) anchored to evidence spans, with
// PHI redacted server-side. Deliberately NOT coding: no billing codes, no compliance gate
// — the clean structured-abstraction surface upstream of the coding review.

const SAMPLE = `主要诊断：慢性心力衰竭，心功能Ⅲ级。
其他诊断：高血压病，2型糖尿病，慢性肾脏病，心房颤动。
手术操作：胃镜检查及活检。
影像学：X线提示骨质疏松伴病理性骨折。
患者姓名：张三，住院号：ZY20260613，联系电话：13800001111。`;

const CATEGORY_LABEL: Record<string, string> = {
  diagnosis: "诊断",
  procedure: "手术操作",
  other: "其他",
};
const CATEGORY_ORDER = ["diagnosis", "procedure", "other"];

function markKey(start: number, end: number): string {
  return `${start}-${end}`;
}

export function FactExtraction({ token, agentId }: { token: string; agentId?: string }) {
  const [text, setText] = useState(SAMPLE);
  const [result, setResult] = useState<ExtractResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const markRefs = useRef<Map<string, HTMLElement | null>>(new Map());

  const run = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      setResult(await extractFacts(token, text, agentId));
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }, [token, text, agentId]);

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

  const docText = result?.redaction.text ?? "";
  const segments = useMemo(() => {
    if (!result) return [];
    const marks: Mark[] = [];
    for (const e of result.entities) {
      for (const ev of e.evidences) marks.push({ start: ev.start, end: ev.end, code: e.term });
    }
    return buildSegments(docText, marks);
  }, [result, docText]);

  const groups = useMemo(() => {
    const g: Record<string, ExtractedEntity[]> = {};
    if (result) {
      for (const e of result.entities) (g[e.category ?? "other"] ??= []).push(e);
    }
    return g;
  }, [result]);

  return (
    <div className="space-y-5">
      <Card>
        <CardBody>
          <div className="flex items-center justify-between">
            <h3 id="extract-doc-heading" className="text-sm font-semibold text-ink">
              病历文本 · 抽取结构化临床事实
            </h3>
            <span className="text-xs text-faint">仅前两阶段：摄入 → 抽取，不出编码/门禁</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            从病历抽取诊断与手术操作等临床事实，并回链证据位置；PHI 在服务端本地脱敏，
            <span className="text-ink">数据不出院</span>。这是编码审核之前的结构化抽象层。
          </p>
          <Textarea
            aria-labelledby="extract-doc-heading"
            className="mt-3 h-44"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="mt-3 flex items-center gap-3">
            <Button onClick={run} disabled={running || !text.trim()}>
              {running ? "抽取中…" : "抽取事实"}
            </Button>
            {running ? (
              <span className="flex items-center gap-2 text-xs text-muted">
                <Spinner /> 正在脱敏并抽取临床实体…
              </span>
            ) : (
              <span className="text-xs text-faint">
                抽取为只读：不创建运行、不写回、不产生计费编码。
              </span>
            )}
          </div>
        </CardBody>
      </Card>

      {error ? <ErrorState error={error} onRetry={run} /> : null}

      {result && (
        <>
          <RedactionPanel result={result} />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardBody>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
                  去标识化病历 · 事实回链
                </h3>
                <div className="mt-3 whitespace-pre-wrap text-sm leading-[1.9] text-ink">
                  {docText ? (
                    segments.map((seg, i) =>
                      seg.mark ? (
                        <mark
                          key={i}
                          ref={(el) => {
                            if (el) markRefs.current.set(markKey(seg.mark!.start, seg.mark!.end), el);
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

            <Card>
              <CardBody>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
                    结构化事实
                  </h3>
                  <span className="font-mono text-[11px] tabular-nums text-faint">
                    {result.entities.length} 项 · {result.provider}
                  </span>
                </div>
                {result.entities.length ? (
                  <div className="mt-3 space-y-4">
                    {CATEGORY_ORDER.filter((c) => groups[c]?.length).map((c) => (
                      <div key={c}>
                        <p className="text-[11px] font-medium text-faint">
                          {CATEGORY_LABEL[c]}（{groups[c].length}）
                        </p>
                        <ul className="mt-1.5 space-y-1.5">
                          {groups[c].map((e, i) => (
                            <li key={`${e.term}-${i}`} className="rounded-lg border border-line p-2.5">
                              <span className="text-sm text-ink">{e.term}</span>
                              <div className="mt-1.5 flex flex-wrap gap-1.5">
                                {e.evidences.length ? (
                                  e.evidences.map((ev, j) => (
                                    <button
                                      key={j}
                                      onClick={() => jumpTo(ev.start, ev.end)}
                                      className="rounded-md border border-teal-100 bg-teal-50 px-1.5 py-0.5 text-[11px] text-teal-600 hover:bg-teal-100"
                                    >
                                      「{ev.text}」 [{ev.start},{ev.end})
                                    </button>
                                  ))
                                ) : (
                                  <span className="text-xs text-faint">无证据</span>
                                )}
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-sm text-faint">未抽取到临床事实。</p>
                )}
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function RedactionPanel({ result }: { result: ExtractResult }) {
  const { spans, by_type } = result.redaction;
  return (
    <Card>
      <CardBody>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-ink">本地去标识化 · 数据不出院</h3>
          <span className="rounded-md bg-surface px-1.5 py-0.5 text-[11px] text-muted">
            {spans > 0 ? `已脱敏 ${spans} 处 PHI` : "未检出 PHI"}
          </span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          PHI 在服务端就地脱敏，抽取仅在去标识化文本上进行；原始标识符不回传、不渲染。
        </p>
        {by_type.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {by_type.map((p) => (
              <span
                key={p.type}
                className="rounded-md border border-line bg-panel px-2 py-0.5 text-xs text-muted"
              >
                {p.type} <span className="font-mono text-faint">×{p.count}</span>
              </span>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
