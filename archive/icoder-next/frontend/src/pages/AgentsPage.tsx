import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { listAgents, listRuns } from "../services/api";
import { useSession } from "../app/session";
import type { AgentSummary, RunSummary } from "../types";
import { Card, CardBody } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Spinner } from "../components/ui/Spinner";
import { ErrorState } from "../components/ui/ErrorState";
import { EmptyState } from "../components/ui/EmptyState";

function Hero() {
  return (
    <section className="mb-10">
      <h1 className="max-w-2xl text-3xl font-semibold leading-tight tracking-tight text-ink sm:text-4xl">
        中国医学编码与收入合规，<span className="text-teal">在院内闭环</span>。
      </h1>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted">
        预置编码审核智能体，证据回链到病历原文、ICD-10-CN / ICD-9-CM-3 双体系、DRG/DIP 分组与合规门禁。
        数据不出院，可嵌入 HIS / EMR。
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Badge tone="teal">数据不出院 · on-prem</Badge>
        <Badge>证据回链</Badge>
        <Badge>人工复核 · 审计</Badge>
      </div>
    </section>
  );
}

function AgentCardItem({ agent, index }: { agent: AgentSummary; index: number }) {
  return (
    <Link
      to={`/agents/${agent.id}`}
      className="group block animate-rise"
      style={{ animationDelay: `${index * 40}ms` }}
    >
      <Card className="h-full transition-shadow duration-base group-hover:shadow-lift">
        <CardBody className="flex h-full flex-col">
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-[15px] font-semibold text-ink">{agent.name}</h3>
            <Badge tone="teal" className="shrink-0">
              {agent.category}
            </Badge>
          </div>
          <p className="mt-1 font-mono text-xs text-faint">{agent.id}</p>
          <div className="mt-auto pt-4">
            <div className="flex flex-wrap gap-1.5">
              {agent.experts.map((e) => (
                <span key={e} className="rounded-md bg-surface px-2 py-0.5 text-xs text-muted">
                  {e}
                </span>
              ))}
            </div>
            <p className="mt-3 text-xs font-medium text-teal opacity-0 transition-opacity duration-base group-hover:opacity-100">
              打开并试用 →
            </p>
          </div>
        </CardBody>
      </Card>
    </Link>
  );
}

function pct(n: number, d: number): string {
  return d === 0 ? "—" : `${Math.round((n / d) * 100)}%`;
}

function AdminStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardBody className="py-3">
        <p className="text-xs text-faint">{label}</p>
        <p className="mt-1 text-xl font-semibold tracking-tight text-ink">{value}</p>
        {hint && <p className="mt-0.5 text-[11px] text-faint">{hint}</p>}
      </CardBody>
    </Card>
  );
}

