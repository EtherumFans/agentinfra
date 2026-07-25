// PatientContext resource — A1C.3 HIS/EMR Integration Contract §2
// Closes RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT.
import type { AxiosInstance } from 'axios';

export type VisitType =
  | 'inpatient' | 'outpatient' | 'emergency' | 'day-case'
  | 'home-care' | 'telemed' | 'rehab' | 'observation';

export type PurposeOfUse =
  | 'treatment' | 'billing' | 'operations' | 'quality' | 'research' | 'public-health';

export type ConsentLegalBasis =
  | 'patient-consent' | 'treatment-necessity'
  | 'legal-obligation' | 'vital-interest' | 'public-interest';

export type ContextStatus = 'active' | 'expired' | 'deleted';

export interface PatientContextCreate {
  tenant_id: string;
  source_system: string;
  patient_id: string;
  encounter_id?: string | null;
  visit_type: VisitType;
  department_id: string;
  ward_id?: string | null;
  clinician_id: string;
  document_ids?: string[];
  purpose_of_use: PurposeOfUse;
  consent_legal_basis: ConsentLegalBasis;
  trace_id?: string | null;
}

export interface PatientContextResponse {
  id: string;
  organization_id: string;
  tenant_id: string;
  source_system: string;
  patient_id: string;
  encounter_id: string | null;
  visit_type: VisitType;
  department_id: string;
  ward_id: string | null;
  clinician_id: string;
  document_ids: string[];
  purpose_of_use: PurposeOfUse;
  consent_legal_basis: ConsentLegalBasis;
  trace_id: string | null;
  status: ContextStatus;
  expires_at: string;
  created_at: string;
  updated_at: string;
}

export class PatientContextResource {
  constructor(private http: AxiosInstance) {}

  async create(
    body: PatientContextCreate,
    options?: { idempotencyKey?: string },
  ): Promise<PatientContextResponse> {
    const headers: Record<string, string> = {};
    if (options?.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
    const { data } = await this.http.post<PatientContextResponse>(
      '/api/v1/patient-context', body, { headers },
    );
    return data;
  }

  async get(contextId: string): Promise<PatientContextResponse> {
    const { data } = await this.http.get<PatientContextResponse>(
      `/api/v1/patient-context/${contextId}`,
    );
    return data;
  }

  async delete(contextId: string): Promise<void> {
    await this.http.delete(`/api/v1/patient-context/${contextId}`);
  }

  async extend(
    contextId: string,
    extendSeconds: number,
  ): Promise<PatientContextResponse> {
    const { data } = await this.http.post<PatientContextResponse>(
      `/api/v1/patient-context/${contextId}/extend`,
      { extend_seconds: extendSeconds },
    );
    return data;
  }
}
