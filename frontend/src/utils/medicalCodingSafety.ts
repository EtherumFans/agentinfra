/**
 * A failed runtime envelope must never be projected as a clinical review.
 *
 * Some coding views historically inferred PASS when review fields were
 * absent.  Provider and contract failures intentionally omit those fields,
 * so the transport error flag is the authoritative publication boundary.
 */
export function shouldRenderCodingReviewSummary(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  return !Boolean((value as { error?: unknown }).error);
}
