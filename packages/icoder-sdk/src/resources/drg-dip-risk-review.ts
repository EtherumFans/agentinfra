import type { AxiosInstance } from 'axios';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export interface DrgDipGovernance {
  asset_id: 'cn.drg_dip.risk_heuristics';
  version: '1.0.0-development';
  asset_type: 'risk_review_rule_pack';
  jurisdiction: 'CN_GENERIC_DEVELOPMENT';
  authority_status: 'experimental_unverified';
  license_status: 'external_review_required';
  effective_from: string | null;
  effective_to: string | null;
  billing_authoritative: false;
  manual_review_required: true;
  use_restriction: 'development_risk_review_only_not_for_grouping_payment_or_settlement';
}

export interface DrgDipCode {
  code: string;
  name?: string;
  description?: string;
  confidence?: number;
}

export interface DrgDipAnalyzeRequest {
  primary_diagnosis: DrgDipCode;
  secondary_diagnoses?: DrgDipCode[];
  procedures?: DrgDipCode[];
  patient_gender?: 'M' | 'F' | '';
  patient_age?: number | null;
}

export interface DrgDipRisk {
  rule_id: string;
  severity: string;
  risk_type: string;
  message: string;
  suggestion: string;
}

export interface DrgDipAnalyzeResponse {
  primary_diagnosis: Required<DrgDipCode>;
  secondary_diagnoses: Array<Required<DrgDipCode>>;
  procedures: Array<Required<DrgDipCode>>;
  drg_impact: {
    /** Backward-compatible field containing an experimental candidate, not an official DRG. */
    predicted_drg: string;
    drg_name: string;
    mdc: string;
    mdc_name: string;
    adrg: string;
    cc_level: string;
    grouping_method: string;
    coverage: boolean;
    payment_weight: 0;
    payment_estimate_yuan: 0;
    billing_authoritative: false;
    result_status: 'experimental_candidate';
  };
  dip_impact: {
    dip_score: 0;
    dip_score_ceiling: 0;
    payment_estimate_yuan: 0;
    note: string;
    billing_authoritative: false;
  };
  risks: DrgDipRisk[];
  recommendations: string[];
  quality_flags: Record<string, unknown>;
  governance: DrgDipGovernance;
  manual_review_required: true;
  review_conclusion: 'WARNING' | 'FAIL';
  confidence: number;
  notes: string;
  provider: string;
  model: string;
  is_mock: boolean;
  error: false;
  error_reason: '';
}

export interface DrgDipRule {
  id: string;
  name: string;
  severity: string;
  category: string;
  description: string;
}

export interface DrgDipRulesResponse {
  rule_set: 'drg_dip';
  total: number;
  rules: DrgDipRule[];
  governance: DrgDipGovernance;
}

/**
 * Development-only China DRG/DIP risk review.
 *
 * This resource deliberately rejects any response that presents the bundled
 * heuristic as authoritative or returns a non-zero grouping/payment value.
 */
export class DrgDipRiskReviewResource {
  constructor(private http: AxiosInstance) {}

  async getGovernance(options?: iCoDerRequestOptions): Promise<DrgDipGovernance> {
    const { data } = await this.http.get<DrgDipGovernance>(
      '/api/drg/governance', requestConfig(options),
    );
    assertDevelopmentOnlyGovernance(data);
    return data;
  }

  async listRules(options?: iCoDerRequestOptions): Promise<DrgDipRulesResponse> {
    const { data } = await this.http.get<DrgDipRulesResponse>(
      '/api/drg/rules', requestConfig(options),
    );
    assertDevelopmentOnlyGovernance(data.governance);
    return data;
  }

  async analyze(
    request: DrgDipAnalyzeRequest,
    options?: iCoDerRequestOptions,
  ): Promise<DrgDipAnalyzeResponse> {
    validateAnalyzeRequest(request);
    const { data } = await this.http.post<DrgDipAnalyzeResponse>('/api/drg/analyze', {
      ...request,
      secondary_diagnoses: request.secondary_diagnoses ?? [],
      procedures: request.procedures ?? [],
      patient_gender: request.patient_gender ?? '',
      patient_age: request.patient_age ?? null,
    }, requestConfig(options));
    assertDevelopmentOnlyAnalysis(data);
    return data;
  }
}

function assertDevelopmentOnlyGovernance(value: DrgDipGovernance): void {
  if (!value || value.asset_id !== 'cn.drg_dip.risk_heuristics'
      || value.version !== '1.0.0-development'
      || value.jurisdiction !== 'CN_GENERIC_DEVELOPMENT'
      || value.authority_status !== 'experimental_unverified'
      || value.license_status !== 'external_review_required'
      || value.billing_authoritative !== false
      || value.manual_review_required !== true
      || value.use_restriction !== 'development_risk_review_only_not_for_grouping_payment_or_settlement') {
    throw new Error('DRG/DIP governance response is not a development-only, manual-review contract');
  }
}

function assertDevelopmentOnlyAnalysis(value: DrgDipAnalyzeResponse): void {
  assertDevelopmentOnlyGovernance(value?.governance);
  if (value.manual_review_required !== true
      || value.error !== false
      || !['WARNING', 'FAIL'].includes(value.review_conclusion)
      || value.drg_impact?.billing_authoritative !== false
      || value.drg_impact?.result_status !== 'experimental_candidate'
      || value.drg_impact?.payment_weight !== 0
      || value.drg_impact?.payment_estimate_yuan !== 0
      || value.dip_impact?.billing_authoritative !== false
      || value.dip_impact?.dip_score !== 0
      || value.dip_impact?.dip_score_ceiling !== 0
      || value.dip_impact?.payment_estimate_yuan !== 0) {
    throw new Error('DRG/DIP response violated the non-authoritative, non-payment contract');
  }
}

function validateAnalyzeRequest(request: DrgDipAnalyzeRequest): void {
  validateCode(request?.primary_diagnosis, 'primary_diagnosis');
  (request.secondary_diagnoses ?? []).forEach((item, index) => {
    validateCode(item, `secondary_diagnoses[${index}]`);
  });
  (request.procedures ?? []).forEach((item, index) => {
    validateCode(item, `procedures[${index}]`);
  });
  if (request.patient_gender !== undefined
      && !['M', 'F', ''].includes(request.patient_gender)) {
    throw new RangeError('patient_gender must be M, F, or empty');
  }
  if (request.patient_age !== undefined && request.patient_age !== null
      && (!Number.isInteger(request.patient_age) || request.patient_age < 0 || request.patient_age > 150)) {
    throw new RangeError('patient_age must be an integer between 0 and 150');
  }
}

function validateCode(item: DrgDipCode | undefined, field: string): void {
  if (!item || typeof item.code !== 'string' || !item.code.trim()
      || item.code.length > 64 || /[\u0000-\u001f\u007f]/.test(item.code)) {
    throw new RangeError(`${field}.code must contain between 1 and 64 printable characters`);
  }
  if (item.confidence !== undefined
      && (!Number.isFinite(item.confidence) || item.confidence < 0 || item.confidence > 1)) {
    throw new RangeError(`${field}.confidence must be between 0 and 1`);
  }
}
