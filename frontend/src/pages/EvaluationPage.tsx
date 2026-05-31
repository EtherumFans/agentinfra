// iCoDer - Evaluation Page (Enhanced: case selection, A/B compare, history)
import { useState, useEffect } from 'react';
import { evaluationApi, goldCasesApi } from '../services/api';
import type { EvaluationSummary } from '../types';
import { Play, BarChart3, Target, Crosshair, Eye, AlertTriangle, CheckCircle, XCircle, Brain, X, GitCompare, History, RotateCcw, Plus, Trash2 } from 'lucide-react';
import { useT } from '../i18n';

interface EvalRecord {
  id: string;
  timestamp: string;
  result: EvaluationSummary;
  label: string;
}
const HISTORY_KEY = 'icoder-eval-history';

export default function EvaluationPage() {
  const t = useT();
  const [tab, setTab] = useState<'run' | 'compare' | 'history'>('run');
  const [result, setResult] = useState<EvaluationSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedCases, setSelectedCases] = useState<string[]>([]);
  const [goldCases, setGoldCases] = useState<any[]>([]);
  const [evalHistory, setEvalHistory] = useState<EvalRecord[]>(() => {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch { return []; }
  });
  const [compareIdA, setCompareIdA] = useState('');
  const [compareIdB, setCompareIdB] = useState('');

  useEffect(() => {
    goldCasesApi.list(1, 50).then(r => setGoldCases(r.data.items || [])).catch(() => {});
  }, []);

  useEffect(() => { localStorage.setItem(HISTORY_KEY, JSON.stringify(evalHistory)); }, [evalHistory]);

  const runEvaluation = async () => {
    setLoading(true); setError('');
    try {
      const { data } = await evaluationApi.run(selectedCases.length > 0 ? selectedCases : undefined);
      setResult(data);
      setEvalHistory(prev => [{
        id: Date.now().toString(36), timestamp: new Date().toISOString(),
        result: data, label: selectedCases.length ? `${selectedCases.length} cases` : 'All',
      }, ...prev].slice(0, 20));
    } catch (err: any) { setError(err.response?.data?.detail || '评估失败'); }
    finally { setLoading(false); }
  };

  const metrics = result ? [
    { label: t.primaryDiagAccuracy, value: `${(result.primary_diag_accuracy * 100).toFixed(1)}%`, target: '≥75%', icon: Target, color: result.primary_diag_accuracy >= 0.75 ? 'text-secondary' : 'text-destructive' },
    { label: t.mainProcAccuracy, value: `${(result.main_proc_accuracy * 100).toFixed(1)}%`, target: '≥80%', icon: Crosshair, color: result.main_proc_accuracy >= 0.80 ? 'text-secondary' : 'text-destructive' },
    { label: t.evidenceCompleteness, value: `${(result.evidence_completeness_avg * 100).toFixed(1)}%`, target: '≥90%', icon: Eye, color: result.evidence_completeness_avg >= 0.90 ? 'text-secondary' : 'text-destructive' },
    { label: t.hallucinationRate, value: `${(result.hallucination_rate * 100).toFixed(1)}%`, target: '≤5%', icon: AlertTriangle, color: result.hallucination_rate <= 0.05 ? 'text-secondary' : 'text-destructive' },
    { label: t.missingCodeRecall, value: `${(result.missing_code_recall * 100).toFixed(1)}%`, target: '≥70%', icon: Brain, color: result.missing_code_recall >= 0.70 ? 'text-secondary' : 'text-destructive' },
    { label: t.overallScore, value: `${(result.avg_overall_score * 100).toFixed(1)}%`, target: '≥70%', icon: BarChart3, color: result.avg_overall_score >= 0.70 ? 'text-secondary' : 'text-destructive' },
  ] : [];

  const getCompareResult = (id: string) => evalHistory.find(r => r.id === id)?.result;
  const resultA = compareIdA ? getCompareResult(compareIdA) : null;
  const resultB = compareIdB ? getCompareResult(compareIdB) : null;

  return (
    <div className="p-6 bg-muted/20 h-full overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold text-foreground">{t.evaluationTitle}</h2>
          <p className="text-sm text-muted-foreground">{t.evaluationDesc}</p>
        </div>
        <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
          {(['run', 'compare', 'history'] as const).map(tb => (
            <button key={tb} onClick={() => setTab(tb)} className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${tab === tb ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>
              {tb === 'run' ? <><Play size={12} className="inline mr-1" />{t.runEvaluation}</>
               : tb === 'compare' ? <><GitCompare size={12} className="inline mr-1" />A/B 对比</>
               : <><History size={12} className="inline mr-1" />历史</>}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="mb-4 px-4 py-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive flex items-center justify-between">{error}<button onClick={() => setError('')} className="text-destructive/60 hover:text-destructive shrink-0 ml-2"><X size={14} /></button></div>}

      {tab === 'run' && (
        <>
          {/* Gold case selector */}
          {goldCases.length > 0 && (
            <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-3 mb-4">
              <p className="text-xs font-semibold text-foreground mb-2">选择评估案例</p>
              <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                <button onClick={() => setSelectedCases(prev => prev.length === goldCases.length ? [] : goldCases.map(c => c.id))} className="text-[10px] px-2 py-0.5 rounded bg-muted hover:bg-accent transition-colors">
                  {selectedCases.length === goldCases.length ? '取消全选' : '全选'} ({goldCases.length})
                </button>
                {goldCases.map(gc => (
                  <button key={gc.id} onClick={() => setSelectedCases(prev => prev.includes(gc.id) ? prev.filter(id => id !== gc.id) : [...prev, gc.id])}
                    className={`text-[10px] px-2 py-0.5 rounded transition-colors ${selectedCases.includes(gc.id) ? 'bg-primary/10 text-primary ring-1 ring-primary/20' : 'bg-muted hover:bg-accent'}`}>
                    {gc.case_id || gc.id}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-muted-foreground mt-1.5">{selectedCases.length > 0 ? `已选 ${selectedCases.length} 个案例` : '未选择（将评估全部案例）'}</p>
            </div>
          )}

          <button onClick={runEvaluation} disabled={loading} className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-3 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-all mb-4">
            <Play size={16} /> {loading ? t.running : t.runEvaluation}
          </button>

          {result && <EvalResultView result={result} metrics={metrics} t={t} />}
          {!result && !loading && <EmptyState icon={BarChart3} text={t.noEvaluationData} hint={t.runEvaluationHint} />}
        </>
      )}

      {tab === 'compare' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-foreground">评估 A</label>
              <select value={compareIdA} onChange={e => setCompareIdA(e.target.value)} className="w-full mt-1 text-xs border border-border rounded-lg px-2 py-1.5 bg-card">
                <option value="">选择...</option>
                {evalHistory.map(r => <option key={r.id} value={r.id}>{new Date(r.timestamp).toLocaleString()} — {r.label}</option>)}
              </select>
              {resultA && <div className="mt-2"><EvalResultView result={resultA} metrics={getMetricsForResult(resultA, t)} t={t} compact /></div>}
            </div>
            <div>
              <label className="text-xs font-medium text-foreground">评估 B</label>
              <select value={compareIdB} onChange={e => setCompareIdB(e.target.value)} className="w-full mt-1 text-xs border border-border rounded-lg px-2 py-1.5 bg-card">
                <option value="">选择...</option>
                {evalHistory.map(r => <option key={r.id} value={r.id}>{new Date(r.timestamp).toLocaleString()} — {r.label}</option>)}
              </select>
              {resultB && <div className="mt-2"><EvalResultView result={resultB} metrics={getMetricsForResult(resultB, t)} t={t} compact /></div>}
            </div>
          </div>
          {resultA && resultB && (
            <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-4">
              <h4 className="text-sm font-semibold mb-2">对比分析</h4>
              <div className="grid grid-cols-6 gap-2 text-center text-xs">
                {['primary_diag_accuracy','main_proc_accuracy','evidence_completeness_avg','hallucination_rate','missing_code_recall','avg_overall_score'].map(key => {
                  const va = (resultA as any)[key] || 0;
                  const vb = (resultB as any)[key] || 0;
                  const diff = vb - va;
                  const better = diff > 0.01 ? 'B' : diff < -0.01 ? 'A' : '—';
                  const betterColor = better === 'A' ? 'text-blue-500' : better === 'B' ? 'text-secondary' : 'text-muted-foreground';
                  return (
                    <div key={key} className="bg-muted/50 rounded-lg p-2">
                      <p className="text-[10px] text-muted-foreground mb-0.5">{key.replace(/_/g,' ')}</p>
                      <p className="font-mono"><span>{(va*100).toFixed(0)}%</span> <span className="text-muted-foreground">→</span> <span>{(vb*100).toFixed(0)}%</span></p>
                      <p className={`font-medium text-[10px] ${betterColor}`}>{better !== '—' ? `${better} 更优 (${(Math.abs(diff)*100).toFixed(1)}%)` : '持平'}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'history' && (
        <div className="space-y-2">
          {evalHistory.length === 0 ? <EmptyState icon={History} text="无评估历史" hint="运行评估后历史记录将显示在此处" /> : (
            <>
              {/* Simple trend chart */}
              <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-4">
                <h4 className="text-xs font-semibold mb-2">综合评分趋势</h4>
                <div className="h-16 flex items-end gap-0.5">
                  {evalHistory.slice().reverse().map((r, i) => (
                    <div key={r.id} className="flex-1 bg-primary/30 hover:bg-primary/50 rounded-t transition-colors" style={{ height: `${r.result.avg_overall_score * 100}%` }} title={`${(r.result.avg_overall_score*100).toFixed(0)}% — ${new Date(r.timestamp).toLocaleDateString()}`} />
                  ))}
                </div>
                <div className="flex justify-between mt-1 text-[9px] text-muted-foreground">
                  <span>{evalHistory[evalHistory.length-1] ? new Date(evalHistory[evalHistory.length-1].timestamp).toLocaleDateString() : ''}</span>
                  <span>{evalHistory[0] ? new Date(evalHistory[0].timestamp).toLocaleDateString() : ''}</span>
                </div>
              </div>
              {evalHistory.map(r => (
                <div key={r.id} className="bg-card rounded-lg shadow-sm ring-1 ring-border/20 p-3 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-medium text-foreground">{new Date(r.timestamp).toLocaleString()}</p>
                    <p className="text-[10px] text-muted-foreground">{r.label} · 综合 {(r.result.avg_overall_score*100).toFixed(0)}% · 诊断准确率 {(r.result.primary_diag_accuracy*100).toFixed(0)}%</p>
                  </div>
                  <button onClick={() => setEvalHistory(prev => prev.filter(h => h.id !== r.id))} className="p-1 text-muted-foreground hover:text-destructive transition-colors"><Trash2 size={12} /></button>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function EmptyState({ icon: Icon, text, hint }: { icon: any; text: string; hint: string }) {
  return (
    <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-5 text-center py-12">
      <Icon size={48} className="mx-auto mb-3 text-muted-foreground/30" />
      <p className="text-muted-foreground">{text}</p>
      <p className="text-sm text-muted-foreground mt-1">{hint}</p>
    </div>
  );
}

function getMetricsForResult(result: EvaluationSummary, t: any) {
  return [
    { label: t.primaryDiagAccuracy, value: `${(result.primary_diag_accuracy * 100).toFixed(1)}%`, target: '≥75%', icon: Target, color: result.primary_diag_accuracy >= 0.75 ? 'text-secondary' : 'text-destructive' },
    { label: t.mainProcAccuracy, value: `${(result.main_proc_accuracy * 100).toFixed(1)}%`, target: '≥80%', icon: Crosshair, color: result.main_proc_accuracy >= 0.80 ? 'text-secondary' : 'text-destructive' },
    { label: t.evidenceCompleteness, value: `${(result.evidence_completeness_avg * 100).toFixed(1)}%`, target: '≥90%', icon: Eye, color: result.evidence_completeness_avg >= 0.90 ? 'text-secondary' : 'text-destructive' },
    { label: t.hallucinationRate, value: `${(result.hallucination_rate * 100).toFixed(1)}%`, target: '≤5%', icon: AlertTriangle, color: result.hallucination_rate <= 0.05 ? 'text-secondary' : 'text-destructive' },
    { label: t.missingCodeRecall, value: `${(result.missing_code_recall * 100).toFixed(1)}%`, target: '≥70%', icon: Brain, color: result.missing_code_recall >= 0.70 ? 'text-secondary' : 'text-destructive' },
    { label: t.overallScore, value: `${(result.avg_overall_score * 100).toFixed(1)}%`, target: '≥70%', icon: BarChart3, color: result.avg_overall_score >= 0.70 ? 'text-secondary' : 'text-destructive' },
  ];
}

function EvalResultView({ result, metrics, t, compact }: { result: EvaluationSummary; metrics: any[]; t: any; compact?: boolean }) {
  return (
    <>
      <div className={`grid ${compact ? 'grid-cols-3' : 'grid-cols-6'} gap-2 mb-4`}>
        {metrics.map((m: any) => (
          <div key={m.label} className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-3 text-center">
            <m.icon size={compact ? 16 : 24} className={`mx-auto mb-1 ${m.color}`} />
            <p className={`${compact ? 'text-base' : 'text-xl'} font-bold ${m.color}`}>{m.value}</p>
            <p className="text-[10px] text-muted-foreground">{m.label}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">{t.target}: {m.target}</p>
          </div>
        ))}
      </div>
      {!compact && (
        <div className="bg-card rounded-xl shadow-sm ring-1 ring-border/20 p-4">
          <h3 className="font-semibold mb-3">{t.perCaseResults} ({result.total_cases} 个案例)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left">{['案例','AI诊断','诊断匹配','手术匹配','幻觉编码','证据','评分'].map(h => <th key={h} className="py-2 px-2 text-xs">{h}</th>)}</tr></thead>
              <tbody>
                {result.per_case_results.map((r: any, i: number) => (
                  <tr key={i} className="border-b hover:bg-accent">
                    <td className="py-1.5 px-2 font-mono text-[10px]">{r.case_id}</td>
                    <td className="py-1.5 px-2 font-mono text-[10px]">{r.agent_primary_diag}</td>
                    <td className="py-1.5 px-2">{r.primary_diag_match ? <CheckCircle size={14} className="text-secondary" /> : <XCircle size={14} className="text-destructive" />}</td>
                    <td className="py-1.5 px-2">{r.main_proc_match ? <CheckCircle size={14} className="text-secondary" /> : <XCircle size={14} className="text-destructive" />}</td>
                    <td className="py-1.5 px-2 text-destructive text-[10px]">{r.hallucinated_codes?.join(', ') || t.none}</td>
                    <td className="py-1.5 px-2 text-[10px]">{(r.evidence_completeness * 100).toFixed(0)}%</td>
                    <td className="py-1.5 px-2 font-semibold text-[10px]">{(r.overall_score * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
