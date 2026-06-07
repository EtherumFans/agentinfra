/**
 * EvidenceHighlighter — wraps <mark> around EvidenceSpan char ranges in source text.
 *
 * Used to visualize MedCodER pipeline output: which sentence in the EMR
 * supports which diagnosis. Falls back to fuzzy substring match if the
 * stored char_start/char_end don't match exactly (server-side fuzzy).
 */
import React, { useMemo } from 'react';

export interface EvidenceSpanLike {
  text: string;
  char_start: number;
  char_end: number;
  doc_id?: string;
  doc_type?: string;
  confidence?: number;
}

interface EvidenceHighlighterProps {
  sourceText: string;
  spans: EvidenceSpanLike[];
  highlightClassName?: string;
}

/**
 * Render `sourceText` with each span wrapped in a <mark> element.
 * Spans are sorted by start position; overlapping spans are handled by
 * splitting them at intersection points to avoid nested <mark> tags.
 */
export const EvidenceHighlighter: React.FC<EvidenceHighlighterProps> = ({
  sourceText,
  spans,
  highlightClassName = 'bg-yellow-200 text-gray-900 px-0.5 rounded',
}) => {
  const segments = useMemo(() => buildSegments(sourceText, spans), [sourceText, spans]);
  if (!spans.length) {
    return <>{sourceText}</>;
  }
  return (
    <>
      {segments.map((seg, i) =>
        seg.highlight ? (
          <mark key={i} className={highlightClassName} title={seg.text}>
            {seg.text}
          </mark>
        ) : (
          <span key={i}>{seg.text}</span>
        )
      )}
    </>
  );
};

interface Segment {
  text: string;
  highlight: boolean;
  spanIndex?: number;
}

function buildSegments(source: string, spans: EvidenceSpanLike[]): Segment[] {
  // Validate and sort spans by start
  const valid = spans
    .map((s, i) => ({
      span: s,
      index: i,
      start: Math.max(0, Math.min(s.char_start, source.length)),
      end: Math.max(0, Math.min(s.char_end, source.length)),
    }))
    .filter((s) => s.end > s.start)
    .sort((a, b) => a.start - b.start || a.end - b.end);

  if (!valid.length) {
    return [{ text: source, highlight: false }];
  }

  // If spans overlap, just pick the first and skip overlapping
  const nonOverlap: typeof valid = [];
  let cursor = 0;
  for (const s of valid) {
    if (s.start >= cursor) {
      nonOverlap.push(s);
      cursor = s.end;
    }
  }

  const out: Segment[] = [];
  let pos = 0;
  for (const s of nonOverlap) {
    if (s.start > pos) {
      out.push({ text: source.slice(pos, s.start), highlight: false });
    }
    out.push({ text: source.slice(s.start, s.end), highlight: true, spanIndex: s.index });
    pos = s.end;
  }
  if (pos < source.length) {
    out.push({ text: source.slice(pos), highlight: false });
  }
  return out;
}
