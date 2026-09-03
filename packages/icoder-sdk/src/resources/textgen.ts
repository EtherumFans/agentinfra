// Text Generation resource
import type { AxiosInstance } from 'axios';
import type { TextGenTemplate, TextGenResponse } from '../types.js';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export class TextGenResource {
  constructor(private http: AxiosInstance) {}

  async templates(options?: iCoDerRequestOptions): Promise<{ templates: TextGenTemplate[] }> {
    const { data } = await this.http.get<Array<{
      id: string;
      name: string;
      description?: string;
      specialties?: string[];
    }>>('/api/v2/tools/templates/', requestConfig(options));
    return {
      templates: data.map((template) => ({
        key: template.id,
        name: template.name,
        desc: template.description || '',
        category: template.specialties?.join(', ') || 'Guided Documents',
        sample: '',
      })),
    };
  }

  async generate(input: string, options?: {
    template?: string;
    outputLanguage?: string;
    docName?: string;
    maxTokens?: number;
    temperature?: number;
  }, requestOptions?: iCoDerRequestOptions): Promise<TextGenResponse> {
    if (!input.trim()) throw new Error('input must not be empty');
    if (options?.maxTokens !== undefined || options?.temperature !== undefined || options?.docName) {
      throw new Error('docName, maxTokens, and temperature are not supported by Guided Documents');
    }
    const name = options?.template?.trim() || 'Clinical document';
    const response = await this.http.post<{
      document: { stringDocument: Record<string, string> };
      usageInfo: { creditsConsumed: number };
    }>('/api/v2/tools/guided-documents', {
      outputLanguage: options?.outputLanguage || 'zh-CN',
      context: [{ type: 'text', text: input }],
      dynamicTemplate: {
        name,
        generation: {
          instructions: {
            prompt: `Generate ${name} from the supplied clinical context. Do not invent undocumented facts.`,
          },
          sections: [{
            heading: name,
            instructions: {
              contentPrompt: `Write the ${name} using only the supplied clinical context.`,
            },
            outputSchema: { type: 'string' },
          }],
        },
      },
    }, requestConfig(
      requestOptions,
      {},
      { 'X-Corti-Retention-Policy': 'none' },
    ));
    if (response.headers['x-corti-retention-policy'] !== 'acknowledged') {
      throw new Error('Server did not acknowledge the zero-retention policy');
    }
    return {
      output: Object.values(response.data.document.stringDocument).join('\n\n'),
      credits_consumed: response.data.usageInfo.creditsConsumed,
    };
  }
}
