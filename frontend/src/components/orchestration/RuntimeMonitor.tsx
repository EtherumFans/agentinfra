import { useState, useEffect, useRef } from 'react';
import { Shield, ChevronDown, ChevronRight, CheckCircle, XCircle, AlertTriangle, Eye, Lock, RefreshCw } from 'lucide-react';
import { runtimeStatusApi } from '../../services/api';

const STATES = ['INGESTED','CONTEXT_READY','FACTS_EXTRACTED','CANDIDATES_READY','RULES_VALIDATED','RISK_IDENTIFIED','REVIEW_REQUIRED','DECISION_CONFIRMED','DOC_FEEDBACK_READY','WRITEBACK_PENDING','WRITTEN_BACK','ARCHIVED'];
const STATE_LABELS: Record<string, string> = {
  INGESTED: '已接收', CONTEXT_READY: '就绪', FACTS_EXTRACTED: '事实提取',
  CANDIDATES_READY: '候选', RULES_VALIDATED: '规则验证', RISK_IDENTIFIED: '风险识别',
  REVIEW_REQUIRED: '待复核', DECISION_CONFIRMED: '已确认', ARCHIVED: '已归档',
  FAILED: '失败', ESCALATED: '已升级',
};

interface Props {
  caseId: string;
  refreshTrigger?: number;
  active?: boolean;
}

