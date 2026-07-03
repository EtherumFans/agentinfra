import { Fragment, type ReactNode } from "react";

// Minimal inline Markdown renderer for the tool agents' prose reports. Zero deps — matching
// the slice's "no extra packages" stance — and handles exactly what the agents are instructed
// to emit: # / ## / ### headings, **bold**, `code`, - / * and 1. lists (with indented
// continuation lines), --- dividers, and blank-line-separated paragraphs. It is deliberately
// NOT a full CommonMark implementation: no tables, no code fences, no links/images.

// Split one line into plain text, **bold** and `code` runs.
function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*|`([^`]+)`/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(<Fragment key={key++}>{text.slice(last, m.index)}</Fragment>);
    if (m[1] !== undefined) {
      nodes.push(
        <strong key={key++} className="font-semibold text-ink">
          {m[1]}
        </strong>,
      );
    } else if (m[2] !== undefined) {
      nodes.push(
        <code
          key={key++}
          className="rounded bg-surface px-1 py-0.5 font-mono text-[0.85em] text-ink"
        >
          {m[2]}
        </code>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(<Fragment key={key++}>{text.slice(last)}</Fragment>);
  return nodes;
}

// Does this (trimmed) line begin a new block? Used to stop list-item / paragraph absorption.
function isBlockStart(t: string): boolean {
  return !t || /^#{1,3}\s/.test(t) || /^---+$/.test(t) || /^\d+\.\s/.test(t) || /^[-*]\s/.test(t);
}

// A list item or paragraph spans its first line plus following non-blank, non-block-start
// lines (the agents' indented label lines), joined with <br/>.
function multiline(parts: string[]): ReactNode {
  return parts.map((p, idx) => (
    <Fragment key={idx}>
      {idx > 0 && <br />}
      {renderInline(p)}
    </Fragment>
  ));
}

export function Markdown({ source }: { source: string }) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const trimmed = lines[i].trim();

    if (!trimmed) {
      i++;
      continue;
    }
    if (/^---+$/.test(trimmed)) {
      blocks.push(<hr key={key++} className="my-4 border-line" />);
      i++;
      continue;
    }

    const h = /^(#{1,3})\s+(.*)$/.exec(trimmed);
    if (h) {
      const content = renderInline(h[2]);
      if (h[1].length === 1) {
        blocks.push(
          <h3 key={key++} className="mt-4 text-sm font-semibold text-ink first:mt-0">
            {content}
          </h3>,
        );
      } else if (h[1].length === 2) {
        blocks.push(
          <h4 key={key++} className="mt-3 text-xs font-semibold uppercase tracking-wide text-faint">
            {content}
          </h4>,
        );
      } else {
        blocks.push(
          <h5 key={key++} className="mt-2 text-xs font-semibold text-muted">
            {content}
          </h5>,
        );
      }
      i++;
      continue;
    }

    const ordered = /^\d+\.\s+/.test(trimmed);
    const unordered = /^[-*]\s+/.test(trimmed);
    if (ordered || unordered) {
      const items: ReactNode[] = [];
      const marker = ordered ? /^\d+\.\s+/ : /^[-*]\s+/;
      while (i < lines.length && marker.test(lines[i].trim())) {
        const parts = [lines[i].trim().replace(marker, "")];
        i++;
        while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i].trim())) {
          parts.push(lines[i].trim());
          i++;
        }
        items.push(
          <li key={items.length} className="text-sm leading-relaxed text-ink">
            {multiline(parts)}
          </li>,
        );
      }
      blocks.push(
        ordered ? (
          <ol key={key++} className="ml-4 list-decimal space-y-1.5 marker:text-faint">
            {items}
          </ol>
        ) : (
          <ul key={key++} className="ml-4 list-disc space-y-1 marker:text-faint">
            {items}
          </ul>
        ),
      );
      continue;
    }

    const para = [trimmed];
    i++;
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i].trim())) {
      para.push(lines[i].trim());
      i++;
    }
    blocks.push(
      <p key={key++} className="text-sm leading-relaxed text-ink">
        {multiline(para)}
      </p>,
    );
  }

  return <div className="space-y-2">{blocks}</div>;
}
