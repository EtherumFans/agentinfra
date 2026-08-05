/**
 * HighlightedTextarea - textarea + absolutely-positioned <pre> overlay
 * that renders evidence highlights behind the editable text.
 *
 * Why not contenteditable?
 *   Chinese IME composition events (拼音) on contenteditable routinely
 *   eat the composed character. The textarea + <pre> overlay pattern keeps
 *   native textarea semantics (selection, copy/paste, IME) intact while
 *   letting us draw highlights in a sibling <pre>.
 *
 * Font-metric sync:
 *   Both the <textarea> and the <pre> use INPUT_TEXT_CLASS (shared below)
 *   so that the highlight positions match the text glyphs exactly. If you
 *   tweak the class, both sides update together - DO NOT hardcode a
 *   different font on either side.
 *
 * Scroll sync:
 *   The <textarea> onScroll handler keeps the overlay in lockstep. The
 *   overlay has pointer-events: none so the textarea owns all input.
 *
 * IME:
 *   onCompositionEnd (not onChange) drives the highlight re-render during
 *   Chinese composition, so the user doesn't see a "flash of un-highlighted
 *   text" mid-composition.
 */
import React, { useRef, useCallback } from 'react';

import { EvidenceHighlighter, EvidenceSpanLike } from './EvidenceHighlighter';

// Shared FONT/PADDING metrics. Both textarea and overlay use this so
// highlight positions line up with the editable text glyphs.
const INPUT_TEXT_METRICS =
  'text-sm font-sans leading-relaxed whitespace-pre-wrap break-words p-3';

// Shared visual chrome. Both sides use this.
const INPUT_CHROME =
  'rounded-lg border border-border/30 bg-background';

export const INPUT_TEXT_CLASS = `${INPUT_TEXT_METRICS} ${INPUT_CHROME} w-full text-transparent`;

export interface HighlightedTextareaProps {
  value: string;
  onChange: (next: string) => void;
  spans?: EvidenceSpanLike[];
  focusedSpanIndex?: number | null;
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
  className?: string;
}

export const HighlightedTextarea: React.FC<HighlightedTextareaProps> = ({
  value,
  onChange,
  spans = [],
  focusedSpanIndex = null,
  placeholder,
  rows = 12,
  disabled,
  className,
}) => {
  const preRef = useRef<HTMLPreElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Sync overlay scroll to textarea scroll. Cheap: just copy scrollTop/Left.
  const handleScroll = useCallback((e: React.UIEvent<HTMLTextAreaElement>) => {
    const ta = e.currentTarget;
    if (preRef.current) {
      preRef.current.scrollTop = ta.scrollTop;
      preRef.current.scrollLeft = ta.scrollLeft;
    }
  }, []);

  // During IME composition the text is still mid-flight; refresh highlight
  // only after compositionEnd to avoid flashing un-highlighted text.
  const handleCompositionEnd = useCallback(
    (e: React.CompositionEvent<HTMLTextAreaElement>) => {
      onChange((e.target as HTMLTextAreaElement).value);
    },
    [onChange],
  );

  return (
    <div className={`relative ${className ?? ''}`}>
      <pre
        ref={preRef}
        aria-hidden="true"
        className={`${INPUT_TEXT_METRICS} ${INPUT_CHROME} absolute inset-0 pointer-events-none overflow-auto m-0 text-foreground`}
        style={{ wordBreak: 'break-word' }}
      >
        <EvidenceHighlighter
          sourceText={value + '\n'}
          spans={spans}
          focusedSpanIndex={focusedSpanIndex}
        />
      </pre>
      <textarea
        ref={taRef}
        value={value}
        rows={rows}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onCompositionEnd={handleCompositionEnd}
        onScroll={handleScroll}
        spellCheck={false}
        data-testid="char-counter-input"
        className={`${INPUT_TEXT_CLASS} relative h-full caret-foreground resize-none bg-transparent focus:outline-none focus:ring-2 focus:ring-primary/20`}
      />
    </div>
  );
};