export default function RuntimeMonitor({ caseId, refreshTrigger, active }: Props) {
  const [open, setOpen] = useState(false);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSummary = () => {
    if (!caseId) return;
    runtimeStatusApi.summary(caseId).then(r => setSummary(r.data)).catch(() => {});
  };

  useEffect(() => {
    if (!caseId || !open) return;
    setLoading(true);
    fetchSummary();
    setLoading(false);

    if (active) {
      pollRef.current = setInterval(fetchSummary, 3000);
      return () => { if (pollRef.current) clearInterval(pollRef.current); };
    } else {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    }
  }, [caseId, open, active, refreshTrigger]);

  if (!caseId) return null;

  const s = summary || {};
  const state = s.session?.current_state || 'INGESTED';
  const events = s.total_audit_events || 0;
  const guardOutcomes = s.guard_outcomes || {};
  const decisions = s.decision_summary || {};
  const timeline = s.state_timeline || [];
  const warnings = s.warnings || [];
  const source = s.source || 'none';
  const stateIndex = STATES.indexOf(state);
  const hasData = source !== 'none';

  return (
    <div className="border border-border rounded-lg overflow-hidden bg-card">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-accent/50 transition-colors">
        {open ? <ChevronDown size={14} className="text-muted-foreground" /> : <ChevronRight size={14} className="text-muted-foreground" />}
        <Shield size={14} className={hasData ? 'text-primary' : 'text-muted-foreground'} />
        <span className="text-sm font-medium text-foreground">安全框架</span>
        {hasData ? (
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full text-white ${state === 'ARCHIVED' ? 'bg-green-600' : state === 'FAILED' ? 'bg-red-500' : 'bg-primary'}`}>
            {STATE_LABELS[state] || state}
          </span>
        ) : (
          <span className="text-[9px] text-muted-foreground/50 bg-muted px-1.5 py-0.5 rounded-full">等待执行</span>
        )}
        <span className="text-[10px] text-muted-foreground ml-auto">{events} 事件</span>
        {active && <RefreshCw size={10} className="text-muted-foreground animate-spin ml-1" />}
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3 max-h-96 overflow-y-auto">
          {!hasData ? (
            <div className="text-center py-6">
              <Lock size={28} className="mx-auto mb-2 text-muted-foreground/20" />
              <p className="text-xs text-muted-foreground">暂无运行时数据</p>
              <p className="text-[10px] text-muted-foreground/40 mt-0.5">执行 Pipeline 后将在此显示 5 层安全框架状态</p>
            </div>
          ) : (
            <>
              {/* 5-layer indicators */}
              <div className="grid grid-cols-5 gap-1.5">
                {[
                  { label: '状态机', ok: stateIndex >= 0, icon: Lock, detail: `${stateIndex + 1}/12` },
                  { label: '门控', ok: Object.keys(guardOutcomes).length > 0, icon: Shield, detail: `${guardOutcomes.ALLOW || 0}✓` },
                  { label: 'DUC', ok: (decisions.total_decisions || 0) > 0, icon: AlertTriangle, detail: `${decisions.approved || 0}/${decisions.total_decisions || 0}` },
                  { label: '审计链', ok: events > 0, icon: Eye, detail: `${events}` },
                  { label: '人工', ok: (decisions.total_decisions || 0) > 0, icon: CheckCircle, detail: (decisions.total_decisions || 0) > 0 ? '已介入' : '—' },
                ].map((layer, i) => (
                  <div key={i} className={`text-center rounded-lg p-2 ${layer.ok ? 'bg-primary/5 border border-primary/15' : 'bg-muted/30'}`}>
                    <layer.icon size={12} className={`mx-auto mb-0.5 ${layer.ok ? 'text-primary' : 'text-muted-foreground/30'}`} />
                    <p className="text-[9px] font-medium text-foreground">{layer.label}</p>
                    <p className="text-[8px] text-muted-foreground">{layer.detail}</p>
                  </div>
                ))}
              </div>

              {/* State machine mini visualization */}
              <div>
                <p className="text-[10px] font-medium text-foreground mb-1">状态流转</p>
                <div className="flex items-center gap-0.5 flex-wrap">
                  {STATES.slice(0, 12).map((s, i) => (
                    <div key={s} className={`w-2 h-2 rounded-full ${i <= stateIndex ? 'bg-primary' : i === stateIndex + 1 ? 'bg-primary/30 animate-pulse' : 'bg-muted'}`} title={`${STATE_LABELS[s] || s}${i <= stateIndex ? ' ✓' : ''}`} />
                  ))}
                </div>
              </div>

              {/* Guard outcomes */}
              {Object.keys(guardOutcomes).length > 0 && (
                <div>
                  <p className="text-[10px] font-medium text-foreground mb-1">门控结果</p>
                  <div className="flex gap-1.5">
                    {['ALLOW','REVIEW','DENY'].map(g => (
                      <span key={g} className={`text-[9px] px-1.5 py-0.5 rounded-full ${g==='ALLOW'?'bg-green-100 text-green-700':g==='REVIEW'?'bg-yellow-100 text-yellow-700':'bg-red-100 text-red-700'}`}>{g}: {guardOutcomes[g]||0}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* DUC decisions */}
              {decisions.total_decisions > 0 && (
                <div>
                  <p className="text-[10px] font-medium text-foreground mb-1">DUC 非确认即拒绝</p>
                  <div className="flex gap-2 text-[10px]">
                    <span className="text-secondary">{decisions.approved||0} 批准</span>
                    <span className="text-destructive">{decisions.rejected||0} 驳回</span>
                    <span className="text-muted-foreground">{decisions.total_decisions||0} 总数</span>
                  </div>
                </div>
              )}

              {/* Warnings */}
              {warnings.length > 0 && (
                <div className="bg-destructive/5 border border-destructive/10 rounded-lg p-2">
                  <p className="text-[10px] font-medium text-destructive mb-1">⚠ 警告 ({warnings.length})</p>
                  {warnings.slice(0, 4).map((w: any, i: number) => (
                    <div key={i} className="text-[9px] text-destructive/80 flex items-center gap-1"><AlertTriangle size={9} />{w.type} - {w.actor}</div>
                  ))}
                </div>
              )}

              <div className="flex items-center justify-between text-[8px] text-muted-foreground/40 pt-1 border-t border-border/10">
                <span>来源: {source}</span>
                <span>审计: {events} 事件</span>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
