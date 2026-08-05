/**
 * DiagnosisCard - one disease extracted by the Medical Coding Agent.
 *
 * Shows:
 *   - disease_text (the normalized disease name)
 *   - supporting_evidence chips (LLM-extracted + char-anchored spans)
 *   - TopKChips of the final ranked codes (click to override)
 *   - Override code input (free text)
 *   - Per-diagnosis confidence badge
 *
 * Renders inside MedicalCodingPage right panel for mode="medcoder" results.
 *
 * Note: the underlying runtime mode is 'medcoder' (the internal engine name);
 * user-facing UI labels this as "编码管线" / "Coding pipeline" per Corti
 * alignment (Phase 3-A). The internal_engine name does not surface to users.
 */
import React, { useState } from 'react';

import { ExtractedDiagnosis, CandidateCode } from '../../types/runtime';
import { useT } from '../../i18n';

import { TopKChips } from './TopKChips';

interface DiagnosisCardProps {
  diagnosis: ExtractedDiagnosis;
  index: number;
  onSelectCode?: (dxIndex: number, code: CandidateCode) => void;
  onOverride?: (dxIndex: number, code: string) => void;
  selectedCode?: string;
}

export const DiagnosisCard: React.FC<DiagnosisCardProps> = ({
  diagnosis,
  index,
  onSelectCode,
  onOverride,
  selectedCode,
}) => {
  const t = useT();
  const [overrideDraft, setOverrideDraft] = useState('');
  const conf = diagnosis.final_confidence;
  const confColor =
    conf >= 0.8 ? 'bg-emerald-100 text-emerald-700' :
    conf >= 0.5 ? 'bg-amber-100 text-amber-700' :
    'bg-rose-100 text-rose-700';

  // Simple {{placeholder}} interpolation
  const interpolate = (template: string, vars: Record<string, string | number>): string =>
    template.replace(/\{\{(\w+)\}\}/g, (_, k) => String(vars[k] ?? ''));

  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1">
          <div className="text-xs text-gray-400 mb-0.5">
            {interpolate(t.diagnosisNumber, { n: index + 1 })}
          </div>
          <div className="text-sm font-semibold text-gray-900">
            {diagnosis.disease_text || t.noDiseaseName}
          </div>
        </div>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${confColor}`}>
          {interpolate(t.confidencePercent, { p: (conf * 100).toFixed(0) })}
        </span>
      </div>

      {/* Supporting evidence */}
      {diagnosis.supporting_evidence.length > 0 && (
        <div className="mb-2">
          <div className="text-[11px] text-gray-500 mb-1">{t.supportingEvidence}</div>
          <div className="flex flex-wrap gap-1">
            {diagnosis.supporting_evidence.map((span, i) => (
              <span
                key={i}
                className="inline-block text-xs bg-yellow-50 text-gray-700 border border-yellow-200 rounded px-1.5 py-0.5"
                title={interpolate(t.positionRange, {
                  start: span.char_start,
                  end: span.char_end,
                })}
              >
                {span.text.slice(0, 40)}{span.text.length > 40 ? '…' : ''}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* LLM initial code (Stage 1) */}
      {diagnosis.llm_initial_code && (
        <div className="mb-2 text-xs text-gray-500">
          {t.llmInitialCode}: <span className="font-mono">{diagnosis.llm_initial_code}</span>
        </div>
      )}

      {/* Top-K chips (Stage 4 final) */}
      {diagnosis.final_top_k.length > 0 && (
        <div className="mb-2">
          <div className="text-[11px] text-gray-500 mb-1">
            {interpolate(t.topKClickHint, { k: diagnosis.final_top_k.length })}
          </div>
          <TopKChips
            candidates={diagnosis.final_top_k}
            selectedCode={selectedCode}
            onSelect={(c) => onSelectCode?.(index, c)}
          />
        </div>
      )}

      {/* Override input */}
      <div className="flex items-center gap-1.5 mt-2">
        <input
          type="text"
          value={overrideDraft}
          onChange={(e) => setOverrideDraft(e.target.value)}
          placeholder={t.overridePlaceholder}
          className="flex-1 text-xs px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-emerald-500"
        />
        <button
          type="button"
          onClick={() => {
            if (overrideDraft.trim()) {
              onOverride?.(index, overrideDraft.trim());
              setOverrideDraft('');
            }
          }}
          disabled={!overrideDraft.trim()}
          className="text-xs px-2 py-1 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-gray-700 rounded"
        >
          {t.overrideConfirm}
        </button>
      </div>

      {/* Re-rank notes */}
      {diagnosis.rerank_notes && (
        <div className="text-[11px] text-gray-400 mt-1.5 italic">
          {diagnosis.rerank_notes}
        </div>
      )}
    </div>
  );
};
