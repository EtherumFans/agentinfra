// Edit System Prompt modal - iCoDer-style, opens from agent detail Settings panel
import { useState } from 'react';
import { X, Sparkles, Loader2 } from 'lucide-react';

import { useT } from '../i18n';

interface Props {
  value: string;
  onSave: (value: string) => void;
  onCancel: () => void;
  agentName?: string;
  agentDesc?: string;
  agentCategory?: string;
}

export default function EditSystemPromptModal({ value, onSave, onCancel, agentName, agentDesc, agentCategory }: Props) {
  const t = useT();
  const [text, setText] = useState(value);
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    if (!agentName || generating) return;
    setGenerating(true);
    // /api/text-gen/generate deleted in Phase 2.1-B Step 4 (text_gen.py removed)
    // Auto-generation disabled; user must write the system prompt manually.
    setGenerating(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onCancel}>
      <div
        className="bg-card rounded-xl border border-border shadow-xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
          <div>
            <h2 className="text-base font-semibold text-foreground">{t.editSystemPromptTitle}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">{t.editSystemPromptSubtitle}</p>
          </div>
          <button onClick={onCancel} className="p-1.5 rounded-lg hover:bg-accent transition-colors">
            <X size={16} className="text-muted-foreground" />
          </button>
        </div>

        {/* Template structure hints */}
        <div className="px-6 py-3 border-b border-border bg-muted/20 shrink-0">
          <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono flex-wrap">
            <span className="text-primary font-medium">&lt;role&gt;</span>
            <span className="text-border">/</span>
            <span className="text-primary font-medium">&lt;output_format&gt;</span>
            <span className="text-border">/</span>
            <span className="text-primary font-medium">&lt;constraints&gt;</span>
            <span className="text-border">/</span>
            <span className="text-primary font-medium">&lt;workflow&gt;</span>
            <span className="text-border">/</span>
            <span className="text-primary font-medium">&lt;required_configurations&gt;</span>
            <span className="text-border">/</span>
            <span className="text-primary font-medium">&lt;quality_standards&gt;</span>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">
            {t.editSystemPromptTemplateHint}
          </p>
        </div>

        {/* Textarea */}
        <div className="flex-1 overflow-y-auto p-6">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={`<role>
You are a [specialty] [role]. Your role is to [primary function]...
</role>

<output_format>
Return your response in the following structure:

## [Section 1]
| Field | Description | Status |
|-------|-------------|--------|
| [item] | "[exact evidence]" | ✓ Supported / ⚠ Insufficient |

## [Section 2]
1. **Key**: [value]
   - **Detail**: [explanation]
   - **Evidence**: "[exact quote]"

## Summary
- Total items: [number]
- Quality: [Complete / Adequate / Insufficient]
- Confidence: [High / Medium / Low]

---
**Example Output:**

## Encounter Summary
[2-3 sentence realistic example based on documented information]

## Analysis
| Finding | Evidence | Code | Status |
|---------|----------|------|--------|
| [realistic example] | "[exact quote from mock record]" | [code] | ✓ Supported |
| [borderline case] | "[partial documentation]" | [code] | ⚠ Insufficient |

## Assignment
### Primary
- **Code**: [code]
- **Description**: [full description]
- **Rationale**: [why primary based on documentation]

### Secondary
1. **Code**: [code]
   - **Description**: [full description]
   - **Evidence**: "[exact quote]"

## Gaps
- ⚠ [Specific gap]: [What is missing and what it prevents]
- ⚠ [Ambiguity]: [Contradiction or unclear documentation]

## Unsupported Items
- ❌ [Item]: [Why it cannot be confirmed based on documentation]

## Validation Summary
- Total codes: [number]
- Documentation quality: [Complete / Adequate / Insufficient]
- Compliance confidence: [High / Medium / Low]
</output_format>

<constraints>
- [Constraint 1: what the agent must NOT do]
- [Constraint 2: evidence requirements]
- [Constraint 3: compliance boundaries]
- [Constraint 4: documentation standards]
- ...
</constraints>

<workflow>
1. **[Step 1]**: [Description]
2. **[Step 2]**: [Description]
3. **[Step 3]**: [Description]
4. **[Step 4]**: [Description]
5. **[Step 5]**: [Description]
6. **[Step 6]**: [Description]
7. **[Step 7]**: [Description]
</workflow>

<required_configurations>
Before processing, confirm:
- [Pre-condition 1]
- [Pre-condition 2]
- [Pre-condition 3]
</required_configurations>

<quality_standards>
- Every [item] must link to specific quoted documentation
- [Standard 2]
- [Standard 3]
- ...
</quality_standards>`}
            rows={22}
            className="w-full h-full min-h-[320px] border border-border rounded-lg p-4 text-xs font-mono bg-transparent text-foreground placeholder:text-foreground/70 resize-none focus:outline-none focus:ring-1 focus:ring-ring leading-relaxed"
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border shrink-0 bg-muted/20">
          <button
            onClick={handleGenerate}
            disabled={!agentName || generating}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border/50 hover:bg-accent hover:border-border disabled:opacity-40 transition-all text-muted-foreground hover:text-foreground"
          >
            {generating ? (
              <><Loader2 size={12} className="animate-spin" /> {t.editSystemPromptGenerating}</>
            ) : (
              <><Sparkles size={12} /> {t.editSystemPromptAIGenerate}</>
            )}
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={onCancel}
              className="text-sm px-4 py-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              {t.editSystemPromptCancel}
            </button>
            <button
              onClick={() => onSave(text)}
              className="text-sm px-5 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors font-medium"
            >
              {t.editSystemPromptSave}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

