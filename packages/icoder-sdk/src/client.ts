// iCoDerClient — main SDK entry point
import axios, {
  AxiosError, AxiosInstance, InternalAxiosRequestConfig, type Method,
} from 'axios';
import type { TokenResponse, ClientCredentials } from './types.js';
import { apiErrorFromAxios, iCoDerClientError } from './errors.js';
import { requestConfig, type iCoDerRequestOptions } from './request-options.js';

export interface iCoDerRetryConfig {
  /** Number of retries after the initial request. */
  maxRetries?: number;
  initialDelayMs?: number;
  maxDelayMs?: number;
}

export interface iCoDerConfig {
  baseURL: string;
  auth: ClientCredentials | { accessToken: string; refreshToken?: string };
  timeout?: number;
  retry?: false | iCoDerRetryConfig;
  tokenRefreshSkewMs?: number;
  onTokenRefresh?: (tokens: { accessToken: string; refreshToken?: string }) => void;
  onAuthFailure?: () => void;
}

type RetriableRequestConfig = InternalAxiosRequestConfig & {
  _icoderAuthRetry?: boolean;
  _icoderRetryCount?: number;
  _icoderMaxRetries?: number;
};

const IDEMPOTENT_METHODS = new Set(['get', 'head', 'options', 'put', 'delete']);

function abortError(): Error {
  const error = new Error('iCoDer request was aborted');
  error.name = 'AbortError';
  return error;
}

function sleep(delayMs: number, signal?: InternalAxiosRequestConfig['signal']): Promise<void> {
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener?.('abort', onAbort);
      resolve();
    }, delayMs);
    signal?.addEventListener?.('abort', onAbort, { once: true });
  });
}

function boundedInteger(value: number | undefined, fallback: number, name: string): number {
  const result = value ?? fallback;
  if (!Number.isInteger(result) || result < 0) {
    throw new RangeError(`${name} must be a non-negative integer`);
  }
  return result;
}

function retryAfterMs(value: unknown, maxDelayMs: number): number | undefined {
  if (typeof value !== 'string' && typeof value !== 'number') return undefined;
  const raw = String(value).trim();
  const seconds = Number(raw);
  let delay: number;
  if (Number.isFinite(seconds) && seconds >= 0) {
    delay = seconds * 1000;
  } else {
    const timestamp = Date.parse(raw);
    if (!Number.isFinite(timestamp)) return undefined;
    delay = Math.max(0, timestamp - Date.now());
  }
  return Math.min(maxDelayMs, Math.ceil(delay));
}

function requestHasIdempotencyKey(config: RetriableRequestConfig): boolean {
  const headers = config.headers;
  return Boolean(headers?.get?.('Idempotency-Key') || headers?.get?.('idempotency-key'));
}

function bearerValue(config: RetriableRequestConfig): string | undefined {
  const value = config.headers?.get?.('Authorization') || config.headers?.get?.('authorization');
  if (typeof value !== 'string' || !value.startsWith('Bearer ')) return undefined;
  return value.slice('Bearer '.length);
}

/** A sanitized authentication failure that never retains credential-bearing request data. */
export class iCoDerAuthenticationError extends iCoDerClientError {
  readonly isAxiosError = true;
  readonly status?: number;
  readonly requestId?: string;
  readonly response?: { status: number; headers: Record<string, string> };

  constructor(status?: number, requestId?: string) {
    super(status ? `iCoDer authentication failed with HTTP ${status}` : 'iCoDer authentication failed');
    this.name = 'iCoDerAuthenticationError';
    this.status = status;
    this.requestId = requestId;
    this.response = status
      ? { status, headers: requestId ? { 'x-request-id': requestId } : {} }
      : undefined;
  }
}

export class iCoDerClient {
  readonly http: AxiosInstance;
  private readonly authHttp: AxiosInstance;
  private readonly config: iCoDerConfig;
  private readonly maxRetries: number;
  private readonly initialDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly tokenRefreshSkewMs: number;
  private tokenExpiresAt = 0;
  private refreshFlight?: Promise<string>;

