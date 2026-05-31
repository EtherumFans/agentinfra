// Billing & Usage resource
import type { AxiosInstance } from 'axios';
import type { UsageSummary } from '../types';

export class BillingResource {
  constructor(private http: AxiosInstance) {}

  async balance(): Promise<{ balance: number; credits_consumed: number }> {
    const { data } = await this.http.get('/api/billing/balance');
    return data;
  }

  async transactions(page = 1, pageSize = 20): Promise<any> {
    const { data } = await this.http.get('/api/billing/transactions', { params: { page, page_size: pageSize } });
    return data;
  }
}

export class UsageResource {
  constructor(private http: AxiosInstance) {}

  async summary(days = 30): Promise<UsageSummary> {
    const { data } = await this.http.get('/api/usage/summary', { params: { days } });
    return data;
  }

  async history(days = 30): Promise<any> {
    const { data } = await this.http.get('/api/usage/history', { params: { days } });
    return data;
  }
}
