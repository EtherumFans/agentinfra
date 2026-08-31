export interface StreamsParticipant { channel: number; role: string }
export interface StreamsReplacement { find: string; replace: string }

export interface StreamsConfiguration {
  transcription: {
    primaryLanguage: string;
    diarize?: boolean;
    isDiarization?: boolean;
    isMultichannel?: boolean;
    participants?: StreamsParticipant[];
  };
  mode: {
    type: 'facts' | 'transcription';
    outputLocale?: string;
    factGenerationInterval?: 'fixed' | 'fast_init';
  };
  retentionPolicy?: 'none' | 'retain';
  audioFormat?: string;
  audioEvents?: { enabled: boolean };
  replacements?: StreamsReplacement[];
  keyterms?: { terms: Array<{ term: string }> };
}

export interface ManagedStreamsConnectOptions {
  interactionId: string;
  tenantName: string;
  environment?: 'cn' | 'eu' | 'us';
  configuration: StreamsConfiguration;
  setupTimeoutMs?: number;
  requireCheckpointResume?: boolean;
}

export type ManagedStreamsServerMessage =
  | {
      type: 'CONFIG_ACCEPTED';
      sessionId: string;
      configuration: StreamsConfiguration;
      resumed: boolean;
      restoredAudioBytes: number;
      restoredTranscriptMessages: number;
      restoredFactMessages: number;
    }
  | { type: 'CONFIG_DENIED' | 'CONFIG_MISSING' | 'CONFIG_NOT_PROVIDED' | 'CONFIG_ALREADY_RECEIVED' }
  | { type: 'transcript'; data: Array<Record<string, unknown>> }
  | { type: 'facts'; fact: Array<Record<string, unknown>> }
  | {
      type: 'audioEvent';
      data: {
        event: 'speechQualityIssueDetected' | 'speechQualityIssueRecovered'
          | 'longSilenceDetected' | 'longSilenceRecovered';
        channel: number;
        startTimeMs: number;
      };
    }
  | { type: 'flushed' }
  | { type: 'delta_usage' | 'usage'; credits: number }
  | { type: 'ENDED' }
  | { type: 'error'; code?: string }
  | { type: 'unknown' };

export interface ManagedStreamsEventMap {
  ready: Extract<ManagedStreamsServerMessage, { type: 'CONFIG_ACCEPTED' }>;
  message: ManagedStreamsServerMessage;
  error: ManagedStreamsSessionError;
  close: { code: number; wasClean: boolean };
}

export class ManagedStreamsSessionError extends Error {
  readonly code: string;
  readonly retryable: boolean;

  constructor(code: string, retryable = false) {
    super(`iCoDer managed Streams session failed (${code})`);
    this.name = 'ManagedStreamsSessionError';
    this.code = code;
    this.retryable = retryable;
  }
}

type Handler<K extends keyof ManagedStreamsEventMap> =
  (event: ManagedStreamsEventMap[K]) => void;

