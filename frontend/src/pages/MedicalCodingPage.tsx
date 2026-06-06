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
  const [showGuideDismissed, setShowGuideDismissed] = useState(false);
  const [guideStep, setGuideStep] = useState(0);
  const [selectedAgent, setSelectedAgent] = useState('medical-coding-agent-1.0.0');
  const [availableAgents, setAvailableAgents] = useState<{agent_ref:string;name:string}[]>([]);
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
    // Load available coding agents
    runtimeApi.listAgents('certified').then(d => {
      const coding = (d.agents||[]).filter((a:any) => a.category === 'medical-coding' || a.category === '编码');
      setAvailableAgents(coding.length ? coding : d.agents||[]);
      if (coding.length > 0) setSelectedAgent(coding[0].agent_ref);
    }).catch(() => {});
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
        const data = await runtimeApi.runAgent(selectedAgent, text);
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
      {/* Coding systems */}
      <div>
        <label className="text-xs font-medium text-foreground block mb-2">Coding systems</label>
        <div className="relative">
          <button onClick={() => setShowSystemMenu(!showSystemMenu)}
            className="w-full flex items-center gap-2 text-xs border border-border rounded-lg px-3 py-2 bg-transparent hover:border-primary/30 transition-colors">
            {selectedSystems.map(sys => {
              const info = codingSystems.find(cs => cs.code_system === sys);
              return (
                <span key={sys} className="px-2 py-0.5 rounded-md bg-muted text-muted-foreground flex items-center gap-1">
                  {info?.name || sys}
                  <button onClick={(e) => { e.stopPropagation(); toggleSystem(sys); }} className="hover:text-foreground">&times;</button>
                </span>
              );
            })}
          </button>
          {showSystemMenu && (
            <div className="absolute top-full mt-1 left-0 right-0 bg-popover border border-border rounded-lg shadow-lg z-50 max-h-56 overflow-y-auto py-1">
              {codingSystems.map((sys) => (
                <label key={sys.code_system} className={"flex items-center gap-2 px-3 py-1.5 text-xs cursor-pointer hover:bg-accent " + (selectedSystems.includes(sys.code_system) ? 'bg-primary/5' : '')}>
                  <input type="checkbox" checked={selectedSystems.includes(sys.code_system)} onChange={() => toggleSystem(sys.code_system)} className="accent-primary shrink-0" />
                  <span>{sys.name}</span>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Filter codes */}
      <div>
        <label className="text-xs font-medium text-foreground block mb-2">Filter codes</label>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Include</span>
            <button onClick={() => setShowIncludeDialog(true)} className="text-xs text-primary hover:underline">Add codes</button>
          </div>
          {includeCodes.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {includeCodes.map((code, i) => (
                <span key={i} className="text-[11px] px-2 py-0.5 rounded-md bg-muted flex items-center gap-1">
                  {code}
                  <button onClick={() => setIncludeCodes(includeCodes.filter((_, j) => j !== i))} className="hover:text-foreground">&times;</button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-center justify-between mt-3">
            <span className="text-xs text-muted-foreground">Exclude</span>
            <button onClick={() => setShowExcludeDialog(true)} className="text-xs text-primary hover:underline">Add codes</button>
          </div>
          {excludeCodes.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {excludeCodes.map((code, i) => (
                <span key={i} className="text-[11px] px-2 py-0.5 rounded-md bg-muted flex items-center gap-1">
                  {code}
                  <button onClick={() => setExcludeCodes(excludeCodes.filter((_, j) => j !== i))} className="hover:text-foreground">&times;</button>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Expand switch */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-foreground">Expand</span>
        <button onClick={() => setExpandResults(!expandResults)}
          className={"relative w-9 h-5 rounded-full transition-colors " + (expandResults ? 'bg-primary' : 'bg-gray-300')}>
          <span className={"absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform " + (expandResults ? 'translate-x-4' : 'translate-x-0.5')} />
        </button>
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
      <div className="flex-1 flex min-h-0">
        {/* ===== LEFT: Input + Event Inspector ===== */}
        <div className="flex-1 p-4 min-w-0 flex flex-col">
          {/* Action bar: Predict + Samples + Clear + Copy */}
          <div className="flex items-center gap-2 mb-3">
            <button onClick={handlePredict} disabled={!hasText || loading}
              className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-30 transition-all flex items-center gap-1.5">
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              {loading ? 'Analyzing...' : 'Predict codes'}
            </button>
            <button onClick={() => setShowSampleMenu(!showSampleMenu)}
              className="px-3 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors flex items-center gap-1">
              <BookOpen size={14} /> Samples
            </button>
            <button onClick={() => setInput('')} disabled={!input}
              className="px-3 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-30">
              Clear input
            </button>
            <button onClick={() => { navigator.clipboard.writeText(input); }} disabled={!input}
              className="px-3 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-30">
              Copy input
            </button>
            {executionModeLabel && (
              <span className={"ml-auto text-xs " + (executionModeLabel.includes('Processing') ? 'text-blue-600' : executionModeLabel.includes('Done') ? 'text-green-600' : 'text-muted-foreground')}>
                {executionModeLabel}
              </span>
            )}
          </div>

          {/* Textarea with guided demo */}
          <div className="flex-1 relative bg-background rounded-xl shadow-sm ring-1 ring-border/20">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Enter clinical text…"
              rows={14}
              className="w-full h-full text-sm leading-relaxed border-0 p-6 bg-transparent focus:outline-none placeholder:text-muted-foreground/30 resize-none text-foreground"
            />
            {/* Guided demo overlay */}
            {!input && !showGuideDismissed && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/95 rounded-xl z-10 px-6">
                <button onClick={() => setShowGuideDismissed(true)} className="absolute top-4 right-4 text-xs text-muted-foreground hover:text-foreground">Dismiss guided demo</button>
                <p className="text-sm text-muted-foreground mb-6 text-center max-w-lg">Medical Coding converts unstructured clinical contexts (e.g., encounter notes, discharge summaries, transcripts) into structured medical codes. Select a sample to continue:</p>
                <div className="flex gap-3 mb-6">
                  {samples.slice(0, 3).map((s: any, i: number) => (
                    <button key={i} onClick={() => { setGuideStep(i); setInput(s.text); }}
                      className={"px-5 py-4 rounded-xl border-2 text-left transition-all max-w-[240px] " + (guideStep === i ? 'border-primary bg-primary/5' : 'border-border/50 hover:border-primary/30')}>
                      <p className="text-sm font-semibold text-foreground">{s.label}</p>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-3">{s.text.slice(0, 120)}...</p>
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setGuideStep(Math.max(0, guideStep-1))} disabled={guideStep===0}
                    className="px-4 py-2 text-sm border border-border rounded-lg disabled:opacity-30 hover:bg-accent transition-colors">Back</button>
                  <button onClick={() => { if(guideStep<2) setGuideStep(guideStep+1); }}
                    className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors">{guideStep<2 ? 'Next' : 'Use this sample'}</button>
                </div>
              </div>
            )}
          </div>

          {/* Event Inspector */}
          <div className="mt-3">
            <EventInspector events={events} creditsConsumed={totalCredits} />
          </div>
        </div>

        {/* Separator */}
        <div className="h-full w-px bg-border/40" />

        {/* ===== RIGHT: Settings | Code Panel ===== */}
        <div className="w-80 bg-muted/10 flex flex-col">
          <SettingsCodeTab
            defaultTab={rightPanel}
            settings={settingsContent}
            code={codeContent}
          />
        </div>
      </div>

      {showAddExpert && <AddExpertModal onClose={() => setShowAddExpert(false)} onCreated={() => { setShowAddExpert(false); }} />}
    </div>
  );
}
