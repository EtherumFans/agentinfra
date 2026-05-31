import { useState, useCallback, useEffect, useRef } from 'react';
import { RotateCcw, FlaskConical } from 'lucide-react';
import { useT } from '../i18n';
import { useReviewPipeline } from '../hooks/useReviewPipeline';
import { reviewsApi } from '../services/api';
import EncounterSelector from '../components/orchestration/EncounterSelector';
import PipelineProgress from '../components/orchestration/PipelineProgress';
import ReviewResults from '../components/orchestration/ReviewResults';
import HumanReviewGate from '../components/orchestration/HumanReviewGate';
import AuditTrailViewer from '../components/orchestration/AuditTrailViewer';
import RuntimeMonitor from '../components/orchestration/RuntimeMonitor';
import SettingsCodeTab from '../components/common/SettingsCodeTab';
import EventInspector from '../components/common/EventInspector';
import CodeSnippet from '../components/common/CodeSnippet';
import { BACKEND_BASE_URL } from '../config';

export default function OrchestrationPage() {
  const t = useT();
  const pipeline = useReviewPipeline();
  const [encounterId, setEncounterId] = useState<string | null>(null);
  const [review, setReview] = useState<any>(null);
  const [auditRefresh, setAuditRefresh] = useState(0);
  const [events, setEvents] = useState<any[]>([]);
  const [batchMode, setBatchMode] = useState(false);
  const [batchIds, setBatchIds] = useState<string[]>([]);

  const handleBatchSubmit = useCallback(async () => {
    if (batchIds.length === 0) return;
    setEvents([{ type: 'batch_start', data: { count: batchIds.length, ids: batchIds }, timestamp: new Date().toISOString(), credits: 0 }]);
    const { reviewsApi } = await import('../services/api');
    try {
      const r = await reviewsApi.batch(batchIds);
      setEvents(prev => [...prev.slice(-50), { type: 'batch_submitted', data: r.data, timestamp: new Date().toISOString(), credits: 0 }]);
      setReview({ batch_result: r.data });
    } catch (err: any) {
      setEvents(prev => [...prev.slice(-50), { type: 'batch_error', data: { error: err.message }, timestamp: new Date().toISOString() }]);
    }
  }, [batchIds]);

  const toggleBatchId = (id: string) => {
    setBatchIds(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
  };

  const handleEncounterSelect = useCallback(async (encId: string, encData?: any) => {
    if (batchMode) { toggleBatchId(encId); return; }
    setEncounterId(encId);
    setReview(null);
    setEvents([]);

    // Add start event
    setEvents(prev => [...prev.slice(-50), {
      type: 'pipeline_start',
      data: { encounterId: encId },
      timestamp: new Date().toISOString(),
      credits: 0,
    }]);

    pipeline.start(encId);
  }, [pipeline]);

  const handleReset = useCallback(() => {
    pipeline.reset();
    setEncounterId(null);
    setReview(null);
    setEvents([]);
  }, [pipeline]);

  // Watch for pipeline completion
  const prevStatusRef = useRef(pipeline.status);
  useEffect(() => {
    if (pipeline.status === 'completed' && pipeline.reviewId && prevStatusRef.current !== 'completed') {
      reviewsApi.get(pipeline.reviewId!).then(r => {
          setReview(r.data);
          setEvents(prev => [...prev.slice(-50), {
            type: 'pipeline_complete',
            data: { reviewId: pipeline.reviewId },
            timestamp: new Date().toISOString(),
            credits: 0,
          }]);
        }).catch(() => {});
    }
    if (pipeline.status === 'failed' && pipeline.error && prevStatusRef.current !== 'failed') {
      setEvents(prev => [...prev.slice(-50), {
        type: 'pipeline_error',
        data: { error: pipeline.error },
        timestamp: new Date().toISOString(),
      }]);
    }
    prevStatusRef.current = pipeline.status;
  }, [pipeline.status, pipeline.reviewId, pipeline.error]);

  const handleViewReport = async () => {
    if (!pipeline.reviewId) return;
    window.open(`${BACKEND_BASE_URL}/docs`, '_blank');
  };

  const handleDecisionComplete = () => {
    setAuditRefresh(n => n + 1);
  };

  return (
    <div className="flex flex-1 min-h-0">
      {/* Main area */}
      <div className="flex-[75_1_0px] flex flex-col min-h-0 overflow-y-auto p-4 gap-4 bg-muted/20">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-foreground">{t.orchestrationTitle}</h2>
            <p className="text-xs text-muted-foreground">{t.orchestrationDesc}</p>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
              <input type="checkbox" checked={batchMode} onChange={e => { setBatchMode(e.target.checked); setBatchIds([]); }} className="w-3 h-3" />
              批量模式
            </label>
            {batchMode && batchIds.length > 0 && (
              <button onClick={handleBatchSubmit} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground hover:bg-primary/90">
                批量提交 ({batchIds.length})
              </button>
            )}
            {pipeline.status !== 'idle' && (
              <button onClick={handleReset} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                <RotateCcw size={12} /> Reset
              </button>
            )}
          </div>
        </div>

        {/* Encounter Selector */}
        <EncounterSelector
          onSelect={handleEncounterSelect}
          disabled={pipeline.status === 'running' || pipeline.status === 'connecting'}
          batchMode={batchMode}
          selectedBatchIds={batchIds}
        />

        {/* Runtime Security Monitor */}
        {encounterId && pipeline.status !== 'idle' && (
          <RuntimeMonitor caseId={pipeline.reviewId || encounterId} refreshTrigger={auditRefresh} active={pipeline.status === 'running'} />
        )}

        {/* Pipeline Progress */}
        {pipeline.status !== 'idle' && (
          <PipelineProgress
            status={pipeline.status}
            progress={pipeline.progress}
            currentStep={pipeline.currentStep}
            steps={pipeline.steps}
            connectionMode={pipeline.connectionMode}
          />
        )}

        {/* Review Results */}
        {review && (
          <ReviewResults review={review} onViewReport={handleViewReport} />
        )}

        {/* Human Review Gate */}
        {review && pipeline.reviewId && (
          <HumanReviewGate
            caseId={pipeline.reviewId}
            review={review}
            onDecisionComplete={handleDecisionComplete}
          />
        )}

        {/* Audit Trail */}
        {encounterId && pipeline.status === 'completed' && (
          <AuditTrailViewer caseId={pipeline.reviewId || encounterId} refreshTrigger={auditRefresh} />
        )}

        {/* Empty state */}
        {pipeline.status === 'idle' && (
          <div className="flex-1 flex flex-col items-center justify-center text-center py-12">
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-4">
              <FlaskConical size={28} className="text-primary" />
            </div>
            <h3 className="text-base font-medium text-foreground mb-2">{t.orchestrationTitle}</h3>
            <p className="text-sm text-muted-foreground max-w-md">{t.orchestrationDesc}</p>
            <div className="flex items-center gap-4 mt-6 text-[10px] text-muted-foreground">
              {pipeline.steps.map((step, i) => (
                <div key={i} className="flex items-center gap-1">
                  <span className="w-4 h-4 rounded-full bg-muted flex items-center justify-center text-[8px]">{i + 1}</span>
                  <span className="hidden sm:inline">{step.split('').slice(0, 4).join('')}...</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Right panel */}
      <div className="flex-[25_1_0px] min-w-[280px] max-w-[380px] border-l border-border flex flex-col min-h-0">
        <div className="flex-1 overflow-y-auto">
          <SettingsCodeTab
            labels={{ settings: t.orchestrationPipelineSteps || 'Settings', code: t.orchestrationReportHtml || 'Code' }}
            settings={
              <div className="flex flex-col gap-4 p-4">
                <div>
                  <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">WebSocket</label>
                  <p className="text-xs font-mono text-foreground mt-1 break-all">
                    {BACKEND_BASE_URL.replace(/^http/, 'ws')}/api/reviews/ws/reviews/{'{task_id}'}
                  </p>
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Pipeline</label>
                  <div className="mt-1 space-y-1">
                    {pipeline.steps.map((step, i) => (
                      <div key={i} className="text-xs text-muted-foreground flex items-center gap-1.5">
                        <span className="w-4 h-4 rounded-full bg-muted flex items-center justify-center text-[8px]">{i + 1}</span>
                        {step}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            }
            code={
              <CodeSnippet
                javascript={`// Run the coding audit pipeline
import { iCoDerClient } from '@icoder/sdk';

const client = new iCoDerClient({
  baseURL: '${BACKEND_BASE_URL}',
  auth: { accessToken: '<token>' },
});

// Start async pipeline
const { task_id } = await client.reviews.createAsync(encounterId);

// Connect to WebSocket for progress
const ws = new WebSocket('${BACKEND_BASE_URL.replace(/^http/, 'ws')}/api/reviews/ws/reviews/' + task_id);
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(msg.type, msg.progress, msg.current_step);
};

// Get full review when complete
const review = await client.reviews.get(reviewId);`}
                python={`from icoder_sdk import iCoDerClient

client = iCoDerClient(base_url="${BACKEND_BASE_URL}", api_key="YOUR_KEY")

# Start async pipeline
task = client.reviews.create_async(encounter_id=encounter_id)

# Poll for progress
while task.status != "completed":
    task = client.reviews.task_status(task.task_id)
    print(f"Progress: {task.progress}% - {task.current_step}")

# Get full review
review = client.reviews.get(task.review_id)`}
              />
            }
          />
        </div>

        {/* Event Inspector */}
        <div className="border-t border-border shrink-0">
          <EventInspector events={events} creditsConsumed={0} />
        </div>
      </div>
    </div>
  );
}
