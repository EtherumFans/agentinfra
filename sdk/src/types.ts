/* iCoDer SDK — TypeScript type definitions */

// Auth
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: string;
  department: string;
}

// Encounters
export interface Encounter {
  id: string;
  encounter_id: string;
  patient_id: string;
  department: string;
  status: string;
  document_count: number;
  created_at: string;
}

// Reviews & Coding
export interface CodeCandidate {
  code: string;
  name: string;
  score: number;
  chapter?: string;
  status: string;
}

export interface Review {
  id: string;
  review_id: string;
  encounter_id: string;
  primary_diagnosis_code?: string;
  primary_diagnosis_name?: string;
  main_procedure_code?: string;
  main_procedure_name?: string;
  candidates?: CodeCandidate[];
  processing_time_ms?: number;
  human_review_status?: string;
  report_markdown?: string;
  report_html?: string;
}

// Experts
export interface Expert {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  category: string;
  capabilities: string[];
  tags: string[];
  is_prebuilt: boolean;
  usage_count: number;
  mcp_servers: McpServer[];
}

export interface McpServer {
  id: string;
  name: string;
  url: string;
  transport_type: string;
}

// Billing & Usage
export interface BillingBalance {
  balance: number;
  currency: string;
}

export interface Transaction {
  id: string;
  date: string;
  description: string;
  amount: string;
  type: string;
}

export interface UsageSummary {
  total_requests: number;
  credits_used: number;
  avg_response_time_ms: number;
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// Gold Cases
export interface GoldCase {
  id: string;
  case_id: string;
  department: string;
  diagnosis_group: string;
  difficulty: string;
  agent_accuracy?: number;
}

// Config
export interface ClientConfig {
  baseURL?: string;
  apiKey?: string;
  accessToken?: string;
  refreshToken?: string;
  onTokenRefresh?: (tokens: { access_token: string; refresh_token: string }) => void;
}
