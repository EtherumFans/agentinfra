// Phase 4-C — fallback markdown renderer for CodeValidationOutput/v2.
// The backend pre-renders markdown, so this fallback only fires when
// result.markdown is empty. Verifies the v2 branch doesn't crash and
// emits the Corti-style 6-section layout (Validated Codes + Cross-Code
// Issues tables).
import { describe, it, expect } from 'vitest';

import { generateFallbackMarkdown } from '../medicalCodingMarkdown';

describe('generateFallbackMarkdown — CodeValidationOutput/v2', () => {
  it('renders validated_codes and cross_code_issues tables', () => {
    const v2 = {
      schema_ref: 'icoder/CodeValidationOutput/v2',
      review_conclusion: 'WARNING',
      manual_review_required: true,
      summary: '2 codes validated, 1 cross-code conflict.',
      validated_codes: [
        {
          code: 'I25.10',
          description: '动脉硬化性心脏病',
          status: 'PASS',
          assignable: true,
          issue: null,
        },
        {
          code: 'I25',
          description: '(category) 慢性缺血性心脏病',
          status: 'FAIL',
          assignable: false,
          issue: 'Category code — pick a more specific subdivision.',
        },
      ],
      cross_code_issues: [
        {
          issue_type: 'EXCLUDES1_CONFLICT',
          codes: ['I25.10', 'I25.5'],
          rule: 'I25.5 excludes I25.10 — cannot be coded together.',
          action: 'Remove one of the codes.',
        },
      ],
    };

    const md = generateFallbackMarkdown(v2);

    expect(md).toContain('Code Validation Agent Output (fallback v2)');
    expect(md).toContain('**Review Conclusion:** WARNING');
    expect(md).toContain('**Manual Review Required:** true');
    expect(md).toContain('**Summary:** 2 codes validated');
    expect(md).toContain('## Validated Codes');
    expect(md).toContain('I25.10');
    expect(md).toContain('动脉硬化性心脏病');
    expect(md).toContain('## Cross-Code Issues');
    expect(md).toContain('EXCLUDES1_CONFLICT');
    expect(md).toContain('I25.10, I25.5');
  });

  it('handles empty validated_codes and cross_code_issues gracefully', () => {
    const md = generateFallbackMarkdown({
      schema_ref: 'icoder/CodeValidationOutput/v2',
      review_conclusion: 'PASS',
      manual_review_required: false,
    });
    expect(md).toContain('**Review Conclusion:** PASS');
    expect(md).not.toContain('## Validated Codes');
    expect(md).not.toContain('## Cross-Code Issues');
  });
});
