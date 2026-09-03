import type { AxiosInstance } from 'axios';
import {
  ManagedStreamsSession,
  ManagedStreamsSessionError,
  type ManagedStreamsConnectOptions,
} from '../managed-streams-session.js';

export class StreamsResource {
  constructor(
    private readonly http: AxiosInstance,
    private readonly getAccessToken: () => string | undefined,
    private readonly ensureAccessToken: () => Promise<string | undefined>,
  ) {}

  async connect(options: ManagedStreamsConnectOptions): Promise<ManagedStreamsSession> {
    await this.ensureAccessToken();
    const baseURL = (this.http.defaults.baseURL || '').replace(/\/$/, '');
    const websocketBase = baseURL.replace(/^http/, 'ws');
    const session = new ManagedStreamsSession(() => {
      const token = this.getAccessToken();
      if (!token) throw new Error('missing access token');
      const query = new URLSearchParams({
        environment: options.environment ?? 'cn',
        'tenant-name': options.tenantName,
        token,
      });
      return `${websocketBase}/api/v2/tools/streams/${encodeURIComponent(options.interactionId)}?${query}`;
    }, options);
    return session.connect();
  }

  async resume(
    options: ManagedStreamsConnectOptions,
  ): Promise<ManagedStreamsSession> {
    if (options.configuration.retentionPolicy !== 'retain') {
      throw new ManagedStreamsSessionError('stream_resume_requires_retention');
    }
    return this.connect({ ...options, requireCheckpointResume: true });
  }
}
