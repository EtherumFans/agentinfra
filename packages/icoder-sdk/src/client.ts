// iCoDerClient — main SDK entry point
import axios, { AxiosInstance } from 'axios';
import type { TokenResponse, ClientCredentials } from './types';

export interface iCoDerConfig {
  baseURL: string;
  auth: ClientCredentials | { accessToken: string; refreshToken?: string };
  timeout?: number;
  onTokenRefresh?: (tokens: { accessToken: string; refreshToken: string }) => void;
  onAuthFailure?: () => void;
}

export class iCoDerClient {
  readonly http: AxiosInstance;
  private config: iCoDerConfig;

  constructor(config: iCoDerConfig) {
    this.config = config;

    this.http = axios.create({
      baseURL: config.baseURL.replace(/\/$/, ''),
      timeout: config.timeout || 120000,
    });

    // Attach token
    this.http.interceptors.request.use((reqConfig) => {
      if ('accessToken' in config.auth) {
        reqConfig.headers.Authorization = `Bearer ${config.auth.accessToken}`;
      }
      return reqConfig;
    });

    // Auto-refresh on 401
    this.http.interceptors.response.use(
      (response) => response,
      async (error) => {
        if (error.response?.status === 401) {
          if ('refreshToken' in config.auth && config.auth.refreshToken && error.config && !(error.config as any)._retry) {
            (error.config as any)._retry = true;
            try {
              const { data } = await axios.post<TokenResponse>(
                `${config.baseURL}/api/auth/refresh`,
                { refresh_token: config.auth.refreshToken }
              );
              (config.auth as any).accessToken = data.access_token;
              (config.auth as any).refreshToken = data.refresh_token;
              config.onTokenRefresh?.({ accessToken: data.access_token, refreshToken: data.refresh_token });
              error.config.headers.Authorization = `Bearer ${data.access_token}`;
              return this.http(error.config);
            } catch {
              config.onAuthFailure?.();
            }
          } else {
            config.onAuthFailure?.();
          }
        }
        return Promise.reject(error);
      }
    );
  }

  /** Authenticate with client credentials (machine-to-machine) */
  async authenticate(clientId: string, clientSecret: string): Promise<TokenResponse> {
    const { data } = await axios.post<TokenResponse>(
      `${this.config.baseURL}/api/oauth/token`,
      { client_id: clientId, client_secret: clientSecret, grant_type: 'client_credentials' }
    );
    return data;
  }
}
