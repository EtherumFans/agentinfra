import { useState } from 'react';
import { ChevronDown, ChevronRight, FileText, AlertTriangle, ClipboardList, Stethoscope, Wrench, ExternalLink } from 'lucide-react';
import { useT } from '../../i18n';

interface Props {
  review: any;
  onViewReport?: () => void;
}

function CollapsibleSection({ icon: Icon, title, count, defaultOpen = false, children }: {
  icon: any; title: string; count?: number; defaultOpen?: boolean; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-accent/50 transition-colors"
      >
        {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
        <Icon size={14} className="text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">{title}</span>
        {count !== undefined && <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">{count}</span>}
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

export default function ReviewResults({ review, onViewReport }: Props) {
  const t = useT();
  if (!review) return null;

  const diagCandidates = (review.diagnosis_candidates && review.diagnosis_candidates.length > 0)
    ? review.diagnosis_candidates
    : (review.diagnosis_analysis || []);
  const procCandidates = (review.procedure_candidates && review.procedure_candidates.length > 0)
    ? review.procedure_candidates
    : (review.procedure_analysis || []);
  const drgImpact = review.drg_impact || {};
  const docGaps = review.documentation_gaps || [];
  const checklist = review.human_checklist || [];
  const primaryDiag = (review.primary_diagnosis && review.primary_diagnosis.code)
    ? review.primary_diagnosis
    : (diagCandidates.length > 0 ? diagCandidates[0] : {});
  const mainProc = (review.main_procedure && review.main_procedure.code)
    ? review.main_procedure
    : (procCandidates.length > 0 ? procCandidates[0] : {});

  return (
    <div className="space-y-3">
      {/* Primary results summary */}
      <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Stethoscope size={14} className="text-primary" />
              <span className="text-xs font-semibold text-foreground">{t.orchestrationDiagnosisCandidates}</span>
            </div>
            {primaryDiag.code ? (
              <div>
                <span className="text-lg font-bold font-mono text-foreground">{primaryDiag.code}</span>
                <p className="text-sm text-foreground mt-0.5">{primaryDiag.name}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Confidence: {(primaryDiag.confidence * 100).toFixed(0)}%</p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No primary diagnosis</p>
            )}
          </div>
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Wrench size={14} className="text-primary" />
              <span className="text-xs font-semibold text-foreground">{t.orchestrationProcedureCandidates}</span>
            </div>
            {mainProc.code ? (
              <div>
                <span className="text-lg font-bold font-mono text-foreground">{mainProc.code}</span>
                <p className="text-sm text-foreground mt-0.5">{mainProc.name}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">Confidence: {(mainProc.confidence * 100).toFixed(0)}%</p>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No primary procedure</p>
            )}
          </div>
        </div>
      </div>

      {/* Secondary candidates */}
      <div className="space-y-2">
        <CollapsibleSection icon={Stethoscope} title={t.orchestrationDiagnosisCandidates} count={diagCandidates.length}>
          {diagCandidates.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No candidates</p>
          ) : (
            <div className="space-y-1.5">
              {diagCandidates.map((c: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-accent/50 text-xs">
                  <div>
                    <span className="font-mono font-medium text-foreground">{c.code}</span>
                    <span className="ml-2 text-foreground">{c.name || c.finding}</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground">{c.score !== undefined ? `${((c.score > 1 ? c.score / 100 : c.score) * 100).toFixed(0)}%` : ''}</span>
                </div>
              ))}
            </div>
          )}
        </CollapsibleSection>

        <CollapsibleSection icon={Wrench} title={t.orchestrationProcedureCandidates} count={procCandidates.length}>
          {procCandidates.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No candidates</p>
          ) : (
            <div className="space-y-1.5">
              {procCandidates.map((c: any, i: number) => (
                <div key={i} className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-accent/50 text-xs">
                  <div>
                    <span className="font-mono font-medium text-foreground">{c.code}</span>
                    <span className="ml-2 text-foreground">{c.name || c.finding || c.procedure}</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground">{c.score !== undefined ? `${((c.score > 1 ? c.score / 100 : c.score) * 100).toFixed(0)}%` : ''}</span>
                </div>
              ))}
            </div>
          )}
        </CollapsibleSection>

        {/* DRG Impact */}
        <CollapsibleSection icon={FileText} title={t.orchestrationDrgImpact}>
          {Object.keys(drgImpact).length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No DRG analysis available</p>
          ) : (
            <div className="space-y-1 text-xs">
              {drgImpact.expected_drg && <p className="text-foreground"><span className="text-muted-foreground">Expected DRG:</span> {drgImpact.expected_drg}</p>}
              {drgImpact.mcc_analysis && <p className="text-foreground"><span className="text-muted-foreground">MCC:</span> {drgImpact.mcc_analysis}</p>}
              {drgImpact.cc_analysis && <p className="text-foreground"><span className="text-muted-foreground">CC:</span> {drgImpact.cc_analysis}</p>}
              {drgImpact.dip_impact && <p className="text-foreground"><span className="text-muted-foreground">DIP:</span> {drgImpact.dip_impact}</p>}
            </div>
          )}
        </CollapsibleSection>

        {/* Documentation Gaps */}
        <CollapsibleSection icon={AlertTriangle} title={t.orchestrationDocumentationGaps} count={docGaps.length}>
          {docGaps.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No gaps identified</p>
          ) : (
            <div className="space-y-1.5">
              {docGaps.map((g: any, i: number) => (
                <div key={i} className="text-xs py-1 px-2 bg-destructive/5 border border-destructive/10 rounded">
                  <span className="text-foreground">{typeof g === 'string' ? g : g.description || g.gap}</span>
                </div>
              ))}
            </div>
          )}
        </CollapsibleSection>

        {/* Human Checklist */}
        <CollapsibleSection icon={ClipboardList} title={t.orchestrationHumanChecklist} count={checklist.length}>
          {checklist.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">No checklist items</p>
          ) : (
            <div className="space-y-1.5">
              {checklist.map((item: any, i: number) => (
                <div key={i} className="flex items-start gap-2 text-xs py-1">
                  <input type="checkbox" className="mt-0.5 shrink-0" />
                  <span className="text-foreground">{typeof item === 'string' ? item : item.task || item.description}</span>
                </div>
              ))}
            </div>
          )}
        </CollapsibleSection>
      </div>

      {/* View full report */}
      {onViewReport && (
        <button
          onClick={onViewReport}
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-border text-sm text-foreground hover:bg-accent transition-colors"
        >
          <ExternalLink size={14} />
          {t.orchestrationViewReport}
        </button>
      )}
    </div>
  );
}
