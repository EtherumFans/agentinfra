// OAuth resource
import type { AxiosInstance } from 'axios';
import type { TokenResponse } from '../types.js';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export class OAuthResource {
  constructor(private http: AxiosInstance) {}

  async getToken(
    clientId: string,
    clientSecret: string,
    options?: iCoDerRequestOptions,
  ): Promise<TokenResponse> {
    const form = new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: clientId,
      client_secret: clientSecret,
      scope: 'api:read api:write',
    });
    const { data } = await this.http.post<TokenResponse>(
      '/api/oauth/token',
      form,
      requestConfig(
        options,
        {},
        { 'Content-Type': 'application/x-www-form-urlencoded' },
      ),
    );
    return data;
  }

  async createClient(
    name: string,
    description: string,
    scopes: string,
    delegation: { allowedAgentIds?: string[]; allowedPurposes?: string[] } = {},
    options?: iCoDerRequestOptions,
  ): Promise<{ client_id: string; client_secret: string; allowed_agent_ids?: string[]; allowed_purposes?: string[] }> {
    const form = new URLSearchParams({
      name,
      description,
      scopes,
      allowed_agent_ids: (delegation.allowedAgentIds ?? []).join(','),
      allowed_purposes: (delegation.allowedPurposes ?? []).join(','),
    });
    const { data } = await this.http.post(
      '/api/oauth/clients',
      form,
      requestConfig(
        options,
        {},
        { 'Content-Type': 'application/x-www-form-urlencoded' },
      ),
    );
    return data;
  }

  async listClients(options?: iCoDerRequestOptions): Promise<{ clients: any[] }> {
    const { data } = await this.http.get('/api/oauth/clients', requestConfig(options));
    return data;
  }

  async updateDelegation(
    clientId: string,
    allowedAgentIds: string[],
    allowedPurposes: string[],
    options?: iCoDerRequestOptions,
  ): Promise<Record<string, unknown>> {
    const { data } = await this.http.patch(
      `/api/clients/${encodeURIComponent(clientId)}/delegation`,
      { allowed_agent_ids: allowedAgentIds, allowed_purposes: allowedPurposes },
      requestConfig(options),
    );
    return data;
  }

  async revokeClient(clientId: string, options?: iCoDerRequestOptions): Promise<void> {
    await this.http.delete(
      `/api/oauth/clients/${encodeURIComponent(clientId)}`,
      requestConfig(options),
    );
  }
}
