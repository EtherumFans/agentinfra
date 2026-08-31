import type { AxiosInstance } from 'axios';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export interface EnvironmentPlanRequest {
  environment_code: 'eu' | 'us' | 'cn';
  region_code: string;
  tenant_id?: string;
  dry_run?: boolean;
}

export class PlatformResource {
  constructor(private readonly http: AxiosInstance) {}

  async listEnvironments(options?: iCoDerRequestOptions): Promise<Record<string, unknown>> {
    const { data } = await this.http.get(
      '/api/platform/environments', requestConfig(options),
    );
    return data;
  }

  async listRegions(options?: iCoDerRequestOptions): Promise<Record<string, unknown>> {
    const { data } = await this.http.get('/api/platform/regions', requestConfig(options));
    return data;
  }

  async planEnvironment(
    request: EnvironmentPlanRequest,
    options?: iCoDerRequestOptions,
  ): Promise<Record<string, unknown>> {
    const { data } = await this.http.post('/api/platform/environments', {
      ...request,
      dry_run: request.dry_run ?? true,
    }, requestConfig(options));
    return data;
  }

  async currentTenant(options?: iCoDerRequestOptions): Promise<Record<string, unknown>> {
    const { data } = await this.http.get('/api/tenants/current', requestConfig(options));
    return data;
  }

  async tenantEnvironments(
    tenantId: string,
    options?: iCoDerRequestOptions,
  ): Promise<Record<string, unknown>> {
    const { data } = await this.http.get(
      `/api/tenants/${encodeURIComponent(tenantId)}/environments`,
      requestConfig(options),
    );
    return data;
  }
}
