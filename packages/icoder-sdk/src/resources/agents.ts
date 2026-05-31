// Agents resource
import type { AxiosInstance } from 'axios';
import type { AgentTemplate, Expert } from '../types';

export class AgentsResource {
  constructor(private http: AxiosInstance) {}

  async list(category?: string, search?: string): Promise<{ agents: any[] }> {
    const { data } = await this.http.get('/api/agents', { params: { category, search } });
    return data;
  }

  async get(id: string): Promise<any> {
    const { data } = await this.http.get(`/api/agents/${id}`);
    return data;
  }

  async create(config: { name: string; description?: string; category?: string; system_prompt?: string; expert_ids?: string[] }): Promise<any> {
    const { data } = await this.http.post('/api/agents', config);
    return data;
  }

  async update(id: string, config: Record<string, unknown>): Promise<any> {
    const { data } = await this.http.put(`/api/agents/${id}`, config);
    return data;
  }

  async delete(id: string): Promise<void> {
    await this.http.delete(`/api/agents/${id}`);
  }

  async run(id: string, input: string, stream = false): Promise<any> {
    const { data } = await this.http.post(`/api/agents/${id}/run`, { input, stream });
    return data;
  }

  /** Stream agent response via SSE. Returns a ReadableStream of string chunks. */
  async stream(id: string, input: string, signal?: AbortSignal): Promise<ReadableStream<Uint8Array>> {
    const token = this.http.defaults.headers.common['Authorization'] as string;
    const baseURL = (this.http.defaults.baseURL || '').replace(/\/$/, '');
    const response = await fetch(`${baseURL}/api/agents/${id}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: token },
      body: JSON.stringify({ input }),
      signal,
    });
    if (!response.ok) throw new Error(`Agent stream failed: ${response.status}`);
    return response.body!;
  }

  async templates(): Promise<{ templates: AgentTemplate[] }> {
    const { data } = await this.http.get('/api/agents/templates');
    return data;
  }
}

export class ExpertsResource {
  constructor(private http: AxiosInstance) {}

  async list(category?: string, search?: string): Promise<{ experts: Expert[] }> {
    const { data } = await this.http.get('/api/experts', { params: { category, search } });
    return data;
  }

  async call(name: string, input: string): Promise<any> {
    const { data } = await this.http.post(`/api/experts/call/${encodeURIComponent(name)}`, null, {
      params: { input },
    });
    return data;
  }

  async create(config: { name: string; category: string; description?: string }): Promise<any> {
    const { data } = await this.http.post('/api/experts', config);
    return data;
  }

  async delete(id: string): Promise<void> {
    await this.http.delete(`/api/experts/${id}`);
  }
}
