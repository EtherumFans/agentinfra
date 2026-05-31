import { useState } from 'react';
import { CheckCircle, XCircle, Send } from 'lucide-react';
import { useT } from '../../i18n';
import { runtimeApi } from '../../services/api';

interface Props {
  caseId: string;
  review: any;
  onDecisionComplete?: () => void;
}

export default function HumanReviewGate({ caseId, review, onDecisionComplete }: Props) {
  const t = useT();
  const [rationale, setRationale] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [decision, setDecision] = useState<'approved' | 'rejected' | null>(
    review?.human_review_status === 'approved' ? 'approved' :
    review?.human_review_status === 'rejected' ? 'rejected' : null
  );

  if (!caseId) return null;

  const handleDecision = async (d: 'approve' | 'reject') => {
    setSubmitting(true);
    try {
      await runtimeApi.review(caseId, 'confirm_decision', rationale, d);
      setDecision(d === 'approve' ? 'approved' : 'rejected');
      onDecisionComplete?.();
    } catch { /* silently fail */ }
    setSubmitting(false);
  };

  if (decision) {
    return (
      <div className={`rounded-xl p-4 flex items-center gap-3 ${decision === 'approved' ? 'bg-secondary/10 border border-secondary/20' : 'bg-destructive/10 border border-destructive/20'}`}>
        {decision === 'approved' ? <CheckCircle size={18} className="text-secondary" /> : <XCircle size={18} className="text-destructive" />}
        <div>
          <p className="text-sm font-medium text-foreground">{decision === 'approved' ? t.orchestrationApprove : t.orchestrationReject}</p>
          <p className="text-xs text-muted-foreground">{t.orchestrationHumanReview} {decision === 'approved' ? 'approved' : 'rejected'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-1 h-4 rounded-full bg-primary/40" />
        <h4 className="text-sm font-semibold text-foreground">{t.orchestrationHumanReview}</h4>
      </div>
      <textarea
        value={rationale}
        onChange={e => setRationale(e.target.value)}
        placeholder={t.orchestrationRationalePlaceholder}
        className="w-full h-20 p-3 text-sm border border-border rounded-lg bg-background text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-2 focus:ring-ring/20 mb-3"
        disabled={submitting}
      />
      <div className="flex items-center gap-2">
        <button
          onClick={() => handleDecision('approve')}
          disabled={submitting || !rationale.trim()}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-secondary text-secondary-foreground text-sm font-medium hover:bg-secondary/90 transition-colors disabled:opacity-50"
        >
          <CheckCircle size={14} />
          {t.orchestrationApprove}
        </button>
        <button
          onClick={() => handleDecision('reject')}
          disabled={submitting || !rationale.trim()}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
        >
          <XCircle size={14} />
          {t.orchestrationReject}
        </button>
        {submitting && <span className="text-xs text-muted-foreground"><Send size={12} className="inline animate-pulse" /> Submitting...</span>}
      </div>
    </div>
  );
}
