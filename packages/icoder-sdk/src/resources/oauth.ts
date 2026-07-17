// OAuth resource
import type { AxiosInstance } from 'axios';
import type { TokenResponse } from '../types.js';

export class OAuthResource {
  constructor(private http: AxiosInstance) {}

  async getToken(clientId: string, clientSecret: string): Promise<TokenResponse> {
    const { data } = await this.http.post<TokenResponse>('/api/oauth/token', {
      client_id: clientId,
      client_secret: clientSecret,
      grant_type: 'client_credentials',
    });
    return data;
  }

  async createClient(name: string, description: string, scopes: string): Promise<{ client_id: string; client_secret: string }> {
    const { data } = await this.http.post('/api/oauth/clients', { name, description, scopes });
    return data;
  }

  async listClients(): Promise<{ clients: any[] }> {
    const { data } = await this.http.get('/api/oauth/clients');
    return data;
  }

  async revokeClient(clientId: string): Promise<void> {
    await this.http.delete(`/api/oauth/clients/${clientId}`);
  }
}
