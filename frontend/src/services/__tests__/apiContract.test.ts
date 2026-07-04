/**
 * API contract test — asserts every hardcoded API path in frontend service files
 * exists in the backend OpenAPI schema (committed at docs/openapi/openapi.json).
 *
 * Catches the class of bugs where frontend calls a path the backend never declared
 * (e.g., the ISSUE-005 from QA Cycle 24 where a2aApi hit /experts/a2a/* paths
 * that never existed on the backend).
 *
 * How it works:
 *   1. Reads each service file (api.ts, runtimeApi.ts)
 *   2. Detects the axios.create({ baseURL: '...' }) for that file
 *   3. Extracts every api.<method>('path') or api.<method>(`template-${literal}`) call
 *   4. Normalizes template literals: ${var} → {var} (OpenAPI param syntax)
 *   5. Strips encodeURIComponent(...) wrappers
 *   6. Combines baseURL + path → full path
 *   7. Asserts openapiSchema.paths[fullPath][method] exists
 *
 * Whitelist: paths that can't be statically extracted (e.g., axios.get() on root
 * paths outside the api instance) live in path_whitelist.json with documented reasons.
 */
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

type HttpMethod = 'get' | 'post' | 'put' | 'patch' | 'delete';

interface PathCall {
  method: HttpMethod;
  path: string; // already normalized: template literals → {param}, encodeURIComponent stripped
  file: string;
  line: number;
  raw: string; // original matched string, for error messages
}

const FRONTEND_DIR = path.resolve(__dirname, '..'); // src/services/
const REPO_ROOT = path.resolve(FRONTEND_DIR, '..', '..', '..'); // E:/Corti4C/
const OPENAPI_PATH = path.resolve(REPO_ROOT, 'docs', 'openapi', 'openapi.json');
const WHITELIST_PATH = path.resolve(REPO_ROOT, 'docs', 'openapi', 'path_whitelist.json');

// Map service file → baseURL. Detected from axios.create({ baseURL: '...' }) in each file.
// Hardcoded here because the test runs against known files; if a new service file is added,
// the test fails with "no baseURL found" which prompts the developer to add it here.
const SERVICE_FILES: Record<string, string> = {
  'api.ts': '/api',
  'runtimeApi.ts': '/api/runtime',
};

function loadWhitelist(): Record<string, string> {
  if (!fs.existsSync(WHITELIST_PATH)) {
    return {};
  }
  return JSON.parse(fs.readFileSync(WHITELIST_PATH, 'utf-8'));
}

function normalizePath(p: string): string {
  // Strip encodeURIComponent(...) wrappers — just keep the inner identifier
  let normalized = p.replace(/encodeURIComponent\(([^)]+)\)/g, '$1');
  // Convert template literal ${var} → OpenAPI {var}
  normalized = normalized.replace(/\$\{([^}]+)\}/g, '{$1}');
  return normalized;
}

/**
 * Canonicalize a path for comparison by replacing every {param} with the literal
 * "{param}" placeholder. This makes the contract test tolerant of param-name
 * differences between frontend (camelCase, e.g. {agentRef}) and backend
 * (snake_case, e.g. {agent_ref}) — FastAPI matches path params by position,
 * not by name, so {agentRef} and {agent_ref} route identically.
 *
 * The segment structure still has to match: /a/{x}/b/{y} won't match /a/{x}/{y}.
 */
function canonicalizePath(p: string): string {
  return p.replace(/\{[^}]+\}/g, '{param}');
}

function extractPathCalls(content: string, file: string): PathCall[] {
  const calls: PathCall[] = [];

  // Match api.<method>('<path>') or api.<method>(`<path>`, ...)
  // Path may be a single-quoted string, double-quoted string, or template literal.
  // Template literals can contain ${expr} which we normalize to {param}.
  const methodPattern = /api\.(get|post|put|patch|delete)\s*\(\s*(['"`])([^`'"]*?)\2/g;

  let match: RegExpExecArray | null;
  while ((match = methodPattern.exec(content)) !== null) {
    const method = match[1] as HttpMethod;
    const rawPath = match[3];
    const line = content.slice(0, match.index).split('\n').length;

    calls.push({
      method,
      path: normalizePath(rawPath),
      file,
      line,
      raw: match[0],
    });
  }

  return calls;
}

function loadOpenApiSchema(): any {
  if (!fs.existsSync(OPENAPI_PATH)) {
    throw new Error(
      `OpenAPI schema not found at ${OPENAPI_PATH}. ` +
      `Run \`python backend/scripts/export_openapi.py\` to generate it.`
    );
  }
  return JSON.parse(fs.readFileSync(OPENAPI_PATH, 'utf-8'));
}

describe('API contract', () => {
  const schema = loadOpenApiSchema();
  const whitelist = loadWhitelist();
  const paths = schema.paths || {};

  // Collect all calls across all service files
  const allCalls: PathCall[] = [];
  for (const [file, baseURL] of Object.entries(SERVICE_FILES)) {
    const filePath = path.resolve(FRONTEND_DIR, file);
    if (!fs.existsSync(filePath)) {
      continue; // skip missing files
    }
    const content = fs.readFileSync(filePath, 'utf-8');
    const calls = extractPathCalls(content, file).map(c => ({
      ...c,
      path: baseURL + c.path,
    }));
    allCalls.push(...calls);
  }

  if (allCalls.length === 0) {
    throw new Error('No API calls found — check that SERVICE_FILES is correct');
  }

  it.each(allCalls)(
    '$file:$line $method $path exists in OpenAPI',
    (call: PathCall) => {
      // Whitelist overrides the path entirely (for dynamic paths not detectable via regex)
      const fullPath = whitelist[call.path] ?? call.path;
      const canonicalFull = canonicalizePath(fullPath);

      // Look up by canonical form — try each OpenAPI path and see if it canonicalizes to the same form
      const matchingPath = Object.keys(paths).find(
        opPath => canonicalizePath(opPath) === canonicalFull
      );

      if (!matchingPath) {
        throw new Error(
          `${call.file}:${call.line} — path ${call.method.toUpperCase()} ${fullPath} ` +
          `not in OpenAPI schema (no path canonicalizes to ${canonicalFull}). ` +
          `(original: ${call.raw})`
        );
      }

      if (!paths[matchingPath][call.method]) {
        const available = Object.keys(paths[matchingPath]).filter(k => !['parameters', '$ref'].includes(k));
        throw new Error(
          `${call.file}:${call.line} — method ${call.method.toUpperCase()} not on path ${matchingPath}. ` +
          `Available methods: ${available.join(', ')}`
        );
      }

      expect(paths[matchingPath][call.method]).toBeDefined();
    }
  );

  it('whitelist entries are valid OpenAPI paths', () => {
    for (const [from, to] of Object.entries(whitelist)) {
      if (!paths[to]) {
        throw new Error(
          `Whitelist maps "${from}" → "${to}" but "${to}" is not in OpenAPI schema. ` +
          `Either fix the whitelist entry or remove it.`
        );
      }
    }
  });
});
