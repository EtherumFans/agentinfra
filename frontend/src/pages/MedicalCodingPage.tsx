// iCoDer Medical Coding — Corti Console 1:1 visual replica
// All UI text is i18n-driven: zh-CN ↔ en-US
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAppStore, useCostStore } from '../store';
import { useT } from '../i18n';
import { codeTablesApi } from '../services/api';
import { runtimeApi } from '../services/runtimeApi';
import type { RuntimeRunResult } from '../types/runtime';
import {
  X, Sparkles, Loader2, Plus, ChevronRight, ChevronLeft,
  Eraser, Copy, BookText, Info, RotateCcw, HelpCircle,
  FileText, ChevronDown, Check,
} from 'lucide-react';
import CodeSnippet from '../components/common/CodeSnippet';

type RightTab = 'settings' | 'code';

const MEDICAL_CODING_AGENT_REF = 'medical-coding-agent-1.0.0';

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

  // ── Input state ──
  const [input, setInput] = useState('');
  const [result, setResult] = useState<RuntimeRunResult | any>(null);
  const [loading, setLoading] = useState(false);

  // ── Sample dropdown (top header "Samples" button) ──
  const [sampleMenuOpen, setSampleMenuOpen] = useState(false);

  // ── Guided demo (2-step wizard) — button-triggered, NOT auto-show ──
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideStep, setGuideStep] = useState(0); // 0=sample, 1=coding system
  const [guideSelectedSample, setGuideSelectedSample] = useState<string | null>(null);
  const openGuide = () => { setGuideOpen(true); setGuideStep(0); setGuideSelectedSample(null); };
  const closeGuide = () => setGuideOpen(false);

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
    codeTablesApi.list().then((r: any) => {
      const tables = r.data?.tables || [];
      const systems = tables.filter((tt:any) => tt.is_active !== false).map((tt:any) => ({
        code_system: tt.code_system, name: tt.name, is_default: tt.is_default,
      }));
      setCodingSystems(systems);
      const defaults = systems.filter((s:any) => s.is_default).map((s:any) => s.code_system);
      setSelectedSystems(defaults.length ? defaults : systems.length ? [systems[0].code_system] : []);
    }).catch(() => {});
  }, []);

  // ── Guide nav (2-step wizard) ──
  const nextGuideStep = () => setGuideStep(1);  // step 0 → step 1
  const prevGuideStep = () => setGuideStep(0);  // step 1 → step 0
  const runGuidePredict = () => {
    // step 1 final: fill selected sample into textarea, then predict
    if (!guideSelectedSample) return;
    const sample = samples.find(s => s.key === guideSelectedSample);
    if (!sample) return;
    setInput(sample.text);
    closeGuide();
    // Trigger predict on next tick so the input state flushes first
    setTimeout(() => handlePredict(sample.text), 0);
  };

  // ── Predict ──
  const handlePredict = async (textOverride?: string) => {
    const text = textOverride || input;
    if (!text.trim() || loading) return;
    if (!textOverride) setInput(text);
    setLoading(true);
    setProcessing(true);
    setError(null);
    setResult(null);
    setEvents([]);
    addEvent(t.startingPrediction, 'info');

    try {
      const startTime = Date.now();
      const data = await runtimeApi.runAgent(MEDICAL_CODING_AGENT_REF, text);
      const elapsed = Date.now() - startTime;
      setResult(data);
      if (data.processing_time_ms) addCost((data.processing_time_ms / 1000) * 0.02);

      addEvent(`${t.completedPrefix} ${data.processing_time_ms || elapsed}ms`, 'success');
      if (data.audit_trail?.length) {
        data.audit_trail.forEach((step: any) => {
          const p = step.payload || {};
          const prefix = `[${step.step}]`;
          if (step.step === 'pre_guard' && p.violations?.length) {
            addEvent(`${prefix} ${fillTmpl(t.preGuardViolations, { count: p.violations.length })}`, 'info');
          } else if (step.step === 'contract_verified') {
            addEvent(`${prefix} ${fillTmpl(t.contractVerified, { status: p.valid ? 'PASS' : 'FAIL' })}`, p.valid ? 'success' : 'error');
          } else if (step.step === 'post_guard') {
            const status = `${t.safety}:${p.safety_valid ? 'PASS' : 'WARN'} ${t.schema}:${p.schema_valid ? 'PASS' : 'ISSUE'}`;
            addEvent(`${prefix} ${status}`, p.safety_valid ? 'success' : 'error');
          } else if (step.step !== 'llm_response') {
            addEvent(`${prefix} ${JSON.stringify(p).slice(0, 80)}`, 'info');
          }
        });
      }
      if (data.errors?.length) {
        data.errors.forEach((e: any) => addEvent(`${t.errorPrefix}: ${typeof e === 'string' ? e : e.message || JSON.stringify(e)}`, 'error'));
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || t.processingFailed;
      setError(msg);
      addEvent(`${t.failedPrefix}: ${msg}`, 'error');
    } finally {
      setLoading(false);
      setProcessing(false);
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
  const primaryDiag = (result as RuntimeRunResult)?.primary_diagnosis;
  const secondaryDiags = (result as RuntimeRunResult)?.secondary_diagnoses || [];
  const procedures = (result as RuntimeRunResult)?.procedures || [];
  const allCodes = [primaryDiag, ...secondaryDiags, ...procedures]
    .filter(Boolean)
    .slice()
    .sort((a: any, b: any) => (b.confidence ?? 0) - (a.confidence ?? 0));
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
      {/* ==================== HEADER (breadcrumb + meta) ==================== */}
      <div className="flex items-center gap-2 px-4 py-1.5 border-b border-border/20 shrink-0 text-xs">
        <Link to="/ai-studio/overview" className="text-muted-foreground hover:text-foreground transition-colors">{t.aiStudio}</Link>
        <ChevronRight size={12} className="text-muted-foreground/50" />
        <span className="text-foreground font-medium truncate">{t.medicalCodingBreadcrumb}</span>
        <div className="ml-auto flex items-center gap-3 text-muted-foreground">
          {liveCost > 0 && <span className="font-mono">${liveCost.toFixed(6)}</span>}
          <a href="/docs" className="hover:text-foreground transition-colors">{t.documentation}</a>
        </div>
      </div>

      {/* ==================== ACTION BAR (Predict codes) ==================== */}
      <div className="flex items-center justify-end gap-2 px-4 py-2 border-b border-border/20 shrink-0">
        <button onClick={() => handlePredict()} disabled={!hasText || loading}
          className="px-4 py-1.5 rounded-lg border border-border bg-background text-foreground text-sm font-medium hover:bg-accent disabled:opacity-30 transition-all flex items-center gap-1.5">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          {loading ? t.analyzing : t.predictCodes}
        </button>
      </div>

      {/* ==================== MAIN 3-PANE ==================== */}
      <div className="flex-1 flex min-h-0">
        {/* ===== LEFT: Input + SampleMenu dropdown + Guide wizard ===== */}
        <div className="flex-1 flex flex-col p-4 min-w-0 border-r border-border/20">
          <div className="flex items-center gap-2 mb-2 relative">
            <span className="text-sm font-medium text-foreground">{t.inputLabel}</span>
            {/* "?" trigger — opens the 2-step Guide wizard (NOT auto-shown) */}
            <button onClick={openGuide} title={t.openGuide}
              className="ml-auto px-1.5 py-1 text-muted-foreground hover:text-foreground rounded-md flex items-center gap-1">
              <HelpCircle size={14} />
            </button>
            {/* "Samples" button — opens a simple dropdown menu (NOT the guide) */}
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
          </div>
          <div className="flex-1 relative min-h-0">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder={t.enterClinicalText}
              className="w-full h-full resize-none bg-background rounded-xl border border-border/30 p-4 text-sm leading-relaxed placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-shadow"
            />
            {/* ─────── Guided demo: 2-step wizard (button-triggered) ─────── */}
            {guideOpen && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="bg-card border border-border rounded-xl p-4 shadow-lg w-[400px] max-w-[90%] pointer-events-auto">
                  {/* Header */}
                  <div className="flex items-start gap-2 mb-2">
                    <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
                      <Sparkles size={12} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-foreground">{t.guidedDemo}</p>
                      <p className="text-xs text-muted-foreground">
                        {guideStep === 0 ? t.startByAddingText : t.selectCodingSystem}
                      </p>
                    </div>
                    <button onClick={closeGuide} className="text-muted-foreground hover:text-foreground -mt-1 -mr-1 p-1" title={t.dismissGuide ?? 'Dismiss'}>
                      <X size={14} />
                    </button>
                  </div>
                  {/* Step indicator (2 dots) */}
                  <div className="flex items-center gap-1 mb-3">
                    <div className={`h-1 flex-1 rounded-full transition-colors ${guideStep >= 0 ? 'bg-primary' : 'bg-muted'}`} />
                    <div className={`h-1 flex-1 rounded-full transition-colors ${guideStep >= 1 ? 'bg-primary' : 'bg-muted'}`} />
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                    {guideStep === 0 ? t.guidedDemoDesc : t.selectCodingSystemDesc}
                  </p>

                  {/* Step 0: sample list */}
                  {guideStep === 0 && (
                    <div className="space-y-1 mb-3">
                      {samples.map(s => (
                        <button key={s.key}
                          onClick={() => setGuideSelectedSample(s.key)}
                          className={`w-full text-left px-3 py-2 rounded-md border text-xs transition-colors flex items-center gap-2 ${
                            guideSelectedSample === s.key
                              ? 'border-primary bg-primary/5'
                              : 'border-border/40 hover:bg-accent'
                          }`}>
                          <FileText size={12} className={guideSelectedSample === s.key ? 'text-primary' : 'text-muted-foreground'} />
                          <span className="font-medium text-foreground flex-1">{s.title}</span>
                          {guideSelectedSample === s.key && <Check size={12} className="text-primary" />}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Step 1: coding systems (shares selectedSystems with right Settings panel) */}
                  {guideStep === 1 && (
                    <div className="space-y-1 mb-3 max-h-48 overflow-y-auto">
                      {codingSystems.length === 0 ? (
                        <p className="text-xs text-muted-foreground/60 text-center py-4">—</p>
                      ) : (
                        codingSystems.map(cs => {
                          const selected = selectedSystems.includes(cs.code_system);
                          return (
                            <button key={cs.code_system}
                              onClick={() => selected ? removeSystem(cs.code_system) : addSystem(cs.code_system)}
                              className={`w-full text-left px-3 py-2 rounded-md border text-xs transition-colors flex items-center gap-2 ${
                                selected ? 'border-primary bg-primary/5' : 'border-border/40 hover:bg-accent'
                              }`}>
                              <FileText size={12} className={selected ? 'text-primary' : 'text-muted-foreground'} />
                              <span className="font-medium text-foreground flex-1">{shortSystemLabel(cs.code_system)}</span>
                              {selected && <Check size={12} className="text-primary" />}
                            </button>
                          );
                        })
                      )}
                    </div>
                  )}

                  {/* Bottom nav: Back / Next OR Back / Predict codes */}
                  <div className="flex items-center justify-end gap-1">
                    {guideStep === 1 && (
                      <button onClick={prevGuideStep}
                        className="px-2 py-1 text-xs text-muted-foreground hover:text-foreground border border-border rounded-md flex items-center gap-0.5">
                        <ChevronLeft size={12} /> {t.back}
                      </button>
                    )}
                    {guideStep === 0 ? (
                      <button onClick={nextGuideStep} disabled={!guideSelectedSample}
                        className="px-2 py-1 text-xs text-primary-foreground bg-primary hover:bg-primary/90 rounded-md flex items-center gap-0.5 disabled:opacity-30">
                        {t.next} <ChevronRight size={12} />
                      </button>
                    ) : (
                      <button onClick={runGuidePredict} disabled={!guideSelectedSample || selectedSystems.length === 0}
                        className="px-2.5 py-1 text-xs text-primary-foreground bg-primary hover:bg-primary/90 rounded-md flex items-center gap-1 disabled:opacity-30">
                        <Sparkles size={12} /> {t.predictCodes}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ===== MIDDLE: Output ===== */}
        <div className="w-[400px] shrink-0 flex flex-col border-r border-border/20">
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
                {primaryDiag?.code && (
                  <div>
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">{t.primaryDiagnosis}</p>
                    <div className="flex items-baseline gap-2">
                      <span className="text-lg font-bold font-mono text-foreground">{primaryDiag.code}</span>
                      <span className="text-xs text-muted-foreground">{primaryDiag.description || ''}</span>
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
                        <tr key={i} className="border-b border-border/10">
                          <td className="py-1.5 text-muted-foreground">{i + 1}</td>
                          <td className="py-1.5 font-mono font-medium">{c.code || ''}</td>
                          <td className="py-1.5 text-muted-foreground">{c.description || ''}</td>
                          <td className="py-1.5 text-right font-mono text-muted-foreground">
                            {c.confidence ? Math.round(c.confidence * 100) + '%' : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {dataEvidences(result).length > 0 && (
                  <div>
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">{t.evidence}</p>
                    <div className="space-y-1">
                      {dataEvidences(result).map((q, i) => (
                        <div key={i} className="text-xs text-muted-foreground bg-primary/5 rounded px-2.5 py-1.5">“{q}”</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ===== RIGHT: Settings / Code ===== */}
        <div className="w-[360px] shrink-0 flex flex-col bg-background">
          <div className="flex items-center border-b border-border/20 shrink-0">
            <button onClick={() => setRightTab('settings')}
              className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${rightTab === 'settings' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
              {t.settings}
            </button>
            <button onClick={() => setRightTab('code')}
              className={`flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors ${rightTab === 'code' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
              {t.tabCode}
            </button>
            <span className="px-2 text-muted-foreground/40 cursor-help" title={t.tabCode}>
              <Info size={12} />
            </span>
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
                <button onClick={() => { setExpandResults(false); setConfidenceThreshold(0.6); setIncludeCodes([]); setExcludeCodes([]); }}
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
      </div>

      {/* ==================== EVENT INSPECTOR ==================== */}
      <div className="h-8 shrink-0 border-t border-border/30 bg-muted/20 flex items-center px-4 gap-4">
        <span className="text-[10px] text-muted-foreground font-medium shrink-0">{t.eventInspector}</span>
        <div className="flex-1 flex items-center gap-3 overflow-hidden">
          {events.length === 0 ? (
            <span className="text-[11px] text-muted-foreground/40 font-mono">{t.ready}</span>
          ) : (
            events.slice(-3).map((ev, i) => (
              <span key={i} className={`text-[11px] font-mono truncate ${ev.type==='error'?'text-red-500':ev.type==='success'?'text-emerald-600':'text-muted-foreground'}`}>
                <span className="text-muted-foreground/40 mr-1">{ev.ts}</span>
                {ev.msg}
              </span>
            ))
          )}
        </div>
        <span className="text-[10px] text-muted-foreground/40 font-mono shrink-0">
          {t.creditsConsumedLabel}: {liveCost > 0 ? `$${liveCost.toFixed(6)}` : 'N/A'}
        </span>
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

function dataEvidences(result: any): string[] {
  const ev = result?.evidences;
  if (!ev || !Array.isArray(ev)) return [];
  return ev.filter((e:any) => e.text || e.quote).map((e:any) => e.text || e.quote);
}
