export interface ManagedSttConnectOptions {
  language?: string;
  mimeType?: string;
  awaitConfiguration?: boolean;
  reconnectAttempts?: number;
  reconnectInitialDelayMs?: number;
  reconnectMaxDelayMs?: number;
  setupTimeoutMs?: number;
}

export type ManagedSttServerMessage =
  | {
      type: 'ready';
      language: string;
      maxSessionBytes?: number;
      protocol?: string;
      resumeSupported?: boolean;
      resumeMode?: string;
      sessionId?: string;
      nextAudioSequence?: number;
    }
  | {
      type: 'audio_ack';
      sequence: number;
      nextAudioSequence: number;
      totalBytes: number;
      duplicate: boolean;
      sessionId?: string;
    }
  | { type: 'interim'; text: string }
  | { type: 'final'; text: string; diarization: unknown[] }
  | { type: 'buffering'; bytes: number }
  | { type: 'pong' }
  | { type: 'error'; code?: string }
  | { type: 'unknown' };

export interface ManagedSttEventMap {
  open: { attempt: number };
  ready: Extract<ManagedSttServerMessage, { type: 'ready' }>;
  message: ManagedSttServerMessage;
  close: { code: number; wasClean: boolean };
  error: ManagedSttSessionError;
  reconnecting: { attempt: number; delayMs: number };
}

export class ManagedSttSessionError extends Error {
  readonly code: string;
  readonly retryable: boolean;

  constructor(code: string, retryable = false) {
    super(`iCoDer managed STT session failed (${code})`);
    this.name = 'ManagedSttSessionError';
    this.code = code;
    this.retryable = retryable;
  }
}

type Handler<K extends keyof ManagedSttEventMap> = (event: ManagedSttEventMap[K]) => void;

function nonNegativeInteger(value: number | undefined, fallback: number, name: string): number {
  const result = value ?? fallback;
  if (!Number.isInteger(result) || result < 0) {
    throw new RangeError(`${name} must be a non-negative integer`);
  }
  return result;
}

function positiveInteger(value: number | undefined, fallback: number, name: string): number {
  const result = value ?? fallback;
  if (!Number.isInteger(result) || result < 1) {
    throw new RangeError(`${name} must be a positive integer`);
  }
  return result;
}

function safeCode(value: unknown): string | undefined {
  return typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(value)
    ? value
    : undefined;
}

const RESUME_PROTOCOL = 'icoder.stt-resume.v1';
const RESUME_MODE = 'client_replay';
const MAXIMUM_SESSION_BYTES = 32 * 1024 * 1024;
const FRAME_HEADER_BYTES = 8;

function safeInteger(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
    ? value
    : undefined;
}

function createSessionId(): string {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === 'function') {
    return `stt_${cryptoApi.randomUUID().replace(/-/g, '')}`;
  }
  if (typeof cryptoApi?.getRandomValues === 'function') {
    const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
    return `stt_${Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('')}`;
  }
  throw new ManagedSttSessionError('secure_random_unavailable');
}

type ReplayableAudioFrame = Uint8Array | Blob;

interface CachedAudioFrame {
  sequence: number;
  size: number;
  frame: ReplayableAudioFrame;
}

function frameAudio(
  sequence: number,
  data: ArrayBuffer | ArrayBufferView | Blob,
  size: number,
): ReplayableAudioFrame {
  const header = new Uint8Array(FRAME_HEADER_BYTES);
  header.set([0x49, 0x43, 0x52, 0x31]);
  new DataView(header.buffer).setUint32(4, sequence, false);
  if (typeof Blob !== 'undefined' && data instanceof Blob) {
    return new Blob([header, data], { type: 'application/octet-stream' });
  }
  let source: Uint8Array;
  if (data instanceof ArrayBuffer) source = new Uint8Array(data);
  else if (ArrayBuffer.isView(data)) {
    source = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  } else {
    throw new TypeError('audio must be binary data');
  }
  const framed = new Uint8Array(FRAME_HEADER_BYTES + size);
  framed.set(header, 0);
  framed.set(source, FRAME_HEADER_BYTES);
  return framed;
}

