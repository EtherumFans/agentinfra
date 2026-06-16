// Domain types mirroring the on-prem backend contract.
// Sources: GET /agents, GET /agents/{id}/card, POST /api/coding-review/run.

export interface AgentSummary {
  id: string;
  name: string;
  version: string;
  category: string;
  experts: string[];
}

export interface AgentCard {
  schemaVersion: string;
  id: string;
  name: string;
  version: string;
  description: string;
  capabilities: { streaming: boolean; humanInTheLoop: boolean; evidenceLinked: boolean };
  skills: { id: string }[];
  nonGoals: string[];
  endpoints: { run: string };
  "x-icoder": {
    deployment: string;
    data_residency: string;
    coding_systems: string[];
    production_writeback_blocked: boolean;
    // "extract" = pure fact/abstraction surface (runs on the tool-calling executor via
    // /api/coding/extract, no compliance gate); "coding-review" = the full run pipeline;
    // "tool" = a Corti-style atomic agent that answers in prose Markdown on the executor
    // (runs via /api/agents/{id}/run, requires an external LLM, no structured codes).
    surface?: "extract" | "coding-review" | "tool";
  };
}

export type Role = "coder" | "reviewer" | "admin";

// --- coding-review run contract (POST /run, GET /{run_id}) ---

export interface Evidence {
  context_index: number;
  start: number; // inclusive
  end: number; // exclusive
  text: string;
}

export interface Alternative {
  code: string;
  display: string;
  reason: string;
}

export interface CodeNote {
  kind: "includes" | "excludes1" | "excludes2" | "code_first" | "use_additional";
  text: string;
}

// --- coding-knowledge lookup (GET /api/coding/search, GET /api/coding/code/{code}) ---

export interface CodeSearchHit {
  code: string;
  display: string;
  system: string;
  score: number;
  high_risk: boolean;
  code_type: "diagnosis" | "procedure" | null;
}

export interface RelatedCode {
  code: string;
  display: string | null;
  member: boolean; // true if the code has its own catalog entry (clickable)
}

export interface CodeDetail {
  code: string;
  display: string;
  system: string;
  code_type: "diagnosis" | "procedure";
  high_risk: boolean;
  notes: CodeNote[];
  guideline: string;
  parent: RelatedCode | null;
  siblings: RelatedCode[];
  children: RelatedCode[];
  alternatives: Alternative[];
}

export interface CodeResult {
  system: string;
  code: string;
  display: string;
  code_type: "diagnosis" | "procedure";
  status: "code" | "candidate";
  confidence: number;
  is_primary: boolean;
  high_risk: boolean;
  evidences: Evidence[];
  alternatives: Alternative[];
  notes: CodeNote[];
}

// --- fact extraction (POST /api/coding/extract) ---
// Pipeline stages 1–2 only (ingest + extract): structured clinical facts with evidence
// spans, no billing codes and no compliance gate. category is the deterministic catalog
// code_type of the top retrieval match (诊断/手术操作), not a predicted code.
export interface ExtractedEntity {
  term: string;
  category: "diagnosis" | "procedure" | null;
  evidences: Evidence[];
}

export interface PhiTypeCount {
  type: string;
  count: number;
}

export interface ExtractResult {
  provider: string;
  redaction: { spans: number; by_type: PhiTypeCount[]; text: string };
  entities: ExtractedEntity[];
}

// --- tool-surface agent run (POST /api/agents/{id}/run) ---
// Corti-style atomic agents (index navigation / code validation / compliance guardrail /
// document standardization) answer in prose Markdown — no structured codes, no submit_findings.
// `report` is the model's prose research report (null if it never produced one); `stages` is
// the tool-call timeline. Requires an external LLM (no deterministic fallback).
export interface AgentRunResult {
  provider: string;
  redaction: { spans: number; by_type: PhiTypeCount[]; text: string };
  report: string | null;
  stages: StageObservation[];
  usage: Record<string, unknown>;
}

export interface RuleHit {
  rule_id: string;
  severity: "Critical" | "Moderate" | "Informational";
  message: string;
  code: string | null;
}

export interface ComplianceGate {
  rule_set: string;
  passed: boolean;
  human_review_required: boolean;
  hits: RuleHit[];
}

// --- compliance rulesets (GET /api/coding-review/rulesets?agent_id=) ---

export interface RuleDef {
  rule_id: string;
  severity: "Critical" | "Moderate" | "Informational";
  title: string;
  intent: string;
}

export interface RuleSetInfo {
  rule_set: string;
  label: string;
  version: string;
  enforced: boolean; // does the queried agent run this domain?
  rules: RuleDef[];
}

export interface RuleSetsResponse {
  agent_id: string | null;
  gate_policy: { passed: string; human_review_required: string };
  rule_sets: RuleSetInfo[];
}

export interface DrgRoute {
  adrg: string | null;
  drg: string | null;
  group_name: string | null;
  mdc: string | null;
  mdc_name: string | null;
  surgical: boolean;
  cc_mcc: string | null;
  dip_code: string | null;
  dip_name: string | null;
  dip_score: number | null;
  rationale: string[];
  note: string;
}

export interface Versions {
  runtime_version: string;
  agent_version: string;
  ruleset_version: string;
  catalog_version: string;
  model_version: string;
}

export interface HumanReview {
  reviewer_role: string;
  decision: string;
  code: string | null;
  override_code: string | null;
  note: string;
}

export interface StageObservation {
  stage: string;
  tool: string;
  tool_run_id: string;
  duration_ms: number;
  summary: string;
}

export interface RunResult {
  run_id: string;
  agent_id: string;
  agent_version: string;
  coding_system: string;
  created_at: number;
  redaction: { redacted?: boolean; spans?: number; text?: string; [k: string]: unknown };
  codes: CodeResult[];
  candidates: CodeResult[];
  compliance: ComplianceGate;
  drg_route: DrgRoute | null;
  stages: StageObservation[];
  usage: Record<string, unknown>;
  versions: Versions;
  production_writeback_blocked: boolean;
  human_review: HumanReview | null;
}

// --- run history (GET /runs) ---

export interface RunSummary {
  run_id: string;
  agent_id: string;
  agent_version: string;
  created_at: number;
  passed: number; // sqlite int 0/1
  human_review_required: number;
  primary_code: string | null;
  drg: string | null;
  dip_code: string | null;
  reviewed: number;
}

// --- batch coding (POST /api/coding-review/batch) ---

// Each batch row is a real persisted run (same shape as a history row) plus its
// position in the submitted list, so the UI can map a row back to its input.
export interface BatchResultRow extends RunSummary {
  index: number;
}

export interface BatchResult {
  batch_id: string;
  total: number;
  passed: number;
  needs_review: number;
  results: BatchResultRow[];
}

// --- audit trail (GET /{run_id}/audit) ---

export interface AuditEvent {
  id: number;
  run_id: string;
  ts: number;
  actor_role: string | null;
  actor_token: string | null;
  action: string;
  detail: Record<string, unknown>;
}
