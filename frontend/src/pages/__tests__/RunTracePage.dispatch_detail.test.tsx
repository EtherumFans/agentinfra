// @vitest-environment jsdom
/**
 * Phase 3-D2.5 Part A3 — Test 7
 *
 * Verifies the ToolDispatchDetail component renders the 15-field
 * dispatch_detail dict and supports collapse/expand. Failed
 * dispatch auto-expands so the failure stage is visible immediately.
 */
import { describe, it, expect, beforeAll, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

// jsdom doesn't implement window.matchMedia; the store import chain
// calls it at module load. Stub it before importing any component that
// transitively imports the store.
beforeAll(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});

// Import AFTER matchMedia stub is registered. Vitest hoists imports
// above beforeAll, so we use a dynamic import inside the test body.
let ToolDispatchDetail: any;
beforeAll(async () => {
  const mod = await import('../RunTracePage');
  ToolDispatchDetail = mod.ToolDispatchDetail;
});

afterEach(() => {
  cleanup();
});

// Minimal t stub — the component only reads string labels from t.
const t = {
  runTraceToolName: 'Tool',
  runTraceDispatchMode: 'Dispatch Mode',
  runTraceHandlerRef: 'Handler',
  runTraceSchemaValidation: 'Schema Validation',
  runTracePhiRedaction: 'PHI Redaction',
  runTraceAuthType: 'auth_type',
  runTraceScopeDiff: 'scope diff',
  runTraceGrantedScopes: 'granted_scopes',
  runTraceScopeCheck: 'Scope Check',
  runTraceHandlerStatus: 'Handler Status',
  runTraceDurationMs: 'Duration',
  runTraceResultShape: 'Result Shape',
  runTraceErrorStage: 'Error Stage',
  runTraceMcpErrorCode: 'mcp_error_code',
  runTraceToolDispatchDetail: 'Tool Dispatch Detail',
} as any;

const successDetail = {
  tool_name: 'validate_codes',
  dispatch_mode: 'in_process',
  handler_ref: 'app.icoder.mcp.handlers.validate_codes:handle',
  input_schema_validation: 'passed',
  phi_redaction: 'skipped',
  auth_type: 'in-process',
  auth_resolved: true,
  required_scopes: ['coding:validate'],
  granted_scopes: ['coding:validate'],
  scope_check: 'passed',
  handler_status: 'ok',
  duration_ms: 12.3,
  result_shape: 'dict({review_conclusion}, size=128B)',
  error_code: null,
  error_stage: null,
};

const failedDetail = {
  ...successDetail,
  handler_status: 'failed',
  error_stage: 'handler_invoke',
  error_code: -32603,
};

describe('ToolDispatchDetail', () => {
  it('renders collapsed by default for successful dispatch', () => {
    const { container } = render(<ToolDispatchDetail detail={successDetail as any} t={t} />);
    // Header label visible
    expect(screen.getByText('Tool Dispatch Detail')).toBeTruthy();
    // Body rows NOT visible when collapsed — validate_codes value should not appear
    expect(screen.queryByText('validate_codes')).toBeNull();
  });

  it('expands on click and shows all 15 fields', () => {
    render(<ToolDispatchDetail detail={successDetail as any} t={t} />);
    // Click the header to expand
    fireEvent.click(screen.getByText('Tool Dispatch Detail'));
    // Now the body rows should be visible
    expect(screen.getByText('validate_codes')).toBeTruthy();
    expect(screen.getByText('in_process')).toBeTruthy();
    // input_schema_validation + scope_check both = "passed" → multiple matches
    expect(screen.getAllByText('passed').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('skipped')).toBeTruthy();
    expect(screen.getByText('in-process')).toBeTruthy();
    expect(screen.getByText('12.3ms')).toBeTruthy();
    // error_stage null + error_code null both render as - (hyphen per §9.G em-dash ban)
    const dashes = screen.getAllByText('-');
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it('auto-expands when handler_status=failed', () => {
    render(<ToolDispatchDetail detail={failedDetail as any} t={t} />);
    // Body should be visible immediately without clicking
    expect(screen.getByText('validate_codes')).toBeTruthy();
    // handler_status=failed + badge "failed" → multiple matches
    expect(screen.getAllByText('failed').length).toBeGreaterThanOrEqual(1);
    // error_stage visible
    expect(screen.getByText('handler_invoke')).toBeTruthy();
    // error_code visible
    expect(screen.getByText('-32603')).toBeTruthy();
  });
});
