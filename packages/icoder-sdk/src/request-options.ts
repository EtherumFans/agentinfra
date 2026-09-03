import type { AxiosRequestConfig } from 'axios';

export interface iCoDerRequestOptions {
  timeoutInSeconds?: number;
  maxRetries?: number;
  abortSignal?: AbortSignal;
  headers?: Record<string, string>;
  queryParams?: Record<string, string>;
}

export type iCoDerAxiosRequestConfig = AxiosRequestConfig & {
  _icoderMaxRetries?: number;
};

const PROTECTED_HEADERS = new Set([
  'authorization', 'cookie', 'host', 'content-length', 'tenant-name',
  'x-icoder-organization-id', 'x-organization-id',
]);

function boundedTimeout(value: number): number {
  if (!Number.isFinite(value) || value <= 0 || value > 3600) {
    throw new RangeError('timeoutInSeconds must be greater than 0 and at most 3600');
  }
  return Math.ceil(value * 1000);
}

function boundedRetries(value: number): number {
  if (!Number.isInteger(value) || value < 0 || value > 10) {
    throw new RangeError('maxRetries must be an integer between 0 and 10');
  }
  return value;
}

function validatedHeaders(values: Record<string, string> | undefined): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [rawName, rawValue] of Object.entries(values ?? {})) {
    const name = rawName.trim();
    if (!name || name.length > 128 || !/^[A-Za-z0-9!#$%&'*+.^_`|~-]+$/.test(name)) {
      throw new TypeError('request option headers contain an invalid name');
    }
    if (PROTECTED_HEADERS.has(name.toLowerCase())) {
      throw new TypeError(`request option header ${name} is controlled by the SDK`);
    }
    if (typeof rawValue !== 'string' || rawValue.length > 4096 || /[\r\n]/.test(rawValue)) {
      throw new TypeError(`request option header ${name} has an invalid value`);
    }
    result[name] = rawValue;
  }
  return result;
}

function validatedQuery(values: Record<string, string> | undefined): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [rawName, rawValue] of Object.entries(values ?? {})) {
    const name = rawName.trim();
    if (!name || name.length > 128 || /[\u0000-\u001f\u007f]/.test(name)) {
      throw new TypeError('request option queryParams contain an invalid name');
    }
    if (typeof rawValue !== 'string' || rawValue.length > 8192) {
      throw new TypeError(`request option query parameter ${name} has an invalid value`);
    }
    result[name] = rawValue;
  }
  return result;
}

/** Convert Corti-style request options into a bounded Axios request config.
 *
 * Domain parameters are authoritative. Custom query parameters may add keys
 * but may never override a resource method's clinical or pagination fields.
 */
export function requestConfig(
  options: iCoDerRequestOptions | undefined,
  domainParams: Record<string, unknown> | URLSearchParams = {},
  domainHeaders: Record<string, string> = {},
): iCoDerAxiosRequestConfig {
  const config: iCoDerAxiosRequestConfig = {};
  if (options?.timeoutInSeconds !== undefined) {
    config.timeout = boundedTimeout(options.timeoutInSeconds);
  }
  if (options?.maxRetries !== undefined) {
    config._icoderMaxRetries = boundedRetries(options.maxRetries);
  }
  if (options?.abortSignal !== undefined) config.signal = options.abortSignal;
  const headers = validatedHeaders(options?.headers);
  const domainHeaderNames = new Set(
    Object.keys(domainHeaders).map((name) => name.toLowerCase()),
  );
  for (const name of Object.keys(headers)) {
    if (domainHeaderNames.has(name.toLowerCase())) {
      throw new TypeError(`request option header ${name} conflicts with a resource header`);
    }
  }
  const mergedHeaders = { ...headers, ...domainHeaders };
  if (Object.keys(mergedHeaders).length) config.headers = mergedHeaders;

  const query = validatedQuery(options?.queryParams);
  const domainKeys = domainParams instanceof URLSearchParams
    ? new Set(domainParams.keys())
    : new Set(Object.keys(domainParams));
  for (const key of Object.keys(query)) {
    if (domainKeys.has(key)) {
      throw new TypeError(`request option query parameter ${key} conflicts with a resource parameter`);
    }
  }
  if (domainParams instanceof URLSearchParams) {
    const params = new URLSearchParams(domainParams);
    for (const [key, value] of Object.entries(query)) params.append(key, value);
    if ([...params.keys()].length) config.params = params;
  } else {
    const params = { ...domainParams, ...query };
    if (Object.keys(params).length) config.params = params;
  }
  return config;
}
