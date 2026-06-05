// iCoDer Medical Coding Agent — iCoDer Console with 3-view output, evidence, alternatives, multi-select systems, include/exclude filters, and live cost integration
import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../store';
import { useCostStore } from '../store';
import { useT, useLocaleStore } from '../i18n';
import { encountersApi, reviewsApi, codeTablesApi, agentsApi, expertsApi } from '../services/api';
import { runtimeApi } from '../services/runtimeApi';
import type { RuntimeRunResult, MedicalCodingStatus } from '../types/runtime';
import {
  X, Sparkles, Loader2, Copy, Pencil, FileText,
  ChevronDown, Stethoscope, FilePlus, Hospital,
  Wrench, ExternalLink, GripVertical, Plus,
  Check, BookOpen,
} from 'lucide-react';
import type { ClinicalEvidence, CodeCandidate } from '../types';
import AddExpertModal from '../components/AddExpertModal';
import SettingsCodeTab from '../components/common/SettingsCodeTab';
import EventInspector from '../components/common/EventInspector';
import CodeSnippet from '../components/common/CodeSnippet';


type OutputView = 'rendered' | 'json' | 'code';

export default function MedicalCodingPage() {
  const t = useT();
  const locale = useLocaleStore(s => s.locale);

  const DEFAULT_SAMPLES = [
    { key: 'hospital', title: t.hospitalMedicalRecord, text: `入院记录\n主诉：腰痛4个月余。\n现病史：患者于4个月前无明显诱因出现腰痛，呈持续性钝痛，久坐久站后加重，卧床休息后稍缓解。近一个月疼痛明显加重，遂来我院就诊。\n既往史：高血压病史5年，口服硝苯地平控制可。无糖尿病史。\n体格检查：脊柱生理曲度改变，T7-L2棘突压痛和叩击痛明显。双下肢无水肿。\n影像学检查：胸腰椎MRI提示：胸7、9、12及腰2椎体考虑为新鲜压缩骨折。胸8棘突区骨髓水肿。\n出院诊断：\n1. 腰椎压缩性骨折\n2. 胸椎压缩性骨折\n3. 重度骨质疏松症\n4. 高血压病\n手术记录：\n手术名称：T7、T9、T12、L2经皮穿刺脊柱后凸成形术\n手术过程：球囊扩张恢复椎体高度，注入骨水泥。\n出院小结：术后腰痛明显缓解。` },
    { key: 'gp', title: t.gpTranscript, text: '患者因持续咳嗽3周就诊。无发热。活动后轻度气短。吸烟史20包年。已行胸部X线检查。评估：排除COPD与慢性支气管炎。' },
    { key: 'ortho', title: t.orthopedicReferral, text: '患者左膝关节疼痛伴肿胀，MRI示内侧半月板撕裂。怀疑退行性关节病。建议骨科评估及可能的关节镜手术。' },
  ];

  const [samples, setSamples] = useState(() => {
    try {
      const saved = localStorage.getItem('icoder-medical-coding-samples');
      return saved ? JSON.parse(saved) : DEFAULT_SAMPLES;
    } catch { return DEFAULT_SAMPLES; }
  });
  const [editingSample, setEditingSample] = useState<{ key: string; title: string; text: string } | null>(null);

  const [input, setInput] = useState('');
  const [codingSystems, setCodingSystems] = useState<{ code_system: string; name: string; is_default: boolean }[]>([]);
  const [selectedSystems, setSelectedSystems] = useState<string[]>(['icd10-cn', 'icd9-cm-3']);
  const [showSystemMenu, setShowSystemMenu] = useState(false);
  const [showSampleMenu, setShowSampleMenu] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [runtimeMode, setRuntimeMode] = useState(() => localStorage.getItem('icoder-mc-runtime-mode') !== 'legacy');
  const [runtimeResult, setRuntimeResult] = useState<RuntimeRunResult | null>(null);
  const [executionModeLabel, setExecutionModeLabel] = useState('');
  const [confThreshold, setConfThreshold] = useState(0.6);
  const [expandResults, setExpandResults] = useState(true);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [dsStatus, setDsStatus] = useState<MedicalCodingStatus | null>(null);

  // Fetch DeepSeek status on mount
  useEffect(() => {
    runtimeApi.getMedicalCodingStatus().then((s) => setDsStatus(s)).catch(() => {});
  }, []);
  const [agentExperts, setAgentExperts] = useState<any[]>([]);

  // Custom experts (user-created)
  const [customExperts, setCustomExperts] = useState<any[]>([]);
  const [showAddExpert, setShowAddExpert] = useState(false);
  const [pinnedParts, setPinnedParts] = useState('default');

  // Right panel state (SettingsCodeTab managed via SettingsCodeTab component's internal state)
  const [rightPanel, setRightPanel] = useState<'settings' | 'code'>('settings');

  // Output view tab
  const [outputView, setOutputView] = useState<OutputView>('rendered');

  const [copied, setCopied] = useState('');

  // Include/Exclude code filters
  const [includeCodes, setIncludeCodes] = useState<string[]>([]);
  const [excludeCodes, setExcludeCodes] = useState<string[]>([]);
  const [showIncludeDialog, setShowIncludeDialog] = useState(false);
  const [showExcludeDialog, setShowExcludeDialog] = useState(false);

  const { setCurrentReview, setProcessing, setError } = useAppStore();
  const addCost = useCostStore(s => s.addCost);
  const navigate = useNavigate();

  // Fetch coding systems + agent config from API
  useEffect(() => {
    codeTablesApi.list().then(r => {
      const tables = r.data?.tables || [];
      const systems = tables
        .filter((t: any) => t.is_active !== false)
        .map((t: any) => ({ code_system: t.code_system, name: t.name, is_default: t.is_default }));
      setCodingSystems(systems);
      const defaults = systems.filter((s: any) => s.is_default).map((s: any) => s.code_system);
      setSelectedSystems(defaults.length ? defaults : systems.length ? [systems[0].code_system] : []);
    }).catch(() => {});
    // Load system prompt and experts from server
    agentsApi.templates().then(r => {
      const tpl = (r.data?.templates || []).find((t: any) => t.id === 'medical-coding');
      if (tpl?.system_prompt) setSystemPrompt(tpl.system_prompt);
      if (tpl?.expert_ids?.length) {
        expertsApi.list('', '', 'all').then(er => {
          const experts = er.data?.experts || [];
          const nameToId: Record<string, string> = {};
          for (const e of experts) nameToId[e.name] = e.id;
          const matched = tpl.expert_ids
            .map((name: string) => ({ id: nameToId[name] || name, name, key: name }))
            .filter((e: any) => e.id);
          if (matched.length) setAgentExperts(matched);
        }).catch(() => {});
      }
    }).catch(() => {});
  }, []);

  // Build evidence lookup map from review data
  const evidenceMap = useMemo(() => {
    if (!result?.evidences) return {} as Record<string, ClinicalEvidence>;
    const map: Record<string, ClinicalEvidence> = {};
    result.evidences.forEach((ev: ClinicalEvidence) => {
      map[ev.id] = ev;
    });
    return map;
  }, [result?.evidences]);

  // Build alternatives map: group candidates by finding, keep groups with multiple different codes
  const alternativesMap = useMemo(() => {
    if (!result?.candidates) return {} as Record<string, CodeCandidate[]>;
    const map: Record<string, CodeCandidate[]> = {};
    result.candidates.forEach((c: CodeCandidate) => {
      if (!map[c.finding]) map[c.finding] = [];
      map[c.finding].push(c);
    });
    // Only retain groups that have at least 2 distinct codes
    Object.keys(map).forEach(key => {
      const uniqueCodes = new Set(map[key].map(c => c.code));
      if (uniqueCodes.size <= 1) delete map[key];
    });
    return map;
  }, [result?.candidates]);

  // Build routing decision lookup from confidence calibration
  const routingMap = useMemo(() => {
    if (!result?.confidence_calibration?.routing_decisions) return {} as Record<string, any>;
    const map: Record<string, any> = {};
    result.confidence_calibration.routing_decisions.forEach((rd: any) => {
      map[rd.code] = rd;
    });
    return map;
  }, [result?.confidence_calibration?.routing_decisions]);

  const confidenceMap = useMemo(() => {
    if (!result?.confidence_calibration?.coding_confidences) return {} as Record<string, any>;
    const map: Record<string, any> = {};
    result.confidence_calibration.coding_confidences.forEach((cc: any) => {
      map[cc.code] = cc;
    });
    return map;
  }, [result?.confidence_calibration?.coding_confidences]);

  const evidenceRanking = result?.evidence_ranking;

  // Build events for EventInspector
  const events = useMemo(() => {
    const evts: Array<{ type: string; data: Record<string, unknown>; timestamp: string; credits?: number }> = [];
    if (runtimeResult) {
      evts.push({
        type: 'POST /api/runtime/agents/run',
        data: { status: '200 OK', run_id: runtimeResult.run_id, agent_ref: runtimeResult.agent_ref },
        timestamp: new Date().toLocaleTimeString(locale, { hour12: false }),
        credits: runtimeResult.processing_time_ms ? (runtimeResult.processing_time_ms / 1000) * 0.02 : undefined,
      });
      evts.push({
        type: 'RUNTIME',
        data: { status: runtimeResult.status, steps: runtimeResult.audit_trail?.length || 0, duration_ms: runtimeResult.processing_time_ms || 0 },
        timestamp: new Date().toLocaleTimeString(locale, { hour12: false }),
      });
      evts.push({
        type: 'CODING',
        data: {
          primary_diag: runtimeResult.primary_diagnosis?.code || '—',
          secondary_count: runtimeResult.secondary_diagnoses?.length || 0,
          procedure_count: runtimeResult.procedures?.length || 0,
          issues: runtimeResult.issues_found?.length || 0,
        },
        timestamp: new Date().toLocaleTimeString(locale, { hour12: false }),
      });
    } else if (result) {
      evts.push({
        type: 'POST /api/reviews',
        data: { status: '200 OK', review_id: (result as any).id },
        timestamp: new Date().toLocaleTimeString(locale, { hour12: false }),
        credits: result.processing_time_ms ? (result.processing_time_ms / 1000) * 0.02 : undefined,
      });
      evts.push({
        type: 'PIPELINE',
        data: { pipeline_id: (result as any).pipeline_id || '—', steps: 8, duration_ms: result.processing_time_ms || 0 },
        timestamp: new Date().toLocaleTimeString(locale, { hour12: false }),
      });
      evts.push({
        type: 'EVIDENCE',
        data: {
          diagnosis_facts: (result as any).evidences?.filter((e: any) => e.entity_type === 'diagnosis_evidence').length || 0,
          procedure_facts: (result as any).evidences?.filter((e: any) => e.entity_type === 'procedure_evidence').length || 0,
        },
        timestamp: new Date().toLocaleTimeString(locale, { hour12: false }),
      });
      evts.push({
        type: 'CANDIDATES',
        data: {
          total: (result as any).candidates?.length || 0,
          supported: (result as any).validation_summary?.supported || 0,
          needs_review: (result as any).validation_summary?.needs_review || 0,
        },
        timestamp: new Date().toLocaleTimeString(locale, { hour12: false }),
      });
    }
    return evts;
  }, [result, runtimeResult, locale]);

  // Calculate total credits consumed from processing time
  const totalCredits = useMemo(() => {
    if (!result?.processing_time_ms) return 0;
    return (result.processing_time_ms / 1000) * 0.02;
  }, [result]);

  const handlePredictWithText = async (text: string) => {
    if (!text.trim() || loading) return;
    setLoading(true);
    setProcessing(true);
    setError(null);
    setResult(null);
    setRuntimeResult(null);

    if (runtimeMode) {
      // ── Runtime mode: use Medical Coding Agent via Runtime API ──
      const startTime = Date.now();
      const progressTimer = setInterval(() => {
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        setExecutionModeLabel(`Processing... ${elapsed}s`);
      }, 500);
      try {
        setExecutionModeLabel('Connecting DeepSeek...');
        const data = await runtimeApi.runAgent('icoder/medical-coding-agent@1.0.0', text);
        clearInterval(progressTimer);
        setRuntimeResult(data);
        setResult(data);
        const elapsed = data.processing_time_ms || (Date.now() - startTime);
        setExecutionModeLabel(`Done (${Math.round(elapsed / 1000)}s)`);
        if (data.processing_time_ms) {
          addCost((data.processing_time_ms / 1000) * 0.02);
        }
      } catch (err: any) {
        clearInterval(progressTimer);
        const msg = err.response?.data?.detail || err.message || 'Runtime 处理失败';
        setError(msg);
        setExecutionModeLabel('platform_runtime (failed)');
        await legacyPredict(text);
      }
    } else {
      // ── Legacy mode ──
      setExecutionModeLabel('legacy');
      await legacyPredict(text);
    }

    setLoading(false);
    setProcessing(false);
  };

  const legacyPredict = async (text: string) => {
    try {
      const { data: encounter } = await encountersApi.createFromText({
        raw_text: text, department: '内科', patient_id: '匿名',
      });
      const { data: review } = await reviewsApi.create(encounter.id);
      setCurrentReview(review);
      setResult(review);
      if (review.processing_time_ms) {
        addCost((review.processing_time_ms / 1000) * 0.02);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '处理失败');
    }
  };

  const handlePredict = () => handlePredictWithText(input);

  // SSE streaming for agent chat (real-time token delivery)
  const handleStreamPredict = async () => {
    if (!input.trim() || loading) return;
    setLoading(true);
    setProcessing(true);
    setError(null);
    setResult(null);
    setStreamOutput('');

    try {
      const { data: encounter } = await encountersApi.createFromText({
        raw_text: input, department: '内科', patient_id: '匿名',
      });
      setStreamOutput('病历已创建...\n');
      const { data: review } = await reviewsApi.create(encounter.id);
      setCurrentReview(review);
      setResult(review);
      setStreamOutput('编码审核完成');
      setTimeout(() => setStreamOutput(''), 3000);
      // Live cost integration
      if (review.processing_time_ms) {
        addCost((review.processing_time_ms / 1000) * 0.02);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '处理失败');
      setStreamOutput('');
    } finally {
      setLoading(false);
      setProcessing(false);
    }
  };
  const [streamOutput, setStreamOutput] = useState('');

  const hasText = input.trim().length > 0;
  const enabledExpertCount = agentExperts.length + customExperts.length;

  const toggleSystem = (sys: string) => {
    setSelectedSystems(prev =>
      prev.includes(sys) ? prev.filter(s => s !== sys) : [...prev, sys]
    );
  };

  // Resolve ClinicalEvidence objects from evidence IDs
  const getEvidenceByIds = (evidenceIds: unknown): ClinicalEvidence[] => {
    if (!evidenceIds || !Array.isArray(evidenceIds)) return [];
    return evidenceIds.map((id: string) => evidenceMap[id]).filter(Boolean);
  };

  // Build code snippets for the Code view / Code tab
  const snippetInput = input.slice(0, 80) + (input.length > 80 ? '...' : '');
  const snippetSystems = selectedSystems.join(', ') || '全部';
  const snippetInclude = includeCodes.length ? includeCodes.join(', ') : '无';
  const snippetExclude = excludeCodes.length ? excludeCodes.join(', ') : '无';

  const codeSnippetJS = [
    `import { iCoDerClient } from "@icoder/sdk";`,
    ``,
    `const client = new iCoDerClient({`,
    `  apiKey: "YOUR_API_KEY",`,
    `});`,
    ``,
    `const agent = client.agent("medical-coding-agent");`,
    `const response = await agent.chat(\`${snippetInput}\`);`,
    ``,
    `// 编码系统: ${snippetSystems}`,
    `// Confidence threshold: ${confThreshold}`,
    `// Include codes: ${snippetInclude}`,
    `// Exclude codes: ${snippetExclude}`,
    ``,
    `// Response includes:`,
    `// - primary_diagnosis: { code, name, confidence, evidence_ids, judgment }`,
    `// - main_procedure: { code, name, confidence, evidence_ids, judgment }`,
    `// - candidates: [{ code, name, score, evidence_ids, status }]`,
    `// - evidences: [{ id, text, supports_codes, certainty }]`,
  ].join('\n');

  const codeSnippetPython = [
    `from icoder_sdk import iCoDerClient`,
    ``,
    `client = iCoDerClient(`,
    `    api_key="YOUR_API_KEY",`,
    `)`,
    ``,
    `agent = client.agent("medical-coding-agent")`,
    `response = agent.chat("""${snippetInput}""")`,
    ``,
    `# Coding systems: ${snippetSystems}`,
    `# Confidence threshold: ${confThreshold}`,
    `# Include codes: ${snippetInclude}`,
    `# Exclude codes: ${snippetExclude}`,
    ``,
    `# Response includes:`,
    `# - primary_diagnosis`,
    `# - main_procedure`,
    `# - candidates`,
    `# - evidences`,
  ].join('\n');

  const codeSnippetJSON = JSON.stringify({
    method: 'agent.chat',
    params: {
      text: snippetInput,
      coding_systems: selectedSystems,
      confidence_threshold: confThreshold,
      include_codes: includeCodes,
      exclude_codes: excludeCodes,
      experts: agentExperts.map(e => e.key),
    },
  }, null, 2);

  // ---- Shared settings panel content ----
  const settingsContent = (
    <div className="p-4 space-y-5">
      {/* Name */}
      <div>
        <label className="text-xs font-medium text-foreground block mb-1">名称</label>
        <input defaultValue="Medical Coding Agent"
          className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-transparent text-foreground focus:outline-none" />
      </div>

      {/* System prompt */}
      <div>
        <label className="text-xs font-medium text-foreground flex items-center gap-1 mb-1">
          系统提示词
          <span className="w-4 h-4 rounded-full border border-border flex items-center justify-center text-[10px] text-muted-foreground cursor-help">?</span>
        </label>
        <div className="border border-border rounded-lg overflow-hidden">
          <div className="bg-muted/50 px-3 py-1.5 border-b border-border flex items-center gap-2">
            <span className="text-[10px] font-mono text-muted-foreground">&lt;role&gt;</span>
          </div>
          <textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)}
            rows={6}
            className="w-full text-xs bg-transparent px-3 py-2 text-muted-foreground resize-none focus:outline-none leading-relaxed" />
        </div>
      </div>

      {/* Coding config */}
      <div className="space-y-3">
        <div>
          <label className="text-xs font-medium text-foreground block mb-1">编码系统</label>
          <div className="relative">
            <button
              onClick={() => setShowSystemMenu(!showSystemMenu)}
              className="w-full flex items-center justify-between text-xs border border-border rounded-lg px-3 py-2 bg-transparent hover:border-primary/30 transition-colors"
            >
              <span className={selectedSystems.length ? 'text-foreground' : 'text-muted-foreground'}>
                {selectedSystems.length ? `已选 ${selectedSystems.length} 个编码系统` : '选择编码系统'}
              </span>
              <ChevronDown size={14} className={`text-muted-foreground transition-transform ${showSystemMenu ? 'rotate-180' : ''}`} />
            </button>
            {showSystemMenu && (
              <div className="absolute top-full mt-1 left-0 right-0 bg-popover border border-border rounded-lg shadow-lg z-50 max-h-60 overflow-y-auto py-1">
                {codingSystems.map((sys) => (
                  <label key={sys.code_system} className={`flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer hover:bg-accent transition-colors ${selectedSystems.includes(sys.code_system) ? 'bg-primary/5' : ''}`}>
                    <input
                      type="checkbox"
                      checked={selectedSystems.includes(sys.code_system)}
                      onChange={() => toggleSystem(sys.code_system)}
                      className="accent-primary shrink-0"
                    />
                    <span className="text-foreground">{sys.name}</span>
                    <span className="text-[10px] text-muted-foreground ml-auto">{sys.code_system}</span>
                  </label>
                ))}
                <div className="border-t border-border mt-1 pt-1 px-2">
                  <button onClick={() => setShowSystemMenu(false)} className="w-full text-center text-xs text-primary hover:bg-accent py-1 rounded transition-colors">完成</button>
                </div>
              </div>
            )}
            {showSystemMenu && <div className="fixed inset-0 z-40" onClick={() => setShowSystemMenu(false)} />}
          </div>
        </div>
        {/* Expand toggle */}
        <div className="flex items-center justify-between py-1.5 border-t border-border pt-3">
          <div>
            <label className="text-xs font-medium text-foreground">展开结果</label>
            <p className="text-[10px] text-muted-foreground">显示所有候选编码</p>
          </div>
          <button onClick={() => setExpandResults(!expandResults)}
            className={`relative w-8 h-5 rounded-full transition-colors shrink-0 ${expandResults ? 'bg-primary' : 'bg-muted border border-border'}`}>
            <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-background shadow-sm transition-all ${expandResults ? 'left-3.5' : 'left-0.5'}`} />
          </button>
        </div>
        <div>
          <label className="text-xs font-medium text-foreground block mb-1">置信度阈值: {confThreshold}</label>
          <input type="range" min={0} max={1} step={0.05} value={confThreshold}
            onChange={(e) => setConfThreshold(parseFloat(e.target.value))}
            className="w-full accent-primary" />
        </div>
      </div>

      {/* Include / Exclude code filters */}
      <div className="space-y-3">
        <div>
          <label className="text-xs font-medium text-foreground block mb-1">包含编码</label>
          {includeCodes.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {includeCodes.map((code, i) => (
                <span key={i}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                  {code}
                  <button onClick={() => setIncludeCodes(includeCodes.filter((_, j) => j !== i))}
                    className="hover:text-red-500">&times;</button>
                </span>
              ))}
            </div>
          )}
          <button onClick={() => setShowIncludeDialog(true)}
            className="text-xs text-primary hover:underline flex items-center gap-1">
            <Plus size={12} /> 添加编码
          </button>
        </div>
        <div>
          <label className="text-xs font-medium text-foreground block mb-1">排除编码</label>
          {excludeCodes.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-2">
              {excludeCodes.map((code, i) => (
                <span key={i}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-700 border border-red-200 flex items-center gap-1">
                  {code}
                  <button onClick={() => setExcludeCodes(excludeCodes.filter((_, j) => j !== i))}
                    className="hover:text-red-500">&times;</button>
                </span>
              ))}
            </div>
          )}
          <button onClick={() => setShowExcludeDialog(true)}
            className="text-xs text-primary hover:underline flex items-center gap-1">
            <Plus size={12} /> Add codes
          </button>
        </div>
      </div>

      {/* Experts */}
      <div>
        <h4 className="text-xs font-semibold text-foreground mb-3 flex items-center gap-1">
          <Wrench size={12} /> 专家
        </h4>
        <div className="space-y-1">
          {agentExperts.map(expert => (
            <div key={expert.id} className="flex items-center py-1.5 group">
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <GripVertical size={12} className="text-muted-foreground/40 shrink-0" />
                <div className="min-w-0">
                  <p className="text-xs font-medium text-foreground">{expert.name}</p>
                  <p className="text-[10px] text-muted-foreground">{expert.key}</p>
                </div>
              </div>
              <button
                onClick={() => setAgentExperts(agentExperts.filter(e => e.id !== expert.id))}
                className="p-0.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                title="移除"
              >
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
        <button onClick={() => navigate('/expert-library')}
          className="text-xs text-primary hover:underline mt-3 flex items-center gap-1">
          浏览专家库 <ExternalLink size={10} />
        </button>
      </div>

      {/* Custom experts */}
      <div>
        <h4 className="text-xs font-semibold text-foreground mb-2">自定义专家</h4>
        {customExperts.length > 0 && (
          <div className="space-y-1 mb-2">
            {customExperts.map((ce: any) => (
              <div key={ce.id} className="flex items-center py-1">
                <GripVertical size={12} className="text-muted-foreground/40 shrink-0 mr-2" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-foreground">{ce.name}</p>
                  <p className="text-[10px] text-muted-foreground">{ce.key || ce.id}</p>
                </div>
                <button onClick={() => setCustomExperts(customExperts.filter(e => e.id !== ce.id))}
                  className="text-destructive/70 hover:text-destructive">
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
        <button onClick={() => setShowAddExpert(true)}
          className="text-xs text-primary hover:underline flex items-center gap-1">
          <Plus size={12} /> 添加专家
        </button>
      </div>

      {/* Pinned message parts */}
      <div>
        <h4 className="text-xs font-semibold text-foreground mb-2">固定消息部分</h4>
        <select value={pinnedParts} onChange={(e) => setPinnedParts(e.target.value)}
          className="w-full min-h-[2.75rem] px-3 py-2 text-sm bg-card border border-input rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/20 focus:border-ring transition-colors text-xs">
          <option value="default">默认</option>
          <option value="role_only">仅角色</option>
          <option value="full_context">完整上下文</option>
          <option value="custom">自定义模板...</option>
        </select>
      </div>
    </div>
  );

  const codeContent = (
    <div className="h-full">
      <CodeSnippet
        javascript={codeSnippetJS}
        python={codeSnippetPython}
        json={codeSnippetJSON}
      />
    </div>
  );

  return (
    <div className="flex flex-col h-full bg-muted/20">
      {/* HEADER — provided by global Layout component */}

      <div className="flex-1 flex min-h-0">
        {/* ===== LEFT: 75% main content ===== */}
        <div className="flex-[75_1_0px] bg-muted/20 p-4 min-w-0">
          <div className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 h-full">
            <div className="flex h-full gap-6 p-6">
        {/* ===== LEFT: Input Card ===== */}
        <div className="w-[420px] shrink-0 flex flex-col gap-4">
          {/* Coding systems — iCoDer-style single box */}
          <div className="bg-background rounded-xl border border-border/20 shadow-sm px-4 py-3">
            <div className="flex items-center gap-2 flex-wrap">
              {selectedSystems.length === 0 ? (
                <span className="text-[13px] text-muted-foreground">未选择编码系统</span>
              ) : (
                selectedSystems.map(sys => {
                  const info = codingSystems.find(cs => cs.code_system === sys);
                  return (
                    <span key={sys} className="text-[11px] px-2.5 py-1 rounded-lg bg-muted text-muted-foreground flex items-center gap-1.5">
                      {info?.name || sys}
                      <button onClick={() => toggleSystem(sys)} className="hover:text-foreground">&times;</button>
                    </span>
                  );
                })
              )}
              <div className="relative ml-auto">
                <button onClick={() => setShowSystemMenu(!showSystemMenu)}
                  className="flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground transition-colors">
                  <Plus size={14} /> 添加
                </button>
                {showSystemMenu && (
                  <div className="absolute top-full right-0 mt-1 bg-background rounded-xl shadow-lg border border-border/20 py-2 z-50 min-w-[240px] max-h-56 overflow-y-auto">
                    {codingSystems.map((sys) => (
                      <label key={sys.code_system} className={`flex items-center gap-2 px-4 py-2 text-[13px] cursor-pointer hover:bg-muted/50 ${selectedSystems.includes(sys.code_system) ? 'text-foreground' : 'text-muted-foreground'}`}>
                        <input type="checkbox" checked={selectedSystems.includes(sys.code_system)}
                          onChange={() => toggleSystem(sys.code_system)} className="accent-primary shrink-0 rounded" />
                        {sys.name}
                      </label>
                    ))}
                    <div className="border-t border-border/20 mt-1 pt-1 px-3">
                      <button onClick={() => setShowSystemMenu(false)} className="w-full text-center text-xs text-primary hover:bg-accent py-1 rounded transition-colors">完成</button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Input card */}
          <div className="bg-background rounded-xl shadow-sm border border-border/20 p-5 flex flex-col gap-5 flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handlePredict(); } }}
              placeholder={input ? '' : '输入临床文本...'}
              rows={14}
              className="w-full text-[15px] leading-relaxed border-0 p-0 pt-8 bg-transparent focus:outline-none placeholder:text-muted-foreground/30 resize-none text-foreground flex-1"
            />
            {/* Guided empty state — Corti-style sample selection */}
            {!input && (
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <p className="text-sm text-muted-foreground mb-3 pointer-events-auto">选择示例病历开始体验：</p>
                <div className="flex gap-2 pointer-events-auto">
                  {samples.slice(0, 3).map((s: any, i: number) => (
                    <button key={i} onClick={() => setInput(s.text)}
                      className="px-3 py-2 rounded-lg border border-border/50 text-xs text-muted-foreground hover:text-foreground hover:border-primary/30 hover:bg-accent/50 transition-all text-left max-w-[200px]">
                      <p className="font-medium text-foreground truncate">{s.label}</p>
                      <p className="text-[10px] text-muted-foreground truncate mt-0.5">{s.text.slice(0, 50)}...</p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Sample cases — top-right collapsible */}
            <div className="absolute top-3 right-4 z-10">
              <div className="relative">
                <button onClick={() => setShowSampleMenu(!showSampleMenu)}
                  className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border hover:bg-accent/50 transition-all">
                  <FileText size={13} />
                  <span>使用样例</span>
                  <ChevronDown size={10} className={`transition-transform ${showSampleMenu ? 'rotate-180' : ''}`} />
                </button>
                {showSampleMenu && (
                  <div className="absolute top-full right-0 mt-1 bg-popover border border-border rounded-xl shadow-lg py-1 min-w-[200px] z-20 max-h-64 overflow-y-auto">
                    {samples.map((s: any) => (
                      <div key={s.key} className="group flex items-center">
                        <button onClick={() => { setInput(s.text); setShowSampleMenu(false); }}
                          className="flex-1 text-left px-3 py-2 text-xs text-foreground hover:bg-accent transition-colors">
                          {s.title}
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); setEditingSample({ key: s.key, title: s.title, text: s.text }); }}
                          className="p-1 mr-1 rounded opacity-0 group-hover:opacity-100 hover:bg-accent text-muted-foreground transition-all">
                          <Pencil size={11} />
                        </button>
                      </div>
                    ))}
                    <div className="border-t border-border/20 mt-1 pt-1 px-1">
                      <button onClick={() => setEditingSample({ key: `sample-${Date.now()}`, title: '', text: '' })}
                        className="w-full text-left px-3 py-2 text-xs text-primary hover:bg-accent transition-colors flex items-center gap-1.5">
                        <Plus size={12} /> 添加样例
                      </button>
                    </div>
                  </div>
                )}
              </div>
              {showSampleMenu && <div className="fixed inset-0 z-[5]" onClick={() => setShowSampleMenu(false)} />}
            </div>

            {/* DeepSeek + Runtime Status Bar */}
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              {dsStatus && (
                <>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${
                    dsStatus.deepseek_configured ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                  }`} title={`Provider: ${dsStatus.provider_mode}, Model: ${dsStatus.model}`}>
                    {dsStatus.deepseek_configured ? `DeepSeek ${dsStatus.model}` : 'DeepSeek: No API Key'}
                  </span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                    dsStatus.provider_mode === 'real' ? 'bg-green-100 text-green-700' :
                    dsStatus.provider_mode === 'mock' ? 'bg-amber-100 text-amber-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {dsStatus.provider_mode === 'real' ? 'Real' : dsStatus.provider_mode === 'mock' ? 'Mock' : dsStatus.provider_mode}
                  </span>
                </>
              )}
              {executionModeLabel && (
                <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${
                  executionModeLabel.includes('failed') ? 'bg-red-100 text-red-700' :
                  executionModeLabel.includes('Done') ? 'bg-green-100 text-green-700' :
                  executionModeLabel.includes('Processing') ? 'bg-blue-100 text-blue-700' :
                  'bg-gray-100 text-gray-600'}`}>
                  {executionModeLabel}
                </span>
              )}
            </div>
            <div className="flex gap-2">
              {/* Samples dropdown — Corti-style quick demo data */}
              <div className="relative">
                <button onClick={() => setShowSampleMenu(!showSampleMenu)}
                  className="px-3 py-2 rounded-lg border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-accent transition-colors flex items-center gap-1">
                  <BookOpen size={13} /> 示例
                </button>
                {showSampleMenu && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowSampleMenu(false)} />
                    <div className="absolute bottom-full mb-1 left-0 bg-popover border border-border rounded-lg shadow-lg z-50 py-1 min-w-[300px] max-h-48 overflow-y-auto">
                      {samples.map((s: any, i: number) => (
                        <button key={i} onClick={() => { setInput(s.text); setShowSampleMenu(false); }}
                          className="w-full text-left px-3 py-2 text-xs hover:bg-accent transition-colors">
                          <p className="font-medium text-foreground truncate">{s.label}</p>
                          <p className="text-[10px] text-muted-foreground truncate">{s.text.slice(0, 60)}...</p>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              <button onClick={handlePredict} disabled={!hasText || loading}
                className="flex-1 py-3 rounded-xl bg-primary text-white text-[15px] font-medium hover:bg-primary/90 disabled:opacity-20 transition-all flex items-center justify-center gap-2 active:scale-[0.98]">
                {loading ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />}
                {loading ? '分析中...' : '开始编码'}
              </button>
            </div>
          </div>

        </div>

        {/* ===== RIGHT: Output ===== */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-y-auto">
            {!result ? (
              <div className="flex flex-col items-center justify-center h-full">
                <div className="w-20 h-20 rounded-3xl bg-muted flex items-center justify-center mb-6">
                  <Stethoscope size={36} className="text-muted-foreground" />
                </div>
                <h2 className="text-xl font-semibold text-foreground mb-2 tracking-tight">智能编码</h2>
                <p className="text-[15px] text-muted-foreground max-w-xs text-center leading-relaxed">
                  输入临床文本，为诊断和手术推荐ICD编码
                </p>
              </div>
            ) : (
              <>
              {/* ── RuntimeRunResult: Layered Display ── */}
              {runtimeResult && (
                <div className="mb-4 space-y-2">
                  {/* Header */}
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-mono text-[10px]">{runtimeResult.run_id?.slice(0,12)}</span>
                    <span className={`px-1 py-0.5 rounded text-[10px] font-medium ${
                      runtimeResult.status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                    }`}>{runtimeResult.status}</span>
                    <span>{runtimeResult.processing_time_ms}ms</span>
                  </div>

                  {/* Section 1: Primary Diagnosis */}
                  <details open className="rounded-lg border border-green-200 bg-green-50/50">
                    <summary className="px-3 py-2 text-sm font-medium text-green-800 cursor-pointer">
                      主诊断: {runtimeResult.primary_diagnosis?.code || '—'} — {runtimeResult.primary_diagnosis?.description || '—'}
                      {runtimeResult.primary_diagnosis?.confidence != null && (
                        <span className="ml-2 text-xs text-green-600">({(runtimeResult.primary_diagnosis.confidence * 100).toFixed(0)}%)</span>
                      )}
                    </summary>
                    <div className="px-3 pb-2 text-xs text-green-700 space-y-1">
                      {runtimeResult.primary_diagnosis?.evidence?.length > 0 && (
                        <div>
                          <span className="font-medium">证据:</span>
                          {runtimeResult.primary_diagnosis.evidence.map((e, i) => (
                            <div key={i} className="pl-2 text-green-600 italic">"{e}"</div>
                          ))}
                        </div>
                      )}
                    </div>
                  </details>

                  {/* Section 2: Secondary Diagnoses */}
                  {runtimeResult.secondary_diagnoses?.length > 0 && (
                    <details className="rounded-lg border border-blue-200 bg-blue-50/50">
                      <summary className="px-3 py-2 text-sm font-medium text-blue-800 cursor-pointer">
                        次要诊断 ({runtimeResult.secondary_diagnoses.length})
                      </summary>
                      <div className="px-3 pb-2 space-y-1">
                        {runtimeResult.secondary_diagnoses.map((d, i) => (
                          <div key={i} className="text-xs text-blue-700">
                            <span className="font-mono font-medium">{d.code}</span> — {d.description}
                            {d.confidence != null && <span className="ml-1 text-blue-500">({(d.confidence * 100).toFixed(0)}%)</span>}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  {/* Section 3: Procedures */}
                  {runtimeResult.procedures?.length > 0 && (
                    <details className="rounded-lg border border-purple-200 bg-purple-50/50">
                      <summary className="px-3 py-2 text-sm font-medium text-purple-800 cursor-pointer">
                        手术操作 ({runtimeResult.procedures.length})
                      </summary>
                      <div className="px-3 pb-2 space-y-1">
                        {runtimeResult.procedures.map((p, i) => (
                          <div key={i} className="text-xs text-purple-700">
                            <span className="font-mono font-medium">{p.code}</span> — {p.description}
                            {p.confidence != null && <span className="ml-1 text-purple-500">({(p.confidence * 100).toFixed(0)}%)</span>}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  {/* Section 4: Rule Warnings */}
                  {runtimeResult.issues_found?.length > 0 && (
                    <details className="rounded-lg border border-amber-200 bg-amber-50/50">
                      <summary className="px-3 py-2 text-sm font-medium text-amber-800 cursor-pointer">
                        规则告警 ({runtimeResult.issues_found.length})
                        {runtimeResult.issues_found.filter((i) => i.severity === 'critical' || i.severity === 'high').length > 0 && (
                          <span className="ml-2 text-xs text-red-600">
                            ({runtimeResult.issues_found.filter((i) => i.severity === 'critical' || i.severity === 'high').length} critical/high)
                          </span>
                        )}
                      </summary>
                      <div className="px-3 pb-2 space-y-1">
                        {runtimeResult.issues_found.map((issue, i) => (
                          <div key={i} className={`text-xs border-l-2 pl-2 ${
                            issue.severity === 'critical' ? 'border-red-400 text-red-700' :
                            issue.severity === 'high' ? 'border-orange-400 text-orange-700' :
                            'border-amber-300 text-amber-700'
                          }`}>
                            <span className="font-mono text-[10px]">{issue.code}</span>: {issue.message}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}

                  {/* Section 5: Quality Flags */}
                  {(runtimeResult as any).quality_flags && Object.values((runtimeResult as any).quality_flags).some(Boolean) && (
                    <details className="rounded-lg border border-gray-200 bg-gray-50/50">
                      <summary className="px-3 py-2 text-xs font-medium text-gray-600 cursor-pointer">Quality Flags</summary>
                      <div className="px-3 pb-2 flex flex-wrap gap-1">
                        {Object.entries((runtimeResult as any).quality_flags).filter(([,v]) => v).map(([k]) => (
                          <span key={k} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 text-gray-700">{k}</span>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              )}

                {/* ---------- Loading / Streaming ---------- */}
                {loading && (
                  <div className="px-6 mb-6">
                    <div className="max-w-3xl mx-auto">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <div className="flex gap-1">
                          <span className="w-2 h-2 rounded-full bg-primary/40 animate-bounce" style={{animationDelay: '0ms'}} />
                          <span className="w-2 h-2 rounded-full bg-primary/40 animate-bounce" style={{animationDelay: '150ms'}} />
                          <span className="w-2 h-2 rounded-full bg-primary/40 animate-bounce" style={{animationDelay: '300ms'}} />
                        </div>
                        <span>分析临床文本中...</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* ---------- Stream output status ---------- */}
                {streamOutput && (
                  <div className="px-6 mb-6">
                    <div className="max-w-3xl mx-auto">
                      <div className="text-xs text-muted-foreground bg-muted/30 rounded-lg px-4 py-2 whitespace-pre-wrap">
                        {streamOutput}
                      </div>
                    </div>
                  </div>
                )}

                {/* ---------- Result — 3-view output (Rendered / JSON / Code) ---------- */}
                {result && (
                  <div className="px-2">
                    {/* View tabs */}
                    <div className="flex items-center gap-1 mb-4 border-b border-border">
                      <button onClick={() => setOutputView('rendered')}
                        className={`text-xs px-3 py-2 border-b-2 transition-colors ${outputView === 'rendered' ? 'border-primary text-foreground font-medium' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
                        渲染
                      </button>
                      <button onClick={() => setOutputView('json')}
                        className={`text-xs px-3 py-2 border-b-2 transition-colors ${outputView === 'json' ? 'border-primary text-foreground font-medium' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
                        JSON
                      </button>
                      <button onClick={() => setOutputView('code')}
                        className={`text-xs px-3 py-2 border-b-2 transition-colors ${outputView === 'code' ? 'border-primary text-foreground font-medium' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
                        代码
                      </button>
                      <div className="flex-1" />
                      <button onClick={() => { navigator.clipboard.writeText(JSON.stringify(result, null, 2)); setCopied('result'); setTimeout(() => setCopied(''), 2000); }}
                        className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 px-2 py-1 rounded hover:bg-accent transition-colors">
                        {copied === 'result' ? <Check size={12} /> : <Copy size={12} />}
                        {copied === 'result' ? '已复制' : '复制'}
                      </button>
                    </div>

                    {/* ===== RENDERED VIEW ===== */}
                    {outputView === 'rendered' && (
                      <div className="space-y-6">
                        {/* Pipeline Health Banner */}
                        {result.pipeline_health && result.pipeline_health !== 'healthy' && (
                          <div className={`px-4 py-3 rounded-lg text-sm ${
                            result.pipeline_health === 'failed'
                              ? 'bg-red-50 border border-red-200 text-red-800'
                              : 'bg-amber-50 border border-amber-200 text-amber-800'
                          }`}>
                            {result.pipeline_health === 'failed'
                              ? '部分核心步骤执行失败，编码结果可能不完整'
                              : '部分分析步骤未完成，核心编码结果仍可用'}
                          </div>
                        )}
                        {/* Primary Diagnosis */}
                        {result.primary_diagnosis?.code && (
                          <div>
                            <p className="text-xs font-medium text-muted-foreground mb-2">主诊断</p>
                            <div className="bg-card border border-border rounded-xl p-5 space-y-3">
                              <div className="flex items-baseline gap-3 flex-wrap">
                                <code className="text-2xl font-bold text-primary font-mono">{result.primary_diagnosis.code}</code>
                                <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-emerald-50 text-emerald-700">
                                  置信度 {(result.primary_diagnosis.confidence * 100).toFixed(0)}%
                                </span>
                                {/* Status */}
                                {result.primary_diagnosis.judgment && (
                                  <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${
                                    result.primary_diagnosis.judgment === 'supported' || result.primary_diagnosis.judgment === 'confirmed'
                                      ? 'bg-emerald-50 text-emerald-700'
                                      : 'bg-amber-50 text-amber-700'
                                  }`}>
                                    {result.primary_diagnosis.judgment === 'supported' || result.primary_diagnosis.judgment === 'confirmed'
                                      ? '✓ 有证据'
                                      : '⚠ 需复核'}
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-foreground leading-relaxed">{result.primary_diagnosis.name}</p>
                              {/* Primary Diagnosis Reasoning */}
                              {result.primary_diagnosis?.reasoning?.why_selected && (
                                <div className="bg-muted/20 rounded-lg p-3 space-y-2 border border-border/50">
                                  <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">选择依据</p>
                                  <p className="text-xs text-foreground leading-relaxed">{result.primary_diagnosis.reasoning.why_selected}</p>
                                  {result.primary_diagnosis.reasoning.why_not_selected?.length > 0 && (
                                    <div>
                                      <p className="text-[10px] font-medium text-muted-foreground mt-2 mb-1 uppercase tracking-wider">未选择的诊断</p>
                                      <div className="space-y-1">
                                        {result.primary_diagnosis.reasoning.why_not_selected.map((wn: any, wi: number) => (
                                          <div key={wi} className="flex items-start gap-2 text-[11px] bg-muted/30 rounded px-2 py-1">
                                            <code className="font-mono text-muted-foreground shrink-0">{wn.code}</code>
                                            <span className="text-muted-foreground">{wn.name}</span>
                                            <span className="text-muted-foreground/70">— {wn.reason}</span>
                                            {wn.rule_reference && <span className="text-[10px] bg-amber-100 text-amber-700 px-1 rounded shrink-0">{wn.rule_reference}</span>}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                  {result.primary_diagnosis.reasoning.rule_basis?.length > 0 && (
                                    <div className="flex items-center gap-1 flex-wrap">
                                      {result.primary_diagnosis.reasoning.rule_basis.map((r: string, ri: number) => (
                                        <span key={ri} className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-mono">{r}</span>
                                      ))}
                                    </div>
                                  )}
                                  <div className="flex items-center gap-2">
                                    <span className="text-[10px] text-muted-foreground">置信度判定:</span>
                                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                                      result.primary_diagnosis.reasoning.confidence_level === 'high' ? 'bg-emerald-50 text-emerald-700'
                                      : result.primary_diagnosis.reasoning.confidence_level === 'medium' ? 'bg-amber-50 text-amber-700'
                                      : 'bg-red-50 text-red-700'
                                    }`}>
                                      {result.primary_diagnosis.reasoning.confidence_level === 'high' ? '高' : result.primary_diagnosis.reasoning.confidence_level === 'medium' ? '中' : '低'}
                                    </span>
                                  </div>
                                </div>
                              )}
                              {/* Evidence for primary diagnosis */}
                              {result.primary_diagnosis.evidence_ids && getEvidenceByIds(result.primary_diagnosis.evidence_ids).length > 0 && (
                                <div>
                                  <p className="text-[10px] font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">证据依据</p>
                                  <div className="space-y-1.5">
                                    {getEvidenceByIds(result.primary_diagnosis.evidence_ids).map((ev: ClinicalEvidence) => (
                                      <div key={ev.id} className="text-xs bg-muted/30 rounded-lg px-3 py-2 border-l-2 border-primary/40">
                                        <p className="text-muted-foreground leading-relaxed">&ldquo;{ev.text}&rdquo;</p>
                                        <p className="text-[10px] text-muted-foreground mt-0.5">
                                          {ev.entity_type === 'diagnosis_evidence' ? '诊断证据' : ev.entity_type}
                                          {ev.certainty ? ` · ${ev.certainty}` : ''}
                                          {ev.confidence > 0 ? ` · ${(ev.confidence * 100).toFixed(0)}%` : ''}
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {/* Evidence Ranking Panel */}
                        {evidenceRanking && (evidenceRanking.top_supporting_evidence?.length > 0 || evidenceRanking.weak_evidence?.length > 0 || evidenceRanking.conflicting_evidence?.length > 0) && (
                          <div>
                            <p className="text-xs font-medium text-muted-foreground mb-2">证据全景</p>
                            <div className="bg-card border border-border rounded-xl overflow-hidden">
                              {/* Summary bar */}
                              <div className="flex items-center gap-4 px-4 py-2 bg-muted/30 border-b border-border text-[10px]">
                                {evidenceRanking.evidence_strength_avg != null && (
                                  <span>证据强度均值 <strong className="text-foreground">{(evidenceRanking.evidence_strength_avg * 100).toFixed(0)}%</strong></span>
                                )}
                                {evidenceRanking.unsupported_code_rate != null && (
                                  <span>无证据编码率 <strong className={evidenceRanking.unsupported_code_rate > 0.3 ? 'text-red-600' : 'text-foreground'}>{(evidenceRanking.unsupported_code_rate * 100).toFixed(0)}%</strong></span>
                                )}
                                {evidenceRanking.conflict_rate != null && (
                                  <span>冲突率 <strong className={evidenceRanking.conflict_rate > 0.2 ? 'text-red-600' : 'text-foreground'}>{(evidenceRanking.conflict_rate * 100).toFixed(0)}%</strong></span>
                                )}
                              </div>
                              <div className="divide-y divide-border/50">
                                {/* Top Supporting Evidence */}
                                {evidenceRanking.top_supporting_evidence?.map((ev: any, ei: number) => (
                                  <div key={`top-${ei}`} className="flex items-start gap-3 px-4 py-2.5 hover:bg-muted/20 transition-colors">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                                    <div className="flex-1 min-w-0">
                                      <div className="flex items-center gap-2 mb-0.5">
                                        <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 px-1 rounded">强证据</span>
                                        <span className="text-[10px] text-muted-foreground">{ev.source_document}</span>
                                        <code className="text-[10px] font-mono text-muted-foreground ml-auto">{ev.related_code}</code>
                                      </div>
                                      <p className="text-[11px] text-foreground leading-relaxed line-clamp-2">&ldquo;{ev.text}&rdquo;</p>
                                    </div>
                                  </div>
                                ))}
                                {/* Weak Evidence */}
                                {evidenceRanking.weak_evidence?.map((ev: any, ei: number) => (
                                  <div key={`weak-${ei}`} className="flex items-start gap-3 px-4 py-2.5 hover:bg-muted/20 transition-colors">
                                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 shrink-0" />
                                    <div className="flex-1 min-w-0">
                                      <div className="flex items-center gap-2 mb-0.5">
                                        <span className="text-[10px] font-medium text-amber-700 bg-amber-50 px-1 rounded">弱证据</span>
                                        <span className="text-[10px] text-muted-foreground">{ev.source_document}</span>
                                        <code className="text-[10px] font-mono text-muted-foreground ml-auto">{ev.related_code}</code>
                                      </div>
                                      <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">&ldquo;{ev.text}&rdquo;</p>
                                    </div>
                                  </div>
                                ))}
                                {/* Conflicting Evidence */}
                                {evidenceRanking.conflicting_evidence?.map((ev: any, ei: number) => (
                                  <div key={`conflict-${ei}`} className="flex items-start gap-3 px-4 py-2.5 hover:bg-muted/20 transition-colors">
                                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 mt-1.5 shrink-0" />
                                    <div className="flex-1 min-w-0">
                                      <div className="flex items-center gap-2 mb-0.5">
                                        <span className="text-[10px] font-medium text-red-700 bg-red-50 px-1 rounded">冲突</span>
                                        <span className="text-[10px] text-muted-foreground">{ev.source_document}</span>
                                        <code className="text-[10px] font-mono text-muted-foreground ml-auto">{ev.related_code}</code>
                                      </div>
                                      <p className="text-[11px] text-red-700 leading-relaxed line-clamp-2">&ldquo;{ev.text}&rdquo;</p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                              {/* Conflicts summary */}
                              {evidenceRanking.conflicts?.length > 0 && (
                                <div className="px-4 py-2 bg-red-50/30 border-t border-border">
                                  {evidenceRanking.conflicts.map((cf: any, ci: number) => (
                                    <p key={ci} className="text-[10px] text-red-700 leading-relaxed">
                                      ⚠ {cf.conflict_summary}
                                    </p>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {/* Main Procedure */}
                        {result.main_procedure?.code && (
                          <div>
                            <p className="text-xs font-medium text-muted-foreground mb-2">主手术</p>
                            <div className="bg-card border border-border rounded-xl p-5 space-y-3">
                              <div className="flex items-baseline gap-3 flex-wrap">
                                <code className="text-2xl font-bold text-secondary font-mono">{result.main_procedure.code}</code>
                                <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-emerald-50 text-emerald-700">
                                  置信度 {(result.main_procedure.confidence * 100).toFixed(0)}%
                                </span>
                                {/* Status */}
                                {result.main_procedure.judgment && (
                                  <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${
                                    result.main_procedure.judgment === 'supported' || result.main_procedure.judgment === 'confirmed'
                                      ? 'bg-emerald-50 text-emerald-700'
                                      : 'bg-amber-50 text-amber-700'
                                  }`}>
                                    {result.main_procedure.judgment === 'supported' || result.main_procedure.judgment === 'confirmed'
                                      ? '✓ 有证据'
                                      : '⚠ 需复核'}
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-foreground leading-relaxed">{result.main_procedure.name}</p>
                              {/* Evidence for main procedure */}
                              {result.main_procedure.evidence_ids && getEvidenceByIds(result.main_procedure.evidence_ids).length > 0 && (
                                <div>
                                  <p className="text-[10px] font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">证据依据</p>
                                  <div className="space-y-1.5">
                                    {getEvidenceByIds(result.main_procedure.evidence_ids).map((ev: ClinicalEvidence) => (
                                      <div key={ev.id} className="text-xs bg-muted/30 rounded-lg px-3 py-2 border-l-2 border-secondary/40">
                                        <p className="text-muted-foreground leading-relaxed">&ldquo;{ev.text}&rdquo;</p>
                                        <p className="text-[10px] text-muted-foreground mt-0.5">
                                          {ev.entity_type === 'procedure_evidence' ? '手术证据' : ev.entity_type}
                                          {ev.certainty ? ` · ${ev.certainty}` : ''}
                                        </p>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {/* All Candidate Codes with Evidence and Alternatives */}
                        {result.candidates?.length > 0 && (
                          <div>
                            <p className="text-xs font-medium text-muted-foreground mb-2">
                              全部候选编码 ({result.candidates.length})
                            </p>
                            <div className="space-y-2">
                              {result.candidates.map((c: any, i: number) => {
                                const candidateEvidence = getEvidenceByIds(c.evidence_ids || []);
                                const alternatives = (alternativesMap[c.finding] || []).filter(
                                  (alt: CodeCandidate) => alt.code !== c.code
                                );
                                return (
                                  <div key={c.id || i}
                                    className="bg-card border border-border rounded-xl p-4 hover:border-primary/20 transition-colors">
                                    {/* Code + Name + Status + Score */}
                                    <div className="flex items-start gap-3">
                                      <code className="text-sm font-semibold text-foreground font-mono w-28 shrink-0 mt-0.5">{c.code}</code>
                                      <div className="flex-1 min-w-0">
                                        <p className="text-sm text-foreground leading-snug">{c.name}</p>
                                        {c.finding && (
                                          <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{c.finding}</p>
                                        )}
                                      </div>
                                      <div className="flex items-center gap-2 shrink-0">
                                        {/* Status badge */}
                                        <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded-full ${
                                          c.status === 'supported' || c.status === 'confirmed'
                                            ? 'bg-emerald-50 text-emerald-700'
                                            : c.status === 'needs_review'
                                            ? 'bg-amber-50 text-amber-700'
                                            : c.status === 'rejected' || c.status === 'unsupported'
                                            ? 'bg-red-50 text-red-700'
                                            : 'bg-muted/50 text-muted-foreground'
                                        }`}>
                                          {c.status === 'supported' || c.status === 'confirmed'
                                            ? '✓ 有证据'
                                            : c.status === 'needs_review'
                                            ? '⚠ 需复核'
                                            : c.status === 'rejected'
                                            ? '✖ 已排除'
                                            : c.status === 'unsupported'
                                            ? '✖ 证据不足'
                                            : c.status || '○ 待处理'}
                                        </span>
                                        {/* Routing tier badge */}
                                        {(() => {
                                          const rd = routingMap[c.code];
                                          const cc = confidenceMap[c.code];
                                          const calibratedScore = cc?.calibrated_score ?? (rd?.calibrated_score ?? c.score);
                                          const tier = rd?.tier;
                                          const tierColor = tier === 'auto' ? 'bg-emerald-50 text-emerald-700'
                                            : tier === 'review' ? 'bg-amber-50 text-amber-700'
                                            : tier === 'escalate' ? 'bg-red-50 text-red-700'
                                            : '';
                                          const tierLabel = tier === 'auto' ? 'AUTO' : tier === 'review' ? 'REVIEW' : tier === 'escalate' ? 'ESCALATE' : '';
                                          const barColor = calibratedScore >= 0.8 ? 'bg-emerald-400'
                                            : calibratedScore >= 0.6 ? 'bg-amber-400'
                                            : 'bg-red-400';
                                          return (
                                            <>
                                              {tierLabel && (
                                                <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded-full ${tierColor}`}>
                                                  {tierLabel}
                                                </span>
                                              )}
                                              {/* Confidence bar */}
                                              <div className="flex items-center gap-1">
                                                <div className="w-14 h-1.5 rounded-full bg-muted overflow-hidden">
                                                  <div className={`h-full rounded-full ${barColor}`} style={{width: `${(calibratedScore * 100).toFixed(0)}%`}} />
                                                </div>
                                                <span className="text-[10px] text-muted-foreground w-8 text-right">{(calibratedScore * 100).toFixed(0)}%</span>
                                              </div>
                                            </>
                                          );
                                        })()}
                                      </div>
                                    </div>

                                    {/* Evidence quotes */}
                                    {candidateEvidence.length > 0 && (
                                      <div className="mt-3 pl-1">
                                        <p className="text-[10px] font-medium text-muted-foreground mb-1 uppercase tracking-wider">证据依据</p>
                                        <div className="space-y-1">
                                          {candidateEvidence.map((ev: ClinicalEvidence) => (
                                            <div key={ev.id} className="text-[11px] bg-muted/20 rounded-lg px-3 py-1.5 border-l-2 border-primary/30">
                                              <p className="text-muted-foreground leading-relaxed">&ldquo;{ev.text}&rdquo;</p>
                                              <p className="text-[10px] text-muted-foreground mt-0.5">
                                                {ev.certainty ? `${ev.certainty}` : ''}
                                                {ev.confidence > 0 ? ` · ${(ev.confidence * 100).toFixed(0)}%` : ''}
                                              </p>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Alternatives */}
                                    {alternatives.length > 0 && (
                                      <div className="mt-3 pl-1">
                                        <p className="text-[10px] font-medium text-muted-foreground mb-1 uppercase tracking-wider">替代编码</p>
                                        <div className="flex flex-wrap gap-1.5">
                                          {alternatives.map((alt: CodeCandidate) => (
                                            <span key={alt.id || alt.code}
                                              className="text-[10px] px-2 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 flex items-center gap-1">
                                              <code className="font-mono">{alt.code}</code>
                                              <span className="text-blue-300">|</span>
                                              <span className="truncate max-w-[120px]">{alt.name}</span>
                                              <span className="text-blue-400 ml-0.5">{(alt.score * 100).toFixed(0)}%</span>
                                            </span>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {/* Rule checks (if any) */}
                                    {c.rule_checks?.length > 0 && (
                                      <div className="mt-3 pl-1">
                                        <p className="text-[10px] font-medium text-muted-foreground mb-1 uppercase tracking-wider">规则检查</p>
                                        <div className="space-y-0.5">
                                          {c.rule_checks.map((r: any, ri: number) => (
                                            <div key={ri} className={`text-[10px] px-2 py-0.5 rounded ${
                                              r.status === 'pass' ? 'text-emerald-600 bg-emerald-50/50'
                                              : r.status === 'warn' ? 'text-amber-600 bg-amber-50/50'
                                              : 'text-red-600 bg-red-50/50'
                                            }`}>
                                              {r.status === 'pass' ? '✓' : r.status === 'warn' ? '⚠' : '✖'} {r.rule_name}: {r.message}
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* ===== JSON VIEW ===== */}
                    {outputView === 'json' && (
                      <div className="bg-muted/20 border border-border rounded-xl overflow-hidden">
                        <pre className="text-[11px] font-mono leading-relaxed p-4 overflow-x-auto max-h-[70vh] overflow-y-auto whitespace-pre">
                          {JSON.stringify(result, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* ===== CODE VIEW ===== */}
                    {outputView === 'code' && (
                      <div className="border border-border rounded-xl overflow-hidden" style={{ height: '20rem' }}>
                        <CodeSnippet
                          javascript={codeSnippetJS}
                          python={codeSnippetPython}
                          json={codeSnippetJSON}
                        />
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Event Inspector footer */}
          <div className="shrink-0 border-t border-border">
            <EventInspector events={events} creditsConsumed={totalCredits} />
          </div>
        </div>

            </div>
          </div>
        </div>

        {/* Separator */}
        <div className="h-full w-px bg-border/40" />

        {/* ===== RIGHT: 25% Settings/Code Panel ===== */}
        <div className="flex-[25_1_0px] bg-muted/10 min-w-0">
          <SettingsCodeTab
            defaultTab={rightPanel}
            settings={settingsContent}
            code={codeContent}
          />
        </div>
      </div>

      {/* ========== Include/Exclude Code Dialogs ========== */}
      {showIncludeDialog && (
        <CodeFilterDialog
          type="include"
          codes={includeCodes}
          onSave={setIncludeCodes}
          onClose={() => setShowIncludeDialog(false)}
        />
      )}
      {showExcludeDialog && (
        <CodeFilterDialog
          type="exclude"
          codes={excludeCodes}
          onSave={setExcludeCodes}
          onClose={() => setShowExcludeDialog(false)}
        />
      )}

      {/* ========== Add Expert Modal ========== */}
      {showAddExpert && (
        <AddExpertModal
          onClose={() => setShowAddExpert(false)}
          onCreated={() => {
            setShowAddExpert(false);
            setCustomExperts([...customExperts, { id: `custom-${Date.now()}`, name: '新专家', key: 'custom-expert' }]);
          }}
        />
      )}
    </div>
  );
}

// ---- Sub-component: Code Filter Dialog (Include/Exclude) ----
function CodeFilterDialog({ type, codes, onSave, onClose }: {
  type: 'include' | 'exclude';
  codes: string[];
  onSave: (codes: string[]) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState(codes.join('\n'));

  const handleSave = () => {
    const parsed = text.split('\n').map(s => s.trim()).filter(Boolean);
    onSave(parsed);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-background border border-border rounded-xl p-5 w-96 max-w-full shadow-xl" onClick={e => e.stopPropagation()}>
        <h3 className="text-sm font-semibold mb-3">{type === 'include' ? '包含编码' : '排除编码'}</h3>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="输入编码，每行一个..."
          rows={6}
          className="w-full text-xs border border-border rounded-lg px-3 py-2 bg-transparent resize-none focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <p className="text-[10px] text-muted-foreground mt-1">每行输入一个编码，或粘贴逗号分隔的编码。</p>
        <div className="flex justify-end gap-2 mt-3">
          <button onClick={onClose}
            className="text-xs h-7 px-3 rounded border border-border hover:bg-accent transition-colors">
            取消
          </button>
          <button onClick={handleSave}
            className="text-xs h-7 px-3 rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors">
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
