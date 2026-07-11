// iCoDer Medical Coding - Corti Console 1:1 visual replica
// All UI text is i18n-driven: zh-CN ↔ en-US
// G001 refactor (2026-07-09): Default flow switched from A2A MedCodER 5-stage
// pipeline to Corti-like Fast Coding Runtime via /api/v1/coding/predict.
// MedCodER retained as Deep Evidence mode (mode=medcoder_deep).
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAppStore, useCostStore } from '../store';
import { useT } from '../i18n';
import { codingApi } from '../services/api';
import type { CodingPredictResult, CodingMode, CodingResultCode } from '../services/api';
import type { RuntimeRunResult, CodingIssue } from '../types/runtime';
import type { ExtractedDiagnosis, CandidateCode } from '../types/runtime';
import { HighlightedTextarea } from '../components/medical-coding/HighlightedTextarea';
import type { EvidenceSpanLike } from '../components/medical-coding/EvidenceHighlighter';
import { DiagnosisCard } from '../components/medical-coding/DiagnosisCard';
import {
  X, Sparkles, Loader2, Plus, ChevronRight, ChevronLeft,
  Eraser, Copy, BookText, Info, RotateCcw,
  FileText, ChevronDown, Check, SlidersHorizontal, Activity,
  AlertTriangle, Zap, FileSearch, Clipboard,
} from 'lucide-react';
import CodeSnippet from '../components/common/CodeSnippet';

type RightTab = 'settings' | 'code';

const MEDICAL_CODING_AGENT_ID = 'medical-coding-agent';

const SAMPLE_TEXTS = {
  admission: `入院记录
患者：张三，男，65岁，住院号：20260512
主诉：反复胸闷、心悸3年，加重伴夜间呼吸困难1周
现病史：患者3年前无明显诱因出现胸闷、心悸，活动后明显，休息后可缓解。曾于外院诊断为"冠心病"，长期口服阿司匹林、阿托伐他汀。近1周症状加重，伴夜间阵发性呼吸困难，需高枕卧位，遂来我院就诊。
既往史：高血压病史10年，最高160/100mmHg，口服氨氯地平5mg qd。2型糖尿病史5年，口服二甲双胍0.5g tid。否认肝炎、结核等传染病史，否认手术外伤史，否认药物过敏史。
体格检查：T 36.5°C，P 78次/分，R 18次/分，BP 138/86mmHg。神清，精神可。双肺呼吸音清，未闻及干湿啰音。心率78次/分，律齐，各瓣膜听诊区未闻及病理性杂音。腹软，无压痛及反跳痛。双下肢无水肿。
辅助检查：心电图示V4-V6导联ST段下移0.1mV。冠脉造影示LAD中段狭窄75%。
初步诊断：
1. 冠状动脉粥样硬化性心脏病 不稳定型心绞痛
2. 高血压病2级（很高危）
3. 2型糖尿病`,
  discharge: `出院小结
入院日期：2026-05-01
出院日期：2026-05-10
住院天数：9天
入院情况：患者因"反复胸闷、心悸3年，加重1周"入院。既往高血压病、2型糖尿病病史。
诊疗经过：入院后完善相关检查，冠脉造影示LAD中段狭窄75%，于2026-05-05在导管室行PCI术，于LAD中段植入药物洗脱支架1枚，术顺。术后予双联抗血小板（阿司匹林+氯吡格雷）、调脂稳斑（阿托伐他汀）、降压降糖等治疗，患者症状明显缓解，未再发胸痛、夜间呼吸困难。
出院诊断：
1. 冠状动脉粥样硬化性心脏病 不稳定型心绞痛 PCI术后
2. 高血压病2级（很高危）
3. 2型糖尿病
出院医嘱：
1. 低盐低脂糖尿病饮食，戒烟限酒
2. 规律服药：阿司匹林100mg qd，氯吡格雷75mg qd，阿托伐他汀20mg qn，氨氯地平5mg qd，二甲双胍0.5g tid
3. 定期心内科门诊随访，1月后复查心电图、血脂、血糖
4. 不适随诊`,
  progress: `病程记录
日期：2026-05-05 16:30  术后第1天
S（主观）：患者PCI术后6小时，自诉胸痛明显缓解，无新发胸闷、心悸。精神、食欲可，睡眠一般。
O（客观）：T 36.4°C，P 72次/分，R 18次/分，BP 128/76mmHg。双肺呼吸音清。心率72次/分，律齐。穿刺部位（右侧桡动脉）敷料干燥，无渗血渗液，周围无血肿。双下肢无水肿。
A（评估）：冠心病 PCI术后，病情稳定，症状改善，今日复查心电图未见新发缺血。
P（计划）：
1. 继续双联抗血小板治疗
2. 监测生命体征，注意穿刺部位出血
3. 指导患者康复活动
4. 明日复查心电图、心肌酶谱、血脂
记录医师：王主治`,
  operation: `手术记录
手术名称：经皮冠状动脉支架植入术（PCI）
手术日期：2026-05-05
麻醉方式：局麻
术者：李主任 助手：张主治、王住院
手术经过：患者平卧位，常规消毒铺巾。Seldinger法穿刺右侧桡动脉，置入6F鞘管。沿导丝送入指引导管至左冠状动脉口，多体位造影示LAD中段狭窄约75%，余血管未见明显狭窄。BMW导丝通过狭窄段至LAD远端，沿导丝送入2.5×18mm药物洗脱支架至狭窄处，12atm扩张释放，支架贴壁良好，无残余狭窄，TIMI血流3级。撤出导管，桡动脉压迫器压迫止血。
术中所见：LAD中段狭窄75%
术中出血：约10ml
标本送检：无
术后处理：转CCU监护，持续心电、血压、血氧监测。`,
  outpatient: `门诊病历
就诊日期：2026-05-15
主诉：咳嗽、咳痰3天
现病史：3天前受凉后出现咳嗽，咳黄色黏痰，量中等，易咳出。无发热，无胸闷、气促，无咯血，无胸痛。自行口服"止咳糖浆"症状无明显缓解，遂来院就诊。发病以来精神、食欲可，睡眠一般，大小便正常。
查体：T 36.8°C，P 82次/分，R 18次/分，BP 122/78mmHg。一般情况可，口唇无紫绀。咽部充血，扁桃体不大。双肺呼吸音粗，未闻及干湿啰音。心率82次/分，律齐。腹软，无压痛及反跳痛。
辅助检查：血常规示WBC 11.2×10⁹/L，N 78%，L 15%。
诊断：急性支气管炎
处理意见：
1. 头孢呋辛酯 0.25g bid ×5天
2. 氨溴索 30mg tid ×5天
3. 多饮水，注意休息
4. 3天后复诊，不适随诊`,
  consultation: `会诊记录
申请科室：骨科  会诊科室：心血管内科
会诊日期：2026-05-18
会诊目的：患者拟行腰椎手术，既往冠心病史，请评估手术风险并指导围术期管理。
病史摘要：患者，男，68岁，因"腰痛伴双下肢麻木3月"入院，诊断腰椎间盘突出症（L4/5、L5/S1），拟于2026-05-20行L4/5椎间盘髓核摘除术+椎间融合术。既往冠心病史3年，3年前因急性前壁心肌梗死于LAD植入支架1枚，长期口服阿司匹林+氯吡格雷双抗治疗。目前无心绞痛发作，日常活动耐量可（可爬3层楼）。
会诊意见：
1. 患者冠心病 PCI术后，心功能I级（NYHA），目前病情稳定，可耐受手术。
2. 围术期管理建议：
   - 术前停用氯吡格雷5天，阿司匹林可继续
   - 改用低分子肝素桥接抗凝
   - 术中持续心电监护，备好硝酸甘油
   - 术后24小时恢复双抗治疗
3. 建议术中请心内科医生在场监护。
4. 术后密切监测心肌酶、心电图。

会诊医师：刘主任医师 心内科`,
};

