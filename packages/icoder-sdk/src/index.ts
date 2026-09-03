// @icoder/sdk — Medical AI Agent Platform SDK for Chinese Hospitals
export { iCoDerAuthenticationError, iCoDerClient } from './client.js';
export type { iCoDerConfig, iCoDerRetryConfig } from './client.js';
export { requestConfig } from './request-options.js';
export type { iCoDerAxiosRequestConfig, iCoDerRequestOptions } from './request-options.js';
export {
  BadGatewayError, BadRequestError, ConflictError, ForbiddenError,
  GatewayTimeoutError, iCoDerAPIError, iCoDerClientError,
  InternalServerError, NotFoundError, UnauthorizedError,
  UnprocessableEntityError,
} from './errors.js';
export type { iCoDerErrorDetail, iCoDerSanitizedErrorBody } from './errors.js';
export { AsyncCursorPager, AsyncPageNumberPager } from './pagination.js';
export type {
  CursorPageAdapter, CursorPagerOptions, PageNumberAdapter, PageNumberPagerOptions,
} from './pagination.js';

export {
  END, Parallel, StateGraph, Workflow, agentNode, parallel, stateGraph, workflow,
} from './composition.js';
export type {
  MessageResponse, ParallelResult, ParallelSettledResult, ParallelStep,
  StateGraphEdge, StateGraphNode, StateGraphResult, StateGraphStep,
  WorkflowResult, WorkflowStep, WorkflowStepConfig,
} from './composition.js';


