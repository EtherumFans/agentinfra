// Phase 3-B2 Loop 3 - Frontend Markdown utilities for Medical Coding Agent.
//
// Two pieces:
//   1. `generateFallbackMarkdown(v2Json)` - auto-generates a minimal
//      Markdown string from the v2 8-field JSON when the backend didn't
//      pre-render one (Loop 3 §3 降级处理).
//   2. `RenderedMarkdown` - a minimal Markdown renderer that handles the
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
      // Pre-section text - emit a synthetic section.
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

    // Table - header + separator + body rows
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
                          {c || '-'}
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
 * The fallback is intentionally simple - it just emits a "JSON dump as
 * code block" so the Rendered tab isn't blank. The backend generator
 * produces the full 6-section table layout; this fallback is only for
 * degraded paths (older backend, non-medical-coding agent, etc.).
 */
export function generateFallbackMarkdown(v2: Record<string, unknown>): string {
  if (!v2 || typeof v2 !== 'object') {
    return '# Medical Coding Agent Output\n\n_No structured output available._';
  }
  // Phase 3-D2 Task 4 - dispatch to per-agent fallback renderers keyed
  // by schema_ref. The backend pre-render is the SSOT (result.markdown);
  // this fallback only fires when the backend didn't pre-render (legacy
  // /old pack). Each branch produces a minimal structured view so the
  // Rendered tab still shows something useful.
  const schemaRef = (v2.schema_ref as string) || (v2.output_contract as string) || '';
  if (
    schemaRef === 'icoder/CodeValidationOutput/v2'
    || schemaRef === 'icoder/CodeValidationOutput/v3'
    || schemaRef === 'icoder/CodeValidationOutput/v4'
    || schemaRef === 'icoder/CodeValidationOutput/v5'
  ) {
    return _fallbackCodeValidationV2(v2);
  }
  if (schemaRef === 'icoder/CodeValidationOutput/v1') {
    return _fallbackCodeValidation(v2);
  }
  if (schemaRef === 'icoder/ComplianceGuardrailOutput/v1' || schemaRef === 'icoder/ComplianceGuardrailOutput/v2') {
    return _fallbackComplianceGuardrail(v2);
  }
  if (schemaRef === 'icoder/NoteCompletenessOutput/v1' || schemaRef === 'icoder/NoteCompletenessOutput/v2') {
    return _fallbackNoteCompleteness(v2);
  }
  // Default fallback: generic JSON dump (covers MedicalCodingAgentOutputV2
  // and unknown schemas).
  const lines: string[] = ['# Medical Coding Agent Output (fallback)'];
  for (const [key, value] of Object.entries(v2)) {
    lines.push(`\n## ${key}`);
    if (value === null || value === undefined) {
      lines.push('-');
    } else if (typeof value === 'object') {
      lines.push('```json', JSON.stringify(value, null, 2), '```');
    } else {
      lines.push(String(value));
    }
  }
  return lines.join('\n');
}

function _fallbackCodeValidationV2(v2: Record<string, unknown>): string {
  // Phase 4-C - v2 schema (BREAKING). The backend pre-renders markdown;
  // this fallback only fires when result.markdown is empty (legacy /
  // degraded path). Mirrors the 6-section layout.
  const lines: string[] = ['# Code Validation Agent Output (fallback v2)'];
  lines.push(`\n**Review Conclusion:** ${v2.review_conclusion ?? '-'}`);
  lines.push(`\n**Manual Review Required:** ${v2.manual_review_required ?? '-'}`);
  if (v2.summary) lines.push(`\n**Summary:** ${v2.summary}`);
  const validated = (v2.validated_codes as Array<Record<string, unknown>>) || [];
  if (validated.length) {
    lines.push('\n## Validated Codes\n');
    lines.push('| Code | Description | Status | Assignable | Issue |');
    lines.push('| --- | --- | --- | --- | --- |');
    for (const c of validated) {
      lines.push(
        `| ${c.code ?? '-'} | ${c.description ?? '-'} | ${c.status ?? '-'} | ${c.assignable ?? '-'} | ${c.issue ?? '-'} |`,
      );
    }
  }
  const cross = (v2.cross_code_issues as Array<Record<string, unknown>>) || [];
  if (cross.length) {
    lines.push('\n## Cross-Code Issues\n');
    lines.push('| Issue Type | Codes | Rule | Action |');
    lines.push('| --- | --- | --- | --- |');
    for (const i of cross) {
      const codes = Array.isArray(i.codes) ? (i.codes as string[]).join(', ') : '-';
      lines.push(`| ${i.issue_type ?? '-'} | ${codes} | ${i.rule ?? '-'} | ${i.action ?? '-'} |`);
    }
  }
  return lines.join('\n');
}

function _fallbackCodeValidation(v2: Record<string, unknown>): string {
  const lines: string[] = ['# Code Validation Agent Output (fallback)'];
  lines.push(`\n**Review Conclusion:** ${v2.review_conclusion ?? '-'}`);
  lines.push(`\n**Manual Review Required:** ${v2.manual_review_required ?? '-'}`);
  lines.push(`\n**Rule Set:** ${v2.rule_set ?? '-'}`);
  const fired = (v2.fired_rules as string[]) || [];
  lines.push('\n## Fired Rules\n');
  lines.push('| Rule ID |');
  lines.push('| --- |');
  for (const r of fired) lines.push(`| ${r} |`);
  const issues = (v2.issues_found as Array<Record<string, unknown>>) || [];
  if (issues.length) {
    lines.push('\n## Issues Found\n');
    lines.push('| Rule ID | Severity | Code | Message |');
    lines.push('| --- | --- | --- | --- |');
    for (const i of issues) {
      lines.push(`| ${i.rule_id ?? '-'} | ${i.severity ?? '-'} | ${i.code ?? '-'} | ${i.message ?? '-'} |`);
    }
  }
  return lines.join('\n');
}

function _fallbackComplianceGuardrail(v2: Record<string, unknown>): string {
  const lines: string[] = ['# Compliance Guardrail Agent Output (fallback)'];
  lines.push(`\n**Risk Conclusion:** ${v2.review_conclusion ?? '-'}`);
  lines.push(`\n**DRG Suggestion:** ${v2.drg_suggestion ?? '-'}`);
  const checks = (v2.compliance_checks as Array<Record<string, unknown>>) || [];
  if (checks.length) {
    lines.push('\n## Compliance Checks\n');
    lines.push('| Check ID | Passed | Severity |');
    lines.push('| --- | --- | --- |');
    for (const c of checks) {
      lines.push(`| ${c.check_id ?? '-'} | ${c.passed ?? '-'} | ${c.severity ?? '-'} |`);
    }
  }
  return lines.join('\n');
}

function _fallbackNoteCompleteness(v2: Record<string, unknown>): string {
  const lines: string[] = ['# Note Completeness Agent Output (fallback)'];
  const score = v2.completeness_score;
  lines.push(
    `\n**Completeness Score:** ${typeof score === 'number' ? (score * 100).toFixed(1) + '%' : '-'}`,
  );
  const missing = (v2.missing_sections as string[]) || [];
  const present = (v2.present_sections as string[]) || [];
  lines.push('\n## Missing Sections\n');
  for (const s of missing) lines.push(`- ${s}`);
  if (!missing.length) lines.push('_(none)_');
  lines.push('\n## Present Sections\n');
  for (const s of present) lines.push(`- ${s}`);
  if (!present.length) lines.push('_(none)_');
  return lines.join('\n');
}