// Admin-only platform pulse. The slice has no persistent nav / no Manage destination
// (locked IA decision), so the cross-agent operational glance an admin/QC lead needs
// lives inline on the home page, gated on the host-injected role. It reuses the existing
// /runs endpoint (agent_id omitted → all agents) — no new route, no backend change.
function AdminOverview({ token, agents }: { token: string; agents: AgentSummary[] }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setRuns(null);
    setError(null);
    listRuns(token, { limit: 1000 })
      .then((r) => alive && setRuns(r))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, [token, nonce]);

  const nameOf = useMemo(() => {
    const m = new Map(agents.map((a) => [a.id, a.name]));
    return (id: string) => m.get(id) ?? id;
  }, [agents]);

  const stats = useMemo(() => {
    if (!runs) return null;
    const total = runs.length;
    const passed = runs.filter((r) => r.passed === 1).length;
    const review = runs.filter((r) => r.human_review_required === 1).length;
    const reviewed = runs.filter((r) => r.reviewed === 1).length;
    const pending = runs.filter((r) => r.human_review_required === 1 && r.reviewed !== 1).length;
    const byAgent = new Map<string, { total: number; passed: number; pending: number }>();
    for (const r of runs) {
      const a = byAgent.get(r.agent_id) ?? { total: 0, passed: 0, pending: 0 };
      a.total += 1;
      if (r.passed === 1) a.passed += 1;
      if (r.human_review_required === 1 && r.reviewed !== 1) a.pending += 1;
      byAgent.set(r.agent_id, a);
    }
    const rows = [...byAgent.entries()]
      .map(([id, v]) => ({ id, ...v }))
      .sort((x, y) => y.total - x.total);
    return { total, passed, review, reviewed, pending, rows };
  }, [runs]);

  return (
    <section className="mb-10">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">平台运行概览</h2>
        <span className="text-xs text-faint">admin · 全部智能体</span>
      </div>

      {error ? (
        <ErrorState error={error} onRetry={() => setNonce((n) => n + 1)} />
      ) : !stats ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted">
          <Spinner /> 正在汇总运行指标…
        </div>
      ) : stats.total === 0 ? (
        <EmptyState
          title="暂无运行数据"
          hint="任一智能体跑过编码审核后，平台级用量与门禁/复核指标将在此聚合。"
        />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <AdminStat label="运行总数" value={String(stats.total)} />
            <AdminStat
              label="门禁通过率"
              value={pct(stats.passed, stats.total)}
              hint={`${stats.passed}/${stats.total} 通过`}
            />
            <AdminStat
              label="需人工复核率"
              value={pct(stats.review, stats.total)}
              hint={`待复核 ${stats.pending}`}
            />
            <AdminStat label="已复核" value={`${stats.reviewed}/${stats.total}`} />
          </div>

          {stats.rows.length > 1 && (
            <Card>
              <CardBody className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[32rem] text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-xs text-faint">
                      <th className="px-4 py-2.5 font-medium">智能体</th>
                      <th className="px-4 py-2.5 font-medium">运行数</th>
                      <th className="px-4 py-2.5 font-medium">门禁通过率</th>
                      <th className="px-4 py-2.5 font-medium">待复核</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.rows.map((a) => (
                      <tr key={a.id} className="border-b border-line/60 last:border-0">
                        <td className="px-4 py-2.5">
                          <Link to={`/agents/${a.id}`} className="text-ink hover:text-teal">
                            {nameOf(a.id)}
                          </Link>
                          <span className="ml-2 font-mono text-xs text-faint">{a.id}</span>
                        </td>
                        <td className="px-4 py-2.5 font-mono text-muted">{a.total}</td>
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface">
                              <div
                                className="h-full rounded-full bg-teal"
                                style={{ width: pct(a.passed, a.total) }}
                              />
                            </div>
                            <span className="font-mono text-xs text-muted">
                              {pct(a.passed, a.total)}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5">
                          {a.pending > 0 ? (
                            <Badge tone="warn">{a.pending}</Badge>
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
          )}
        </div>
      )}
    </section>
  );
}

export function AgentsPage() {
  const { token, role } = useSession();
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setAgents(null);
    setError(null);
    listAgents(token)
      .then((a) => alive && setAgents(a))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, [token, nonce]);

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  return (
    <>
      <Hero />
      {role === "admin" && <AdminOverview token={token} agents={agents ?? []} />}
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">智能体</h2>
        {agents && <span className="text-xs text-faint">{agents.length} 个可用</span>}
      </div>

      {error && <ErrorState error={error} onRetry={retry} />}

      {!agents && !error && (
        <div className="flex items-center gap-2 py-10 text-sm text-muted">
          <Spinner /> 正在加载智能体…
        </div>
      )}

      {agents && agents.length === 0 && (
        <EmptyState
          title="暂无可用智能体"
          hint="此运行时尚未注册任何智能体。安装或发布一个 .icoder-agent 包后将在此显示。"
        />
      )}

      {agents && agents.length > 0 && (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((a, i) => (
            <AgentCardItem key={a.id} agent={a} index={i} />
          ))}
        </div>
      )}
    </>
  );
}
