import type { AxiosInstance } from 'axios';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export interface DocumentFact {
  text: string;
  group?: string;
  source?: 'core' | 'system' | 'user';
}

export type DocumentContext =
  | { type: 'facts'; data: DocumentFact[] }
  | { type: 'transcript'; data: { text: string; channel?: number; participant?: number; speakerId?: number; start?: number; end?: number } }
  | { type: 'string'; data: string };

export interface DocumentSectionOverride {
  key: string;
  nameOverride?: string;
  writingStyleOverride?: string;
  formatRuleOverride?: string;
  additionalInstructionsOverride?: string;
  contentOverride?: string;
}

export type DocumentTemplate =
  | {
      sections: DocumentSectionOverride[];
      sectionKeys?: never;
      description?: string;
      documentName?: string;
      additionalInstructionsOverride?: string;
    }
  | {
      sectionKeys: string[];
      sections?: never;
      documentName?: string;
      additionalInstructions?: string;
    };

interface DocumentCreateBase {
  context: DocumentContext[];
  name?: string;
  outputLanguage: string;
  disableGuardrails?: boolean;
  documentationMode?: 'global_sequential' | 'routed_parallel';
}

export type DocumentCreateRequest = DocumentCreateBase & (
  | { templateKey: string; template?: never }
  | { template: DocumentTemplate; templateKey?: never }
);

export interface DocumentSection {
  key: string;
  name: string;
  text: string;
  sort: number;
  createdAt: string;
  updatedAt: string;
}

export interface ClassicDocument {
  id: string;
  name: string;
  templateRef: string;
  isStream: boolean;
  sections: DocumentSection[];
  createdAt: string;
  updatedAt: string;
  outputLanguage: string;
  usageInfo: { creditsConsumed: number };
}

export interface DocumentCreateResult {
  document: ClassicDocument;
  statusCode: number;
  retentionAcknowledged: boolean;
}

export class DocumentsResource {
  constructor(private readonly http: AxiosInstance) {}

  async create(
    interactionId: string,
    request: DocumentCreateRequest,
    options: { retentionPolicy?: 'none' } = {},
    requestOptions?: iCoDerRequestOptions,
  ): Promise<DocumentCreateResult> {
    const response = await this.http.post<ClassicDocument>(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/documents/`,
      request,
      requestConfig(
        requestOptions,
        {},
        options.retentionPolicy === 'none'
          ? { 'X-Corti-Retention-Policy': 'none' }
          : {},
      ),
    );
    return {
      document: response.data,
      statusCode: response.status,
      retentionAcknowledged:
        response.headers['x-corti-retention-policy'] === 'acknowledged',
    };
  }

  async preview(
    interactionId: string,
    request: DocumentCreateRequest,
    requestOptions?: iCoDerRequestOptions,
  ): Promise<ClassicDocument> {
    const result = await this.create(
      interactionId, request, { retentionPolicy: 'none' }, requestOptions,
    );
    if (!result.retentionAcknowledged) {
      throw new Error('Server did not acknowledge the zero-retention policy');
    }
    return result.document;
  }

  async list(interactionId: string, options?: iCoDerRequestOptions): Promise<ClassicDocument[]> {
    const { data } = await this.http.get<{ data: ClassicDocument[] }>(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/documents/`,
      requestConfig(options),
    );
    return data.data;
  }

  async get(
    interactionId: string,
    documentId: string,
    options?: iCoDerRequestOptions,
  ): Promise<ClassicDocument> {
    const { data } = await this.http.get<ClassicDocument>(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/documents/${encodeURIComponent(documentId)}`,
      requestConfig(options),
    );
    return data;
  }

  async update(
    interactionId: string,
    documentId: string,
    request: { name?: string; sections?: Array<Pick<DocumentSection, 'key' | 'name' | 'text' | 'sort'>> },
    options?: iCoDerRequestOptions,
  ): Promise<ClassicDocument> {
    const { data } = await this.http.patch<ClassicDocument>(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/documents/${encodeURIComponent(documentId)}`,
      request,
      requestConfig(options),
    );
    return data;
  }

  async delete(
    interactionId: string,
    documentId: string,
    options?: iCoDerRequestOptions,
  ): Promise<void> {
    await this.http.delete(
      `/api/v2/tools/interactions/${encodeURIComponent(interactionId)}/documents/${encodeURIComponent(documentId)}`,
      requestConfig(options),
    );
  }
}