const MAX_AUDIO_BYTES = 32 * 1024 * 1024;
const MAX_CHUNK_BYTES = 64_000;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SAFE_CODE = /^[A-Za-z0-9_.:-]{1,128}$/;
const STREAM_AUDIO_FORMATS = new Map([
  ['audio/ogg', 'ogg'], ['audio/webm', 'webm'], ['audio/opus', 'ogg'],
  ['audio/vorbis', 'ogg'], ['audio/mpeg', 'mpeg'], ['audio/mp3', 'mpeg'],
  ['audio/mpeg3', 'mpeg'], ['audio/flac', 'flac'], ['audio/mp4', 'mp4'],
  ['audio/m4a', 'mp4'],
  ['audio/pcm', 'pcm'],
]);
const STREAM_AUDIO_CODECS = new Set(['flac', 'opus', 'vorbis']);
const STREAM_AUDIO_EVENTS = new Set([
  'speechQualityIssueDetected', 'speechQualityIssueRecovered',
  'longSilenceDetected', 'longSilenceRecovered',
]);

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function parseMessage(raw: unknown): ManagedStreamsServerMessage {
  let value: Record<string, unknown> | undefined;
  try { value = record(JSON.parse(String(raw))); } catch { return { type: 'unknown' }; }
  if (!value || typeof value.type !== 'string') return { type: 'unknown' };
  switch (value.type) {
    case 'CONFIG_ACCEPTED': {
      const configuration = record(value.configuration);
      if (typeof value.sessionId !== 'string' || !UUID_PATTERN.test(value.sessionId) || !configuration) {
        return { type: 'unknown' };
      }
      const counters = [
        value.restoredAudioBytes ?? 0,
        value.restoredTranscriptMessages ?? 0,
        value.restoredFactMessages ?? 0,
      ];
      if (counters.some((item) => !Number.isInteger(item) || Number(item) < 0)) {
        return { type: 'unknown' };
      }
      return {
        type: 'CONFIG_ACCEPTED',
        sessionId: value.sessionId,
        configuration: configuration as unknown as StreamsConfiguration,
        resumed: value.resumed === true,
        restoredAudioBytes: Number(counters[0]),
        restoredTranscriptMessages: Number(counters[1]),
        restoredFactMessages: Number(counters[2]),
      };
    }
    case 'CONFIG_DENIED':
    case 'CONFIG_MISSING':
    case 'CONFIG_NOT_PROVIDED':
    case 'CONFIG_ALREADY_RECEIVED':
      return { type: value.type };
    case 'transcript':
      return Array.isArray(value.data)
        ? { type: 'transcript', data: value.data.filter(record) as Array<Record<string, unknown>> }
        : { type: 'unknown' };
    case 'facts':
      return Array.isArray(value.fact)
        ? { type: 'facts', fact: value.fact.filter(record) as Array<Record<string, unknown>> }
        : { type: 'unknown' };
    case 'audioEvent': {
      const data = record(value.data);
      return data
        && typeof data.event === 'string' && STREAM_AUDIO_EVENTS.has(data.event)
        && Number.isInteger(data.channel) && Number(data.channel) >= 0 && Number(data.channel) <= 15
        && Number.isInteger(data.startTimeMs) && Number(data.startTimeMs) >= 0
        ? {
            type: 'audioEvent',
            data: {
              event: data.event as Extract<ManagedStreamsServerMessage, { type: 'audioEvent' }>['data']['event'],
              channel: Number(data.channel),
              startTimeMs: Number(data.startTimeMs),
            },
          }
        : { type: 'unknown' };
    }
    case 'flushed':
      return { type: 'flushed' };
    case 'delta_usage':
    case 'usage':
      return typeof value.credits === 'number' && Number.isFinite(value.credits) && value.credits >= 0
        ? { type: value.type, credits: value.credits }
        : { type: 'unknown' };
    case 'ENDED':
      return { type: 'ENDED' };
    case 'error': {
      const error = record(value.error);
      const code = error?.id;
      return {
        type: 'error',
        ...(typeof code === 'string' && SAFE_CODE.test(code) ? { code } : {}),
      };
    }
    default:
      return { type: 'unknown' };
  }
}

