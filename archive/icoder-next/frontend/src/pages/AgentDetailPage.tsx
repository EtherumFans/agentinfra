import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { getAgentCard } from "../services/api";
import { useSession } from "../app/session";
import type { AgentCard } from "../types";
import { Card, CardBody } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Tabs } from "../components/ui/Tabs";
import { Textarea } from "../components/ui/Textarea";
import { CodeBlock, useBase } from "../components/ui/CodeBlock";
import { Spinner } from "../components/ui/Spinner";
import { ErrorState } from "../components/ui/ErrorState";
import { useEmbedded } from "./useEmbedded";
import { RunHistory } from "./RunHistory";
import { CodeLookup } from "./CodeLookup";
import { BatchReview } from "./BatchReview";
import { ComplianceRules } from "./ComplianceRules";
import { FactExtraction } from "./FactExtraction";
import { AgentToolRun } from "./AgentToolRun";

const SAMPLE = `主要诊断：慢性心力衰竭，心功能Ⅲ级。
其他诊断：高血压病，2型糖尿病，慢性肾脏病，心房颤动。
手术操作：胃镜检查及活检。
影像学：X线提示骨质疏松伴病理性骨折。
患者姓名：张三，住院号：ZY20260613，联系电话：13800001111。`;

const TABS = [
  { id: "try", label: "试用" },
  { id: "batch", label: "批量" },
  { id: "history", label: "运行历史" },
  { id: "lookup", label: "编码查询" },
  { id: "rules", label: "合规规则" },
  { id: "settings", label: "设置" },
  { id: "code", label: "代码" },
];

// The extract surface is a pure fact/abstraction agent: no run history, no batch, no
// compliance rules, no code lookup — those are coding-review concepts. It collapses to
// try / settings / code, branched on card["x-icoder"].surface (not a hardcoded id).
const EXTRACT_TABS = [
  { id: "try", label: "试用" },
  { id: "settings", label: "设置" },
  { id: "code", label: "代码" },
];

// The tool surface (Corti-style atomic agents answering in prose) is likewise standalone:
// no run history / batch / rules / lookup. Same try / settings / code collapse as extract.
const TOOL_TABS = EXTRACT_TABS;

