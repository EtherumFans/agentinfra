import { useCallback, useState } from "react";
import { runAgent } from "../services/api";
import type { AgentRunResult } from "../types";
import { Card, CardBody } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Textarea } from "../components/ui/Textarea";
import { Spinner } from "../components/ui/Spinner";
import { ErrorState } from "../components/ui/ErrorState";
import { Markdown } from "../components/Markdown";

// AgentToolRun — the run surface for the Corti-style atomic *tool* agents (index navigation /
// code validation / compliance guardrail / document standardization). They run on the
// tool-calling executor and answer in prose Markdown: no structured billing codes, no
// evidence-highlight overlay (that's the extract surface), no compliance gate (that's
// coding-review). PHI is redacted server-side first; this is read-only research.

// The four tool agents take genuinely different inputs (a single term to navigate vs. a set
// of proposed codes vs. a raw colloquial narrative), so seed a fitting sample per agent.
const SAMPLES: Record<string, string> = {
  "icoder/icd-index-navigator-agent": `椎间盘突出
（可选上下文）患者腰痛伴左下肢放射痛，MRI 提示 L4/5 椎间盘向后突出。`,
  "icoder/code-validation-agent": `拟用编码：
I50.900 慢性心力衰竭
I10.x00 高血压
E11.900 2型糖尿病性
J18.900 肺炎

病历摘要：患者因气促、双下肢水肿入院，既往高血压、糖尿病史。
住院号：ZY20260613，联系电话：13800001111。`,
  "icoder/compliance-guardrail-agent": `拟用编码：
I50.900 慢性心力衰竭
Z51.102 维持性化疗
M80.900 骨质疏松伴病理性骨折

病历摘要：患者主诉乏力，门诊以心功能不全收入院；本次未见肿瘤相关记录。
患者姓名：张三，住院号：ZY20260613。`,
  "icoder/document-semantic-standardization-agent": `患者心衰、房颤好多年了，这次因为冠心病三支病变住院，
上了两个支架，住院期间还做了拍片和抽血化验。既往有糖尿，血压高。
患者姓名：李四，住院号：ZY20260614，联系电话：13900002222。`,
};

const FALLBACK_SAMPLE = `主要诊断：慢性心力衰竭，心功能Ⅲ级。
其他诊断：高血压病，2型糖尿病。
患者姓名：张三，住院号：ZY20260613，联系电话：13800001111。`;

export function AgentToolRun({ token, agentId }: { token: string; agentId: string }) {
  const [text, setText] = useState(SAMPLES[agentId] ?? FALLBACK_SAMPLE);
  const [result, setResult] = useState<AgentRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      setResult(await runAgent(token, agentId, text));
    } catch (e) {
      setError(e);
    } finally {
      setRunning(false);
    }
  }, [token, agentId, text]);

  return (
    <div className="space-y-5">
      <Card>
        <CardBody>
          <div className="flex items-center justify-between">
            <h3 id="tool-doc-heading" className="text-sm font-semibold text-ink">
              输入文本 · 工具型 Agent 研判
            </h3>
            <span className="text-xs text-faint">散文研究报告 · 不产生结构化计费编码</span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            该 Agent 在 LLM 工具调用执行器上自主研究并产出散文 Markdown 报告；PHI 在服务端本地脱敏，
            <span className="text-ink">数据不出院</span>。需配置外部 LLM，未配置将返回 503。
          </p>
          <Textarea
            aria-labelledby="tool-doc-heading"
            className="mt-3 h-44"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="mt-3 flex items-center gap-3">
            <Button onClick={run} disabled={running || !text.trim()}>
              {running ? "研判中…" : "运行 Agent"}
            </Button>
            {running ? (
              <span className="flex items-center gap-2 text-xs text-muted">
                <Spinner /> 正在脱敏并研判…
              </span>
            ) : (
              <span className="text-xs text-faint">
                只读：不创建运行、不写回、不产生计费编码，结论交人工复核。
              </span>
            )}
          </div>
        </CardBody>
      </Card>

      {error ? <ErrorState error={error} onRetry={run} /> : null}

      {result && (
        <>
          <RedactionSummary redaction={result.redaction} />

          <Card>
            <CardBody>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
                  研究报告
                </h3>
                <span className="font-mono text-[11px] tabular-nums text-faint">
                  {result.provider}
                </span>
              </div>
              <div className="mt-3">
                {result.report ? (
                  <Markdown source={result.report} />
                ) : (
                  <p className="text-sm text-faint">
                    模型未产出散文报告（可能仅调用工具后停止）。请查看下方工具调用时间线。
                  </p>
                )}
              </div>
            </CardBody>
          </Card>

          <StageTimeline stages={result.stages} />
        </>
      )}
    </div>
  );
}

function RedactionSummary({
  redaction,
}: {
  redaction: AgentRunResult["redaction"];
}) {
  const { spans, by_type } = redaction;
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
          PHI 在服务端就地脱敏，模型仅见去标识化文本；原始标识符不回传、不渲染。
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

function StageTimeline({ stages }: { stages: AgentRunResult["stages"] }) {
  return (
    <Card>
      <CardBody>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-faint">
            工具调用时间线
          </h3>
          <span className="font-mono text-[11px] tabular-nums text-faint">
            {stages.length} 步
          </span>
        </div>
        {stages.length ? (
          <ol className="mt-3 space-y-1.5">
            {stages.map((s, i) => (
              <li
                key={s.tool_run_id || i}
                className="flex items-center justify-between gap-3 rounded-lg border border-line px-2.5 py-1.5"
              >
                <span className="flex items-center gap-2 text-sm text-ink">
                  <span className="font-mono text-[11px] text-faint">{i + 1}</span>
                  <span className="font-mono text-xs text-teal-600">{s.tool}</span>
                  <span className="text-xs text-muted">{s.summary}</span>
                </span>
                <span className="font-mono text-[11px] tabular-nums text-faint">
                  {s.duration_ms.toFixed(0)} ms
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-3 text-sm text-faint">无工具调用。</p>
        )}
      </CardBody>
    </Card>
  );
}
