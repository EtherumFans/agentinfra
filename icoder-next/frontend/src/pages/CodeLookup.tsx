import { useCallback, useState } from "react";
import { getCodeDetail, searchCodes } from "../services/api";
import type { CodeDetail, CodeSearchHit, RelatedCode } from "../types";
import { Card, CardBody } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorState } from "../components/ui/ErrorState";
import { cn } from "../design/cn";

// Standalone coding-knowledge lookup — the iCoDer analog of Corti's coding-expert
// (Search / Verify / Guidelines / Explore). Pure reference: no run is created, nothing
// is written back. Surfaces the official coding guideline + full hierarchy, which the
// run-result view never shows, so it's net-new — not a duplicate of a run.

const NOTE_LABEL: Record<string, string> = {
  includes: "包含",
  excludes1: "不可同时编码",
  excludes2: "可另编码",
  code_first: "先编码",
  use_additional: "附加编码",
};
const NOTE_WARN = new Set(["excludes1"]);
const TYPE_LABEL: Record<string, string> = { diagnosis: "诊断", procedure: "操作" };

export function CodeLookup({ token }: { token: string }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<CodeSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchErr, setSearchErr] = useState<unknown>(null);

  const [code, setCode] = useState<string | null>(null);
  const [detail, setDetail] = useState<CodeDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailErr, setDetailErr] = useState<unknown>(null);

  const doSearch = useCallback(async () => {
    const term = q.trim();
    if (!term) return;
    setSearching(true);
    setSearchErr(null);
    try {
      setHits(await searchCodes(token, term));
    } catch (e) {
      setSearchErr(e);
      setHits(null);
    } finally {
      setSearching(false);
    }
  }, [q, token]);

  const loadCode = useCallback(
    async (c: string) => {
      setCode(c);
      setDetail(null);
      setLoadingDetail(true);
      setDetailErr(null);
      try {
        setDetail(await getCodeDetail(token, c));
      } catch (e) {
        setDetailErr(e);
      } finally {
        setLoadingDetail(false);
      }
    },
    [token],
  );

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Left: search */}
      <Card>
        <CardBody>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
            编码检索 · ICD-10-CN / ICD-9-CM-3
          </h3>
          <div className="mt-3 flex gap-2">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") doSearch();
              }}
              placeholder="按名称 / 同义词 / 编码检索，如「心衰」「肺部阴影」「胃镜活检」"
              aria-label="编码检索"
              className="min-w-0 flex-1 rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink placeholder:text-faint focus-visible:border-teal"
            />
            <Button onClick={doSearch} disabled={searching || !q.trim()}>
              {searching ? "检索中…" : "检索"}
            </Button>
          </div>

          <div className="mt-3">
            {searchErr ? (
              <ErrorState error={searchErr} onRetry={doSearch} />
            ) : searching ? (
              <div className="flex items-center gap-2 py-6 text-sm text-muted">
                <Spinner /> 正在检索…
              </div>
            ) : hits == null ? (
              <p className="py-6 text-sm leading-relaxed text-faint">
                输入关键词检索编码，查看其指令注释、官方编码指南、上下级层级与易错鉴别。纯查询，不发起运行、不写回。
              </p>
            ) : hits.length === 0 ? (
              <EmptyState title="无匹配编码" hint="换个名称、同义词或编码再试。" />
            ) : (
              <ul className="divide-y divide-line/60">
                {hits.map((h) => (
                  <li key={h.code}>
                    <button
                      onClick={() => loadCode(h.code)}
                      className={cn(
                        "flex w-full items-center gap-2 py-2 text-left transition-colors",
                        h.code === code ? "text-teal" : "text-ink hover:text-teal",
                      )}
                    >
                      <span className="font-mono text-sm font-semibold">{h.code}</span>
                      <span className="min-w-0 flex-1 truncate text-sm text-muted">{h.display}</span>
                      {h.high_risk && <Badge tone="warn">高风险/易错</Badge>}
                      <Badge>{h.system}</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </CardBody>
      </Card>

      {/* Right: detail */}
      <Card>
        <CardBody>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
            编码详情 · 指令注释 / 官方指南 / 层级
          </h3>
          {detailErr ? (
            <div className="mt-3">
              <ErrorState error={detailErr} onRetry={() => code && loadCode(code)} />
            </div>
          ) : loadingDetail ? (
            <div className="mt-3 flex items-center gap-2 py-6 text-sm text-muted">
              <Spinner /> 正在加载详情…
            </div>
          ) : !detail ? (
            <p className="mt-3 py-6 text-sm text-faint">从左侧选择一个编码查看详情。</p>
          ) : (
            <CodeDetailView detail={detail} onNavigate={loadCode} />
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function CodeDetailView({
  detail,
  onNavigate,
}: {
  detail: CodeDetail;
  onNavigate: (c: string) => void;
}) {
  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-base font-semibold text-ink">{detail.code}</span>
        <span className="text-sm text-muted">{detail.display}</span>
        <Badge tone="teal">{TYPE_LABEL[detail.code_type] ?? detail.code_type}</Badge>
        <Badge>{detail.system}</Badge>
        {detail.high_risk && <Badge tone="warn">高风险/易错</Badge>}
      </div>

      {/* Official coding guideline — mandatory per code in Corti's coding-expert; not
          surfaced anywhere in the run result, so this is the net-new value. */}
      {detail.guideline && (
        <div className="rounded-lg border border-teal-100 bg-teal-50/40 p-2.5 text-xs leading-6 dark:border-teal-900">
          <p className="text-[11px] font-medium text-faint">官方编码指南</p>
          <p className="mt-0.5 text-muted">{detail.guideline}</p>
        </div>
      )}

      {detail.notes.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-faint">指令注释</p>
          {detail.notes.map((n, i) => (
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

      <div className="rounded-lg border border-line p-2.5">
        <p className="text-[11px] font-medium text-faint">编码层级</p>
        <div className="mt-1.5 space-y-1.5 text-[11px] leading-5">
          <RelRow label="上级" items={detail.parent ? [detail.parent] : []} onNavigate={onNavigate} />
          <RelRow label="同级" items={detail.siblings} onNavigate={onNavigate} />
          <RelRow label="下级" items={detail.children} onNavigate={onNavigate} />
        </div>
      </div>

      {detail.alternatives.length > 0 && (
        <div className="rounded-md border border-dashed border-line bg-surface/40 p-2">
          <p className="text-[11px] font-medium text-faint">鉴别诊断 · 易错对照</p>
          <div className="mt-1 space-y-0.5">
            {detail.alternatives.map((a, i) => (
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

function RelRow({
  label,
  items,
  onNavigate,
}: {
  label: string;
  items: RelatedCode[];
  onNavigate: (c: string) => void;
}) {
  return (
    <div className="flex gap-2">
      <span className="w-8 shrink-0 text-faint">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {items.length === 0 ? (
          <span className="text-faint">—</span>
        ) : (
          items.map((r) =>
            r.member ? (
              <button
                key={r.code}
                onClick={() => onNavigate(r.code)}
                className="rounded-md border border-teal-100 bg-teal-50 px-1.5 py-0.5 font-mono text-teal-600 hover:bg-teal-100"
              >
                {r.code}
                {r.display ? ` ${r.display}` : ""}
              </button>
            ) : (
              <span
                key={r.code}
                title="非样板编码 · 不可下钻"
                className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-faint"
              >
                {r.code}
              </span>
            ),
          )
        )}
      </div>
    </div>
  );
}
