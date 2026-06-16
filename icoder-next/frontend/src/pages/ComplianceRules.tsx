import { useCallback, useEffect, useState } from "react";
import { getRuleSets } from "../services/api";
import type { RuleSetInfo, RuleSetsResponse } from "../types";
import { Card, CardBody } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Spinner } from "../components/ui/Spinner";
import { ErrorState } from "../components/ui/ErrorState";
import { cn } from "../design/cn";

// Read-only catalog of the compliance gate's rule domains — the iCoDer analog of Corti
// surfacing its rule/guideline definitions. Shows all four wired domains (编码→分组→结算→
// 病历) but marks which this agent enforces, so a coder sees both what gates them now and
// the platform's compliance breadth. Pure metadata: no run, no writeback.

const sevClass: Record<string, string> = {
  Critical: "text-red-700 font-semibold dark:text-red-300",
  Moderate: "text-amber-700 dark:text-amber-300",
  Informational: "text-faint",
};

export function ComplianceRules({ agentId, token }: { agentId: string; token: string }) {
  const [data, setData] = useState<RuleSetsResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    getRuleSets(token, agentId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, [agentId, token, nonce]);

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  if (error) return <ErrorState error={error} onRetry={retry} />;
  if (!data) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-muted">
        <Spinner /> 正在加载合规规则集…
      </div>
    );
  }

  const enforcedCount = data.rule_sets.filter((r) => r.enforced).length;

  return (
    <div className="space-y-4">
      <Card>
        <CardBody>
          <h3 className="text-sm font-semibold text-ink">合规门禁规则集</h3>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            每次运行在服务端评估下列规则域，并折叠为单一门禁。本智能体启用{" "}
            <span className="font-mono text-ink">
              {enforcedCount}/{data.rule_sets.length}
            </span>{" "}
            个合规域。
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-line p-2.5">
              <p className="text-[11px] font-medium text-faint">通过条件</p>
              <p className="mt-0.5 text-xs text-muted">{data.gate_policy.passed}</p>
            </div>
            <div className="rounded-lg border border-line p-2.5">
              <p className="text-[11px] font-medium text-faint">人工复核条件</p>
              <p className="mt-0.5 text-xs text-muted">{data.gate_policy.human_review_required}</p>
            </div>
          </div>
        </CardBody>
      </Card>

      {data.rule_sets.map((rs) => (
        <RuleSetCard key={rs.rule_set} rs={rs} />
      ))}
    </div>
  );
}

function RuleSetCard({ rs }: { rs: RuleSetInfo }) {
  return (
    <Card>
      <CardBody className={cn(!rs.enforced && "opacity-70")}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-ink">{rs.label}</h3>
            <p className="mt-0.5 font-mono text-xs text-faint">
              {rs.rule_set} · {rs.version}
            </p>
          </div>
          {rs.enforced ? <Badge tone="teal">本智能体启用</Badge> : <Badge>未启用</Badge>}
        </div>

        <ul className="mt-3 divide-y divide-line/60">
          {rs.rules.map((r) => (
            <li key={r.rule_id} className="py-2.5 first:pt-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-semibold text-ink">{r.rule_id}</span>
                <span className={cn("text-[11px]", sevClass[r.severity] ?? "text-muted")}>
                  [{r.severity}]
                </span>
                <span className="text-sm text-ink">{r.title}</span>
              </div>
              <p className="mt-0.5 text-xs leading-5 text-muted">{r.intent}</p>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}
