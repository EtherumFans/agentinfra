// Facts resource
import type { AxiosInstance } from 'axios';
import type { FactExtractResponse } from '../types.js';

export class FactsResource {
  constructor(private http: AxiosInstance) {}

  /** Extract structured clinical facts from raw text */
  async extract(text: string, outputLanguage = 'zh-CN'): Promise<FactExtractResponse> {
    const { data } = await this.http.post<FactExtractResponse>('/api/facts/extract', {
      text,
      output_language: outputLanguage,
    });
    return data;
  }
}
