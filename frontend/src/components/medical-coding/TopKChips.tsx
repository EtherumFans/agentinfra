/**
 * TopKChips - clickable list of top-K ICD code candidates for one diagnosis.
 *
 * Each chip shows the code, name, and source (llm/retrieve/rerank). Clicking
 * a chip emits the selected code via `onSelect`. The selected chip is
 * highlighted.
 */
import React from 'react';
import { CandidateCode } from '../../types/runtime';
import { useT } from '../../i18n';

interface TopKChipsProps {
  candidates: CandidateCode[];
  selectedCode?: string;
  onSelect?: (code: CandidateCode) => void;
}

const SOURCE_LABELS: Record<CandidateCode['source'], string> = {
  llm: 'LLM',
  retrieve: 'RAG',
  differentiation_kb: 'KB',
  rerank: '★',
};

const SOURCE_COLORS: Record<CandidateCode['source'], string> = {
  llm: 'bg-blue-50 text-blue-700 border-blue-200',
  retrieve: 'bg-gray-50 text-gray-700 border-gray-200',
  differentiation_kb: 'bg-purple-50 text-purple-700 border-purple-200',
  rerank: 'bg-emerald-50 text-emerald-700 border-emerald-300',
};

export const TopKChips: React.FC<TopKChipsProps> = ({
  candidates,
  selectedCode,
  onSelect,
}) => {
  const t = useT();
  if (!candidates.length) {
    return <div className="text-xs text-gray-400 italic">{t.topKChipsNoCandidates}</div>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {candidates.map((c, i) => {
        const isSelected = c.code === selectedCode;
        const baseClass = SOURCE_COLORS[c.source] || SOURCE_COLORS.retrieve;
        const selectedClass = isSelected
          ? 'ring-2 ring-emerald-500 ring-offset-1'
          : 'hover:ring-1 hover:ring-gray-300';
        return (
          <button
            key={`${c.code}-${i}`}
            type="button"
            onClick={() => onSelect?.(c)}
            className={`inline-flex items-center gap-1.5 px-2 py-1 text-xs rounded-md border ${baseClass} ${selectedClass} transition-all`}
            title={`${c.name || '(no name)'} (score=${c.score.toFixed(3)}, source=${c.source})`}
          >
            <span className="font-mono font-semibold">{c.code}</span>
            {c.name && (
              <span className="text-gray-600 max-w-[120px] truncate">{c.name}</span>
            )}
            <span className="text-[10px] text-gray-400 ml-0.5">
              {SOURCE_LABELS[c.source] || c.source}
            </span>
            {c.score > 0 && (
              <span className="text-[10px] text-gray-400">·{c.score.toFixed(2)}</span>
            )}
          </button>
        );
      })}
    </div>
  );
};

