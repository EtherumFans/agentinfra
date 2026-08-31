import axios, { AxiosError } from 'axios';

export interface iCoDerErrorDetail {
  code?: string | number;
  reason?: string;
  field?: string;
  location?: Array<string | number>;
  type?: string;
}

export interface iCoDerSanitizedErrorBody {
  details: iCoDerErrorDetail[];
  error?: {
    code: number;
    data?: { a2a_error_code: string };
    details?: Array<{ reason: string }>;
  };
}

export class iCoDerClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'iCoDerClientError';
  }
}

function safeCode(value: unknown): string | number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(value)) return value;
  return undefined;
}

function safeReason(value: unknown): string | undefined {
  return typeof value === 'string' && /^[A-Z0-9_.:-]{1,128}$/.test(value)
    ? value
    : undefined;
}

function safeLocation(value: unknown): Array<string | number> | undefined {
  if (!Array.isArray(value) || value.length > 16) return undefined;
  const result = value.filter(
    (item): item is string | number => (
      (typeof item === 'number' && Number.isInteger(item))
      || (typeof item === 'string' && /^[A-Za-z0-9_.:-]{1,64}$/.test(item))
    ),
  );
  return result.length === value.length ? result : undefined;
}

function detailFrom(value: unknown): iCoDerErrorDetail | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const item = value as Record<string, unknown>;
  const code = safeCode(item.code ?? item.error_code ?? item.a2a_error_code);
  const reason = safeReason(item.reason);
  const field = typeof item.field === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(item.field)
    ? item.field
    : undefined;
  const location = safeLocation(item.loc ?? item.location);
  const type = typeof item.type === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(item.type)
    ? item.type
    : undefined;
  if (code === undefined && !reason && !field && !location && !type) return undefined;
  return {
    ...(code !== undefined ? { code } : {}),
    ...(reason ? { reason } : {}),
    ...(field ? { field } : {}),
    ...(location ? { location } : {}),
    ...(type ? { type } : {}),
  };
}

function sanitizedBody(value: unknown): iCoDerSanitizedErrorBody | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const body = value as Record<string, unknown>;
  const candidates: unknown[] = [];
  candidates.push(body);
  if (body.error && typeof body.error === 'object') {
    candidates.push(body.error);
    const error = body.error as Record<string, unknown>;
    if (error.data && typeof error.data === 'object' && !Array.isArray(error.data)) {
      candidates.push(error.data);
    }
    if (Array.isArray(error.details)) candidates.push(...error.details.slice(0, 32));
    if (Array.isArray(error.data)) candidates.push(...error.data.slice(0, 32));
  }
  if (Array.isArray(body.detail)) candidates.push(...body.detail.slice(0, 32));
  const details = candidates.map(detailFrom).filter((item): item is iCoDerErrorDetail => Boolean(item));
  let protocolError: iCoDerSanitizedErrorBody['error'];
  if (body.error && typeof body.error === 'object' && !Array.isArray(body.error)) {
    const error = body.error as Record<string, unknown>;
    if (typeof error.code === 'number' && Number.isInteger(error.code)) {
      const data = error.data;
      const a2aCode = data && typeof data === 'object' && !Array.isArray(data)
        ? safeCode((data as Record<string, unknown>).a2a_error_code)
        : undefined;
      const reasons = [
        ...(Array.isArray(error.details) ? error.details : []),
        ...(Array.isArray(error.data) ? error.data : []),
      ].map((item) => (
        item && typeof item === 'object' && !Array.isArray(item)
          ? safeReason((item as Record<string, unknown>).reason)
          : undefined
      )).filter((item): item is string => Boolean(item));
      protocolError = {
        code: error.code,
        ...(typeof a2aCode === 'string' ? { data: { a2a_error_code: a2aCode } } : {}),
        ...(reasons.length ? { details: reasons.map((reason) => ({ reason })) } : {}),
      };
    }
  }
  return details.length || protocolError ? { details, ...(protocolError ? { error: protocolError } : {}) } : undefined;
}

function requestIdFrom(error: AxiosError): string | undefined {
  const headers = error.response?.headers;
  const value = headers?.['x-request-id'] ?? headers?.['x-correlation-id'];
  return typeof value === 'string' && value.length <= 256 ? value : undefined;
}

export class iCoDerAPIError extends iCoDerClientError {
  readonly isAxiosError = true;
  readonly status: number;
  readonly statusCode: number;
  readonly requestId?: string;
  readonly details: readonly iCoDerErrorDetail[];
  readonly body?: iCoDerSanitizedErrorBody;
  readonly retryable: boolean;
  readonly response: {
    status: number;
    headers: Record<string, string>;
    data?: iCoDerSanitizedErrorBody;
  };

  constructor(status: number, requestId?: string, body?: iCoDerSanitizedErrorBody) {
    super(`iCoDer API request failed with HTTP ${status}`);
    this.name = new.target.name;
    this.status = status;
    this.statusCode = status;
    this.requestId = requestId;
    this.body = body;
    this.details = body?.details ?? [];
    this.retryable = status === 408 || status === 429 || status >= 500;
    this.response = {
      status,
      headers: requestId ? { 'x-request-id': requestId } : {},
      ...(body ? { data: body } : {}),
    };
  }
}

export class BadRequestError extends iCoDerAPIError {}
export class UnauthorizedError extends iCoDerAPIError {}
export class ForbiddenError extends iCoDerAPIError {}
export class NotFoundError extends iCoDerAPIError {}
export class ConflictError extends iCoDerAPIError {}
export class UnprocessableEntityError extends iCoDerAPIError {}
export class InternalServerError extends iCoDerAPIError {}
export class BadGatewayError extends iCoDerAPIError {}
export class GatewayTimeoutError extends iCoDerAPIError {}

const STATUS_ERRORS: Record<number, typeof iCoDerAPIError> = {
  400: BadRequestError,
  401: UnauthorizedError,
  403: ForbiddenError,
  404: NotFoundError,
  409: ConflictError,
  422: UnprocessableEntityError,
  500: InternalServerError,
  502: BadGatewayError,
  504: GatewayTimeoutError,
};

export function apiErrorFromAxios(error: AxiosError): iCoDerAPIError | AxiosError {
  if (!axios.isAxiosError(error) || !error.response) return error;
  const status = error.response.status;
  const ErrorType = STATUS_ERRORS[status] ?? iCoDerAPIError;
  return new ErrorType(status, requestIdFrom(error), sanitizedBody(error.response.data));
}
