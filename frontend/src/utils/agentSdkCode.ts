export interface AgentRunSnippetOptions {
  agentId?: string;
  agentRef?: string;
  baseURL: string;
  runtimeMode?: string;
}

export interface AgentRunSnippets {
  javascript: string;
  python: string;
  curl: string;
  json: string;
}

function shortAgentId(agentRef: string): string {
  const tail = agentRef.trim().split('/').pop() || '';
  return tail.split('@')[0];
}

/** Generate copy/paste examples from the shipped unified Agent Run contract. */
export function buildAgentRunSnippets({
  agentId = '',
  agentRef = '',
  baseURL,
  runtimeMode = '',
}: AgentRunSnippetOptions): AgentRunSnippets {
  // The unified route accepts a project Agent database ID or an official
  // pack's URL-safe short ID, never the full `vendor/name@version` ref.
  const target = agentId.trim() || shortAgentId(agentRef) || '<agent-id>';
  const targetLiteral = JSON.stringify(target);
  const normalizedBaseURL = baseURL.replace(/\/$/, '');
  const baseURLLiteral = JSON.stringify(normalizedBaseURL);
  const endpoint = `/api/v1/agents/${encodeURIComponent(target)}/run`;
  const runtimeJs = runtimeMode
    ? `\n    runtime_mode: ${JSON.stringify(runtimeMode)},`
    : '';
  const runtimePython = runtimeMode
    ? `\n    runtime_mode=${JSON.stringify(runtimeMode)},`
    : '';
  const body = {
    input: { text: 'Your input here' },
    ...(runtimeMode ? { runtime_mode: runtimeMode } : {}),
    include_trace: true,
    include_evidence: true,
  };

  return {
    javascript: `import iCoDer from "@icoder/sdk";

const icoder = new iCoDer({
  baseURL: ${baseURLLiteral},
  auth: { accessToken: process.env.ICODER_ACCESS_TOKEN },
});

const { data: run } = await icoder.runs.runText(
  ${targetLiteral},
  "Your input here",
  {${runtimeJs}
    idempotencyKey: globalThis.crypto.randomUUID(),
  },
);

console.log(run.run_id, run.runtime_mode, run.latency_ms);
console.log(run.result);`,
    python: `import os
import uuid

from icoder_sdk import iCoDerClient, iCoDerConfig

client = iCoDerClient(iCoDerConfig(
    base_url=${baseURLLiteral},
    access_token=os.environ["ICODER_ACCESS_TOKEN"],
))

run = client.runs.run_text(
    ${targetLiteral},
    "Your input here",${runtimePython}
    idempotency_key=uuid.uuid4().hex,
    include_trace=True,
    include_evidence=True,
)

print(run["run_id"], run["runtime_mode"], run["latency_ms"])
print(run["result"])`,
    curl: `curl -X POST "${normalizedBaseURL}${endpoint}" \\
  -H "Authorization: Bearer $ICODER_ACCESS_TOKEN" \\
  -H "Idempotency-Key: <unique-idempotency-key>" \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(body, null, 2)}'`,
    json: JSON.stringify({
      endpoint,
      method: 'POST',
      headers: {
        Authorization: 'Bearer <tenant-bound-access-token>',
        'Idempotency-Key': '<unique-idempotency-key>',
        'Content-Type': 'application/json',
      },
      body,
    }, null, 2),
  };
}