function parseMessage(raw: unknown): ManagedSttServerMessage {
  let value: unknown;
  try {
    value = JSON.parse(String(raw));
  } catch {
    return { type: 'unknown' };
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { type: 'unknown' };
  const message = value as Record<string, unknown>;
  switch (message.type) {
    case 'ready':
      return {
        type: 'ready',
        language: typeof message.language === 'string' ? message.language : 'zh-CN',
        ...(typeof message.maxSessionBytes === 'number'
          ? { maxSessionBytes: message.maxSessionBytes }
          : {}),
        ...(typeof message.protocol === 'string' ? { protocol: message.protocol } : {}),
        ...(typeof message.resumeSupported === 'boolean'
          ? { resumeSupported: message.resumeSupported }
          : {}),
        ...(typeof message.resumeMode === 'string' ? { resumeMode: message.resumeMode } : {}),
        ...(typeof message.sessionId === 'string' ? { sessionId: message.sessionId } : {}),
        ...(safeInteger(message.nextAudioSequence) !== undefined
          ? { nextAudioSequence: safeInteger(message.nextAudioSequence) }
          : {}),
      };
    case 'audio_ack': {
      const sequence = safeInteger(message.sequence);
      const nextAudioSequence = safeInteger(message.nextAudioSequence);
      const totalBytes = safeInteger(message.totalBytes);
      if (sequence === undefined || sequence < 1 || nextAudioSequence === undefined ||
        nextAudioSequence < 1 || totalBytes === undefined) return { type: 'unknown' };
      return {
        type: 'audio_ack',
        sequence,
        nextAudioSequence,
        totalBytes,
        duplicate: message.duplicate === true,
        ...(typeof message.sessionId === 'string' ? { sessionId: message.sessionId } : {}),
      };
    }
    case 'interim':
      return { type: 'interim', text: typeof message.text === 'string' ? message.text : '' };
    case 'final':
      return {
        type: 'final',
        text: typeof message.text === 'string' ? message.text : '',
        diarization: Array.isArray(message.diarization) ? message.diarization : [],
      };
    case 'buffering':
      return { type: 'buffering', bytes: typeof message.bytes === 'number' ? message.bytes : 0 };
    case 'pong':
      return { type: 'pong' };
    case 'error':
      return { type: 'error', ...(safeCode(message.code) ? { code: safeCode(message.code) } : {}) };
    default:
      return { type: 'unknown' };
  }
}

/** Managed lifecycle with negotiated, bounded client-replay audio recovery. */
export class ManagedSttSession {
  private readonly listeners = new Map<keyof ManagedSttEventMap, Set<(event: never) => void>>();
  private readonly reconnectAttempts: number;
  private readonly reconnectInitialDelayMs: number;
  private readonly reconnectMaxDelayMs: number;
  private readonly setupTimeoutMs: number;
  private readonly language: string;
  private readonly mimeType: string;
  private readonly sessionId = createSessionId();
  private readonly audioFrames: CachedAudioFrame[] = [];
  private socket?: WebSocket;
  private generation = 0;
  private reconnectsUsed = 0;
  private started = false;
  private manuallyClosed = false;
  private audioSent = false;
  private endSent = false;
  private resumeSupported = false;
  private sentAudioBytes = 0;
  private maxSessionBytes = MAXIMUM_SESSION_BYTES;
  private lastAcknowledgedSequence = 0;
  private ready = false;
  private recovery?: Promise<void>;
  private readyPromise?: Promise<void>;
  private terminalError?: ManagedSttSessionError;

  constructor(
    private readonly urlFactory: () => string,
    options: ManagedSttConnectOptions = {},
    private readonly prepareConnection: () => Promise<void> = async () => undefined,
  ) {
    this.language = options.language ?? 'zh-CN';
    this.mimeType = options.mimeType ?? 'audio/webm;codecs=opus';
    this.reconnectAttempts = nonNegativeInteger(options.reconnectAttempts, 3, 'reconnectAttempts');
    this.reconnectInitialDelayMs = nonNegativeInteger(
      options.reconnectInitialDelayMs,
      250,
      'reconnectInitialDelayMs',
    );
    this.reconnectMaxDelayMs = nonNegativeInteger(
      options.reconnectMaxDelayMs,
      2000,
      'reconnectMaxDelayMs',
    );
    if (this.reconnectMaxDelayMs < this.reconnectInitialDelayMs) {
      throw new RangeError('reconnectMaxDelayMs must be >= reconnectInitialDelayMs');
    }
    this.setupTimeoutMs = positiveInteger(options.setupTimeoutMs, 5000, 'setupTimeoutMs');
  }

  get readyState(): number {
    return this.socket?.readyState ?? 3;
  }

  get isReady(): boolean {
    return this.ready;
  }

  on<K extends keyof ManagedSttEventMap>(event: K, handler: Handler<K>): this {
    const handlers = this.listeners.get(event) ?? new Set();
    handlers.add(handler as (event: never) => void);
    this.listeners.set(event, handlers);
    return this;
  }

  off<K extends keyof ManagedSttEventMap>(event: K, handler?: Handler<K>): this {
    if (!handler) this.listeners.delete(event);
    else this.listeners.get(event)?.delete(handler as (event: never) => void);
    return this;
  }

  async connect(awaitConfiguration = true): Promise<this> {
    if (this.started) throw new ManagedSttSessionError('already_started');
    this.started = true;
    this.readyPromise = this.establishWithReconnect(false);
    if (awaitConfiguration) await this.readyPromise;
    else void this.readyPromise.catch(() => undefined);
    return this;
  }

  async waitForOpen(): Promise<void> {
    if (this.terminalError) throw this.terminalError;
    if (this.readyState === 1) return;
    await new Promise<void>((resolve, reject) => {
      const opened = () => { cleanup(); resolve(); };
      const failed = (error: ManagedSttSessionError) => { cleanup(); reject(error); };
      const cleanup = () => {
        this.off('open', opened);
        this.off('error', failed);
      };
      this.on('open', opened);
      this.on('error', failed);
    });
  }

  async waitForReady(): Promise<void> {
    if (this.ready) return;
    if (this.terminalError) throw this.terminalError;
    if (!this.readyPromise) throw new ManagedSttSessionError('not_started');
    await this.readyPromise;
    if (!this.ready) {
      throw this.terminalError ?? new ManagedSttSessionError('configuration_not_ready', true);
    }
  }

  sendAudio(data: ArrayBuffer | ArrayBufferView | Blob): void {
    this.assertReady();
    const size = data instanceof ArrayBuffer
      ? data.byteLength
      : ArrayBuffer.isView(data)
        ? data.byteLength
        : typeof Blob !== 'undefined' && data instanceof Blob
          ? data.size
          : undefined;
    if (size === undefined) throw new TypeError('audio must be binary data');
    if (size === 0) throw new RangeError('audio cannot be empty');
    if (this.sentAudioBytes + size > this.maxSessionBytes) {
      throw new RangeError(`audio exceeds the ${this.maxSessionBytes}-byte session limit`);
    }
    this.audioSent = true;
    this.sentAudioBytes += size;
    if (this.resumeSupported) {
      const sequence = this.audioFrames.length + 1;
      const frame = frameAudio(sequence, data, size);
      this.audioFrames.push({ sequence, size, frame });
      this.socket!.send(frame);
    } else {
      this.socket!.send(data);
    }
  }

  requestInterim(): void {
    this.assertReady();
    this.socket!.send(JSON.stringify({ type: 'interim' }));
  }

  sendEnd(): void {
    this.assertReady();
    this.endSent = true;
    this.socket!.send(JSON.stringify(this.resumeSupported
      ? { type: 'end', lastAudioSequence: this.audioFrames.length }
      : { type: 'end' }));
  }

  send(data: string | ArrayBuffer | ArrayBufferView | Blob): void {
    if (this.readyState !== 1) throw new ManagedSttSessionError('socket_not_open', true);
    if (this.resumeSupported && typeof data !== 'string') {
      throw new ManagedSttSessionError('use_send_audio_for_resumable_binary');
    }
    this.socket!.send(data);
  }

  close(code = 1000): void {
    this.manuallyClosed = true;
    this.ready = false;
    this.terminalError ??= new ManagedSttSessionError('client_closed');
    try { this.socket?.close(code, 'client close'); } catch { /* best effort */ }
  }

  private emit<K extends keyof ManagedSttEventMap>(event: K, payload: ManagedSttEventMap[K]): void {
    for (const handler of this.listeners.get(event) ?? []) {
      try { (handler as (value: ManagedSttEventMap[K]) => void)(payload); } catch { /* isolate handlers */ }
    }
  }

  private assertReady(): void {
    if (!this.ready || this.readyState !== 1) {
      throw new ManagedSttSessionError('configuration_not_ready', true);
    }
    if (this.endSent) throw new ManagedSttSessionError('session_already_ended');
  }

  private async establishWithReconnect(isReconnect: boolean): Promise<void> {
    let reconnect = isReconnect;
    while (!this.manuallyClosed) {
      if (reconnect) {
        if (this.audioSent && !this.resumeSupported) {
          throw new ManagedSttSessionError('audio_resume_unsupported');
        }
        if (this.reconnectsUsed >= this.reconnectAttempts) {
          throw new ManagedSttSessionError('reconnect_exhausted');
        }
        this.reconnectsUsed += 1;
        const delayMs = Math.min(
          this.reconnectMaxDelayMs,
          this.reconnectInitialDelayMs * (2 ** (this.reconnectsUsed - 1)),
        );
        this.emit('reconnecting', { attempt: this.reconnectsUsed, delayMs });
        if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));
        if (this.manuallyClosed) return;
      }
      try {
        await this.prepareConnection();
        await this.establishOnce();
        return;
      } catch (error) {
        const managed = error instanceof ManagedSttSessionError
          ? error
          : new ManagedSttSessionError('connection_failed', true);
        if (!managed.retryable || (this.audioSent && !this.resumeSupported) || this.manuallyClosed) {
          throw managed;
        }
        reconnect = true;
      }
    }
  }

  private establishOnce(): Promise<void> {
    const generation = ++this.generation;
    this.ready = false;
    return new Promise<void>((resolve, reject) => {
      let settled = false;
      let suppressRecovery = false;
      let socket: WebSocket;
      const finishFailure = (error: ManagedSttSessionError) => {
        if (settled) return;
        settled = true;
        suppressRecovery = true;
        clearTimeout(timeout);
        try { socket.close(1000, 'setup failed'); } catch { /* best effort */ }
        reject(error);
      };
      const timeout = setTimeout(
        () => finishFailure(new ManagedSttSessionError('setup_timeout', true)),
        this.setupTimeoutMs,
      );
      try {
        socket = new WebSocket(this.urlFactory());
        this.socket = socket;
      } catch {
        clearTimeout(timeout);
        reject(new ManagedSttSessionError('connection_failed', true));
        return;
      }
      socket.onopen = () => {
        if (generation !== this.generation) return;
        this.emit('open', { attempt: this.reconnectsUsed });
        try {
          socket.send(JSON.stringify({
            type: 'start',
            protocol: RESUME_PROTOCOL,
            sessionId: this.sessionId,
            mimeType: this.mimeType,
            language: this.language,
          }));
        } catch {
          finishFailure(new ManagedSttSessionError('configuration_send_failed', true));
        }
      };
      socket.onmessage = (event) => {
        if (generation !== this.generation) return;
        const message = parseMessage(event.data);
        this.emit('message', message);
        if (message.type === 'ready') {
          const negotiatedResume = message.protocol === RESUME_PROTOCOL
            && message.resumeSupported === true
            && message.resumeMode === RESUME_MODE
            && message.sessionId === this.sessionId;
          if ((this.audioSent || this.endSent) && !negotiatedResume) {
            finishFailure(new ManagedSttSessionError('audio_resume_unsupported'));
            return;
          }
          const requestedSequence = negotiatedResume ? message.nextAudioSequence : undefined;
          if (negotiatedResume && (
            requestedSequence === undefined
            || requestedSequence < 1
            || requestedSequence > this.audioFrames.length + 1
          )) {
            finishFailure(new ManagedSttSessionError('invalid_resume_cursor'));
            return;
          }
          this.resumeSupported = negotiatedResume;
          if (typeof message.maxSessionBytes === 'number'
            && Number.isSafeInteger(message.maxSessionBytes)
            && message.maxSessionBytes > 0) {
            this.maxSessionBytes = Math.min(MAXIMUM_SESSION_BYTES, message.maxSessionBytes);
          }
          if (this.sentAudioBytes > this.maxSessionBytes) {
            finishFailure(new ManagedSttSessionError('session_too_large'));
            return;
          }
          if (negotiatedResume) {
            this.lastAcknowledgedSequence = requestedSequence! - 1;
            for (const cached of this.audioFrames) {
              if (cached.sequence >= requestedSequence!) socket.send(cached.frame);
            }
            if (this.endSent) {
              socket.send(JSON.stringify({
                type: 'end', lastAudioSequence: this.audioFrames.length,
              }));
            }
          }
          this.ready = true;
          this.terminalError = undefined;
          this.emit('ready', message);
          if (!settled) {
            settled = true;
            clearTimeout(timeout);
            resolve();
          }
        } else if (message.type === 'audio_ack') {
          if (!this.resumeSupported || message.sessionId !== this.sessionId
            || message.sequence > this.audioFrames.length
            || message.nextAudioSequence < message.sequence + 1
            || message.nextAudioSequence > this.audioFrames.length + 1) {
            const error = new ManagedSttSessionError('invalid_audio_ack');
            this.terminalError = error;
            this.ready = false;
            this.manuallyClosed = true;
            this.emit('error', error);
            try { socket.close(1002, 'invalid audio acknowledgement'); } catch { /* best effort */ }
            return;
          }
          this.lastAcknowledgedSequence = Math.max(
            this.lastAcknowledgedSequence,
            message.nextAudioSequence - 1,
          );
        } else if (message.type === 'error') {
          const error = new ManagedSttSessionError(message.code ?? 'server_error');
          this.emit('error', error);
          if (!settled) finishFailure(error);
        }
      };
      socket.onerror = () => {
        const error = new ManagedSttSessionError('transport_error', true);
        this.emit('error', error);
        if (!settled) finishFailure(error);
      };
      socket.onclose = (event) => {
        if (generation !== this.generation) return;
        this.ready = false;
        clearTimeout(timeout);
        this.emit('close', { code: event.code, wasClean: event.wasClean });
        if (!settled) {
          finishFailure(new ManagedSttSessionError('closed_before_ready', true));
          return;
        }
        if (!suppressRecovery && !this.manuallyClosed) this.recoverAfterClose();
      };
    });
  }

  private recoverAfterClose(): void {
    if (this.recovery) return;
    if ((this.audioSent || this.endSent) && !this.resumeSupported) {
      const error = new ManagedSttSessionError('audio_resume_unsupported');
      this.terminalError = error;
      this.emit('error', error);
      return;
    }
    const recovery = this.establishWithReconnect(true);
    this.recovery = recovery;
    this.readyPromise = recovery;
    void recovery.then(
      () => {
        if (this.recovery === recovery) this.recovery = undefined;
      },
      (error) => {
        const managed = error instanceof ManagedSttSessionError
          ? error
          : new ManagedSttSessionError('reconnect_exhausted');
        this.terminalError = managed;
        if (!this.manuallyClosed) this.emit('error', managed);
        if (this.recovery === recovery) this.recovery = undefined;
      },
    );
  }
}
