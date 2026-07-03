import type {
  AgentCard,
  AgentRunResult,
  AgentSummary,
  AuditEvent,
  BatchResult,
  CodeDetail,
  CodeSearchHit,
  ExtractResult,
  RuleSetsResponse,
  RunResult,
  RunSummary,
} from "../types";

// A typed transport error so the UI can render an actionable message instead of a raw
// string: `status` is 0 for network failures (backend down), otherwise the HTTP status;
// `code` carries the backend's structured detail.code (e.g. llm_credential_missing).
export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

// Same-origin: in dev the Vite proxy forwards /agents + /api to the backend; in
// production the FastAPI process serves both this SPA and the API from one origin.
async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code: string | undefined;
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      const detail = body?.detail;
      if (typeof detail === "string") message = detail;
      else if (detail && typeof detail === "object") {
        code = detail.code;
        message = detail.message ?? message;
      }
    } catch {
      /* non-JSON error body — keep the generic HTTP message */
    }
    throw new ApiError(res.status, message, code);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string, token: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
  } catch {
    // fetch rejects (DNS/refused/offline) before any HTTP status exists.
    throw new ApiError(0, `无法连接后端（${path}）`);
  }
  return handle<T>(res);
}

async function post<T>(path: string, token: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `无法连接后端（${path}）`);
  }
  return handle<T>(res);
}

export async function listAgents(token: string): Promise<AgentSummary[]> {
  const data = await get<{ agents: AgentSummary[] }>("/agents", token);
  return data.agents;
}

export async function getAgentCard(id: string, token: string): Promise<AgentCard> {
  return get<AgentCard>(`/agents/${id}/card`, token);
}

export async function listRuns(
  token: string,
  opts: { agentId?: string; limit?: number; offset?: number } = {},
): Promise<RunSummary[]> {
  const q = new URLSearchParams();
  if (opts.agentId) q.set("agent_id", opts.agentId);
  if (opts.limit != null) q.set("limit", String(opts.limit));
  if (opts.offset != null) q.set("offset", String(opts.offset));
  const qs = q.toString();
  const data = await get<{ runs: RunSummary[] }>(
    `/api/coding-review/runs${qs ? `?${qs}` : ""}`,
    token,
  );
  return data.runs;
}

export async function getRun(token: string, runId: string): Promise<RunResult> {
  return get<RunResult>(`/api/coding-review/${runId}`, token);
}

export async function getRunAudit(token: string, runId: string): Promise<AuditEvent[]> {
  const data = await get<{ events: AuditEvent[] }>(`/api/coding-review/${runId}/audit`, token);
  return data.events;
}

// Batch: one submission, many records, run through the identical single-run pipeline
// server-side. Each record is persisted as its own run, so rows drill down exactly
// like run history.
export async function runBatch(
  token: string,
  records: string[],
  opts: { codingSystem?: string; agentId?: string } = {},
): Promise<BatchResult> {
  return post<BatchResult>("/api/coding-review/batch", token, {
    records,
    coding_system: opts.codingSystem ?? "ICD-10-CN",
    agent_id: opts.agentId,
  });
}

// --- coding-knowledge lookup (Search / Verify / Guidelines / Explore, standalone) ---

export async function searchCodes(
  token: string,
  q: string,
  limit = 20,
): Promise<CodeSearchHit[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const data = await get<{ query: string; hits: CodeSearchHit[] }>(
    `/api/coding/search?${params.toString()}`,
    token,
  );
  return data.hits;
}

export async function getCodeDetail(token: string, code: string): Promise<CodeDetail> {
  return get<CodeDetail>(`/api/coding/code/${encodeURIComponent(code)}`, token);
}

// Fact extraction — the atomic 医疗事实抽取 Agent surface. With an external LLM
// configured the backend drives the tool-calling executor; with no key it falls back to
// deterministic local extraction. Identical output shape either way. `agentId` selects
// which extract-surface agent runs (defaults server-side to the diagnostic entity extractor).
export async function extractFacts(
  token: string,
  text: string,
  agentId?: string,
): Promise<ExtractResult> {
  return post<ExtractResult>("/api/coding/extract", token, { text, agent_id: agentId });
}

// Tool-surface agent run — the Corti-style atomic agents (index navigation / code
// validation / compliance guardrail / document standardization). The backend runs the
// tool-calling executor and the model answers in prose Markdown (no structured codes).
// Requires an external LLM: with no key the backend returns 503 llm_credential_missing
// (no deterministic fallback). `agentId` carries a slash and maps to the {id:path} route.
export async function runAgent(
  token: string,
  agentId: string,
  text: string,
): Promise<AgentRunResult> {
  return post<AgentRunResult>(`/api/agents/${agentId}/run`, token, { text });
}

// Compliance ruleset catalog — agent-aware: marks which of the four domains the given
// agent enforces. Pure metadata (no run), so safe to read on the detail page.
export async function getRuleSets(token: string, agentId: string): Promise<RuleSetsResponse> {
  const params = new URLSearchParams({ agent_id: agentId });
  return get<RuleSetsResponse>(`/api/coding-review/rulesets?${params.toString()}`, token);
}

// Report export. Both formats require the Bearer token, so a plain <a download>
// can't carry auth — fetch with the header, then trigger a blob download.
export async function downloadReport(
  token: string,
  runId: string,
  format: "html" | "json",
): Promise<void> {
  const path = `/api/coding-review/${runId}/report?format=${format}`;
  let res: Response;
  try {
    res = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
  } catch {
    throw new ApiError(0, `无法连接后端（${path}）`);
  }
  if (!res.ok) {
    throw new ApiError(res.status, `导出失败 HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `coding-review-${runId}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
