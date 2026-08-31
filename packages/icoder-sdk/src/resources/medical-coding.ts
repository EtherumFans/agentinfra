import type { AxiosInstance } from 'axios';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export type CodingMode = 'corti_like_fast' | 'medcoder_deep';
export type ChinaCodingSystem = 'icd10cn' | 'icd9cm3';

export interface CodingCodeFilter {
  include?: string[];
  exclude?: string[];
  expand?: boolean;
}

export interface CodingPredictRequest {
  text: string;
  mode?: CodingMode;
  /** @deprecated Prefer coding_systems for one or both China systems. */
  coding_system?: ChinaCodingSystem;
  coding_systems?: ChinaCodingSystem[];
  include_evidence?: boolean;
  include_trace?: boolean;
  filter?: CodingCodeFilter;
}

export interface CodingPredictResponse {
  codes: Array<Record<string, unknown>>;
  summary: string;
  runtime_mode: CodingMode | string;
  latency_ms: number;
  llm_provider: string;
  trace_id: string;
  run_id: string;
  cost: { amount?: number; currency?: string };
  error: boolean;
  error_reason: string;
  filter_applied?: Required<CodingCodeFilter> | null;
  coding_systems_applied?: ChinaCodingSystem[];
}

export interface CodingPricingEstimate {
  input_chars: number;
  runtime_mode: CodingMode;
  currency: string;
  estimated_input_tokens_min: number;
  estimated_input_tokens_max: number;
  estimated_output_tokens_min: number;
  estimated_output_tokens_max: number;
  estimated_model_calls_min: number;
  estimated_model_calls_max: number;
  estimated_cost_min: number;
  estimated_cost_max: number;
  input_price_per_1m: number;
  output_price_per_1m: number;
  price_source: string;
  billing_authoritative: false;
  disclaimer: string;
}

export class MedicalCodingResource {
  constructor(private http: AxiosInstance) {}

  async predict(
    request: CodingPredictRequest,
    options?: iCoDerRequestOptions,
  ): Promise<CodingPredictResponse> {
    if (typeof request.text !== 'string' || !request.text.trim() || request.text.length > 16000) {
      throw new RangeError('text must contain between 1 and 16000 characters');
    }
    if (request.mode && request.mode !== 'corti_like_fast' && request.mode !== 'medcoder_deep') {
      throw new RangeError('mode must be corti_like_fast or medcoder_deep');
    }
    const codingSystems = normalizeCodingSystems(request);
    const filter = request.filter ? normalizeFilter(request.filter) : undefined;
    const { coding_system: _legacySystem, coding_systems: _systems, ...rest } = request;
    const { data } = await this.http.post<CodingPredictResponse>(
      '/api/v1/coding/predict',
      { ...rest, coding_systems: codingSystems, filter },
      requestConfig(options),
    );
    return data;
  }

  async estimateCost(
    inputChars: number,
    mode: CodingMode = 'corti_like_fast',
    options?: iCoDerRequestOptions,
  ): Promise<CodingPricingEstimate> {
    if (!Number.isInteger(inputChars) || inputChars < 0 || inputChars > 16000) {
      throw new RangeError('inputChars must be an integer between 0 and 16000');
    }
    const { data } = await this.http.get<CodingPricingEstimate>(
      '/api/v1/coding/pricing',
      requestConfig(options, { input_chars: inputChars, mode }),
    );
    return data;
  }
}

function normalizeCodingSystems(request: CodingPredictRequest): ChinaCodingSystem[] {
  if (request.coding_system && request.coding_systems) {
    throw new RangeError('use coding_system or coding_systems, not both');
  }
  const systems = request.coding_systems ?? (
    request.coding_system ? [request.coding_system] : ['icd10cn']
  );
  if (systems.length < 1 || systems.length > 2) {
    throw new RangeError('coding_systems must contain one or two systems');
  }
  if (systems.some((system) => system !== 'icd10cn' && system !== 'icd9cm3')) {
    throw new RangeError('coding systems must be icd10cn or icd9cm3');
  }
  if (new Set(systems).size !== systems.length) {
    throw new RangeError('coding_systems must not contain duplicates');
  }
  return [...systems] as ChinaCodingSystem[];
}

function normalizeFilter(filter: CodingCodeFilter): Required<CodingCodeFilter> {
  const include = normalizeTerms(filter.include ?? []);
  const exclude = normalizeTerms(filter.exclude ?? []);
  if (include.length + exclude.length > 100) {
    throw new RangeError('filter include and exclude may contain at most 100 entries combined');
  }
  return { include, exclude, expand: filter.expand ?? true };
}

function normalizeTerms(values: string[]): string[] {
  const seen = new Set<string>();
  return values.map((raw) => {
    if (typeof raw !== 'string') {
      throw new TypeError('code filter entries must be strings');
    }
    const value = raw.trim();
    if (!value || value.length > 64 || /[\u0000-\u001f\u007f]/.test(value)) {
      throw new RangeError('code filter entries must contain between 1 and 64 printable characters');
    }
    return value;
  }).filter((value) => {
    const key = value.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
