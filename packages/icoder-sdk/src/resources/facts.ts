// Facts resource
import type { AxiosInstance } from 'axios';
import type { FactExtractRequest, FactExtractResponse } from '../types.js';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export class FactsResource {
  constructor(private http: AxiosInstance) {}

  /** Extract structured clinical facts with the Corti-compatible v2 contract. */
  async extract(
    request: FactExtractRequest,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<FactExtractResponse>;
  async extract(
    text: string,
    outputLanguage?: string,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<FactExtractResponse>;
  async extract(
    requestOrText: FactExtractRequest | string,
    outputLanguageOrOptions: string | iCoDerRequestOptions = 'zh-CN',
    requestOptions?: iCoDerRequestOptions,
  ): Promise<FactExtractResponse> {
    const outputLanguage = typeof outputLanguageOrOptions === 'string'
      ? outputLanguageOrOptions
      : 'zh-CN';
    const options = typeof requestOrText === 'string'
      ? requestOptions
      : typeof outputLanguageOrOptions === 'string'
        ? undefined
        : outputLanguageOrOptions;
    const request: FactExtractRequest = typeof requestOrText === 'string'
      ? { context: [{ type: 'text', text: requestOrText }], outputLanguage }
      : requestOrText;
    if (!request.context.some((item) => item.text.trim())) {
      throw new Error('context must contain at least one non-empty text item');
    }
    const { data } = await this.http.post<FactExtractResponse>('/api/v2/tools/extract-facts', {
      ...request,
      outputLanguage: request.outputLanguage || 'zh-CN',
    }, requestConfig(options));
    return data;
  }
}
