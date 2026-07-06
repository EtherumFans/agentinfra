// Phase 3-B2 Loop 3 — Frontend Markdown utilities for Medical Coding Agent.
//
// Two pieces:
//   1. `generateFallbackMarkdown(v2Json)` — auto-generates a minimal
//      Markdown string from the v2 8-field JSON when the backend didn't
//      pre-render one (Loop 3 §3 降级处理).
//   2. `RenderedMarkdown` — a minimal Markdown renderer that handles the
//      constructs the backend generator emits: headings (#, ##, ###) and
//      tables (|...| header rows + |---| separator + |...| body rows).
//      Built without react-markdown to avoid adding a dependency for a
//      single page. Inline pipes inside cells are un-escaped (\\| → |)
//      before rendering.

import { useMemo } from 'react';

interface Row {
  cells: string[];
}

interface Table {
  headers: string[];
  rows: Row[];
}

interface Section {
  heading: string;
  level: 1 | 2 | 3;
  body?: string;
  table?: Table;
}

/**
 * Parse a Markdown string into sections (heading + table) for rendering.
 * Only handles the constructs the backend markdown_generator emits:
 *   - `#` / `##` / `###` headings (single line)
 *   - Tables (header row + `| --- |` separator + body rows)
 *   - Paragraph text (fallback for non-table lines)
 *
 * Anything else is treated as paragraph text.
 */
function parseMarkdown(md: string): Section[] {
  const lines = md.split('\n');
  const sections: Section[] = [];
  let current: Section | null = null;
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (current && paragraph.length > 0) {
      current.body = (current.body || '') + paragraph.join(' ') + ' ';
      paragraph = [];
    } else if (!current && paragraph.length > 0) {
      // Pre-section text — emit a synthetic section.
      sections.push({ heading: '', level: 2, body: paragraph.join(' ') });
      paragraph = [];
    }
  };

  const isTableRow = (line: string) => line.trim().startsWith('|') && line.trim().endsWith('|');
  const isTableSeparator = (line: string) =>
    isTableRow(line) && line.replace(/[^|]/g, '').replace(/\|/g, '').length === 0
      ? false
      : /^\|[\s-]+\|/.test(line.trim()) && line.includes('---');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Heading
    const headingMatch = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (headingMatch) {
      flushParagraph();
      current = {
        heading: headingMatch[2],
        level: headingMatch[1].length as 1 | 2 | 3,
      };
      sections.push(current);
      continue;
    }

    // Table — header + separator + body rows
    if (isTableRow(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      flushParagraph();
      const headers = splitRow(line);
      const rows: Row[] = [];
      i += 2; // skip header + separator
      while (i < lines.length && isTableRow(lines[i])) {
        rows.push({ cells: splitRow(lines[i]) });
        i++;
      }
      i--; // counter the for-loop's i++
      if (current) {
        current.table = { headers, rows };
      } else {
        sections.push({ heading: '', level: 2, table: { headers, rows } });
      }
      continue;
    }

    // Paragraph text
    if (trimmed) {
      paragraph.push(trimmed);
    } else {
      flushParagraph();
    }
  }
  flushParagraph();
  return sections;
}

function splitRow(line: string): string[] {
  const trimmed = line.trim().slice(1, -1); // remove leading + trailing |
  return trimmed.split('|').map((c) => c.trim().replace(/\\\|/g, '|'));
}

export function RenderedMarkdown({ markdown }: { markdown: string }) {
  const sections = useMemo(() => parseMarkdown(markdown), [markdown]);

  return (
    <div className="space-y-3 text-sm text-foreground leading-relaxed">
      {sections.map((section, idx) => (
        <div key={idx}>
          {section.level === 1 && (
            <h1 className="text-base font-bold text-foreground mb-2">{section.heading}</h1>
          )}
          {section.level === 2 && (
            <h2 className="text-sm font-semibold text-foreground mt-3 mb-1.5">{section.heading}</h2>
          )}
          {section.level === 3 && (
            <h3 className="text-[13px] font-medium text-foreground mt-2 mb-1">{section.heading}</h3>
          )}
          {section.body && (
            <p className="text-xs text-muted-foreground">{section.body.trim()}</p>
          )}
          {section.table && (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px] border-collapse">
                <thead>
                  <tr className="border-b border-border">
                    {section.table.headers.map((h, i) => (
                      <th
                        key={i}
                        className="text-left font-medium text-foreground px-2 py-1.5 bg-muted/40"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {section.table.rows.map((row, ri) => (
                    <tr key={ri} className="border-b border-border/40">
                      {row.cells.map((c, ci) => (
                        <td key={ci} className="px-2 py-1.5 align-top text-foreground/90">
                          {c || '—'}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {section.table.rows.length === 0 && (
                    <tr>
                      <td
                        colSpan={section.table.headers.length}
                        className="px-2 py-1.5 text-muted-foreground italic"
                      >
                        No items
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * Generate a minimal fallback Markdown string from a v2 JSON dict.
 * Used when the backend didn't pre-render markdown (Loop 3 §3 降级处理).
 *
 * The fallback is intentionally simple — it just emits a "JSON dump as
 * code block" so the Rendered tab isn't blank. The backend generator
 * produces the full 6-section table layout; this fallback is only for
 * degraded paths (older backend, non-medical-coding agent, etc.).
 */
export function generateFallbackMarkdown(v2: Record<string, unknown>): string {
  if (!v2 || typeof v2 !== 'object') {
    return '# Medical Coding Agent Output\n\n_No structured output available._';
  }
  const lines: string[] = ['# Medical Coding Agent Output (fallback)'];
  for (const [key, value] of Object.entries(v2)) {
    lines.push(`\n## ${key}`);
    if (value === null || value === undefined) {
      lines.push('—');
    } else if (typeof value === 'object') {
      lines.push('```json', JSON.stringify(value, null, 2), '```');
    } else {
      lines.push(String(value));
    }
  }
  return lines.join('\n');
}
