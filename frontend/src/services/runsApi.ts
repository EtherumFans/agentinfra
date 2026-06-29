// Run Trace API client (P1.0-E)
// Hits /api/icoder/runs/* — thin aliases over app.state.run_history.

import axios from 'axios';
import { BACKEND_BASE_URL } from '../config';

const client = axios.create({
  baseURL: `${BACKEND_BASE_URL}/api/icoder/runs`,
});

export interface RunHistoryEntry {
  schema_version: string;
  timestamp: string;
  run_id: string;
  agent_ref: string;
  status: string;
  processing_time_ms: number;
  primary_diagnosis_code: string;
  primary_diagnosis_description: string;
  review_conclusion: string;
  issues_count: number;
  errors: string[];
  input_preview?: string;
}

export interface ListRunsResponse {
  runs: RunHistoryEntry[];
  total: number;
  history_available: boolean;
}

export interface RunNotFound {
  error_code: 'RUN_NOT_FOUND';
  run_id: string;
  message: string;
}

export const runsApi = {
  async list(agentRef?: string, limit = 50): Promise<ListRunsResponse> {
    const r = await client.get<ListRunsResponse>('', {
      params: { agent_ref: agentRef ?? '', limit },
    });
    return r.data;
  },
  async get(runId: string): Promise<RunHistoryEntry> {
    const r = await client.get<RunHistoryEntry>(`/${encodeURIComponent(runId)}`);
    return r.data;
  },
};