export { FactsResource } from './resources/facts.js';
export { AgentsResource, ExpertsResource } from './resources/agents.js';
export type {
  A2AConnectorConfig, AgentConnector, AgentConnectorConfig,
  AgentCloneRequest, AgentCloneResponse,
  AgentConnectorCreateRequest, AgentConnectorCredentialMetadata,
  AgentConnectorType, AgentConnectorUpdateRequest, ConnectorCredentialBindRequest,
  BuiltinRegistryKey,
  ConnectorDataClassification, ConnectorGraph, ConnectorGraphNode,
  ConnectorGraphPutRequest, ConnectorPurposeOfUse, ConnectorRedirectPolicy,
  InternalAgentConnectorConfig, MCPConnectorConfig, RegistryConnectorConfig,
  SchemaConnectorConfig,
} from './resources/agents.js';
export { SpeechToTextResource } from './resources/speech-to-text.js';
export type { SttSessionConfig, TranscriptCreateRequest, TranscriptCreateResult } from './resources/speech-to-text.js';
export { ManagedSttSession, ManagedSttSessionError } from './managed-stt-session.js';
export type {
  ManagedSttConnectOptions, ManagedSttEventMap, ManagedSttServerMessage,
} from './managed-stt-session.js';
export { ManagedStreamsSession, ManagedStreamsSessionError } from './managed-streams-session.js';
export type {
  ManagedStreamsConnectOptions, ManagedStreamsEventMap, ManagedStreamsServerMessage,
  StreamsConfiguration, StreamsParticipant, StreamsReplacement,
} from './managed-streams-session.js';
export { StreamsResource } from './resources/streams.js';
export { TextGenResource } from './resources/textgen.js';
export { BillingResource, UsageResource } from './resources/billing.js';
export type {
  BillingRunSettlement, BillingRunSettlementPage,
  BillingTransaction, BillingTransactionPage,
} from './resources/billing.js';
export { OAuthResource } from './resources/oauth.js';
export { RuntimeResource } from './resources/runtime.js';
export { ComplianceResource } from './resources/compliance.js';
export { PlatformResource } from './resources/platform.js';
export type { EnvironmentPlanRequest } from './resources/platform.js';
export { DocumentsResource } from './resources/documents.js';
export type {
  ClassicDocument, DocumentContext, DocumentCreateRequest, DocumentCreateResult,
  DocumentFact, DocumentSection, DocumentSectionOverride, DocumentTemplate,
} from './resources/documents.js';
export { TemplatesResource } from './resources/templates.js';
export type {
  GuidedDiscoveryFilters, GuidedLabel, GuidedSection, GuidedTemplate, SectionMutation,
} from './resources/templates.js';
export { MedicalCodingResource } from './resources/medical-coding.js';
export { ModelsResource } from './resources/models.js';
export { DrgDipRiskReviewResource } from './resources/drg-dip-risk-review.js';
export type {
  DrgDipAnalyzeRequest, DrgDipAnalyzeResponse, DrgDipCode, DrgDipGovernance,
  DrgDipRisk, DrgDipRule, DrgDipRulesResponse,
} from './resources/drg-dip-risk-review.js';
export type {
  ModelCatalog, ModelCatalogItem, ModelCatalogStatus,
  ModelLiveCanaryPolicy, ModelLiveCanaryResponse,
} from './resources/models.js';
export type {
  CodingMode, ChinaCodingSystem, CodingPredictRequest, CodingPredictResponse, CodingPricingEstimate,
} from './resources/medical-coding.js';
// Phase 6 Gate 4 — unified agent-run + observability resources
export {
  RunEventRetentionError, RunEventStreamError, RunsResource, RunHistoryResource, RunTraceResource,
} from './resources/runs.js';
export type {
  AgentRunRequest, AgentRunResponse, AgentRunCost, AgentRunRequestInput,
  AgentRunSourceDocument, AgentRunUpstreamResult,
  RunHistoryItem, RunHistoryListResponse,
  RunTraceEvent, RunTraceTimelineResponse, RunTraceRawResponse,
  RunStatusResponse, RunCancelOutcome, RunCancelResponse,
  RunTraceTokenRenewResponse, RunSseEvent, RunStreamRetryOptions,
} from './resources/runs.js';
export { A2AProtocolError, A2AResource, A2ATransportError } from './resources/a2a.js';
export type {
  A2AContext, A2AContextDeleted, A2AContextItem,
  A2ADataPart, A2AMessage, A2APart, A2ASendOptions, A2AStreamOptions, A2ATextPart,
  A2AV1TaskIteratorOptions,
  A2AV1AgentCard, A2AV1Artifact, A2AV1Message, A2AV1Part,
  A2AV1SendOptions, A2AV1SendResult, A2AV1StreamOptions, A2AV1StreamResponse,
  A2AV1SubscribeOptions, A2AV1Task, A2AV1TaskList, A2AV1TaskListOptions,
  A2AV1TaskArtifactUpdateEvent, A2AV1TaskState, A2AV1TaskStatusUpdateEvent,
  AgentUsageGranularity, AgenticAgentUsage, AgenticArtifact,
  AgenticArtifactDownloadAuthorization, AgenticArtifactObject,
  AgenticArtifactObjectClassification, AgenticArtifactObjectPage,
  AgenticArtifactObjectPurpose, AgenticArtifactObjectStatus,
  AgenticArtifactObjectUpload,
  AgenticContextListOptions, AgenticContextPage, AgenticContextResource,
  AgenticContextSummary, AgenticContextTaskListOptions, AgenticTaskPage, AgenticFeedback,
  AgenticFeedbackInput, AgenticFeedbackLabel, AgenticFeedbackList, AgenticTracePage,
} from './resources/a2a.js';
// A1C.3 — Patient Context API (closes RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT)
export { PatientContextResource } from './resources/patient-context.js';
export type {
  PatientContextCreate, PatientContextResponse,
  VisitType, PurposeOfUse, ConsentLegalBasis, ContextStatus,
} from './resources/patient-context.js';

export type {
  TokenResponse, User, UserRole, Encounter,
  FactExtractionResult, FactExtractRequest, FactExtractResponse, FactItem,
  FactDiagnosis, FactProcedure,
  AgentTemplate, Expert, McpServer,
  AgentOutputFieldType, AgentOutputFieldSchema, AgentOutputFieldRelation,
  AgentOutputEvidenceBinding, AgentOutputCrossAgentRelation,
  A2ALegacyAgentCard, AgentHubOutputContract, AgentHubRuntimeReadiness,
  AgentHubCard, AgentHubResponse, AgentHubTenantRuntimeReadiness,
  AgentHubTenantReadinessEvidence, AgentHubTenantReadinessItem,
  AgentHubTenantReadinessResponse,
  TextGenTemplate, TextGenResponse,
  GoldCase, EvaluationSummary,
  PaginatedResponse, UsageSummary,
  ClientCredentials, ClinicalEvidence, CodeCandidate,
} from './types.js';

