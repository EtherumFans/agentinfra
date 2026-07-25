// @icoder/sdk — Medical AI Agent Platform SDK for Chinese Hospitals
export { iCoDerClient } from './client.js';
export type { iCoDerConfig } from './client.js';


export { FactsResource } from './resources/facts.js';
export { AgentsResource, ExpertsResource } from './resources/agents.js';
export { ReviewsResource } from './resources/reviews.js';
export { SpeechToTextResource } from './resources/speech-to-text.js';
export type { SttSessionConfig } from './resources/speech-to-text.js';
export { TextGenResource } from './resources/textgen.js';
export { BillingResource, UsageResource } from './resources/billing.js';
export { OAuthResource } from './resources/oauth.js';
export { RuntimeResource } from './resources/runtime.js';
export { MarketplaceResource } from './resources/marketplace.js';
export { ComplianceResource } from './resources/compliance.js';
// Phase 6 Gate 4 — unified agent-run + observability resources
export { RunsResource, RunHistoryResource, RunTraceResource } from './resources/runs.js';
export type {
  AgentRunRequest, AgentRunResponse, AgentRunCost, AgentRunRequestInput,
  RunHistoryItem, RunHistoryListResponse,
  RunTraceEvent, RunTraceTimelineResponse, RunTraceRawResponse,
  A2AEnvelope, A2AMessage, A2AMessagePart,
} from './resources/runs.js';
// A1C.3 — Patient Context API (closes RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT)
export { PatientContextResource } from './resources/patient-context.js';
export type {
  PatientContextCreate, PatientContextResponse,
  VisitType, PurposeOfUse, ConsentLegalBasis, ContextStatus,
} from './resources/patient-context.js';

export type {
  TokenResponse, User, UserRole, Encounter, Review,
  FactExtractionResult, FactExtractResponse,
  FactDiagnosis, FactProcedure,
  AgentTemplate, Expert, McpServer,
  TextGenTemplate, TextGenResponse,
  GoldCase, EvaluationSummary,
  PaginatedResponse, UsageSummary,
  ClientCredentials, ClinicalEvidence, CodeCandidate,
} from './types.js';

import { iCoDerClient } from './client.js';
import { FactsResource } from './resources/facts.js';
import { AgentsResource, ExpertsResource } from './resources/agents.js';
import { ReviewsResource } from './resources/reviews.js';
import { SpeechToTextResource } from './resources/speech-to-text.js';
import { TextGenResource } from './resources/textgen.js';
import { BillingResource, UsageResource } from './resources/billing.js';
import { OAuthResource } from './resources/oauth.js';
import { RuntimeResource } from './resources/runtime.js';
import { MarketplaceResource } from './resources/marketplace.js';
import { ComplianceResource } from './resources/compliance.js';
import { RunsResource, RunHistoryResource, RunTraceResource } from './resources/runs.js';
import { PatientContextResource } from './resources/patient-context.js';

export default class iCoDer {
  client: iCoDerClient;
  facts: FactsResource;
  agents: AgentsResource;
  experts: ExpertsResource;
  reviews: ReviewsResource;
  speechToText: SpeechToTextResource;
  textGen: TextGenResource;
  billing: BillingResource;
  usage: UsageResource;
  oauth: OAuthResource;
  runtime: RuntimeResource;
  marketplace: MarketplaceResource;
  compliance: ComplianceResource;
  /** Phase 6 Gate 4 — unified agent-run facade (POST /api/v1/agents/{id}/run). */
  runs: RunsResource;
  /** Phase 6 Gate 4 — run_history table (alembic 010). */
  runHistory: RunHistoryResource;
  /** Phase 6 Gate 4 — run_trace store (alembic 009). */
  runTrace: RunTraceResource;
  /** A1C.3 — Patient Context API (closes RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT). */
  patientContext: PatientContextResource;

  constructor(config: import('./client.js').iCoDerConfig) {
    this.client = new iCoDerClient(config);
    this.facts = new FactsResource(this.client.http);
    this.agents = new AgentsResource(this.client.http);
    this.experts = new ExpertsResource(this.client.http);
    this.reviews = new ReviewsResource(this.client.http);
    this.speechToText = new SpeechToTextResource(this.client.http);
    this.textGen = new TextGenResource(this.client.http);
    this.billing = new BillingResource(this.client.http);
    this.usage = new UsageResource(this.client.http);
    this.oauth = new OAuthResource(this.client.http);
    this.runtime = new RuntimeResource(this.client.http);
    this.marketplace = new MarketplaceResource(this.client.http);
    this.compliance = new ComplianceResource(this.client.http);
    this.runs = new RunsResource(this.client.http);
    this.runHistory = new RunHistoryResource(this.client.http);
    this.runTrace = new RunTraceResource(this.client.http);
    this.patientContext = new PatientContextResource(this.client.http);
  }
}
