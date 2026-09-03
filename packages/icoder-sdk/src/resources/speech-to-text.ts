// Speech To Text resource
import type { AxiosInstance } from 'axios';
import {
  ManagedSttSession,
  type ManagedSttConnectOptions,
} from '../managed-stt-session.js';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export interface SttSessionConfig {
  language?: string;
  punctuation?: 'auto' | 'spoken';
  interimResults?: boolean;
}

export interface TranscriptCreateRequest {
  recordingId: string;
  primaryLanguage?: string;
  spokenPunctuation?: boolean;
  automaticPunctuation?: boolean;
  isDictation?: boolean;
  isMultichannel?: boolean;
  diarize?: boolean;
  participants?: Array<{ channel: number; role: string }>;
  async?: boolean;
  replacements?: Array<{ find: string; replace: string }>;
  keyterms?: { terms: Array<{ term: string }> };
}

export interface TranscriptCreateResult {
  transcript: Record<string, unknown>;
  statusCode: number;
  location?: string;
}

export interface SttReadiness {
  configuration_status: 'configured_not_live_verified' | 'unavailable';
  verified_languages: string[];
  local_engine_enabled: boolean;
  whisper_fallback_configured: boolean;
  batch_provider_priority: string[];
  recording_storage_backend: 'encrypted_database';
  external_object_storage_configured: false;
  at_rest_encryption_enabled: boolean;
  durable_job_state: true;
  restart_recovery: true;
  queue_backend: 'in_process';
  horizontally_scalable_queue: false;
  pending_transcript_count: number;
  live_health_verified: false;
  maximum_recording_bytes: number;
  production_ready: false;
}

export class SpeechToTextResource {
  static readonly maximumRecordingBytes = 150 * 1024 * 1024;
  static readonly supportedRecordingMediaTypes = new Set([
    'application/octet-stream', 'audio/wav', 'audio/x-wav', 'audio/webm',
    'audio/mpeg', 'audio/mp3', 'audio/mpeg3', 'audio/mp4', 'audio/m4a',
    'audio/ogg', 'audio/opus', 'audio/vorbis', 'audio/flac',
  ]);

  constructor(
    private http: AxiosInstance,
    private getAccessToken: () => string | undefined = () => undefined,
    private ensureAccessToken: () => Promise<string | undefined> = async () => this.getAccessToken(),
  ) {}

  async readiness(options?: iCoDerRequestOptions): Promise<SttReadiness> {
    const { data } = await this.http.get<SttReadiness>(
      '/api/v2/tools/stt/readiness',
      requestConfig(options),
    );
    return data;
  }

  /** Corti-style managed connection with ready handshake and safe pre-audio reconnection. */
  async connectManagedSession(
    options: ManagedSttConnectOptions = {},
  ): Promise<ManagedSttSession> {
    const language = options.language || 'zh-CN';
    if (!language.toLowerCase().startsWith('zh')) {
      throw new Error('the verified real-time STT runtime currently supports zh-CN only');
    }
    const token = await this.ensureAccessToken();
    if (!token) throw new Error('an access token is required for real-time STT');
    const baseURL = (this.http.defaults.baseURL || '').replace(/\/$/, '');
    const wsUrl = baseURL.replace(/^http/, 'ws');
    const session = new ManagedSttSession(
      () => {
        const current = this.getAccessToken();
        if (!current) throw new Error('missing access token');
        return `${wsUrl}/ws/speech-to-text?token=${encodeURIComponent(current)}`;
      },
      { ...options, language },
      async () => {
        const current = await this.ensureAccessToken();
        if (!current) throw new Error('missing access token');
      },
    );
    return session.connect(options.awaitConfiguration ?? true);
  }

