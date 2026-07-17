// Reviews resource — medical coding pipeline
import type { AxiosInstance } from 'axios';
import type { Review } from '../types.js';

export class ReviewsResource {
  constructor(private http: AxiosInstance) {}

  async create(encounterId: string, options?: { coding_systems?: string[]; async?: boolean }): Promise<Review> {
    const { data } = await this.http.post<Review>('/api/reviews', {
      encounter_id: encounterId,
      coding_systems: options?.coding_systems,
    }, { params: options?.async ? { async: true } : {} });
    return data;
  }

  async get(id: string): Promise<Review> {
    const { data } = await this.http.get<Review>(`/api/reviews/${id}`);
    return data;
  }

  async list(page = 1, pageSize = 20): Promise<{ items: Review[]; total: number }> {
    const { data } = await this.http.get('/api/reviews', { params: { page, page_size: pageSize } });
    return data;
  }

  async reviewCandidate(reviewId: string, candidateId: string, decision: { decision: string; reason: string; modified_code?: string; modified_name?: string }): Promise<any> {
    const { data } = await this.http.put(`/api/reviews/${reviewId}/candidates/${candidateId}/review`, {
      candidate_id: candidateId,
      ...decision,
    });
    return data;
  }

  async complete(id: string, notes?: string): Promise<Review> {
    const { data } = await this.http.put(`/api/reviews/${id}/complete`, {
      reviewer_notes: notes,
      human_review_status: 'completed',
    });
    return data;
  }

  async getReport(id: string, format: 'markdown' | 'html' = 'markdown'): Promise<string> {
    const { data } = await this.http.get(`/api/reviews/${id}/report/${format}`);
    return data;
  }
}
