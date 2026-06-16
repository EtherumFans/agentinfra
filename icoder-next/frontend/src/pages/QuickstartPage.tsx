import { useMemo } from "react";
import { useSession } from "../app/session";
import { Card, CardBody } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { CodeBlock, useBase } from "../components/ui/CodeBlock";

function Step({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-center gap-3">
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-teal-600 text-xs font-semibold text-white dark:bg-teal dark:text-canvas">
            {n}
          </span>
          <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
        </div>
        {children}
      </CardBody>
    </Card>
  );
}

export function QuickstartPage() {
  const { token, role } = useSession();
  const base = useBase();

  const snip = useMemo(
    () => ({
      list: `curl ${base}/agents \\
  -H "Authorization: Bearer ${token}"`,
      run: `curl -X POST ${base}/api/coding-review/run \\
  -H "Authorization: Bearer ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "text": "主要诊断：慢性心力衰竭，心功能Ⅲ级。其他诊断：2型糖尿病。",
    "coding_system": "ICD-10-CN",
    "agent_id": "icoder/homepage-coding-review-agent"
  }'`,
      review: `curl -X POST ${base}/api/coding-review/<run_id>/human-review \\
  -H "Authorization: Bearer ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{"decision": "accept", "code": "M80.900"}'`,
      report: `curl "${base}/api/coding-review/<run_id>/report?format=html" \\
  -H "Authorization: Bearer ${token}" -o report.html`,
      embed: `<script src="${base}/icoder-embedded.js"></script>
<icoder-embedded id="w" base-url="${base}"></icoder-embedded>
<script>
  const w = document.getElementById('w');
  w.configureSession({ token: HOST_ISSUED_TOKEN }); // 宿主负责签发短时令牌
  w.configure({ agentId: 'icoder/homepage-coding-review-agent', codingSystem: 'ICD-10-CN' });
  w.addEventListener('embedded-event', (e) => console.log(e.detail.type, e.detail.payload));
  w.run(clinicalText); // PHI 在服务端脱敏，证据回链按字符偏移高亮
</script>`,
    }),
    [base, token],
  );

  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-rise">
      <section>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">开发者接入</h1>
        <p className="mt-3 text-[15px] leading-relaxed text-muted">
          iCoDer 以 API 为产品：同一套接口既驱动本控制台，也供 HIS / EMR
          集成与 ISV 二次开发。所有推理在院内闭环，数据不出院。下面用当前登录身份
          <span className="mx-1 font-mono text-ink">demo:{role}</span>
          演示一条最小接入链路，示例可直接复制运行。
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge tone="teal">数据不出院 · on-prem</Badge>
          <Badge>Bearer 鉴权</Badge>
          <Badge>Web Component 嵌入</Badge>
        </div>
      </section>

      <Step n={1} title="认证">
        <p className="text-sm leading-relaxed text-muted">
          每个请求携带 <span className="font-mono text-ink">Authorization: Bearer demo:&lt;role&gt;</span>，
          role ∈ <span className="font-mono text-ink">coder / reviewer / admin</span>。人工复核需
          coder 或 admin。生产环境由宿主（SSO / HIS）签发短时令牌，前端不持有长期密钥。
        </p>
        <CodeBlock lang="header" code={`Authorization: Bearer ${token}`} />
      </Step>

      <Step n={2} title="列出智能体">
        <p className="text-sm leading-relaxed text-muted">
          <span className="font-mono text-ink">GET /agents</span> 返回已注册的预置智能体（id / 名称 /
          类别 / 专家）。当前实例预置编码审核、DRG/DIP 分组校验、收入合规终审三个智能体。
        </p>
        <CodeBlock lang="bash" code={snip.list} />
      </Step>

      <Step n={3} title="运行编码审核">
        <p className="text-sm leading-relaxed text-muted">
          <span className="font-mono text-ink">POST /api/coding-review/run</span>{" "}
          提交病历文本，返回完整 <span className="font-mono text-ink">RunResult</span>。响应关键字段：
        </p>
        <ul className="space-y-1.5 text-sm text-muted">
          <li>
            <span className="font-mono text-ink">codes[]</span> — 确信、可计费的编码，含{" "}
            <span className="font-mono text-ink">evidences</span> 字符偏移{" "}
            <span className="font-mono text-ink">[start, end)</span>（回链病历原文）
          </li>
          <li>
            <span className="font-mono text-ink">candidates[]</span> — 需人工复核，不与 codes 合并
          </li>
          <li>
            <span className="font-mono text-ink">compliance</span> — 门禁{" "}
            <span className="font-mono text-ink">passed</span> /{" "}
            <span className="font-mono text-ink">human_review_required</span> /{" "}
            <span className="font-mono text-ink">hits[]</span>
          </li>
          <li>
            <span className="font-mono text-ink">drg_route</span> — DRG/DIP 分组（adrg / drg / mdc /
            dip_code / dip_score）
          </li>
          <li>
            <span className="font-mono text-ink">stages[]</span> — 7 阶段工具编排（运行管线，可逐阶段追溯）
          </li>
          <li>
            <span className="font-mono text-ink">versions</span> — runtime / agent / ruleset /
            catalog / model 版本（报告与审计可追溯）
          </li>
        </ul>
        <CodeBlock lang="bash" code={snip.run} />
      </Step>

      <Step n={4} title="人工复核（coder / admin）">
        <p className="text-sm leading-relaxed text-muted">
          <span className="font-mono text-ink">POST /api/coding-review/&lt;run_id&gt;/human-review</span>。
          复核人角色从令牌注入、不取自请求体；reviewer 角色调用将返回 403。
        </p>
        <CodeBlock lang="bash" code={snip.review} />
      </Step>

      <Step n={5} title="导出报告">
        <p className="text-sm leading-relaxed text-muted">
          <span className="font-mono text-ink">GET /api/coding-review/&lt;run_id&gt;/report?format=html|json</span>。
          报告经 PHI 脱敏，含证据回链、合规门禁、DRG/DIP 与版本字段；每次导出都会写入 append-only 审计。
        </p>
        <CodeBlock lang="bash" code={snip.report} />
      </Step>

      <Step n={6} title="嵌入 HIS / EMR">
        <p className="text-sm leading-relaxed text-muted">
          <span className="font-mono text-ink">&lt;icoder-embedded&gt;</span>{" "}
          是框架无关的 Web Component（Shadow DOM 隔离样式）。宿主命令式调用{" "}
          <span className="font-mono text-ink">configureSession / configure / run</span>，并监听{" "}
          <span className="font-mono text-ink">embedded-event</span> 获取 ready / auth /
          run.completed / rule-gate-triggered 等事件。
        </p>
        <CodeBlock lang="html" code={snip.embed} />
      </Step>
    </div>
  );
}
