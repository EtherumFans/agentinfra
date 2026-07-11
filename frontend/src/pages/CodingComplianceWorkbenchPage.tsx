/**
 * CodingComplianceWorkbenchPage — Phase 5 Track C Gate 5
 *
 * 7-stage coding compliance mainline UI. Drives POST /api/v1/coding-compliance/run
 * which threads CaseState through discharge → medical-coding → principal-dx →
 * evidence → compliance → note-completeness → drg. Shows per-stage results +
 * Human Review Gate decision (AUTO_PASS / REVIEW_RECOMMENDED / REVIEW_REQUIRED /
 * BLOCKED_*).
 *
 * Pattern: Corti-style single coding workbench (not 7 separate agent pages).
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';

const SAMPLE = `患者男性,78岁,因跌倒后腰背疼痛12小时入院。
既往糖尿病史10年,高血压20年。
查体:T12棘突压痛(+),叩痛(+)。
MRI:T12椎体压缩性骨折。
入院诊断:T12椎体压缩性骨折,2型糖尿病,高血压病3级。
住院期间行后路椎体成形术+骨水泥注入术,手术顺利。
术后恢复良好,出院。`;

type StageResult = {
  stage_id: string;
  stage_name: string;
  stage_index: number;
  output: any;
  error: string;
  latency_ms: number;
  normalized: {
    codes_emitted?: string[];
    procedures_emitted?: string[];
    issues?: any[];
    confidence?: number | null;
    ok?: boolean;
  } | null;
};

type CaseResponse = {
  case_id: string;
  agent_id: string;
  input_text_preview: string;
  input_text_length: number;
  stages: StageResult[];
  conflicts: any[];
  completion: {
    status: string;
    reasons: string[];
    must_replan: boolean;
    review_required: boolean;
  };
  review_gate: {
    status: string;
    blocker: string;
    reasons: string[];
  };
  total_latency_ms: number;
};

const GATE_COLORS: Record<string, string> = {
  AUTO_PASS: 'bg-emerald-100 text-emerald-700 border-emerald-300',
  REVIEW_RECOMMENDED: 'bg-amber-100 text-amber-700 border-amber-300',
  REVIEW_REQUIRED: 'bg-orange-100 text-orange-700 border-orange-300',
  BLOCKED: 'bg-rose-100 text-rose-700 border-rose-300',
};

const GATE_LABELS: Record<string, string> = {
  AUTO_PASS: '自动通过',
  REVIEW_RECOMMENDED: '建议人工复核',
  REVIEW_REQUIRED: '必须人工复核',
  BLOCKED: '已阻断',
};

const BLOCKER_LABELS: Record<string, string> = {
  BLOCKED_MISSING_DISCHARGE: '出院小结缺失',
  BLOCKED_NO_CODES_EXTRACTED: '未抽取到编码',
  BLOCKED_PRIMARY_DX_CONFLICT: '主诊断冲突',
  BLOCKED_CRITICAL_RULE_VIOLATION: '严重规则违反',
  BLOCKED_NOTE_SEVERELY_INCOMPLETE: '病历严重不完整',
};

export default function CodingComplianceWorkbenchPage() {
  const navigate = useNavigate();
  const [inputText, setInputText] = useState(SAMPLE);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CaseResponse | null>(null);
  const [error, setError] = useState('');

  async function handleRun() {
    setRunning(true);
    setError('');
    setResult(null);
    try {
      const response = await api.post<CaseResponse>(
        '/v1/coding-compliance/run',
        { input_text: inputText },
        { timeout: 300000 },
      );
      setResult(response.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || String(e));
    } finally {
      setRunning(false);
    }
  }

  const gateStatus = result?.review_gate?.status || '';
  const gateClass = GATE_COLORS[gateStatus] || 'bg-slate-100 text-slate-700 border-slate-300';
  const gateLabel = GATE_LABELS[gateStatus] || gateStatus;

  return (
    <div className="min-h-dvh bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <button
              onClick={() => navigate('/app/agents')}
              className="text-xs text-slate-500 hover:text-slate-700 mb-1"
            >
              ← 返回智能体列表
            </button>
            <h1 className="text-xl font-semibold text-slate-900">
              编码合规工作台
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              7 阶段主流程: 出院小结 → ICD 编码 → 主诊断复核 → 证据强度 → 合规审查 → 病历完整度 → DRG/DIP 风险
            </p>
          </div>
          {result && (
            <div className={`px-3 py-2 rounded-md border text-sm font-medium ${gateClass}`}>
              {gateLabel}
              {result.review_gate.blocker && (
                <span className="ml-2 text-xs opacity-75">
                  ({BLOCKER_LABELS[result.review_gate.blocker] || result.review_gate.blocker})
                </span>
              )}
            </div>
          )}
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6 grid grid-cols-12 gap-6">
        {/* Input pane */}
        <section className="col-span-5 bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">病历输入</h2>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={running}
            className="w-full h-96 px-3 py-2 text-sm border border-slate-300 rounded-md font-mono resize-none focus:outline-none focus:ring-2 focus:ring-slate-400"
            placeholder="粘贴出院小结文本..."
          />
          <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
            <span>{inputText.length} 字符</span>
            <span>上限 32000</span>
          </div>
          <button
            onClick={handleRun}
            disabled={running || !inputText.trim()}
            className="mt-3 w-full px-4 py-2 bg-slate-900 text-white rounded-md text-sm font-medium hover:bg-slate-700 disabled:bg-slate-300 disabled:cursor-not-allowed"
          >
            {running ? '运行中...' : '▶ 运行 7 阶段主流程'}
          </button>
          {error && (
            <div className="mt-3 px-3 py-2 bg-rose-50 border border-rose-200 rounded text-xs text-rose-700">
              {error}
            </div>
          )}
          {result && (
            <div className="mt-3 px-3 py-2 bg-slate-50 border border-slate-200 rounded text-xs text-slate-600">
              <div>case_id: <code className="text-[10px]">{result.case_id}</code></div>
              <div>总耗时: {result.total_latency_ms}ms</div>
              <div>阶段数: {result.stages.length}</div>
            </div>
          )}
        </section>

        {/* Output pane — 7 stage tabs */}
        <section className="col-span-7 bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">阶段输出</h2>
          {!result && (
            <div className="h-96 flex items-center justify-center text-sm text-slate-400">
              {running ? '运行中,预计 20-40 秒...' : '点击"运行"开始'}
            </div>
          )}
          {result && (
            <div className="space-y-3 max-h-[36rem] overflow-y-auto">
              {result.stages.map((s) => (
                <StageCard key={s.stage_id} stage={s} />
              ))}
              {result.conflicts.length > 0 && (
                <div className="px-3 py-2 bg-amber-50 border border-amber-200 rounded text-xs">
                  <div className="font-medium text-amber-800 mb-1">跨阶段冲突</div>
                  {result.conflicts.map((c, i) => (
                    <div key={i} className="text-amber-700">
                      • {c.field_path}: {c.strategy === 'defer_to_human' ? '人工复核' : '自动解决'}
                    </div>
                  ))}
                </div>
              )}
              {result.completion.reasons.length > 0 && (
                <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded text-xs">
                  <div className="font-medium text-slate-700 mb-1">完成原因 ({result.completion.status})</div>
                  <ul className="list-disc list-inside text-slate-600 space-y-0.5">
                    {result.completion.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function StageCard({ stage }: { stage: StageResult }) {
  const hasError = !!stage.error;
  const codes = stage.normalized?.codes_emitted || [];
  const procs = stage.normalized?.procedures_emitted || [];
  const issues = stage.normalized?.issues || [];

  return (
    <div className={`border rounded-md ${hasError ? 'border-rose-300 bg-rose-50' : 'border-slate-200 bg-white'}`}>
      <div className="px-3 py-2 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-slate-400">#{stage.stage_index}</span>
          <span className="text-sm font-medium text-slate-800">{stage.stage_name}</span>
          <span className="text-[10px] font-mono text-slate-400">{stage.stage_id}</span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {codes.length > 0 && (
            <span className="text-blue-600">{codes.length} 编码</span>
          )}
          {procs.length > 0 && (
            <span className="text-purple-600">{procs.length} 手术</span>
          )}
          {issues.length > 0 && (
            <span className="text-amber-600">{issues.length} 问题</span>
          )}
          <span className="text-slate-400">{stage.latency_ms}ms</span>
          {hasError ? (
            <span className="text-rose-600">✗ 失败</span>
          ) : (
            <span className="text-emerald-600">✓ 成功</span>
          )}
        </div>
      </div>
      {hasError ? (
        <div className="px-3 py-2 text-xs text-rose-700 font-mono">{stage.error}</div>
      ) : (
        <div className="px-3 py-2">
          {codes.length > 0 && (
            <div className="mb-1.5">
              <span className="text-[10px] uppercase text-slate-500">编码</span>
              <div className="flex flex-wrap gap-1 mt-0.5">
                {codes.slice(0, 12).map((c, idx) => (
                  <code key={`${c}-${idx}`} className="text-[10px] px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded">{c}</code>
                ))}
                {codes.length > 12 && (
                  <span className="text-[10px] text-slate-500">+{codes.length - 12}...</span>
                )}
              </div>
            </div>
          )}
          {issues.length > 0 && (
            <div>
              <span className="text-[10px] uppercase text-slate-500">问题</span>
              <ul className="text-xs text-slate-700 mt-0.5 space-y-0.5">
                {issues.slice(0, 5).map((i, idx) => (
                  <li key={idx}>
                    {i.rule_id && <code className="text-[10px] text-rose-600">{i.rule_id}</code>} {i.message || i.text || JSON.stringify(i).slice(0, 100)}
                  </li>
                ))}
                {issues.length > 5 && (
                  <li className="text-[10px] text-slate-500">+{issues.length - 5} 更多...</li>
                )}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
