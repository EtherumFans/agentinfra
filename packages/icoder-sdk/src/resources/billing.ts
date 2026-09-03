// Billing & Usage resource
import type { AxiosInstance } from 'axios';
import type { UsageSummary } from '../types.js';
import { AsyncPageNumberPager } from '../pagination.js';
import { requestConfig, type iCoDerRequestOptions } from '../request-options.js';

export interface BillingTransaction {
  id: string;
  date: string;
  description: string;
  amount: string;
  type: string;
  source?: string | null;
  balance_after?: number | null;
}

export interface BillingTransactionPage {
  transactions: BillingTransaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface BillingRunSettlement {
  run_id: string;
  status: string;
  reserved_amount: number;
  settled_amount: number;
  currency: string;
  error_code?: string | null;
  created_at?: string | null;
}

export interface BillingRunSettlementPage {
  items: BillingRunSettlement[];
  total: number;
  page: number;
  page_size: number;
  simulation: boolean;
}

function positiveInteger(value: number, name: string, maximum?: number): number {
  if (!Number.isInteger(value) || value < 1 || (maximum !== undefined && value > maximum)) {
    throw new RangeError(`${name} must be a positive integer${maximum ? ` at most ${maximum}` : ''}`);
  }
  return value;
}

export class BillingResource {
  constructor(private http: AxiosInstance) {}

  async balance(options?: iCoDerRequestOptions): Promise<{
    balance: number;
    reserved?: number;
    available?: number;
    currency: string;
    simulation?: boolean;
    ledger_authoritative?: boolean;
    quota?: { kind: string; limit: number | null; remaining: number; enforced: boolean };
    alerts?: { low_balance: boolean; threshold: number };
  }> {
    const { data } = await this.http.get('/api/billing/balance', requestConfig(options));
    return data;
  }

  async transactions(
    page = 1,
    pageSize = 20,
    options?: iCoDerRequestOptions,
  ): Promise<BillingTransactionPage> {
    positiveInteger(page, 'page');
    positiveInteger(pageSize, 'pageSize', 100);
    const params = { page, page_size: pageSize };
    const { data } = await this.http.get<BillingTransactionPage>(
      '/api/billing/transactions',
      requestConfig(options, params),
    );
    return data;
  }

  /** Lazily iterate transaction history without pre-fetching or unbounded loops. */
  iterateTransactions(
    pageSize = 20,
    options?: iCoDerRequestOptions,
    pagerOptions: { initialPage?: number; maxPages?: number } = {},
  ): AsyncPageNumberPager<BillingTransactionPage, BillingTransaction> {
    positiveInteger(pageSize, 'pageSize', 100);
    return new AsyncPageNumberPager(
      (page) => this.transactions(page, pageSize, options),
      { items: (response) => response.transactions, totalItems: (response) => response.total },
      pagerOptions,
    );
  }

  /** Development-only ledger simulation; cloud mode rejects this mutation. */
  async simulateDebit(amount: number, reference: string, options?: iCoDerRequestOptions): Promise<{
    status: string;
    debited: number;
    new_balance: number;
    simulation: boolean;
  }> {
    const { data } = await this.http.post(
      '/api/billing/simulation/debit',
      { amount, reference },
      requestConfig(options),
    );
    return data;
  }

  /** PHI-free, development-only Agent Run settlement audit records. */
  async runSettlements(limit = 20, options?: iCoDerRequestOptions): Promise<BillingRunSettlementPage> {
    positiveInteger(limit, 'limit', 100);
    const { data } = await this.http.get<BillingRunSettlementPage>(
      '/api/billing/run-settlements',
      requestConfig(options, { limit }),
    );
    return data;
  }

  async runSettlementPage(
    page = 1,
    pageSize = 20,
    options?: iCoDerRequestOptions,
  ): Promise<BillingRunSettlementPage> {
    positiveInteger(page, 'page');
    positiveInteger(pageSize, 'pageSize', 100);
    const params = { page, page_size: pageSize };
    const { data } = await this.http.get<BillingRunSettlementPage>(
      '/api/billing/run-settlements',
      requestConfig(options, params),
    );
    return data;
  }

  iterateRunSettlements(
    pageSize = 20,
    options?: iCoDerRequestOptions,
    pagerOptions: { initialPage?: number; maxPages?: number } = {},
  ): AsyncPageNumberPager<BillingRunSettlementPage, BillingRunSettlement> {
    positiveInteger(pageSize, 'pageSize', 100);
    return new AsyncPageNumberPager(
      (page) => this.runSettlementPage(page, pageSize, options),
      { items: (response) => response.items, totalItems: (response) => response.total },
      pagerOptions,
    );
  }

  /** Retry an idempotent failed local settlement after adding credits. */
  async retryRunSettlement(
    runId: string,
    options?: iCoDerRequestOptions,
  ): Promise<Record<string, unknown>> {
    const { data } = await this.http.post(
      `/api/billing/run-settlements/${encodeURIComponent(runId)}/retry`,
      undefined,
      requestConfig(options),
    );
    return data;
  }

  /** Reconcile old crash-orphaned reservations; active runs are skipped. */
  async reconcileStaleRunSettlements(
    olderThanSeconds = 3600,
    options?: iCoDerRequestOptions,
  ): Promise<{
    simulation: boolean;
    released: number;
    marked_retryable: number;
    skipped_active: number;
    inspected: number;
    older_than_seconds: number;
  }> {
    const { data } = await this.http.post(
      '/api/billing/run-settlements/reconcile-stale',
      undefined,
      requestConfig(options, { older_than_seconds: olderThanSeconds }),
    );
    return data;
  }
}

export class UsageResource {
  constructor(private http: AxiosInstance) {}

  async summary(days = 30, options?: iCoDerRequestOptions): Promise<UsageSummary> {
    const { data } = await this.http.get(
      '/api/usage/summary',
      requestConfig(options, { days }),
    );
    return data;
  }

  async history(days = 30, options?: iCoDerRequestOptions): Promise<any> {
    const { data } = await this.http.get(
      '/api/usage/history',
      requestConfig(options, { days }),
    );
    return data;
  }
}
