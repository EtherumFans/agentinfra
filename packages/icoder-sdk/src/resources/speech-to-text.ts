// Speech To Text resource
import type { AxiosInstance } from 'axios';

export interface SttSessionConfig {
  language?: string;
  punctuation?: 'auto' | 'spoken';
  interimResults?: boolean;
}

export class SpeechToTextResource {
  constructor(private http: AxiosInstance) {}

  /** Start a real-time STT session via WebSocket. Returns a WebSocket connected to the STT endpoint. */
  async createSession(config: SttSessionConfig = {}): Promise<WebSocket> {
    const baseURL = (this.http.defaults.baseURL || '').replace(/\/$/, '');
    const wsUrl = baseURL.replace(/^http/, 'ws');
    const ws = new WebSocket(`${wsUrl}/ws/speech-to-text`);

    return new Promise((resolve, reject) => {
      ws.onopen = () => {
        ws.send(JSON.stringify({
          type: 'start',
          mimeType: 'audio/webm;codecs=opus',
          language: config.language || 'zh-CN',
        }));
        resolve(ws);
      };
      ws.onerror = () => reject(new Error('WebSocket connection failed'));
      setTimeout(() => reject(new Error('WebSocket connection timeout')), 5000);
    });
  }

  /** Punctuate text (post-processing) */
  async punctuate(text: string): Promise<{ refined: string }> {
    const { data } = await this.http.post('/api/experts/stt/punctuate', { text });
    return data;
  }
}