function validateOptions(options: ManagedStreamsConnectOptions): void {
  if (!UUID_PATTERN.test(options.interactionId)) throw new TypeError('interactionId must be a UUID');
  if (!options.tenantName || options.tenantName.length > 128) throw new TypeError('tenantName is invalid');
  const cfg = options.configuration;
  if (!cfg?.transcription?.primaryLanguage?.toLowerCase().startsWith('zh')) {
    throw new ManagedStreamsSessionError('unsupported_primary_language');
  }
  if (cfg.transcription.diarize || cfg.transcription.isDiarization) {
    throw new ManagedStreamsSessionError('diarization_not_available');
  }
  if (cfg.mode?.type === 'facts' && !cfg.mode.outputLocale) {
    throw new ManagedStreamsSessionError('output_locale_required');
  }
  const keyterms = cfg.keyterms?.terms ?? [];
  if (!Array.isArray(keyterms) || keyterms.length > 1000) {
    throw new ManagedStreamsSessionError('keyterm_limit_exceeded');
  }
  if (keyterms.some((item) => typeof item?.term !== 'string'
    || item.term.length < 1 || item.term.length > 50)) {
    throw new ManagedStreamsSessionError('keyterm_invalid');
  }
  const audioProfile = cfg.audioFormat ? validateAudioFormat(cfg.audioFormat) : undefined;
  if (cfg.audioEvents?.enabled && audioProfile?.container !== 'pcm') {
    throw new ManagedStreamsSessionError('audio_events_require_pcm');
  }
  const participantChannels = new Set((cfg.transcription.participants ?? []).map((item) => item.channel));
  if (cfg.transcription.isMultichannel) {
    if (audioProfile?.container !== 'pcm' || !audioProfile.channels || audioProfile.channels < 2) {
      throw new ManagedStreamsSessionError('multichannel_pcm_format_required');
    }
    const expected = Array.from({ length: audioProfile.channels }, (_, channel) => channel);
    if (participantChannels.size !== expected.length || expected.some((channel) => !participantChannels.has(channel))) {
      throw new ManagedStreamsSessionError('multichannel_participants_must_match_channels');
    }
  } else {
    if (audioProfile?.container === 'pcm' && (audioProfile.channels ?? 1) !== 1) {
      throw new ManagedStreamsSessionError('multichannel_flag_required');
    }
    if ([...participantChannels].some((channel) => channel !== 0)) {
      throw new ManagedStreamsSessionError('mono_participant_channel_required');
    }
  }
}

function validateAudioFormat(value: string): { container: string; channels?: number } {
  const parts = value.split(';').map((part) => part.trim());
  const mime = parts[0]?.toLowerCase() ?? '';
  const container = STREAM_AUDIO_FORMATS.get(mime);
  if (!container) throw new ManagedStreamsSessionError('audio_format_not_supported');
  if (container === 'pcm') {
    const parameters = new Map<string, string>();
    for (const parameter of parts.slice(1)) {
      const match = /^(rate|channels|bits|endian|encoding)\s*=\s*"?([^"\s]+)"?$/i.exec(parameter);
      const key = match?.[1].toLowerCase();
      if (!match || !key || parameters.has(key)) {
        throw new ManagedStreamsSessionError('audio_format_not_supported');
      }
      parameters.set(key, match[2].toLowerCase());
    }
    if (!parameters.has('rate') || !parameters.has('channels') || !parameters.has('bits')) {
      throw new ManagedStreamsSessionError('audio_format_not_supported');
    }
    const channels = Number(parameters.get('channels'));
    if (parameters.get('rate') !== '16000'
      || !Number.isInteger(channels) || channels < 1 || channels > 8
      || parameters.get('bits') !== '16'
      || (parameters.get('endian') ?? 'little') !== 'little'
      || (parameters.get('encoding') ?? 'sint') !== 'sint') {
      throw new ManagedStreamsSessionError('raw_pcm_profile_not_available');
    }
    return { container, channels };
  }
  let codec: string | undefined;
  for (const parameter of parts.slice(1)) {
    const match = /^codecs\s*=\s*"?([^"\s]+)"?$/i.exec(parameter);
    if (!match || !STREAM_AUDIO_CODECS.has(match[1].toLowerCase()) || codec) {
      throw new ManagedStreamsSessionError('audio_format_not_supported');
    }
    codec = match[1].toLowerCase();
  }
  if (codec && container !== 'ogg' && container !== 'webm') {
    throw new ManagedStreamsSessionError('audio_format_not_supported');
  }
  const implied = mime === 'audio/opus' ? 'opus' : mime === 'audio/vorbis' ? 'vorbis' : undefined;
  if (implied && codec && codec !== implied) {
    throw new ManagedStreamsSessionError('audio_format_not_supported');
  }
  return { container };
}