  /** Start a real-time STT session and return only after the server acknowledges `ready`. */
  async createSession(config: SttSessionConfig = {}): Promise<WebSocket> {
    const language = config.language || 'zh-CN';
    if (!language.toLowerCase().startsWith('zh')) {
      throw new Error('the verified real-time STT runtime currently supports zh-CN only');
    }
    if (config.punctuation === 'spoken') {
      throw new Error('spoken punctuation is not supported by the verified real-time STT runtime');
    }
    const token = this.getAccessToken();
    if (!token) throw new Error('an access token is required for real-time STT');
    const baseURL = (this.http.defaults.baseURL || '').replace(/\/$/, '');
    const wsUrl = baseURL.replace(/^http/, 'ws');
    const ws = new WebSocket(`${wsUrl}/ws/speech-to-text?token=${encodeURIComponent(token)}`);

    return new Promise((resolve, reject) => {
      let settled = false;
      const fail = (message: string) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        try { ws.close(1000, 'session setup failed'); } catch { /* best effort */ }
        reject(new Error(message));
      };
      const timeout = setTimeout(
        () => fail('real-time STT session setup timed out'),
        5000,
      );
      ws.onopen = () => {
        ws.send(JSON.stringify({
          type: 'start',
          mimeType: 'audio/webm;codecs=opus',
          language,
        }));
      };
      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(String(event.data));
          if (message?.type !== 'ready') {
            fail('real-time STT server did not acknowledge the session');
            return;
          }
          settled = true;
          clearTimeout(timeout);
          ws.onmessage = null;
          ws.onerror = null;
          ws.onclose = null;
          resolve(ws);
        } catch {
          fail('real-time STT server returned an invalid setup event');
        }
      };
      ws.onerror = () => {
        fail('real-time STT WebSocket connection failed');
      };
      ws.onclose = () => fail('real-time STT WebSocket closed before ready');
    });
  }

  async uploadRecording(
    interactionId: string,
    audio: ArrayBuffer | Uint8Array,
    mediaType = 'application/octet-stream',
    options?: iCoDerRequestOptions,
  ): Promise<{ recordingId: string }> {
    const bytes = audio instanceof Uint8Array ? audio : new Uint8Array(audio);
    if (bytes.byteLength === 0) throw new Error('audio cannot be empty');
    if (bytes.byteLength > SpeechToTextResource.maximumRecordingBytes) {
      throw new Error(`audio exceeds ${SpeechToTextResource.maximumRecordingBytes} bytes`);
    }
    const normalizedMediaType = mediaType.split(';', 1)[0].trim().toLowerCase();
    if (!SpeechToTextResource.supportedRecordingMediaTypes.has(normalizedMediaType)) {
      throw new Error(`unsupported recording media type: ${normalizedMediaType || '<empty>'}`);
    }
    const { data } = await this.http.post(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/recordings`,
      bytes,
      requestConfig(options, {}, { 'Content-Type': mediaType }),
    );
    return data;
  }

  async listRecordings(
    interactionId: string,
    options?: iCoDerRequestOptions,
  ): Promise<{ recordings: string[] }> {
    const { data } = await this.http.get(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/recordings`,
      requestConfig(options),
    );
    return data;
  }

  async downloadRecording(
    interactionId: string,
    recordingId: string,
    options?: iCoDerRequestOptions,
  ): Promise<ArrayBuffer> {
    const config = requestConfig(options);
    config.responseType = 'arraybuffer';
    const { data } = await this.http.get(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/recordings/${encodeURIComponent(recordingId)}`,
      config,
    );
    return data;
  }

  async deleteRecording(
    interactionId: string,
    recordingId: string,
    options?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.http.delete(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/recordings/${encodeURIComponent(recordingId)}`,
      requestConfig(options),
    );
  }

  async createTranscript(
    interactionId: string,
    request: TranscriptCreateRequest,
    options?: iCoDerRequestOptions,
  ): Promise<TranscriptCreateResult> {
    this.validateTranscriptRequest(request);
    const response = await this.http.post(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/transcripts`,
      { primaryLanguage: 'zh-CN', ...request },
      requestConfig(options),
    );
    return {
      transcript: response.data,
      statusCode: response.status,
      location: response.headers.location,
    };
  }

  async listTranscripts(
    interactionId: string,
    full = false,
    options?: iCoDerRequestOptions,
  ): Promise<{ transcripts: any[] | null }> {
    const { data } = await this.http.get(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/transcripts`,
      requestConfig(options, { full }),
    );
    return data;
  }

  async getTranscript(
    interactionId: string,
    transcriptId: string,
    options?: iCoDerRequestOptions,
  ): Promise<Record<string, unknown>> {
    const { data } = await this.http.get(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/transcripts/${encodeURIComponent(transcriptId)}`,
      requestConfig(options),
    );
    return data;
  }

  async getTranscriptStatus(
    interactionId: string,
    transcriptId: string,
    options?: iCoDerRequestOptions,
  ): Promise<{ status: string }> {
    const { data } = await this.http.get(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/transcripts/${encodeURIComponent(transcriptId)}/status`,
      requestConfig(options),
    );
    return data;
  }

  async deleteTranscript(
    interactionId: string,
    transcriptId: string,
    options?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.http.delete(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/transcripts/${encodeURIComponent(transcriptId)}`,
      requestConfig(options),
    );
  }

  private validateTranscriptRequest(request: TranscriptCreateRequest): void {
    const language = request.primaryLanguage || 'zh-CN';
    if (!language.toLowerCase().startsWith('zh')) {
      throw new Error('the verified STT runtime currently supports Chinese audio only');
    }
    const unsupported: string[] = [];
    if (request.automaticPunctuation === false && request.spokenPunctuation !== true) {
      unsupported.push('automaticPunctuation=false');
    }
    if (request.diarize) unsupported.push('diarize');
    const participants = request.participants ?? [];
    if (participants.some((item) => !Number.isInteger(item?.channel)
      || !['doctor', 'patient', 'multiple'].includes(item?.role))) {
      throw new Error('participants require an integer channel and a supported role');
    }
    if (request.isMultichannel) {
      const channels = participants.map((item) => item.channel).sort((a, b) => a - b);
      if (participants.length !== 2 || channels[0] !== 0 || channels[1] !== 1) {
        throw new Error('multichannel transcription requires participants for channels 0 and 1');
      }
    } else if (participants.length > 1) {
      unsupported.push('participants>1');
    }
    if (unsupported.length) {
      throw new Error(`unsupported STT features: ${unsupported.join(', ')}`);
    }
    if ((request.replacements?.length || 0) > 1000) {
      throw new Error('replacements cannot exceed 1000 items');
    }
    const keyterms = request.keyterms?.terms ?? [];
    if (!Array.isArray(keyterms) || keyterms.length > 1000) {
      throw new Error('keyterms cannot exceed 1000 items');
    }
    if (keyterms.some((item) => typeof item?.term !== 'string'
      || item.term.length < 1 || item.term.length > 50)) {
      throw new Error('each keyterm must contain 1 to 50 characters');
    }
  }
}
