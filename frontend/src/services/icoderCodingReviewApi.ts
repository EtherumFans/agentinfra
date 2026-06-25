// iCoDer M3-0 — MedCodER Coding Review API client.
//
// Talks to the real backend at /api/icoder/coding-review/* (see
// backend/app/api/icoder_coding_review.py). The canonical agent is
// icoder/medcoder-coding-review-agent@1.0.0 (5-stage MedCodER pipeline).
//
// This module is the single source of truth for the request/response
// types consumed by the embed components (IcoderReviewPanel /
// IcoderEvidenceViewer / IcoderTraceViewer) and the embed demo page.

import axios, { AxiosError } from 'axios';

import type {
  CodingMethodInfo,
  CompareRequest,
  CompareResponse,
  ListMethodsResponse,
  MethodFamily,
  RunV2Request,
  RunV2Response,
} from '../types/runtime';

const api = axios.create({
  baseURL: '/api',
  timeout: 120000, // 2 min — long-running 5-stage pipeline
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Shared types ───────────────────────────────────────────────────────

export interface DiagnosisCard {
  code: string;
  name: string;
  description: string;
  confidence: number;
  human_review_required: boolean;
  evidence?: Array<{
    text: string;
    char_start: number;
    char_end: number;
    doc_id?: string;
    doc_type?: string;
  }>;
}

export interface HighRiskCodingPoint {
  code: string;
  reason: string;
  is_priority?: boolean;
  evidence?: unknown[];
  human_review_required: boolean;
  current_status: 'pending' | 'accepted' | 'rejected' | 'modified';
}

export interface EvidenceChainEntry {
  text: string;
  char_start: number;
  char_end: number;
  doc_id?: string;
  doc_type?: string;
  supports_code: string;
  match_method: 'exact' | 'fuzzy' | 'rapidfuzz' | 'auto_bootstrap';
  confidence: number;
}

export interface CodingReviewRunResponse {
  run_id: string;
  trace_id: string;
  agent_ref: string;
  agent_category: string;
  prediction_mode: 'link_validation' | 'model_evaluation';
  status: 'ok' | 'unavailable' | 'degraded';
  degraded: boolean;
  business_result_generated: boolean;
  manual_review_required: boolean;
  reason: string;
  primary_diagnosis: DiagnosisCard | null;
  secondary_diagnoses: DiagnosisCard[];
  procedures: DiagnosisCard[];
  high_risk_coding_points: HighRiskCodingPoint[];
  evidence_chain: EvidenceChainEntry[];
  risk_route: Record<string, unknown>;
  safety_gate: Record<string, unknown>;
  drg_route: Record<string, unknown> | null;
  pipeline_stages_observed: string[];
  trace_url: string;
  human_review_url: string;
  report_url: string;
  started_at: string;
  finished_at: string;
}

export interface HumanReviewAction {
  case_id?: string;
  target_code: string;
  target_role: 'primary_disease' | 'other_disease' | 'primary_surgery' | 'other_surgery';
  action: 'accept' | 'reject' | 'modify' | 'insufficient_evidence' | 'escalate';
  new_code?: string;
  reason_code: string; // M3 任务 §5 — required
  review_note?: string;
  reviewer: string; // required
  reviewer_role?: string;
}

export interface HumanReviewResponse {
  run_id: string;
  accepted: boolean;
  record_id: string;
  action: string;
  target_code: string;
  new_code: string;
  production_writeback_blocked: boolean; // always true in M3-0
  validation_errors: string[];
  warnings: string[];
  audit_log_entry: Record<string, unknown>;
  recorded_at: string;
}

export interface CodingReviewRunRequest {
  encounter_text: string;
  mode?: 'link_validation' | 'model_evaluation';
  case_id?: string;
  input_source?: 'manual' | 'm2b_sample' | 'validated' | 'api' | 'embed_demo';
  primary_disease_codes?: string;
  other_disease_codes?: string;
  primary_surgery_codes?: string;
  other_surgery_codes?: string;
}

// ── API methods ────────────────────────────────────────────────────────

export const icoderCodingReviewApi = {
  /** Run the 5-stage MedCodER pipeline on a piece of EMR text. */
  async run(req: CodingReviewRunRequest): Promise<CodingReviewRunResponse> {
    const { data } = await api.post<CodingReviewRunResponse>(
      '/icoder/coding-review/run',
      {
        encounter_text: req.encounter_text,
        mode: req.mode ?? 'link_validation',
        case_id: req.case_id ?? '',
        input_source: req.input_source ?? 'manual',
        primary_disease_codes: req.primary_disease_codes ?? '',
        other_disease_codes: req.other_disease_codes ?? '',
        primary_surgery_codes: req.primary_surgery_codes ?? '',
        other_surgery_codes: req.other_surgery_codes ?? '',
      },
    );
    return data;
  },

  /** Fetch a stored run by id. */
  async getRun(runId: string): Promise<CodingReviewRunResponse> {
    const { data } = await api.get<CodingReviewRunResponse>(
      `/icoder/coding-review/${runId}`,
    );
    return data;
  },

  /** Submit a human review action (accept / reject / modify / ...). */
  async humanReview(
    runId: string,
    action: HumanReviewAction,
  ): Promise<HumanReviewResponse> {
    const { data } = await api.post<HumanReviewResponse>(
      `/icoder/coding-review/${runId}/human-review`,
      action,
    );
    return data;
  },

  /** Fetch the HTML report for a run. */
  async getReport(runId: string): Promise<{ content: string; filename: string; disclaimer: string }> {
    const { data } = await api.get<{ format: string; content: string; filename: string; disclaimer: string; generated_at: string }>(
      `/icoder/coding-review/${runId}/report`,
    );
    return { content: data.content, filename: data.filename, disclaimer: data.disclaimer };
  },

  // ── Phase B: Coding Method Runtime API ──

  /** List all registered CodingMethod instances + capability probes. */
  async listMethods(family?: MethodFamily): Promise<ListMethodsResponse> {
    const { data } = await api.get<ListMethodsResponse>(
      '/icoder/coding-methods/list',
      { params: family ? { family } : {} },
    );
    return data;
  },

  /** Describe a single method by id. Throws 404 (axios) when unknown. */
  async getMethod(methodId: string): Promise<CodingMethodInfo> {
    const { data } = await api.get<CodingMethodInfo>(
      `/icoder/coding-methods/${encodeURIComponent(methodId)}`,
    );
    return data;
  },

  /** Run N methods on the same EMR text and return side-by-side results. */
  async compareMethods(req: CompareRequest): Promise<CompareResponse> {
    const { data } = await api.post<CompareResponse>(
      '/icoder/coding-review/compare',
      {
        emr_text: req.emr_text,
        method_ids: req.method_ids,
        case_id: req.case_id ?? '',
      },
    );
    return data;
  },

  /** Run a single method by canonical method_id (or legacy mode alias). */
  async runV2(req: RunV2Request): Promise<RunV2Response> {
    const { data } = await api.post<RunV2Response>(
      '/icoder/coding-review/run-v2',
      {
        emr_text: req.emr_text,
        method_id: req.method_id ?? '',
        mode: req.mode ?? '',
        case_id: req.case_id ?? '',
      },
    );
    return data;
  },
};

export type { AxiosError };
