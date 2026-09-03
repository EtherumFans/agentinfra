import { describe, expect, it } from 'vitest';

import { shouldRenderCodingReviewSummary } from '../medicalCodingSafety';

describe('shouldRenderCodingReviewSummary', () => {
  it('suppresses a failed envelope even when an optimistic nested PASS exists', () => {
    expect(shouldRenderCodingReviewSummary({
      error: true,
      result: {
        validation_summary: { passed: true },
        human_review: { review_conclusion: 'PASS' },
      },
    })).toBe(false);
  });

  it('allows successful current and legacy result shapes', () => {
    expect(shouldRenderCodingReviewSummary({ error: false, review_conclusion: 'PASS' })).toBe(true);
    expect(shouldRenderCodingReviewSummary({ review_conclusion: 'WARNING' })).toBe(true);
  });

  it('does not render an absent result', () => {
    expect(shouldRenderCodingReviewSummary(null)).toBe(false);
  });
});