function fillTmpl(tmpl: string, vars: Record<string, string | number>): string {
  return tmpl.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''));
}

export default function MedicalCodingPage() {
  const t = useT();
  const { setProcessing, setError } = useAppStore();
  const addCost = useCostStore(s => s.addCost);
  const liveCost = useCostStore(s => s.liveCost);

  // ── Right panel ──
  const [rightTab, setRightTab] = useState<RightTab>('settings');

  // ── Phase 3-F: Config drawer + Event Inspector drawer (Corti-style) ──
  const [configOpen, setConfigOpen] = useState(false);
  const [eventInspectorOpen, setEventInspectorOpen] = useState(false);

  // ── Input state ──
  const [input, setInput] = useState('');
  const [result, setResult] = useState<RuntimeRunResult | CodingPredictResult | any>(null);
  const [loading, setLoading] = useState(false);

  // ── G001 refactor: coding mode (corti_like_fast default, medcoder_deep for advanced) ──
  const [codingMode, setCodingMode] = useState<CodingMode>('corti_like_fast');

  // ── Real-time char + cost estimate (live, not gated on Predict) ──
  // TODO: replace 0.00001 with real pricing once /api/v2/tools/coding/pricing lands.
  const charCount = input.length;
  const costEstimate = (charCount * 0.00001).toFixed(6);

  // ── Evidence highlight focus (which code row is currently clicked) ──
  const [focusedSpanIndex, setFocusedSpanIndex] = useState<number | null>(null);

  // ── Sample dropdown (top header "Samples" button) ──
  const [sampleMenuOpen, setSampleMenuOpen] = useState(false);

  // ── Inline templates (Corti-style 4-card layout) ──

  // ── Coding systems ──
  const [codingSystems, setCodingSystems] = useState<{code_system:string;name:string;is_default:boolean}[]>([]);
  const [selectedSystems, setSelectedSystems] = useState<string[]>([]);

  // ── Filter codes ──
  const [includeCodes, setIncludeCodes] = useState<string[]>([]);
  const [excludeCodes, setExcludeCodes] = useState<string[]>([]);
  const [addCodeDialog, setAddCodeDialog] = useState<{show:boolean; target:'include'|'exclude'}>({show:false, target:'include'});
  const [addCodeVal, setAddCodeVal] = useState('');

  // ── Expand & threshold ──
  const [expandResults, setExpandResults] = useState(false);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.6);

  // ── Event Inspector ──
  const [events, setEvents] = useState<{ts:string; msg:string; type:'info'|'success'|'error'}[]>([]);
  const addEvent = useCallback((msg: string, type: 'info'|'success'|'error' = 'info') => {
    const ts = new Date().toLocaleTimeString('en-US', { hour12: false });
    setEvents(prev => [...prev.slice(-50), { ts, msg, type }]);
  }, []);

  // ── 6 Chinese medical document types (used by BOTH SampleMenu and Guide wizard) ──
  const samples = useMemo(() => [
    { key: 'admission' as const, title: t.admissionRecord, text: SAMPLE_TEXTS.admission },
    { key: 'discharge' as const, title: t.dischargeSummary, text: SAMPLE_TEXTS.discharge },
    { key: 'progress' as const, title: t.progressNote, text: SAMPLE_TEXTS.progress },
    { key: 'operation' as const, title: t.operationRecord, text: SAMPLE_TEXTS.operation },
    { key: 'outpatient' as const, title: t.outpatientRecord, text: SAMPLE_TEXTS.outpatient },
    { key: 'consultation' as const, title: t.consultationRecord, text: SAMPLE_TEXTS.consultation },
  ], [t]);

  // ── Derived: short chip label (avoid crowding with long Chinese names + year) ──
  const shortSystemLabel = (sys: string) => {
    const info = codingSystems.find(cs => cs.code_system === sys);
    const name = info?.name || sys;
    // Strip year suffix and version noise; keep the meaningful short form
    return name.replace(/\s*\(20\d{2}.*?\)\s*/g, '').replace(/\s*国标版\s*/g, '').replace(/\s*国科版\s*/g, '').trim() || sys;
  };

  // ── Load coding systems ──
  useEffect(() => {
    // code-tables endpoint deleted in Phase 2.1-B Step 1; coding systems now hardcoded
    const systems = [
      { code_system: 'icd10cn', name: 'ICD-10-CN', is_default: true },
      { code_system: 'icd9cm3', name: 'ICD-9-CM-3', is_default: false },
    ];
    setCodingSystems(systems);
    setSelectedSystems([systems[0].code_system]);
  }, []);

  // ── Inline templates (Corti-style 4-card layout) ──
  const loadSampleAndRun = (sampleKey: typeof samples[number]['key']) => {
    const sample = samples.find(s => s.key === sampleKey);
    if (!sample) return;
    setInput(sample.text);
    addEvent(t.sampleLoaded, 'info');
    setTimeout(() => handlePredict(sample.text), 0);
  };
  const loadSampleOnly = (sampleKey: typeof samples[number]['key']) => {
    const sample = samples.find(s => s.key === sampleKey);
    if (!sample) return;
    setInput(sample.text);
    addEvent(t.sampleLoaded, 'info');
  };

  // ── Predict ──
  // G001 refactor: Default calls /api/v1/coding/predict (Corti-like Fast Coding).
  // mode=corti_like_fast (default) → single LLM call, target <15s
  // mode=medcoder_deep             → 5-stage MedCodER pipeline, 30-60s+
  const handlePredict = async (textOverride?: string) => {
    const text = textOverride || input;
    if (!text.trim() || loading) return;
    if (!textOverride) setInput(text);
    setLoading(true);
    setProcessing(true);
    setError(null);
    setResult(null);
    setUserOverrides({});
    setEvents([]);
    addEvent(t.startingPrediction, 'info');
    addEvent(`mode=${codingMode}`, 'info');

    try {
      const startTime = Date.now();
      const response = await codingApi.predict(text, codingMode, {
        coding_system: selectedSystems[0] || 'icd10cn',
        include_evidence: true,
        include_trace: true,
      });
      const elapsed = Date.now() - startTime;
      const data: CodingPredictResult = response.data;
      setResult(data);
      if (data.latency_ms) addCost((data.latency_ms / 1000) * 0.02);

      // Emit trace events from the runtime (7-step Fast / 5-stage+2 Deep)
      if (data.trace_events?.length) {
        data.trace_events.forEach((ev) => {
          const prefix = `[${ev.step}]`;
          const meta = ev.metadata && Object.keys(ev.metadata).length
            ? ` ${JSON.stringify(ev.metadata).slice(0, 80)}`
            : '';
          addEvent(`${prefix} ${ev.status}${meta}`, ev.status === 'ok' ? 'info' : 'error');
        });
      }

      if (data.error) {
        // Runtime reported an error — show friendly message + retry path
        setError(data.summary || t.processingFailed);
        addEvent(`${t.failedPrefix}: ${data.error_reason}`, 'error');
      } else {
        addEvent(`${t.completedPrefix} ${data.latency_ms || elapsed}ms (${data.runtime_mode})`, 'success');
      }
    } catch (err: any) {
      // axios error — distinguish timeout from other errors
      const isTimeout = err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '');
      const detail = err.response?.data?.detail || err.message || t.processingFailed;
      const msg = isTimeout
        ? (codingMode === 'corti_like_fast'
            ? 'Fast Coding 超时,请重试或切换至 Deep Evidence 模式。'
            : 'Deep Evidence 超时,请切换至 Fast Coding 模式或缩减输入后重试。')
        : (typeof detail === 'string' ? detail : JSON.stringify(detail).slice(0, 200));
      setError(msg);
      addEvent(`${t.failedPrefix}: ${msg}`, 'error');
    } finally {
      setLoading(false);
      setProcessing(false);
    }
  };

  // ── Retry (re-run with same input + mode, or switch mode first) ──
  const handleRetry = (switchToFast?: boolean) => {
    if (switchToFast && codingMode !== 'corti_like_fast') {
      setCodingMode('corti_like_fast');
      setTimeout(() => handlePredict(), 0);
    } else {
      handlePredict();
    }
  };

  // ── Sample selection (used by SampleMenu and Guide) ──
  const selectSample = (sampleText: string) => {
    setInput(sampleText);
    addEvent(t.sampleLoaded, 'info');
  };

  // ── Coding system chip ──
  const removeSystem = (sys: string) => {
    setSelectedSystems(prev => prev.filter(s => s !== sys));
  };
  const addSystem = (sys: string) => {
    if (!selectedSystems.includes(sys)) setSelectedSystems(prev => [...prev, sys]);
  };

  // ── Add include/exclude code ──
  const confirmAddCode = () => {
    if (!addCodeVal.trim()) return;
    if (addCodeDialog.target === 'include') setIncludeCodes(prev => [...prev, addCodeVal.trim()]);
    else setExcludeCodes(prev => [...prev, addCodeVal.trim()]);
    setAddCodeVal('');
    setAddCodeDialog({show:false, target:'include'});
  };

  // ── Derived ──
  // G001 refactor: result can be either:
  //   - CodingPredictResult (new shape from /api/v1/coding/predict) with flat `codes` array
  //   - RuntimeRunResult (legacy A2A shape) with primary_diagnosis/secondary_diagnoses/procedures
  // Detect shape and project uniformly.
  const isCodingPredictResult = (result as any)?.runtime_mode !== undefined;
  const codingResult: CodingPredictResult | null = isCodingPredictResult ? (result as CodingPredictResult) : null;
  const codingResultCodes: CodingResultCode[] = codingResult?.codes || [];

  const primaryDiag = codingResult
    ? codingResultCodes.find(c => c.type === 'primary_diagnosis')
    : (result as RuntimeRunResult)?.primary_diagnosis;
  const secondaryDiags = codingResult
    ? codingResultCodes.filter(c => c.type === 'secondary_diagnosis' || c.type === 'complication')
    : (result as RuntimeRunResult)?.secondary_diagnoses || [];
  const procedures = codingResult
    ? codingResultCodes.filter(c => c.type === 'procedure' || c.type === 'external_cause' || c.type === 'aftercare')
    : (result as RuntimeRunResult)?.procedures || [];
  const isMedcoderMode = codingResult
    ? codingResult.runtime_mode === 'medcoder_deep'
    : (result as RuntimeRunResult)?.mode === 'medcoder';
  const extractedDiagnoses: ExtractedDiagnosis[] = codingResult
    ? ((codingResult.raw_schema as any)?.extracted_diagnoses as ExtractedDiagnosis[]) || []
    : (result as RuntimeRunResult)?.extracted_diagnoses || [];
  // Map dx index → user-selected code (override)
  const [userOverrides, setUserOverrides] = useState<Record<number, string>>({});
  const allCodes = codingResult
    ? [...codingResultCodes]
    : [primaryDiag, ...secondaryDiags, ...procedures].filter(Boolean).slice().sort((a: any, b: any) => (b.confidence ?? 0) - (a.confidence ?? 0));
  const hasText = input.trim().length > 0;
  const availableSystems = codingSystems.filter(cs => !selectedSystems.includes(cs.code_system));
  const snippetSystems = selectedSystems.length ? selectedSystems : ['icd10-cn'];

  // ── Code snippets (live) ──
  const snippetInput = input.slice(0, 80) + (input.length > 80 ? '...' : '');
  const codeSnippetJS = useMemo(() => {
    const lines = [
      `import { iCoDerClient } from "@icoder/sdk";`,
      ``,
      `const client = new iCoDerClient({`,
      `  baseURL: "http://localhost:8000",`,
      `  accessToken: "<your-access-token>",`,
      `});`,
      ``,
      `const response = await client.codes.predict({`,
      `  context: [{ type: "text", text: \`${snippetInput || t.enterClinicalText}\` }],`,
      `  system: [${snippetSystems.map(s => `"${s}"`).join(', ')}],`,
    ];
    if (includeCodes.length) lines.push(`  include_codes: [${includeCodes.map(c => `"${c}"`).join(', ')}],`);
    if (excludeCodes.length) lines.push(`  exclude_codes: [${excludeCodes.map(c => `"${c}"`).join(', ')}],`);
    lines.push(`  expand: ${expandResults},`);
    lines.push(`  confidence_threshold: ${confidenceThreshold},`);
    lines.push(`});`);
    return lines.join('\n');
  }, [snippetInput, snippetSystems, includeCodes, excludeCodes, expandResults, confidenceThreshold, t]);
  const codeSnippetJSON = useMemo(() => JSON.stringify({
    method: 'codes.predict',
    params: {
      context: [{ type: 'text', text: snippetInput || t.enterClinicalText }],
      system: snippetSystems,
      include_codes: includeCodes.length ? includeCodes : undefined,
      exclude_codes: excludeCodes.length ? excludeCodes : undefined,
      expand: expandResults,
      confidence_threshold: confidenceThreshold,
    },
  }, null, 2), [snippetInput, snippetSystems, includeCodes, excludeCodes, expandResults, confidenceThreshold, t]);

  // ── Render ──
  return (
    <div className="flex flex-col h-full bg-background">
      {/* ==================== HEADER (breadcrumb only - cost/Docs now in global header) ==================== */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-border/20 shrink-0 text-xs">
        <Link to="/ai-studio/overview" className="text-muted-foreground hover:text-foreground transition-colors">{t.aiStudio}</Link>
        <ChevronRight size={12} className="text-muted-foreground/50" />
        <span className="text-foreground font-medium truncate">{t.medicalCodingBreadcrumb}</span>
      </div>

      {/* ==================== Phase 3-A Section D - MVP + AI-assisted banners (Corti red lines) ==================== */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-amber-200/40 bg-amber-50/60 shrink-0 text-[11px]">
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-medium" data-testid="mvp-banner">
          <Info size={10} /> {t.mvpBanner}
        </span>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium" data-testid="ai-assisted-banner">
          <Check size={10} /> {t.aiAssistedBanner}
        </span>
      </div>

      {/* ==================== ACTION BAR - Corti-style: Coding systems + Predict + Config ==================== */}
      <div className="flex shrink-0 items-center border-b bg-muted px-4 py-3 gap-3">
        {/* 左: Coding systems label + info tooltip + combobox chips */}
        <span className="text-sm font-medium text-foreground">{t.codingSystems}</span>
        <span title={t.codingSystemsInfo} className="cursor-help">
          <Info size={14} className="text-muted-foreground/50" />
        </span>
        <div className="flex items-center gap-2 flex-wrap">
          {selectedSystems.map(sys => (
            <span
              key={sys}
              data-testid={`coding-system-chip-${sys}`}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-border bg-background text-foreground"
            >
              {shortSystemLabel(sys)}
              <button
                onClick={() => removeSystem(sys)}
                className="text-muted-foreground hover:text-foreground"
                aria-label={`Remove ${sys}`}
              >
                <X size={10} />
              </button>
            </span>
          ))}
          {availableSystems.length > 0 && (
            <button
              onClick={() => addSystem(availableSystems[0].code_system)}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md border border-dashed border-border bg-background text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
            >
              <Plus size={10} /> {t.addSystem}
            </button>
          )}
        </div>
        {/* 右: Mode indicator + Predict codes + Config */}
        <div className="ml-auto flex items-center gap-2">
          {codingMode === 'corti_like_fast' ? (
            <span data-testid="active-mode-fast" className="inline-flex items-center gap-1 px-2 py-1 text-[10px] rounded-md bg-emerald-50 text-emerald-700 font-medium">
              <Zap size={10} /> Fast
            </span>
          ) : (
            <span data-testid="active-mode-deep" className="inline-flex items-center gap-1 px-2 py-1 text-[10px] rounded-md bg-violet-50 text-violet-700 font-medium">
              <FileSearch size={10} /> Deep
            </span>
          )}
          <button
            data-testid="predict-codes-btn"
            onClick={() => handlePredict()}
            disabled={!hasText || loading}
            className="px-4 py-1.5 rounded-lg border border-border bg-background text-foreground text-sm font-medium hover:bg-accent disabled:opacity-30 transition-all flex items-center gap-1.5"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {loading ? t.analyzing : t.predictCodes}
          </button>
          <button
            onClick={() => setConfigOpen(true)}
            data-testid="config-btn"
            className="px-3 py-1.5 rounded-lg border border-border bg-background text-foreground text-sm font-medium hover:bg-accent transition-all flex items-center gap-1.5"
          >
            <SlidersHorizontal size={14} />
            {t.config}
          </button>
        </div>
      </div>

      {/* ==================== MAIN 2-PANE (Corti-style: Input + Output) ==================== */}
      <div className={`flex-1 flex min-h-0 transition-all duration-200 ${configOpen ? 'mr-[400px]' : ''}`}>
        {/* ===== LEFT: Input + sub-toolbar + floating onboarding card ===== */}
        <div className="flex-1 flex flex-col min-w-0 border-r border-border/20">
          {/* Corti-style Input/Samples/Clear/Copy sub-toolbar */}
          <div className="flex items-center justify-between px-4 py-2">
            <span className="text-sm font-medium text-foreground">{t.inputLabel}</span>
            <div className="flex items-center gap-1">
              {/* "Samples" button - opens a simple dropdown menu */}
              <div className="relative">
                <button onClick={() => setSampleMenuOpen(o => !o)}
                  className={`px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground border border-border rounded-md flex items-center gap-1 ${sampleMenuOpen ? 'bg-accent' : ''}`}>
                  <BookText size={12} /> {t.samples} <ChevronDown size={10} />
                </button>
                {sampleMenuOpen && (
                  <>
                    {/* Backdrop to close on outside click */}
                    <div className="fixed inset-0 z-40" onClick={() => setSampleMenuOpen(false)} />
                    <div className="absolute right-0 top-full mt-1 w-64 bg-popover border border-border rounded-lg shadow-lg z-50 py-1">
                      {samples.map(s => (
                        <button key={s.key}
                          onClick={() => { selectSample(s.text); setSampleMenuOpen(false); }}
                          className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent transition-colors text-foreground">
                          {s.title}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
              <button onClick={() => setInput('')} disabled={!hasText}
                className="px-2 py-1 text-muted-foreground hover:text-foreground disabled:opacity-30" title={t.clearInput}>
                <Eraser size={14} />
              </button>
              <button onClick={() => navigator.clipboard?.writeText(input)} disabled={!hasText}
                className="px-2 py-1 text-muted-foreground hover:text-foreground disabled:opacity-30" title={t.copyInput}>
                <Copy size={14} />
              </button>
              {/* Live char + cost counter (updates per keystroke; not gated on Predict) */}
              <span
                className="ml-1 text-[11px] text-muted-foreground/70 font-mono tabular-nums"
                data-testid="char-counter"
                title="Live char + cost estimate (placeholder rate, see TODO in source)"
              >
                {fillTmpl(t.charCount, { n: charCount })} · {fillTmpl(t.costEstimate, { n: costEstimate })}
              </span>
            </div>
          </div>
          {/* textarea + floating onboarding card (Corti-style overlay) */}
          <div className="flex-1 relative min-h-0">
            <HighlightedTextarea
              value={input}
              onChange={setInput}
              spans={dataEvidences(result)}
              focusedSpanIndex={focusedSpanIndex}
              placeholder={t.enterClinicalText}
              className="h-full"
            />
            {/* Floating onboarding card - only shown when input is empty */}
            {!hasText && (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-end overflow-hidden">
                <div className="pointer-events-auto max-h-[calc(100%-4rem)] w-full overflow-y-auto p-4 pt-16">
                  <div className="overflow-hidden border border-t-0 bg-stone-50 shadow-sm rounded-b-lg dark:bg-stone-800">
                    <div className="flex flex-col gap-4 p-6">
                      {/* icon + Medical Coding title + description */}
                      <div className="flex gap-3 items-start">
                        <div className="w-8 h-8 rounded-md bg-primary/10 text-primary flex items-center justify-center shrink-0">
                          <Sparkles size={16} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-foreground">{t.medicalCoding}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{t.medicalCodingDesc}</p>
                        </div>
                      </div>
                      {/* Get started with + horizontal 4 sample buttons (Corti-style) */}
                      <div className="flex gap-3 items-start">
                        <p className="text-[11px] font-medium text-muted-foreground shrink-0 pt-1.5">{t.getStartedWith}</p>
                        <div className="flex flex-wrap gap-2">
                          {[
                            { key: 'admission' as const, label: t.hospitalMedicalRecord, run: false },
                            { key: 'outpatient' as const, label: t.gpTranscript, run: false },
                            { key: 'consultation' as const, label: t.orthopedicReferral, run: false },
                            { key: 'admission' as const, label: t.guidedDemo, run: true },
                          ].map((card) => (
                            <button
                              key={card.label}
                              onClick={() => card.run ? loadSampleAndRun(card.key) : loadSampleOnly(card.key)}
                              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md border border-border bg-background hover:border-primary/40 hover:bg-primary/5 transition-colors text-foreground"
                            >
                              <FileText size={12} className="text-muted-foreground" />
                              {card.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ===== RIGHT: Output (Corti-style w-[480px]) — hidden when config drawer open to avoid being covered ===== */}
        <div className={`w-[480px] shrink-0 flex flex-col ${configOpen ? 'hidden' : 'flex'}`}>
          <div className="px-4 py-3 border-b border-border/20 shrink-0">
            <span className="text-sm font-medium text-foreground">{t.outputLabel}</span>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {!result ? (
              <div className="h-full flex items-center justify-center">
                <p className="text-xs text-muted-foreground/60">{t.predictedCodesWillShow}</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* ===== G001 refactor: Runtime Info panel (Fast / Deep mode badge + latency + trace_id + summary) ===== */}
                {codingResult && (
                  <div className="rounded-md border border-border/30 bg-muted/30 p-3 space-y-2" data-testid="runtime-info-panel">
                    <div className="flex items-center gap-2 flex-wrap">
                      {codingResult.runtime_mode === 'corti_like_fast' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-medium" data-testid="mode-badge-fast">
                          <Zap size={10} /> Fast Coding
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 text-[10px] font-medium" data-testid="mode-badge-deep">
                          <FileSearch size={10} /> Deep Evidence
                        </span>
                      )}
                      <span className="text-[10px] text-muted-foreground font-mono">
                        {codingResult.latency_ms ? (codingResult.latency_ms / 1000).toFixed(2) : '?'}s
                      </span>
                      <span className="text-[10px] text-muted-foreground/60 font-mono">{codingResult.llm_provider || 'deepseek'}</span>
                      {codingResult.trace_id && (
                        <span className="text-[10px] text-muted-foreground/40 font-mono ml-auto" title={codingResult.trace_id}>
                          trace: {codingResult.trace_id.slice(0, 16)}…
                        </span>
                      )}
                    </div>
                    {codingResult.summary && (
                      <p className="text-xs text-foreground/80 leading-relaxed">{codingResult.summary}</p>
                    )}
                    {codingResult.error && (
                      <div className="rounded-md bg-amber-50 border border-amber-200/60 p-2 flex items-start gap-2">
                        <AlertTriangle size={12} className="text-amber-600 mt-0.5 shrink-0" />
                        <div className="flex-1">
                          <p className="text-[11px] text-amber-800">{codingResult.summary}</p>
                          <div className="flex gap-2 mt-1.5">
                            <button
                              onClick={() => handleRetry(false)}
                              className="text-[10px] px-2 py-0.5 rounded border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 transition-colors"
                              data-testid="retry-same-mode"
                            >
                              <RotateCcw size={10} className="inline mr-1" />重试
                            </button>
                            {codingMode !== 'corti_like_fast' && (
                              <button
                                onClick={() => handleRetry(true)}
                                className="text-[10px] px-2 py-0.5 rounded border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 transition-colors"
                                data-testid="retry-switch-fast"
                              >
                                <Zap size={10} className="inline mr-1" />切换 Fast Coding
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* ===== Copy JSON / Copy Markdown buttons (G001 §5.3) ===== */}
                {codingResult && codingResult.codes.length > 0 && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        navigator.clipboard?.writeText(JSON.stringify(codingResult, null, 2));
                        addEvent('Copied JSON', 'info');
                      }}
                      className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-border bg-background text-foreground hover:bg-accent transition-colors"
                      data-testid="copy-json-btn"
                    >
                      <Copy size={10} /> Copy JSON
                    </button>
                    <button
                      onClick={() => {
                        const md = codingResult.codes.map((c, i) =>
                          `### ${i + 1}. ${c.code} — ${c.display}\n` +
                          `- **Type**: ${c.type}\n` +
                          `- **Confidence**: ${(c.confidence * 100).toFixed(0)}%\n` +
                          `- **System**: ${c.system}\n` +
                          (c.evidence ? `- **Evidence**: ${c.evidence}\n` : '') +
                          (c.rationale ? `- **Rationale**: ${c.rationale}\n` : '') +
                          (c.warnings?.length ? `- **Warnings**: ${c.warnings.join('; ')}\n` : '')
                        ).join('\n');
                        navigator.clipboard?.writeText(`# Medical Coding Result\n\nRuntime: ${codingResult.runtime_mode} | Latency: ${codingResult.latency_ms}ms\n\n${md}`);
                        addEvent('Copied Markdown', 'info');
                      }}
                      className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-border bg-background text-foreground hover:bg-accent transition-colors"
                      data-testid="copy-markdown-btn"
                    >
                      <Clipboard size={10} /> Copy Markdown
                    </button>
                  </div>
                )}

                {primaryDiag?.code && (
                  <div>
                    <p className="text-[10px] font-semibold text-muted-foreground mb-1">{t.primaryDiagnosis}</p>
                    <div className="flex items-baseline gap-2">
                      <span className="text-lg font-bold font-mono text-foreground">{primaryDiag.code}</span>
                      <span className="text-xs text-muted-foreground">{(primaryDiag as any).display || (primaryDiag as any).description || ''}</span>
                    </div>
                  </div>
                )}
                {allCodes.length > 0 && (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border/30 text-muted-foreground">
                        <th className="pb-1.5 text-left font-medium">#</th>
                        <th className="pb-1.5 text-left font-medium">{t.tableCode}</th>
                        <th className="pb-1.5 text-left font-medium">{t.tableDescription}</th>
                        <th className="pb-1.5 text-right font-medium">{t.tableConfidence}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {allCodes.map((c:any, i:number) => (
                        <tr
                          key={i}
                          data-testid={`code-row-${i}`}
                          onClick={() => setFocusedSpanIndex(focusedSpanIndex === i ? null : i)}
                          className={`border-b border-border/10 cursor-pointer transition-colors ${focusedSpanIndex === i ? 'bg-primary/5' : 'hover:bg-muted/30'}`}
                          title="Click to highlight the evidence span in the input"
                        >
                          <td className="py-1.5 text-muted-foreground">{i + 1}</td>
                          <td className="py-1.5 font-mono font-medium">{c.code || ''}</td>
                          <td className="py-1.5 text-muted-foreground">{c.display || c.description || ''}</td>
                          <td className="py-1.5 text-right font-mono text-muted-foreground">
                            {c.confidence ? Math.round(c.confidence * 100) + '%' : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

                {/* ===== G001 refactor: per-code rationale + warnings + evidence + alternatives ===== */}
                {codingResult && codingResultCodes.length > 0 && focusedSpanIndex !== null && codingResultCodes[focusedSpanIndex] && (
                  <div className="rounded-md border border-primary/20 bg-primary/5 p-3 space-y-2" data-testid="code-detail-panel">
                    {(() => {
                      const c = codingResultCodes[focusedSpanIndex];
                      return (
                        <>
                          <div className="flex items-baseline gap-2">
                            <span className="text-base font-bold font-mono text-foreground">{c.code}</span>
                            <span className="text-xs text-muted-foreground">{c.display}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground ml-auto">{c.type}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-mono">{(c.confidence * 100).toFixed(0)}%</span>
                          </div>
                          {c.evidence && (
                            <div>
                              <p className="text-[10px] font-semibold text-muted-foreground mb-1">{t.evidence}</p>
                              <p className="text-xs text-foreground/80 italic bg-background/60 rounded px-2 py-1.5">"{c.evidence}"</p>
                            </div>
                          )}
                          {c.rationale && (
                            <div>
                              <p className="text-[10px] font-semibold text-muted-foreground mb-1">Rationale</p>
                              <p className="text-xs text-foreground/80 leading-relaxed">{c.rationale}</p>
                            </div>
                          )}
                          {c.warnings?.length > 0 && (
                            <div>
                              <p className="text-[10px] font-semibold text-amber-700 mb-1 flex items-center gap-1">
                                <AlertTriangle size={10} /> Warnings
                              </p>
                              <ul className="text-[11px] text-amber-800 list-disc list-inside space-y-0.5">
                                {c.warnings.map((w, i) => <li key={i}>{w}</li>)}
                              </ul>
                            </div>
                          )}
                          {c.alternatives?.length > 0 && (
                            <div>
                              <p className="text-[10px] font-semibold text-muted-foreground mb-1">Alternatives</p>
                              <div className="flex flex-wrap gap-1">
                                {c.alternatives.map((alt, i) => (
                                  <span key={i} className="text-[10px] px-1.5 py-0.5 rounded border border-border bg-background text-muted-foreground font-mono" title={alt.name}>
                                    {alt.code} <span className="text-muted-foreground/60">({alt.score.toFixed(2)})</span>
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </>
                      );
                    })()}
                  </div>
                )}

                {dataEvidences(result).length > 0 && (
                  <div>
                    <p className="text-[10px] font-semibold text-muted-foreground mb-1">{t.evidence}</p>
                    <div className="space-y-1">
                      {dataEvidences(result).map((span, i) => (
                        <div key={i} className="text-xs text-muted-foreground bg-primary/5 rounded px-2.5 py-1.5">“{span.text}”</div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Medical Coding Agent per-diagnosis cards (only when mode==='medcoder') */}
                {isMedcoderMode && (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-[10px] font-semibold text-muted-foreground">
                        {t.codingPipeline}
                      </p>
                      <span className="text-[10px] font-mono text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">
                        {t.extractedDiagnosesCount.replace('{{n}}', String(extractedDiagnoses.length))}
                      </span>
                    </div>
                    {extractedDiagnoses.length === 0 ? (
                      <div className="text-xs text-muted-foreground italic">
                        {t.noExtractedDiagnoses}
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {extractedDiagnoses.map((dx, i) => (
                          <DiagnosisCard
                            key={i}
                            diagnosis={dx}
                            index={i}
                            selectedCode={userOverrides[i]}
                            onSelectCode={(idx, c) => {
                              setUserOverrides((prev) => ({ ...prev, [idx]: c.code }));
                            }}
                            onOverride={(idx, code) => {
                              setUserOverrides((prev) => ({ ...prev, [idx]: code }));
                            }}
                          />
                        ))}
                      </div>
                    )}
                    {((result as RuntimeRunResult)?.structured as any)?.notes && (
                      <div className="mt-3 text-[11px] text-muted-foreground italic">
                        {t.pipelineNotes}: {((result as RuntimeRunResult)?.structured as any).notes}
                      </div>
                    )}
                  </div>
                )}

                {/* ==================== Phase 3-A Section D - Corti-style Review Summary (8-field output) ==================== */}
                {(() => {
                  const r = result as RuntimeRunResult;
                  // Project v1 → Corti-style display when v2 fields absent (Section E will populate v2)
                  const reviewConclusion = r?.review_conclusion
                    || (r?.human_review?.review_conclusion as string | undefined)
                    || (r?.issues_found && r.issues_found.length > 0 ? 'WARNING' : 'PASS');
                  const manualReview = r?.manual_review_required
                    ?? r?.human_review?.review_required
                    ?? (r?.issues_found?.some((i: CodingIssue) => i.severity === 'critical' || i.severity === 'high') ?? false);
                  const issues: CodingIssue[] = r?.corti_validation_summary?.issues_found || r?.issues_found || [];
                  const gaps = r?.documentation_gaps || [];
                  const uncodable = r?.uncodable_items || [];
                  const firedRules: string[] = r?.corti_validation_summary?.fired_rules
                    || (r?.trace_refs?.rule_fired as string[] | undefined)
                    || [];
                  const conclusionLabel = reviewConclusion === 'PASS' ? t.reviewConclusionPass
                    : reviewConclusion === 'WARNING' ? t.reviewConclusionWarning
                    : reviewConclusion === 'FAIL' ? t.reviewConclusionFail
                    : reviewConclusion;
                  const conclusionColor = reviewConclusion === 'PASS' ? 'bg-emerald-100 text-emerald-700'
                    : reviewConclusion === 'WARNING' ? 'bg-amber-100 text-amber-700'
                    : 'bg-rose-100 text-rose-700';

                  return (
                    <div data-testid="corti-review-summary" className="mt-4 rounded-lg border border-border/40 bg-muted/20 p-3 space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-[10px] font-semibold text-muted-foreground">
                          {t.reviewSummary}
                        </p>
                        <div className="flex items-center gap-1.5">
                          <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${conclusionColor}`} data-testid="review-conclusion-badge">
                            {t.reviewConclusion}: {conclusionLabel}
                          </span>
                          {manualReview && (
                            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-rose-100 text-rose-700" data-testid="manual-review-badge">
                              {t.manualReviewRequired}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Validation summary - issues found list */}
                      {issues.length > 0 && (
                        <div>
                          <p className="text-[10px] font-medium text-muted-foreground mb-1">{t.validationSummary} - {issues.length}</p>
                          <ul className="space-y-1">
                            {issues.map((iss: CodingIssue, i: number) => (
                              <li key={i} className="text-[11px] text-muted-foreground bg-background rounded px-2 py-1 border border-border/30">
                                <span className={`font-mono text-[10px] mr-1 ${iss.severity === 'critical' ? 'text-rose-600' : iss.severity === 'high' ? 'text-amber-600' : 'text-muted-foreground'}`}>
                                  [{iss.severity}]
                                </span>
                                {iss.code && <span className="font-mono text-[10px] mr-1">{iss.code}</span>}
                                {iss.message}
                                {iss.suggestion && <span className="block text-[10px] text-muted-foreground/70 italic mt-0.5">→ {iss.suggestion}</span>}
                              </li>
                            ))}
                          </ul>
                          {firedRules.length > 0 && (
                            <p className="text-[10px] text-muted-foreground mt-1">
                              {t.rulesFired}: <span className="font-mono">{firedRules.join(', ')}</span>
                            </p>
                          )}
                        </div>
                      )}

                      {/* Documentation gaps */}
                      <div>
                        <p className="text-[10px] font-medium text-muted-foreground mb-1">{t.documentationGaps}</p>
                        {gaps.length === 0 ? (
                          <p className="text-[11px] text-muted-foreground/60 italic">{t.noDocumentationGaps}</p>
                        ) : (
                          <ul className="space-y-1">
                            {gaps.map((g, i) => (
                              <li key={i} className="text-[11px] text-muted-foreground bg-background rounded px-2 py-1 border border-border/30">
                                <span className="font-mono text-[10px] mr-1 text-amber-600">[{g.gap_type}]</span>
                                {g.description}
                                {g.related_code && <span className="font-mono text-[10px] ml-1">→ {g.related_code}</span>}
                                {g.suggestion && <span className="block text-[10px] text-muted-foreground/70 italic mt-0.5">→ {g.suggestion}</span>}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>

                      {/* Uncodable items */}
                      <div>
                        <p className="text-[10px] font-medium text-muted-foreground mb-1">{t.uncodableItems}</p>
                        {uncodable.length === 0 ? (
                          <p className="text-[11px] text-muted-foreground/60 italic">{t.noUncodableItems}</p>
                        ) : (
                          <ul className="space-y-1">
                            {uncodable.map((u, i) => (
                              <li key={i} className="text-[11px] text-muted-foreground bg-background rounded px-2 py-1 border border-border/30">
                                <span className="font-mono text-[10px] mr-1 text-rose-600">[{u.item_type}]</span>
                                {u.text}
                                {u.reason && <span className="block text-[10px] text-muted-foreground/70 italic mt-0.5">→ {u.reason}</span>}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>

                      {/* Trace refs (collapsed) */}
                      {r?.trace_refs?.run_id && (
                        <div className="text-[10px] text-muted-foreground/70 border-t border-border/30 pt-1.5">
                          {t.runId}: <span className="font-mono">{r.trace_refs.run_id}</span>
                          {r.trace_refs.method_id && <> · method: <span className="font-mono">{r.trace_refs.method_id}</span></>}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        </div>

        {/* ===== (Corti-style: no fixed right Settings pane - moved to Config drawer) ===== */}
      </div>

      {/* ==================== CONFIG DRAWER (Corti-style right slide-out) ==================== */}
      {configOpen && (
        <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setConfigOpen(false)} />
      )}
      <div
        data-testid="config-drawer"
        className={`fixed right-0 top-0 h-full w-[400px] bg-background border-l border-border shadow-xl z-50 transform transition-transform duration-200 flex flex-col ${
          configOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/20 shrink-0">
          <div className="flex items-center gap-2">
            <SlidersHorizontal size={14} className="text-muted-foreground" />
            <span className="text-sm font-medium text-foreground">{t.config}</span>
          </div>
          <button
            onClick={() => setConfigOpen(false)}
            className="text-muted-foreground hover:text-foreground"
            aria-label={t.close || 'Close'}
          >
            <X size={16} />
          </button>
        </div>
        {/* Sub-tab: Settings / Code */}
        <div className="flex items-center border-b border-border/20 shrink-0">
          <button
            onClick={() => setRightTab('settings')}
            className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${rightTab === 'settings' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          >
            {t.settings}
          </button>
          <button
            onClick={() => setRightTab('code')}
            className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${rightTab === 'code' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
          >
            {t.tabCode}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {rightTab === 'settings' ? (
            <div className="p-4 space-y-5">
              {/* Coding systems (chips) */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1">
                    <label className="text-xs font-medium text-foreground">{t.codingSystems}</label>
                    <span className="text-muted-foreground/40 cursor-help" title={t.codingSystems}>
                      <Info size={11} />
                    </span>
                  </div>
                  {availableSystems.length > 0 && (
                    <div className="relative group">
                      <button className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-0.5">
                        <Plus size={11} /> {t.add}
                      </button>
                      <div className="absolute right-0 top-full mt-1 w-48 bg-popover border border-border rounded-lg shadow-lg z-50 py-1 hidden group-hover:block">
                        {availableSystems.map(cs => (
                          <button key={cs.code_system} onClick={() => addSystem(cs.code_system)}
                            className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent transition-colors">
                            {cs.name}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {selectedSystems.length === 0 && (
                    <span className="text-[11px] text-muted-foreground/50">{t.noSystemsSelected}</span>
                  )}
                  {selectedSystems.map(sys => (
                    <span key={sys} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-muted text-xs text-foreground">
                      {shortSystemLabel(sys)}
                      <button onClick={() => removeSystem(sys)} className="text-muted-foreground hover:text-foreground">
                        <X size={11} />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              {/* Filter codes */}
              <div>
                <div className="flex items-center gap-1">
                  <label className="text-xs font-medium text-foreground">{t.filterCodes}</label>
                  <span className="text-muted-foreground/40 cursor-help" title={t.filterCodes}>
                    <Info size={11} />
                  </span>
                </div>
                <div className="mt-1.5 space-y-2.5">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-muted-foreground">{t.include}</span>
                        <span className="text-muted-foreground/30"><Info size={10} /></span>
                      </div>
                      <button onClick={() => setAddCodeDialog({show:true, target:'include'})} className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-0.5">
                        <Plus size={11} /> {t.addCodes}
                      </button>
                    </div>
                    {includeCodes.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {includeCodes.map((c, i) => (
                          <span key={i} className="text-[11px] px-1.5 py-0.5 rounded bg-muted flex items-center gap-1">
                            {c}
                            <button onClick={() => setIncludeCodes(prev => prev.filter((_, j) => j !== i))} className="hover:text-foreground">
                              <X size={10} />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-muted-foreground">{t.exclude}</span>
                        <span className="text-muted-foreground/30"><Info size={10} /></span>
                      </div>
                      <button onClick={() => setAddCodeDialog({show:true, target:'exclude'})} className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-0.5">
                        <Plus size={11} /> {t.addCodes}
                      </button>
                    </div>
                    {excludeCodes.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {excludeCodes.map((c, i) => (
                          <span key={i} className="text-[11px] px-1.5 py-0.5 rounded bg-muted flex items-center gap-1">
                            {c}
                            <button onClick={() => setExcludeCodes(prev => prev.filter((_, j) => j !== i))} className="hover:text-foreground">
                              <X size={10} />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* ===== G001 refactor: Coding Mode selector (Fast vs Deep Evidence) ===== */}
              <div data-testid="coding-mode-section">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-medium text-foreground">Coding Mode</span>
                    <span className="text-muted-foreground/40 cursor-help" title="G001: Fast = Corti-like single LLM call (~7-12s). Deep Evidence = MedCodER 5-stage pipeline (30-60s+).">
                      <Info size={11} />
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    data-testid="mode-fast-btn"
                    onClick={() => setCodingMode('corti_like_fast')}
                    className={`text-left px-2.5 py-2 rounded-md border transition-all ${
                      codingMode === 'corti_like_fast'
                        ? 'border-emerald-400 bg-emerald-50 text-emerald-800'
                        : 'border-border bg-background text-muted-foreground hover:border-foreground/30'
                    }`}
                  >
                    <div className="flex items-center gap-1 mb-0.5">
                      <Zap size={11} />
                      <span className="text-[11px] font-medium">Fast Coding</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground/70 leading-tight">单阶段 LLM · ~7-12s · 默认</p>
                  </button>
                  <button
                    data-testid="mode-deep-btn"
                    onClick={() => setCodingMode('medcoder_deep')}
                    className={`text-left px-2.5 py-2 rounded-md border transition-all ${
                      codingMode === 'medcoder_deep'
                        ? 'border-violet-400 bg-violet-50 text-violet-800'
                        : 'border-border bg-background text-muted-foreground hover:border-foreground/30'
                    }`}
                  >
                    <div className="flex items-center gap-1 mb-0.5">
                      <FileSearch size={11} />
                      <span className="text-[11px] font-medium">Deep Evidence</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground/70 leading-tight">MedCodER 5 阶段 · 30-60s+ · 高级</p>
                  </button>
                </div>
                {codingMode === 'medcoder_deep' && (
                  <p className="text-[10px] text-amber-700 mt-1.5 flex items-start gap-1">
                    <AlertTriangle size={10} className="mt-0.5 shrink-0" />
                    Deep Evidence 模式更慢但更详细,适合复杂病例。超时建议切换至 Fast Coding。
                  </p>
                )}
              </div>

              {/* Expand */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1">
                  <span className="text-xs font-medium text-foreground">{t.expand}</span>
                  <span className="text-muted-foreground/40 cursor-help" title={t.expand}>
                    <Info size={11} />
                  </span>
                </div>
                <button onClick={() => setExpandResults(!expandResults)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${expandResults ? 'bg-primary' : 'bg-gray-300 dark:bg-gray-600'}`}
                  role="switch" aria-checked={expandResults}>
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform ${expandResults ? 'translate-x-[18px]' : 'translate-x-[2px]'}`} />
                </button>
              </div>

              {/* Confidence threshold */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-medium text-foreground">{t.confidenceThreshold}</span>
                    <span className="text-muted-foreground/40 cursor-help" title="Minimum confidence to include a candidate">
                      <Info size={11} />
                    </span>
                  </div>
                  <span className="text-[11px] font-mono text-muted-foreground">{confidenceThreshold.toFixed(2)}</span>
                </div>
                <input
                  type="range" min={0} max={1} step={0.05}
                  value={confidenceThreshold}
                  onChange={e => setConfidenceThreshold(parseFloat(e.target.value))}
                  className="w-full h-1.5 bg-muted rounded-full appearance-none cursor-pointer accent-primary"
                />
                <div className="flex justify-between text-[10px] text-muted-foreground/50 mt-0.5 font-mono">
                  <span>0.00</span><span>0.50</span><span>1.00</span>
                </div>
              </div>

              {/* Reset settings */}
              <button onClick={() => { setExpandResults(false); setConfidenceThreshold(0.6); setIncludeCodes([]); setExcludeCodes([]); setCodingMode('corti_like_fast'); }}
                className="w-full text-[11px] text-muted-foreground hover:text-foreground flex items-center justify-center gap-1 py-1.5 border border-border/40 rounded-md transition-colors">
                <RotateCcw size={11} /> {t.resetSettings}
              </button>
            </div>
          ) : (
            <div className="p-4">
              <CodeSnippet javascript={codeSnippetJS} json={codeSnippetJSON} compact />
            </div>
          )}
        </div>
      </div>

      {/* ==================== EVENT INSPECTOR - Corti-style floating button + drawer ==================== */}
      <button
        data-testid="event-inspector-fab"
        onClick={() => setEventInspectorOpen(true)}
        className="fixed bottom-4 right-4 z-40 flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-background shadow-lg text-sm hover:bg-accent transition-colors"
      >
        <Activity size={14} className="text-muted-foreground" />
        <span className="text-foreground font-medium">{t.eventInspector}</span>
        <span className="text-xs text-muted-foreground/70 font-mono">
          {t.creditsConsumed}: {liveCost > 0 ? `¥${liveCost.toFixed(6)}` : 'N/A'}
        </span>
      </button>
      {eventInspectorOpen && (
        <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setEventInspectorOpen(false)} />
      )}
      <div
        data-testid="event-inspector-drawer"
        className={`fixed right-0 top-0 h-full w-[400px] bg-background border-l border-border shadow-xl z-50 transform transition-transform duration-200 flex flex-col ${
          eventInspectorOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/20 shrink-0">
          <div className="flex items-center gap-2">
            <Activity size={14} className="text-muted-foreground" />
            <span className="text-sm font-medium text-foreground">{t.eventInspector}</span>
          </div>
          <button
            onClick={() => setEventInspectorOpen(false)}
            className="text-muted-foreground hover:text-foreground"
            aria-label={t.close || 'Close'}
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-1">
          {events.length === 0 ? (
            <span className="text-[11px] text-muted-foreground/40 font-mono">{t.ready}</span>
          ) : (
            events.map((ev, i) => (
              <div key={i} className={`text-[11px] font-mono ${ev.type==='error'?'text-red-500':ev.type==='success'?'text-emerald-600':'text-muted-foreground'}`}>
                <span className="text-muted-foreground/40 mr-1">{ev.ts}</span>
                {ev.msg}
              </div>
            ))
          )}
        </div>
      </div>

      {/* ==================== ADD CODE DIALOG ==================== */}
      {addCodeDialog.show && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setAddCodeDialog({show:false, target:'include'})}>
          <div className="bg-background rounded-xl shadow-xl p-5 w-80" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold">{addCodeDialog.target === 'include' ? t.addIncludeCode : t.addExcludeCode}</p>
              <button onClick={() => setAddCodeDialog({show:false, target:'include'})}><X size={14} /></button>
            </div>
            <input value={addCodeVal} onChange={e => setAddCodeVal(e.target.value)} placeholder={t.enterCodePlaceholder} autoFocus
              className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-transparent focus:outline-none focus:ring-2 focus:ring-primary/20 mb-3"
              onKeyDown={e => { if (e.key === 'Enter') confirmAddCode(); }} />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setAddCodeDialog({show:false, target:'include'})} className="px-3 py-1.5 text-xs border border-border rounded-lg hover:bg-accent">{t.cancel}</button>
              <button onClick={confirmAddCode} className="px-3 py-1.5 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90">{t.add}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function dataEvidences(result: any): EvidenceSpanLike[] {
  const ev = result?.evidences;
  if (!ev || !Array.isArray(ev)) return [];
  return ev
    .filter((e: any) => e && (e.text || e.quote))
    .map((e: any) => ({
      text: e.text || e.quote,
      char_start: typeof e.char_start === 'number' ? e.char_start : 0,
      char_end: typeof e.char_end === 'number' ? e.char_end : 0,
      confidence: e.confidence,
    }));
}