function Overview({ card }: { card: AgentCard }) {
  const x = card["x-icoder"];
  return (
    <Card>
      <CardBody>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-ink">{card.name}</h1>
            <p className="mt-1 font-mono text-xs text-faint">
              {card.id} · v{card.version}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge tone="teal">{x.deployment}</Badge>
            <Badge tone="teal">{x.data_residency}</Badge>
            {x.production_writeback_blocked && <Badge tone="warn">生产写回已锁</Badge>}
          </div>
        </div>

        <p className="mt-4 text-[15px] leading-relaxed text-muted">{card.description}</p>

        <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-3">
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-faint">能力</h4>
            <ul className="mt-2 space-y-1 text-sm text-ink">
              <li>{card.capabilities.evidenceLinked ? "✓" : "—"} 证据回链</li>
              <li>{card.capabilities.humanInTheLoop ? "✓" : "—"} 人工复核</li>
              <li>{card.capabilities.streaming ? "✓" : "—"} 流式输出</li>
            </ul>
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-faint">技能 / 专家</h4>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {card.skills.map((s) => (
                <span key={s.id} className="rounded-md bg-surface px-2 py-0.5 text-xs text-muted">
                  {s.id}
                </span>
              ))}
            </div>
            <h4 className="mt-3 text-xs font-semibold uppercase tracking-wide text-faint">编码体系</h4>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {x.coding_systems.map((c) => (
                <Badge key={c}>{c}</Badge>
              ))}
            </div>
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-faint">非目标</h4>
            <ul className="mt-2 space-y-1 text-sm text-muted">
              {card.nonGoals.map((g) => (
                <li key={g}>· {g}</li>
              ))}
            </ul>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function TryIt({
  card,
  codingSystem,
}: {
  card: AgentCard;
  codingSystem: string;
}) {
  const { token, role } = useSession();
  const { ref, events, run, clearEvents, running } = useEmbedded(token, card.id, codingSystem);
  const [text, setText] = useState(SAMPLE);

  return (
    <div className="space-y-5">
      <Card>
        <CardBody>
          <div className="flex items-center justify-between">
            <h3 id="tryit-doc-heading" className="text-sm font-semibold text-ink">病历文本（去标识化前 · PHI 在服务端脱敏）</h3>
            <span className="text-xs text-faint">
              身份 <span className="font-mono text-muted">demo:{role}</span> · 体系 {codingSystem}
            </span>
          </div>
          <Textarea
            aria-labelledby="tryit-doc-heading"
            className="mt-3 h-44"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="mt-3 flex items-center gap-3">
            <Button onClick={() => run(text)} disabled={running}>
              {running ? "运行中…" : "运行编码审核"}
            </Button>
            {running ? (
              <span className="flex items-center gap-2 text-xs text-muted">
                <Spinner /> 正在执行 7 阶段管线 · 约 30–40 秒
              </span>
            ) : (
              <span className="text-xs text-faint">
                {role === "reviewer" ? "reviewer 仅可查看；人工复核（采纳候选）将返回 403。" : "可在结果中采纳候选编码并提交人工复核。"}
              </span>
            )}
          </div>
        </CardBody>
      </Card>

      {/* The vanilla widget renders evidence highlight + code cards + compliance gate + DRG route. */}
      <Card>
        <CardBody>
          <icoder-embedded ref={ref} base-url="" />
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">embedded-event 事件总线</h3>
            <Button variant="ghost" size="sm" onClick={clearEvents}>
              清空
            </Button>
          </div>
          <div
            tabIndex={0}
            role="log"
            aria-label="嵌入事件日志"
            className="mt-3 max-h-48 overflow-auto rounded-lg bg-[#0f1722] p-3 font-mono text-xs leading-6 text-[#cfe9e4]"
          >
            {events.length === 0 ? (
              <span className="text-[#76889c]">运行后，ready / auth / run.completed / rule-gate-triggered 等事件将在此显示…</span>
            ) : (
              events.map((ev, i) => (
                <div key={i}>
                  <span className="text-[#7fd7c9]">{ev.type}</span>{" "}
                  <span className="text-[#76889c]">{JSON.stringify(ev.payload)}</span>
                </div>
              ))
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function Settings({
  codingSystem,
  setCodingSystem,
  card,
}: {
  codingSystem: string;
  setCodingSystem: (s: string) => void;
  card: AgentCard;
}) {
  return (
    <Card>
      <CardBody className="space-y-5">
        <div>
          <label htmlFor="settings-coding-system" className="text-xs font-semibold uppercase tracking-wide text-faint">编码体系</label>
          <select
            id="settings-coding-system"
            value={codingSystem}
            onChange={(e) => setCodingSystem(e.target.value)}
            className="mt-2 block w-full max-w-xs rounded-lg border border-line bg-panel px-3 py-2 text-sm text-ink focus-visible:border-teal"
          >
            {card["x-icoder"].coding_systems.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <p className="mt-2 text-xs text-muted">
            注入 <span className="font-mono">configure(&#123; codingSystem &#125;)</span>，下次运行生效。
          </p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">智能体 ID</label>
          <p className="mt-2 font-mono text-sm text-ink">{card.id}</p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">运行端点</label>
          <p className="mt-2 font-mono text-sm text-ink">{card.endpoints.run}</p>
        </div>
        <div className="border-t border-line pt-4">
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">鉴权</label>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            <span className="font-mono text-ink">Authorization: Bearer demo:&lt;role&gt;</span>，role ∈{" "}
            <span className="font-mono text-ink">coder / reviewer / admin</span>。复核人角色从令牌注入，不取自请求体；
            人工复核需 coder 或 admin，reviewer 调用返回 403。生产由宿主（SSO / HIS）签发短时令牌。
          </p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">合规门禁</label>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            每次运行在服务端评估合规规则集，结果回填{" "}
            <span className="font-mono text-ink">compliance.passed</span> /{" "}
            <span className="font-mono text-ink">human_review_required</span> /{" "}
            <span className="font-mono text-ink">hits[]</span>（命中规则 id、严重度、定位编码）。
            生产写回{card["x-icoder"].production_writeback_blocked ? "已锁（样板阶段硬约束）" : "开放"}。
          </p>
        </div>
      </CardBody>
    </Card>
  );
}

function CodeTab({ card, surface }: { card: AgentCard; surface: string }) {
  const { token } = useSession();
  const base = useBase();
  const snippets = useMemo(() => {
    const id = card.id;
    type Snippet = { lang: string; code: string };
    if (surface === "extract") {
      // The extract surface is REST-only (no embed widget): one endpoint, configurable
      // LLM behind it. Snippets target /api/coding/extract with the agent id.
      const out: Record<string, Snippet> = {
        curl: {
          lang: "bash",
          code: `curl -X POST ${base}/api/coding/extract \\
  -H "Authorization: Bearer ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "主要诊断：慢性心力衰竭，心功能Ⅲ级。其他诊断：2型糖尿病。",
    "agent_id": "${id}"
  }'`,
        },
        Python: {
          lang: "python",
          code: `import requests

# 院内同源部署：宿主进程同时服务 SPA 与 API；token 由宿主（SSO / HIS）签发。
resp = requests.post(
    "${base}/api/coding/extract",
    headers={"Authorization": "Bearer ${token}"},
    json={
        "text": "主要诊断：慢性心力衰竭，心功能Ⅲ级。其他诊断：2型糖尿病。",
        "agent_id": "${id}",
    },
    timeout=60,
)
resp.raise_for_status()
out = resp.json()
print("provider:", out["provider"], "· 脱敏", out["redaction"]["spans"], "处 PHI")
for e in out["entities"]:
    spans = ", ".join(f"[{ev['start']},{ev['end']})" for ev in e["evidences"])
    print(e["term"], e["category"], "证据", spans)`,
        },
        "Agent Card": {
          lang: "json",
          code: JSON.stringify(card, null, 2),
        },
      };
      return out;
    }
    if (surface === "tool") {
      // Tool agents are REST-only (no embed widget): one endpoint, an external LLM behind
      // it (no deterministic fallback — no key returns 503). Body is just text; the response
      // is a prose `report` plus the tool-call `stages` timeline.
      const out: Record<string, Snippet> = {
        curl: {
          lang: "bash",
          code: `curl -X POST ${base}/api/agents/${id}/run \\
  -H "Authorization: Bearer ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "拟用编码：I50.900 慢性心力衰竭；E11.900 2型糖尿病。病历：患者因气促入院。"
  }'`,
        },
        Python: {
          lang: "python",
          code: `import requests

# 院内同源部署：宿主进程同时服务 SPA 与 API；token 由宿主（SSO / HIS）签发。
# 工具型 Agent 必须配置外部 LLM；未配置返回 503 llm_credential_missing。
resp = requests.post(
    "${base}/api/agents/${id}/run",
    headers={"Authorization": "Bearer ${token}"},
    json={"text": "拟用编码：I50.900 慢性心力衰竭；E11.900 2型糖尿病。病历：患者因气促入院。"},
    timeout=120,
)
resp.raise_for_status()
out = resp.json()
print("provider:", out["provider"], "· 脱敏", out["redaction"]["spans"], "处 PHI")
print(out["report"])            # 散文 Markdown 研究报告
for s in out["stages"]:         # 工具调用时间线
    print(s["tool"], s["summary"], f"{s['duration_ms']:.0f}ms")`,
        },
        "Agent Card": {
          lang: "json",
          code: JSON.stringify(card, null, 2),
        },
      };
      return out;
    }
    const out: Record<string, Snippet> = {
      curl: {
        lang: "bash",
        code: `curl -X POST ${base}/api/coding-review/run \\
  -H "Authorization: Bearer ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "主要诊断：慢性心力衰竭，心功能Ⅲ级。其他诊断：2型糖尿病。",
    "coding_system": "ICD-10-CN",
    "agent_id": "${id}"
  }'`,
      },
      Python: {
        lang: "python",
        code: `import requests

# 院内同源部署：宿主进程同时服务 SPA 与 API；token 由宿主（SSO / HIS）签发。
resp = requests.post(
    "${base}/api/coding-review/run",
    headers={"Authorization": "Bearer ${token}"},
    json={
        "text": "主要诊断：慢性心力衰竭，心功能Ⅲ级。其他诊断：2型糖尿病。",
        "coding_system": "ICD-10-CN",
        "agent_id": "${id}",
    },
    timeout=60,
)
resp.raise_for_status()
run = resp.json()
for c in run["codes"]:
    spans = ", ".join(f"[{e['start']},{e['end']})" for e in c["evidences"])
    print(c["code"], c["display"], "证据", spans)`,
      },
      HTML: {
        lang: "html",
        code: `<script src="${base}/icoder-embedded.js"></script>
<icoder-embedded id="w" base-url="${base}"></icoder-embedded>
<script>
  const w = document.getElementById('w');
  w.configureSession({ token: HOST_ISSUED_TOKEN });   // 宿主负责鉴权
  w.configure({ agentId: '${id}', codingSystem: 'ICD-10-CN' });
  w.addEventListener('embedded-event', e => handle(e.detail));
  w.run(deidentifiedOrRawClinicalText);
</script>`,
      },
      React: {
        lang: "tsx",
        code: `import { useEffect, useRef } from 'react';
import 'icoder-embedded';   // 注册自定义元素

export function CodingReview({ token, text }) {
  const ref = useRef(null);
  useEffect(() => {
    const w = ref.current;
    w.configureSession({ token });
    w.configure({ agentId: '${id}', codingSystem: 'ICD-10-CN' });
    const on = e => console.log(e.detail.type, e.detail.payload);
    w.addEventListener('embedded-event', on);
    return () => w.removeEventListener('embedded-event', on);
  }, [token]);
  return <icoder-embedded ref={ref} base-url="${base}" />;
}`,
      },
      "Agent Card": {
        lang: "json",
        code: JSON.stringify(card, null, 2),
      },
    };
    return out;
  }, [card, base, token, surface]);

  const keys = Object.keys(snippets);
  const [fmt, setFmt] = useState<string>(keys[0]);
  const activeKey = snippets[fmt] ? fmt : keys[0];
  const active = snippets[activeKey];

  return (
    <Card>
      <CardBody className="space-y-3">
        <Tabs
          items={keys.map((k) => ({ id: k, label: k }))}
          active={activeKey}
          onChange={(id) => setFmt(id)}
        />
        <p className="text-xs leading-relaxed text-muted">
          {surface === "extract" ? (
            <>
              curl / Python 直连 REST，示例用当前登录身份{" "}
              <span className="font-mono text-ink">{token}</span> 可直接运行；返回{" "}
              <span className="font-mono text-ink">provider</span> /{" "}
              <span className="font-mono text-ink">redaction</span> /{" "}
              <span className="font-mono text-ink">entities[]</span>（带服务端锚定的证据偏移）。
            </>
          ) : surface === "tool" ? (
            <>
              curl / Python 直连 REST，示例用当前登录身份{" "}
              <span className="font-mono text-ink">{token}</span> 可直接运行；返回{" "}
              <span className="font-mono text-ink">provider</span> /{" "}
              <span className="font-mono text-ink">redaction</span> /{" "}
              <span className="font-mono text-ink">report</span>（散文）/{" "}
              <span className="font-mono text-ink">stages[]</span>（工具调用时间线）。需配置外部 LLM。
            </>
          ) : (
            <>
              curl / Python 直连 REST，示例用当前登录身份{" "}
              <span className="font-mono text-ink">{token}</span> 可直接运行；HTML / React
              为 <span className="font-mono text-ink">&lt;icoder-embedded&gt;</span> 嵌入，生产由宿主签发短时令牌。
            </>
          )}
        </p>
        <CodeBlock lang={active.lang} code={active.code} />
      </CardBody>
    </Card>
  );
}

// Extract-surface settings: no codingSystem (extract takes none), no compliance gate
// (pure abstraction layer). Foregrounds the configurable-LLM story — the hospital can
// point ICODER_LLM_BASE_URL at an in-house OpenAI-compatible model, PHI never leaves.
function ExtractSettings({ card }: { card: AgentCard }) {
  return (
    <Card>
      <CardBody className="space-y-5">
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">智能体 ID</label>
          <p className="mt-2 font-mono text-sm text-ink">{card.id}</p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">运行端点</label>
          <p className="mt-2 font-mono text-sm text-ink">{card.endpoints.run}</p>
        </div>
        <div className="border-t border-line pt-4">
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">LLM 连接 · 可配置</label>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            配置外部 LLM（<span className="font-mono text-ink">ICODER_LLM_BASE_URL</span> /{" "}
            <span className="font-mono text-ink">ICODER_LLM_MODEL</span> /{" "}
            <span className="font-mono text-ink">ICODER_CREDENTIAL_LLM</span>）时，由工具调用执行器驱动抽取；
            未配置时回退本地确定性抽取。端点可指向
            <span className="text-ink">院内自建的 OpenAI 兼容模型</span>，去标识文本不出院；产品不绑定任何单一厂商。
          </p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">鉴权</label>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            <span className="font-mono text-ink">Authorization: Bearer demo:&lt;role&gt;</span>，role ∈{" "}
            <span className="font-mono text-ink">coder / reviewer / admin</span>。生产由宿主（SSO / HIS）签发短时令牌。
          </p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">边界</label>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            纯事实 / 抽象层：只输出带证据锚点的结构化临床事实，
            <span className="text-ink">不出计费编码、无合规门禁、不写回</span>。字符偏移恒在服务端锚定，不取自模型。
          </p>
        </div>
      </CardBody>
    </Card>
  );
}

// Tool-surface settings: like extract (no codingSystem, no compliance gate) but the LLM is
// MANDATORY — prose synthesis has no deterministic fallback, so no key returns a clean 503.
function ToolSettings({ card }: { card: AgentCard }) {
  return (
    <Card>
      <CardBody className="space-y-5">
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">智能体 ID</label>
          <p className="mt-2 font-mono text-sm text-ink">{card.id}</p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">运行端点</label>
          <p className="mt-2 font-mono text-sm text-ink">{card.endpoints.run}</p>
        </div>
        <div className="border-t border-line pt-4">
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">LLM 连接 · 必需且可配置</label>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            工具型 Agent <span className="text-ink">必须</span>配置外部 LLM（
            <span className="font-mono text-ink">ICODER_LLM_BASE_URL</span> /{" "}
            <span className="font-mono text-ink">ICODER_LLM_MODEL</span> /{" "}
            <span className="font-mono text-ink">ICODER_CREDENTIAL_LLM</span>）：模型在工具调用执行器上自主研判并产出散文报告，
            <span className="text-ink">没有本地确定性兜底</span>，未配置时返回{" "}
            <span className="font-mono text-ink">503 llm_credential_missing</span>。端点可指向
            <span className="text-ink">院内自建的 OpenAI 兼容模型</span>，去标识文本不出院；产品不绑定任何单一厂商。
          </p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">鉴权</label>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            <span className="font-mono text-ink">Authorization: Bearer demo:&lt;role&gt;</span>，role ∈{" "}
            <span className="font-mono text-ink">coder / reviewer / admin</span>。生产由宿主（SSO / HIS）签发短时令牌。
          </p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">边界</label>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            咨询 / 研究式工具层：产出<span className="text-ink">散文 Markdown 研究报告</span>，
            <span className="text-ink">不出结构化计费编码、不替代确定性合规闸门、不写回</span>，结论交人工复核。
            PHI 在服务端就地脱敏，模型仅见去标识文本。
          </p>
        </div>
      </CardBody>
    </Card>
  );
}

export function AgentDetailPage() {
  const params = useParams();
  const agentId = params["*"] || "";
  const { token } = useSession();
  const [card, setCard] = useState<AgentCard | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState("try");
  const [codingSystem, setCodingSystem] = useState("ICD-10-CN");
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setCard(null);
    setError(null);
    getAgentCard(agentId, token)
      .then((c) => alive && setCard(c))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, [agentId, token, nonce]);

  // The component stays mounted across /agents/* param changes, so tab state would leak
  // between agents — and the extract vs. coding-review surfaces have different tab sets.
  // Reset to the first tab whenever we navigate to a different agent.
  useEffect(() => {
    setTab("try");
  }, [agentId]);

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  if (error) {
    return <ErrorState error={error} onRetry={retry} />;
  }

  if (!card) {
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-muted">
        <Spinner /> 正在加载智能体…
      </div>
    );
  }

  // Declarative surface branch (no hardcoded agent ids): extract agents have no rule sets
  // (x-icoder.surface === "extract"); tool agents are the Corti-style atomic prose agents
  // (surface === "tool"); everything else is the full coding-review pipeline.
  const surface = card["x-icoder"].surface ?? "coding-review";
  const isExtract = surface === "extract";
  const isTool = surface === "tool";
  const isReview = !isExtract && !isTool;
  const tabs = isTool ? TOOL_TABS : isExtract ? EXTRACT_TABS : TABS;

  return (
    <div className="space-y-6 animate-rise">
      <Overview card={card} />
      <Tabs items={tabs} active={tab} onChange={setTab} idBase="detail" />
      <div role="tabpanel" id={`detail-panel-${tab}`} aria-labelledby={`detail-tab-${tab}`}>
        {tab === "try" &&
          (isTool ? (
            <AgentToolRun token={token} agentId={card.id} />
          ) : isExtract ? (
            <FactExtraction token={token} agentId={card.id} />
          ) : (
            <TryIt card={card} codingSystem={codingSystem} />
          ))}
        {isReview && tab === "batch" && (
          <BatchReview agentId={card.id} token={token} codingSystem={codingSystem} />
        )}
        {isReview && tab === "history" && <RunHistory agentId={card.id} token={token} />}
        {isReview && tab === "lookup" && <CodeLookup token={token} />}
        {isReview && tab === "rules" && <ComplianceRules agentId={card.id} token={token} />}
        {tab === "settings" &&
          (isTool ? (
            <ToolSettings card={card} />
          ) : isExtract ? (
            <ExtractSettings card={card} />
          ) : (
            <Settings card={card} codingSystem={codingSystem} setCodingSystem={setCodingSystem} />
          ))}
        {tab === "code" && <CodeTab card={card} surface={surface} />}
      </div>
    </div>
  );
}
