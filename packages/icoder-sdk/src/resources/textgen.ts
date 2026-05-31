// Text Generation resource
import type { AxiosInstance } from 'axios';
import type { TextGenTemplate, TextGenResponse } from '../types';

export class TextGenResource {
  constructor(private http: AxiosInstance) {}

  async templates(): Promise<{ templates: TextGenTemplate[] }> {
    const { data } = await this.http.get('/api/text-gen/templates');
    return data;
  }

  async generate(input: string, options?: {
    template?: string;
    outputLanguage?: string;
    docName?: string;
    maxTokens?: number;
    temperature?: number;
  }): Promise<TextGenResponse> {
    const { data } = await this.http.post<TextGenResponse>('/api/text-gen/generate', {
      input,
      template: options?.template,
      output_language: options?.outputLanguage || 'zh-CN',
      doc_name: options?.docName,
      max_tokens: options?.maxTokens,
      temperature: options?.temperature,
    });
    return data;
  }
}