import { iCoDerClient } from './client.js';
import { FactsResource } from './resources/facts.js';
import { AgentsResource, ExpertsResource } from './resources/agents.js';
import { SpeechToTextResource } from './resources/speech-to-text.js';
import { StreamsResource } from './resources/streams.js';
import { TextGenResource } from './resources/textgen.js';
import { BillingResource, UsageResource } from './resources/billing.js';
import { OAuthResource } from './resources/oauth.js';
import { RuntimeResource } from './resources/runtime.js';
import { ComplianceResource } from './resources/compliance.js';
import { RunsResource, RunHistoryResource, RunTraceResource } from './resources/runs.js';
import { A2AResource } from './resources/a2a.js';
import { PatientContextResource } from './resources/patient-context.js';
import { PlatformResource } from './resources/platform.js';
import { DocumentsResource } from './resources/documents.js';
import { TemplatesResource } from './resources/templates.js';
import { MedicalCodingResource } from './resources/medical-coding.js';
import { ModelsResource } from './resources/models.js';
import { DrgDipRiskReviewResource } from './resources/drg-dip-risk-review.js';

export default class iCoDer {
  client: iCoDerClient;
  facts: FactsResource;
  agents: AgentsResource;
  experts: ExpertsResource;
  speechToText: SpeechToTextResource;
  /** Corti-compatible stateful ambient transcript and Facts stream. */
  streams: StreamsResource;
  textGen: TextGenResource;
  billing: BillingResource;
  usage: UsageResource;
  oauth: OAuthResource;
  runtime: RuntimeResource;
  compliance: ComplianceResource;
  /** Phase 6 Gate 4 — unified agent-run facade (POST /api/v1/agents/{id}/run). */
  runs: RunsResource;
  /** Phase 6 Gate 4 — run_history table (alembic 010). */
  runHistory: RunHistoryResource;
  /** Phase 6 Gate 4 — run_trace store (alembic 009). */
  runTrace: RunTraceResource;
  /** A2A v0.3 Context plus v1 synchronous/asynchronous Task API. */
  a2a: A2AResource;
  /** A1C.3 — Patient Context API (closes RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT). */
  patientContext: PatientContextResource;
  /** Declarative Environments/Regions and Tenant compatibility APIs. */
  platform: PlatformResource;
  /** Corti-compatible Classic Documents generation and encrypted lifecycle. */
  documents: DocumentsResource;
  /** Corti-compatible Guided Template and Section discovery/management. */
  templates: TemplatesResource;
  /** Medical Coding prediction plus non-authoritative pre-run cost range. */
  medicalCoding: MedicalCodingResource;
  /** Secret-free model configuration and regional egress readiness. */
  models: ModelsResource;
  /** Development-only China DRG/DIP risk review; never an official grouper or settlement result. */
  drgDipRiskReview: DrgDipRiskReviewResource;

  constructor(config: import('./client.js').iCoDerConfig) {
    this.client = new iCoDerClient(config);
    this.facts = new FactsResource(this.client.http);
    this.agents = new AgentsResource(this.client.http, () => this.client.accessToken);
    this.experts = new ExpertsResource(this.client.http);
    this.speechToText = new SpeechToTextResource(
      this.client.http,
      () => this.client.accessToken,
      () => this.client.ensureAccessToken(),
    );
    this.streams = new StreamsResource(
      this.client.http,
      () => this.client.accessToken,
      () => this.client.ensureAccessToken(),
    );
    this.textGen = new TextGenResource(this.client.http);
    this.billing = new BillingResource(this.client.http);
    this.usage = new UsageResource(this.client.http);
    this.oauth = new OAuthResource(this.client.http);
    this.runtime = new RuntimeResource(this.client.http);
    this.compliance = new ComplianceResource(this.client.http);
    this.runs = new RunsResource(this.client.http);
    this.runHistory = new RunHistoryResource(this.client.http);
    this.runTrace = new RunTraceResource(this.client.http);
    this.a2a = new A2AResource(this.client.http, () => this.client.accessToken);
    this.patientContext = new PatientContextResource(this.client.http);
    this.platform = new PlatformResource(this.client.http);
    this.documents = new DocumentsResource(this.client.http);
    this.templates = new TemplatesResource(this.client.http);
    this.medicalCoding = new MedicalCodingResource(this.client.http);
    this.models = new ModelsResource(this.client.http);
    this.drgDipRiskReview = new DrgDipRiskReviewResource(this.client.http);
  }
}