  constructor(config: iCoDerConfig) {
    this.config = config;
    const baseURL = config.baseURL.replace(/\/$/, '');
    this.http = axios.create({ baseURL, timeout: config.timeout || 120000 });
    this.authHttp = axios.create({ baseURL, timeout: config.timeout || 120000 });

    const retry = config.retry === false ? { maxRetries: 0 } : (config.retry || {});
    this.maxRetries = boundedInteger(retry.maxRetries, 2, 'retry.maxRetries');
    this.initialDelayMs = boundedInteger(retry.initialDelayMs, 250, 'retry.initialDelayMs');
    this.maxDelayMs = boundedInteger(retry.maxDelayMs, 2000, 'retry.maxDelayMs');
    if (this.maxDelayMs < this.initialDelayMs) {
      throw new RangeError('retry.maxDelayMs must be greater than or equal to retry.initialDelayMs');
    }
    this.tokenRefreshSkewMs = boundedInteger(config.tokenRefreshSkewMs, 30000, 'tokenRefreshSkewMs');

    this.http.interceptors.request.use(async (requestConfig) => {
      const token = this.clientCredentials()
        ? await this.ensureClientCredentialsToken()
        : this.config.auth.accessToken;
      if (token) requestConfig.headers.set('Authorization', `Bearer ${token}`);
      return requestConfig;
    });

    this.http.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => this.handleResponseError(error),
    );
  }

  /** Current bearer token used by transports (updated after refresh). */
  get accessToken(): string | undefined {
    return this.config.auth.accessToken;
  }

  /** Authenticate with client credentials without retaining the supplied secret. */
  async authenticate(clientId: string, clientSecret: string): Promise<TokenResponse> {
    return this.exchangeClientCredentials(clientId, clientSecret);
  }

  /** Ensure transports such as WebSockets receive a current managed bearer token. */
  async ensureAccessToken(): Promise<string | undefined> {
    return this.clientCredentials()
      ? this.ensureClientCredentialsToken()
      : this.config.auth.accessToken;
  }

  /** Low-level request surface with the same bounded per-request options as resources. */
  async request<T>(
    method: Method,
    path: string,
    body?: unknown,
    options?: iCoDerRequestOptions,
  ): Promise<T> {
    const url = this.safeRelativePath(path);
    const config = requestConfig(options);
    config.method = method;
    config.url = url;
    if (body !== undefined) config.data = body;
    const response = await this.http.request<T>(config);
    return response.data;
  }

  get<T>(path: string, options?: iCoDerRequestOptions): Promise<T> {
    return this.request<T>('GET', path, undefined, options);
  }

  post<T>(path: string, body?: unknown, options?: iCoDerRequestOptions): Promise<T> {
    return this.request<T>('POST', path, body, options);
  }

  put<T>(path: string, body?: unknown, options?: iCoDerRequestOptions): Promise<T> {
    return this.request<T>('PUT', path, body, options);
  }

  patch<T>(path: string, body?: unknown, options?: iCoDerRequestOptions): Promise<T> {
    return this.request<T>('PATCH', path, body, options);
  }

  delete<T>(path: string, options?: iCoDerRequestOptions): Promise<T> {
    return this.request<T>('DELETE', path, undefined, options);
  }

  private clientCredentials(): ClientCredentials | undefined {
    return 'clientId' in this.config.auth ? this.config.auth : undefined;
  }

  private async exchangeClientCredentials(clientId: string, clientSecret: string): Promise<TokenResponse> {
    const form = new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: clientId,
      client_secret: clientSecret,
      scope: 'api:read api:write',
    });
    try {
      const { data } = await this.authHttp.post<TokenResponse>(
        `${this.authHttp.defaults.baseURL}/api/oauth/token`,
        form,
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      );
      return data;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const requestId = error.response?.headers?.['x-request-id'];
        throw new iCoDerAuthenticationError(
          error.response?.status,
          typeof requestId === 'string' ? requestId : undefined,
        );
      }
      throw new iCoDerAuthenticationError();
    }
  }

  private async ensureClientCredentialsToken(force = false): Promise<string> {
    const auth = this.clientCredentials();
    if (!auth) throw new iCoDerAuthenticationError();
    const now = Date.now();
    if (!force && auth.accessToken && now + this.tokenRefreshSkewMs < this.tokenExpiresAt) {
      return auth.accessToken;
    }
    if (this.refreshFlight) return this.refreshFlight;

    const flight = this.exchangeClientCredentials(
      auth.clientId,
      auth.clientSecret,
    ).then((tokens) => {
      auth.accessToken = tokens.access_token;
      const ttlMs = Math.max(0, (tokens.expires_in ?? 300) * 1000);
      const effectiveSkewMs = Math.min(this.tokenRefreshSkewMs, ttlMs / 2);
      this.tokenExpiresAt = Date.now() + ttlMs - effectiveSkewMs;
      this.config.onTokenRefresh?.({ accessToken: tokens.access_token });
      return tokens.access_token;
    });
    this.refreshFlight = flight;
    try {
      return await flight;
    } finally {
      if (this.refreshFlight === flight) this.refreshFlight = undefined;
    }
  }

  private async refreshUserToken(staleToken?: string): Promise<string> {
    if (this.clientCredentials()) return this.ensureClientCredentialsToken(true);
    const auth = this.config.auth as { accessToken: string; refreshToken?: string };
    if (staleToken && auth.accessToken !== staleToken) return auth.accessToken;
    if (!auth.refreshToken) throw new iCoDerAuthenticationError(401);
    if (this.refreshFlight) return this.refreshFlight;

    const refreshToken = auth.refreshToken;
    const flight = (async () => {
      try {
        const { data } = await this.authHttp.post<TokenResponse>(
          '/api/auth/refresh',
          { refresh_token: refreshToken },
        );
        const nextRefreshToken = data.refresh_token || refreshToken;
        auth.accessToken = data.access_token;
        auth.refreshToken = nextRefreshToken;
        this.config.onTokenRefresh?.({ accessToken: data.access_token, refreshToken: nextRefreshToken });
        return data.access_token;
      } catch (error) {
        if (axios.isAxiosError(error)) {
          const requestId = error.response?.headers?.['x-request-id'];
          throw new iCoDerAuthenticationError(
            error.response?.status,
            typeof requestId === 'string' ? requestId : undefined,
          );
        }
        throw new iCoDerAuthenticationError();
      }
    })();
    this.refreshFlight = flight;
    try {
      return await flight;
    } finally {
      if (this.refreshFlight === flight) this.refreshFlight = undefined;
    }
  }

  private shouldRetry(config: RetriableRequestConfig, status?: number): boolean {
    if (status !== 408 && status !== 429 && !(status && status >= 500 && status <= 599)) {
      return false;
    }
    const method = (config.method || 'get').toLowerCase();
    if (!IDEMPOTENT_METHODS.has(method) && !requestHasIdempotencyKey(config)) return false;
    const maxRetries = config._icoderMaxRetries ?? this.maxRetries;
    return (config._icoderRetryCount || 0) < maxRetries;
  }

  private async handleResponseError(error: AxiosError): Promise<unknown> {
    const config = error.config as RetriableRequestConfig | undefined;
    const status = error.response?.status;
    if (!config) return Promise.reject(error);

    if (status === 401 && !config._icoderAuthRetry) {
      config._icoderAuthRetry = true;
      const userAuth = this.clientCredentials()
        ? undefined
        : this.config.auth as { accessToken: string; refreshToken?: string };
      if (!this.clientCredentials() && !userAuth?.refreshToken) {
        this.config.onAuthFailure?.();
        return Promise.reject(apiErrorFromAxios(error));
      }
      try {
        const token = this.clientCredentials()
          ? await this.refreshClientCredentialsAfter401(bearerValue(config))
          : await this.refreshUserToken(bearerValue(config));
        config.headers.set('Authorization', `Bearer ${token}`);
        return this.http(config);
      } catch (refreshError) {
        this.config.onAuthFailure?.();
        return Promise.reject(refreshError);
      }
    }

    if (this.shouldRetry(config, status)) {
      const retryCount = config._icoderRetryCount || 0;
      config._icoderRetryCount = retryCount + 1;
      const headerDelay = retryAfterMs(error.response?.headers?.['retry-after'], this.maxDelayMs);
      const delay = headerDelay ?? Math.min(this.maxDelayMs, this.initialDelayMs * (2 ** retryCount));
      if (delay > 0) await sleep(delay, config.signal);
      return this.http(config);
    }
    return Promise.reject(apiErrorFromAxios(error));
  }

  private async refreshClientCredentialsAfter401(staleToken?: string): Promise<string> {
    const auth = this.clientCredentials();
    if (!auth) throw new iCoDerAuthenticationError(401);
    if (staleToken && auth.accessToken !== staleToken && auth.accessToken) {
      return auth.accessToken;
    }
    return this.ensureClientCredentialsToken(true);
  }

  private safeRelativePath(path: string): string {
    if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')
        || path.includes('\\') || path.includes('#') || path.includes('?')) {
      throw new TypeError('request path must be an absolute-path reference on the configured origin');
    }
    const base = new URL(this.http.defaults.baseURL || 'http://localhost');
    const resolved = new URL(path, base);
    if (resolved.origin !== base.origin || resolved.username || resolved.password) {
      throw new TypeError('request path must stay on the configured origin');
    }
    return `${resolved.pathname}${resolved.search}`;
  }
}
