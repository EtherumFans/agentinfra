// @icoder/sdk — Medical AI Agent Platform SDK for Chinese Hospitals
export { iCoDerClient } from './client';
export type { iCoDerConfig } from './client';

export { FactsResource } from './resources/facts';
export { AgentsResource, ExpertsResource } from './resources/agents';
export { ReviewsResource } from './resources/reviews';
export { SpeechToTextResource } from './resources/speech-to-text';
export type { SttSessionConfig } from './resources/speech-to-text';
export { TextGenResource } from './resources/textgen';
export { BillingResource, UsageResource } from './resources/billing';
export { OAuthResource } from './resources/oauth';
export { RuntimeResource } from './resources/runtime';
export { MarketplaceResource } from './resources/marketplace';
export { ComplianceResource } from './resources/compliance';

export type {
  TokenResponse, User, UserRole, Encounter, Review,
  FactExtractionResult, FactExtractResponse,
  FactDiagnosis, FactProcedure,
  AgentTemplate, Expert, McpServer,
  TextGenTemplate, TextGenResponse,
  GoldCase, EvaluationSummary,
  PaginatedResponse, UsageSummary,
  ClientCredentials, ClinicalEvidence, CodeCandidate,
} from './types';

import { iCoDerClient } from './client';
import { FactsResource } from './resources/facts';
import { AgentsResource, ExpertsResource } from './resources/agents';
import { ReviewsResource } from './resources/reviews';
import { SpeechToTextResource } from './resources/speech-to-text';
import { TextGenResource } from './resources/textgen';
import { BillingResource, UsageResource } from './resources/billing';
import { OAuthResource } from './resources/oauth';
import { RuntimeResource } from './resources/runtime';
import { MarketplaceResource } from './resources/marketplace';
import { ComplianceResource } from './resources/compliance';

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

  constructor(config: import('./client').iCoDerConfig) {
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
  }
}