export class ManagedStreamsSession {
  private readonly listeners = new Map<keyof ManagedStreamsEventMap, Set<(event: never) => void>>();
  private readonly setupTimeoutMs: number;
  private socket?: WebSocket;
  private ready = false;
  private ended = false;
  private endSent = false;
  private audioBytes = 0;
  private durableAudioBytes = 0;
  private readyMessage?: Extract<ManagedStreamsServerMessage, { type: 'CONFIG_ACCEPTED' }>;
  private terminalError?: ManagedStreamsSessionError;
  private endedPromise?: Promise<void>;
  private resolveEnded?: () => void;
  private rejectEnded?: (error: ManagedStreamsSessionError) => void;

  constructor(
    private readonly urlFactory: () => string,
    private readonly options: ManagedStreamsConnectOptions,
  ) {
    validateOptions(options);
    this.setupTimeoutMs = options.setupTimeoutMs ?? 10_000;
    if (!Number.isInteger(this.setupTimeoutMs) || this.setupTimeoutMs < 1 || this.setupTimeoutMs > 60_000) {
      throw new RangeError('setupTimeoutMs must be an integer between 1 and 60000');
    }
  }

  get isReady(): boolean { return this.ready; }
  get isEnded(): boolean { return this.ended; }
  get acceptedConfiguration(): Extract<ManagedStreamsServerMessage, { type: 'CONFIG_ACCEPTED' }> | undefined {
    return this.readyMessage;
  }

  on<K extends keyof ManagedStreamsEventMap>(event: K, handler: Handler<K>): this {
    const handlers = this.listeners.get(event) ?? new Set();
    handlers.add(handler as (event: never) => void);
    this.listeners.set(event, handlers);
    return this;
  }

  off<K extends keyof ManagedStreamsEventMap>(event: K, handler?: Handler<K>): this {
    if (!handler) this.listeners.delete(event);
    else this.listeners.get(event)?.delete(handler as (event: never) => void);
    return this;
  }

  async connect(): Promise<this> {
    if (this.socket) throw new ManagedStreamsSessionError('already_started');
    await new Promise<void>((resolve, reject) => {
      let settled = false;
      let socket: WebSocket;
      const fail = (error: ManagedStreamsSessionError) => {
        if (settled) return;
        settled = true;
        this.terminalError = error;
        clearTimeout(timeout);
        try { socket.close(1000, 'setup failed'); } catch { /* best effort */ }
        reject(error);
      };
      const timeout = setTimeout(
        () => fail(new ManagedStreamsSessionError('setup_timeout', true)),
        this.setupTimeoutMs,
      );
      try {
        socket = new WebSocket(this.urlFactory());
        this.socket = socket;
      } catch {
        clearTimeout(timeout);
        reject(new ManagedStreamsSessionError('connection_failed', true));
        return;
      }
      socket.onopen = () => {
        try {
          socket.send(JSON.stringify({ type: 'config', configuration: this.options.configuration }));
        } catch {
          fail(new ManagedStreamsSessionError('configuration_send_failed', true));
        }
      };
      socket.onmessage = (event) => {
        const message = parseMessage(event.data);
        this.emit('message', message);
        if (!settled) {
          if (message.type === 'CONFIG_ACCEPTED') {
            if (this.options.requireCheckpointResume && !message.resumed) {
              fail(new ManagedStreamsSessionError('stream_checkpoint_not_found'));
              return;
            }
            settled = true;
            clearTimeout(timeout);
            this.ready = true;
            this.readyMessage = message;
            this.audioBytes = message.restoredAudioBytes;
            this.durableAudioBytes = message.restoredAudioBytes;
            this.emit('ready', message);
            resolve();
            return;
          }
          if (message.type.startsWith('CONFIG_') || message.type === 'unknown') {
            fail(new ManagedStreamsSessionError(
              message.type === 'unknown' ? 'invalid_configuration_response' : message.type.toLowerCase(),
            ));
            return;
          }
        }
        if (message.type === 'flushed') {
          this.durableAudioBytes = this.audioBytes;
        }
        if (message.type === 'error') {
          const error = new ManagedStreamsSessionError(message.code ?? 'server_error');
          this.emit('error', error);
        } else if (message.type === 'ENDED') {
          this.ended = true;
          this.ready = false;
          this.resolveEnded?.();
        }
      };
      socket.onerror = () => {
        const error = new ManagedStreamsSessionError('transport_error', true);
        this.emit('error', error);
        if (!settled) fail(error);
      };
      socket.onclose = (event) => {
        this.ready = false;
        clearTimeout(timeout);
        this.emit('close', { code: event.code, wasClean: event.wasClean });
        if (!settled) {
          fail(new ManagedStreamsSessionError('closed_before_configuration', true));
        } else if (!this.ended) {
          const safelyCheckpointed = (
            this.options.configuration.retentionPolicy === 'retain'
            && this.audioBytes > 0
            && this.durableAudioBytes === this.audioBytes
          );
          const error = new ManagedStreamsSessionError(
            safelyCheckpointed
              ? 'stream_resume_required'
              : this.audioBytes > 0 ? 'audio_resume_unsupported' : 'stream_interrupted',
            safelyCheckpointed || this.audioBytes === 0,
          );
          this.terminalError = error;
          this.emit('error', error);
          this.rejectEnded?.(error);
        }
      };
    });
    return this;
  }

