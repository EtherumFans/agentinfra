import { Check, Loader2, XCircle } from 'lucide-react';
import { useT } from '../../i18n';

type PipelineStatus = 'idle' | 'connecting' | 'running' | 'completed' | 'failed';

interface Props {
  status: PipelineStatus;
  progress: number;
  currentStep: string;
  steps: readonly string[];
  connectionMode: 'websocket' | 'polling' | null;
}

const STATUS_CONFIG: Record<PipelineStatus, { color: string; bg: string }> = {
  idle: { color: 'text-muted-foreground', bg: 'bg-muted' },
  connecting: { color: 'text-primary', bg: 'bg-primary/10' },
  running: { color: 'text-primary', bg: 'bg-primary/10' },
  completed: { color: 'text-secondary', bg: 'bg-secondary/10' },
  failed: { color: 'text-destructive', bg: 'bg-destructive/10' },
};

export default function PipelineProgress({ status, progress, currentStep, steps, connectionMode }: Props) {
  const t = useT();
  const conf = STATUS_CONFIG[status];

  // Determine which step is active
  const activeStepIndex = status === 'idle' ? -1
    : status === 'completed' ? steps.length
    : steps.indexOf(currentStep);

  return (
    <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 rounded-full bg-primary/40" />
          <h4 className="text-sm font-semibold text-foreground">{t.orchestrationPipelineSteps}</h4>
        </div>
        <div className="flex items-center gap-2">
          {connectionMode === 'polling' && (
            <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">polling</span>
          )}
          <span className={`text-xs font-medium ${conf.color}`}>
            {status === 'idle' ? t.orchestrationStatusIdle
              : status === 'connecting' ? t.orchestrationStatusRunning
              : status === 'running' ? `${t.orchestrationProgress}: ${progress}%`
              : status === 'completed' ? t.orchestrationStatusCompleted
              : t.orchestrationStatusFailed}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 bg-muted rounded-full mb-4 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${status === 'failed' ? 'bg-destructive' : 'bg-primary'}`}
          style={{ width: `${status === 'failed' ? 100 : progress}%` }}
        />
      </div>

      {/* Current step label */}
      {status === 'running' && currentStep && (
        <p className="text-xs text-muted-foreground mb-3 flex items-center gap-1.5">
          <Loader2 className="animate-spin h-3 w-3" />
          {currentStep}
        </p>
      )}
      {status === 'completed' && (
        <p className="text-xs text-secondary mb-3 flex items-center gap-1.5">
          <Check size={12} />
          {t.orchestrationStatusCompleted}
        </p>
      )}
      {status === 'failed' && (
        <p className="text-xs text-destructive mb-3 flex items-center gap-1.5">
          <XCircle size={12} />
          {t.orchestrationStatusFailed}
        </p>
      )}

      {/* Step indicators */}
      <div className="flex items-center gap-1">
        {steps.map((step, i) => {
          const done = status === 'completed' || (status === 'running' && i < activeStepIndex);
          const active = status === 'running' && i === activeStepIndex;
          const failed = status === 'failed' && i === activeStepIndex;

          return (
            <div key={i} className="flex items-center flex-1 last:flex-[0_0_auto]">
              <div className={`flex items-center justify-center w-6 h-6 rounded-full text-[10px] font-medium transition-colors shrink-0 ${
                done ? 'bg-secondary text-secondary-foreground'
                  : failed ? 'bg-destructive text-destructive-foreground'
                  : active ? 'bg-primary text-primary-foreground ring-2 ring-primary/20'
                  : 'bg-muted text-muted-foreground'
              }`}>
                {done ? <Check size={10} /> : failed ? <XCircle size={10} /> : i + 1}
              </div>
              {i < steps.length - 1 && (
                <div className={`flex-1 h-px mx-0.5 transition-colors ${
                  i < activeStepIndex || done ? 'bg-secondary/50' : 'bg-border'
                }`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Step labels */}
      <div className="flex items-start gap-1 mt-1.5">
        {steps.map((step, i) => (
          <div key={i} className="flex-1 text-center last:flex-[0_0_auto] last:text-right">
            <span className="text-[9px] text-muted-foreground leading-tight block">{step}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