  sendAudio(data: ArrayBuffer | ArrayBufferView | Blob): void {
    this.assertWritable();
    const size = data instanceof ArrayBuffer
      ? data.byteLength
      : ArrayBuffer.isView(data)
        ? data.byteLength
        : typeof Blob !== 'undefined' && data instanceof Blob
          ? data.size
          : undefined;
    if (size === undefined) throw new TypeError('audio must be binary data');
    if (size < 1) throw new RangeError('audio cannot be empty');
    if (size > MAX_CHUNK_BYTES) throw new RangeError('audio chunk exceeds 64000 bytes');
    if (this.audioBytes + size > MAX_AUDIO_BYTES) {
      throw new RangeError(`audio exceeds the ${MAX_AUDIO_BYTES}-byte session limit`);
    }
    this.audioBytes += size;
    this.socket!.send(data);
  }

  flush(): void {
    this.assertWritable();
    this.socket!.send(JSON.stringify({ type: 'flush' }));
  }

  end(): void {
    this.assertWritable();
    this.endSent = true;
    this.socket!.send(JSON.stringify({ type: 'end' }));
  }

  waitForEnded(): Promise<void> {
    if (this.ended) return Promise.resolve();
    if (this.terminalError) return Promise.reject(this.terminalError);
    if (!this.endedPromise) {
      this.endedPromise = new Promise<void>((resolve, reject) => {
        this.resolveEnded = resolve;
        this.rejectEnded = reject;
      });
    }
    return this.endedPromise;
  }

  close(code = 1000): void {
    this.ready = false;
    try { this.socket?.close(code, 'client close'); } catch { /* best effort */ }
  }

  private assertWritable(): void {
    if (!this.ready || this.socket?.readyState !== 1) {
      throw new ManagedStreamsSessionError('configuration_not_ready', true);
    }
    if (this.endSent) throw new ManagedStreamsSessionError('session_already_ended');
  }

  private emit<K extends keyof ManagedStreamsEventMap>(event: K, payload: ManagedStreamsEventMap[K]): void {
    for (const handler of this.listeners.get(event) ?? []) {
      try { (handler as (value: ManagedStreamsEventMap[K]) => void)(payload); } catch { /* isolate */ }
    }
  }
}
