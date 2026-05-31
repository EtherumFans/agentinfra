import { useLocaleStore } from '../i18n';
import { useState, useCallback, useEffect } from 'react';
import {
  Loader2, Copy, Check, FileText, Stethoscope,
  Activity, Clock, AlertTriangle, FileCheck, Sparkles,
  Wand2, ChevronDown,
} from 'lucide-react';
import { factsApi, billingApi } from '../services/api';
import SettingsCodeTab from '../components/common/SettingsCodeTab';
import EventInspector from '../components/common/EventInspector';
import CodeSnippet from '../components/common/CodeSnippet';

// ---- 示例文本 ----
const SAMPLES: Record<string, { label: string; text: string }> = {
  orthopedic: {
    label: '骨科转诊信',
    text: '患者，女，65岁。因"腰痛伴左下肢放射痛3月，加重1周"就诊。患者3月前无明显诱因出现腰部酸胀不适，久坐及弯腰时加重，休息后稍缓解，伴左下肢放射性疼痛，沿臀部、大腿后外侧放射至足背，偶伴麻木感。1周前提重物后症状明显加重，VAS评分7分。否认外伤史。既往体健，否认高血压、糖尿病史。查体：腰椎生理曲度变直，L4-S1棘突及椎旁压痛明显，左侧直腿抬高试验45°(+)，加强试验(+)，左侧跟趾行走试验弱阳性，双侧膝腱反射及跟腱反射对称存在。腰椎MRI示L4/5、L5/S1椎间盘突出，压迫左侧神经根。入院诊断：腰椎间盘突出症（L4/5、L5/S1）。建议行L4/5、L5/S1椎间盘髓核摘除术（PLIF）。',
  },
  gp: {
    label: '全科转录',
    text: '患者：张三，45岁男性。就诊日期：2025-11-15。主诉：持续咳嗽2周，发热最高38.5°C，乏力。患者自述咳痰，痰呈绿色。无咯血。否认胸痛、静息时气短及近期旅行史。既往史：轻度间歇性哮喘（沙丁胺醇PRN控制良好），高血压（赖诺普利10mg每日一次）。吸烟史15包年。查体：体温38.2°C，呼吸18次/分，血氧饱和度97%（静息），心率88次/分，血压138/86 mmHg。胸部听诊：右肺下叶可闻及湿啰音。快速链球菌检测阴性。胸部X线片示右肺下叶浸润影。评估：社区获得性肺炎，右肺下叶。治疗计划：阿奇霉素500mg第1天，随后250mg第2-5天，继续服用赖诺普利，1周后随访。',
  },
};

// ---- 语言选项 ----
const LANGUAGES: Record<string, string> = {
  'zh-CN': '简体中文',
  'en-US': '英文 (美国)',
};

// ---- 事实类型图标 ----
const factIcons: Record<string, React.ReactNode> = {
  diagnosis: <Stethoscope size={14} />,
  procedure: <Activity size={14} />,
  drug: <Activity size={14} />,
  lab: <Activity size={14} />,
  allergy: <AlertTriangle size={14} />,
  social_history: <FileText size={14} />,
  negated: <AlertTriangle size={14} />,
  chief_complaint: <FileText size={14} />,
  timing: <Clock size={14} />,
  overview: <FileCheck size={14} />,
};

// ---- SDK 代码示例 ----
function getSdkCode(languageCode: string, sampleText: string): string {
  const escaped = sampleText.slice(0, 80).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n');
  return `import { iCoDerClient } from "@icoder/sdk"

const client = new iCoDerClient({
  auth: { accessToken: "<access-token>" }
})

try {
  const response = await client.facts.extract({
    context: { type: "text", text: "${escaped}..." },
    outputLanguage: "${languageCode}",
  })
  console.log("Extracted facts:", response.facts)
  console.log("Credits consumed:", response.creditsConsumed)
} catch (error) {
  console.error("Error extracting facts:", error)
}`;
}

export default function FactExtractionPage() {
  const locale = useLocaleStore(s => s.locale);
  const [input, setInput] = useState('');
  const [output, setOutput] = useState<any>(null);
  const [rawOutput, setRawOutput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [cost, setCost] = useState(0);
  const [balance, setBalance] = useState(0);
  const [outputLanguage, setOutputLanguage] = useState('zh-CN');
  const [showSampleMenu, setShowSampleMenu] = useState(false);
  const [copiedRaw, setCopiedRaw] = useState(false);
  const [creditsConsumed, setCreditsConsumed] = useState(0);
  const [editableFacts, setEditableFacts] = useState<any>(null);
  const [extractEvents, setExtractEvents] = useState<{type:string;data:Record<string,unknown>;timestamp:string;credits?:number}[]>([]);

  // 加载计费信息
  useEffect(() => {
    billingApi.balance().then(({ data }) => {
      setBalance(data.balance);
    }).catch(() => {});
  }, []);

  // 提取事实
  const handleExtract = useCallback(async () => {
    if (!input.trim() || loading) return;
    setLoading(true); setOutput(null); setError(''); setRawOutput('');
    setExtractEvents(prev => [...prev.slice(-50), { type: 'extract_start', data: { inputLength: input.length, language: outputLanguage }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }), credits: 0.000001 }]);
    try {
      const { data } = await factsApi.extract(input.trim(), outputLanguage);
      setOutput(data.facts);
      setRawOutput(data.raw_output);
      const credits = (data as any).credits_consumed || 1;
      setCreditsConsumed(credits);
      setCost(c => c + 0.000001);
      setEditableFacts(data.facts);
      setExtractEvents(prev => [...prev.slice(-50), { type: 'extract_complete', data: { diagCount: (data.facts as any)?.diagnosis_facts?.length || 0, procCount: (data.facts as any)?.procedure_facts?.length || 0 }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }), credits }]);
    } catch (err: any) {
      const msg = err.response?.data?.detail || '提取失败';
      setError(msg);
      setExtractEvents(prev => [...prev.slice(-50), { type: 'extract_error', data: { error: msg }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }) }]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, outputLanguage]);

  // 清空
  const handleClear = () => { setInput(''); setOutput(null); setRawOutput(''); setError(''); };

  // Cycle fact status: confirmed → suspected → ruled_out → confirmed
  const cycleStatus = (sectionKey: string, itemIndex: number) => {
    if (!editableFacts) return;
    const updated = JSON.parse(JSON.stringify(editableFacts));
    const order = ['confirmed', 'suspected', 'ruled_out', 'performed', 'planned', 'discussed'];
    // Navigate sections
    let items: any[] | null = null;
    if (sectionKey === 'diagnosis') items = updated.diagnosis_facts;
    else if (sectionKey === 'procedure') items = updated.procedure_facts;
    else if (sectionKey === 'negated') items = updated.negated_findings;
    else return;

    if (items && items[itemIndex]) {
      const current = items[itemIndex].status || '';
      const next = order[(order.indexOf(current) + 1) % order.length];
      items[itemIndex].status = next;
      setEditableFacts(updated);
    }
  };

  // 渲染结构化事实
  const renderFacts = (facts: any) => {
    if (!facts) return null;

    const sections: { key: string; title: string; items: any[] }[] = [];

    if (facts.chief_complaint) {
      sections.push({ key: 'chief_complaint', title: '主诉', items: [{ text: facts.chief_complaint }] });
    }

    if (facts.diagnosis_facts?.length) {
      sections.push({ key: 'diagnosis', title: `诊断事实 (${facts.diagnosis_facts.length})`, items: facts.diagnosis_facts });
    }

    if (facts.procedure_facts?.length) {
      sections.push({ key: 'procedure', title: `手术/操作事实 (${facts.procedure_facts.length})`, items: facts.procedure_facts });
    }

    if (facts.drug_facts?.length) {
      sections.push({ key: 'drug', title: `药物信息 (${facts.drug_facts.length})`, items: facts.drug_facts });
    }
    if (facts.lab_facts?.length) {
      sections.push({ key: 'lab', title: `检验检查 (${facts.lab_facts.length})`, items: facts.lab_facts });
    }
    if (facts.allergy_facts?.length) {
      sections.push({ key: 'allergy', title: `过敏信息 (${facts.allergy_facts.length})`, items: facts.allergy_facts });
    }
    if (facts.social_history_facts && Object.values(facts.social_history_facts).some(Boolean)) {
      sections.push({ key: 'social_history', title: '社会史', items: [facts.social_history_facts] });
    }

    if (facts.negated_findings?.length) {
      sections.push({ key: 'negated', title: `排除的发现 (${facts.negated_findings.length})`, items: facts.negated_findings });
    }

    if (facts.timing_facts && Object.values(facts.timing_facts).some(Boolean)) {
      sections.push({
        key: 'timing',
        title: '时间信息',
        items: [facts.timing_facts],
      });
    }

    if (facts.documentation_overview && Object.values(facts.documentation_overview).some(Boolean)) {
      sections.push({
        key: 'overview',
        title: '文档概览',
        items: [facts.documentation_overview],
      });
    }

    return sections.map(section => (
      <div key={section.key} className="mb-4 last:mb-0">
        <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5 mb-2">
          {factIcons[section.key] || <FileText size={14} />}
          {section.title}
        </h4>
        <div className="space-y-2">
          {section.items.map((item: any, i: number) => (
            <div key={i} className="bg-muted/50 rounded-lg p-3 border border-border/50">
              {/* Diagnosis/Procedure facts */}
              {(item.diagnosis || item.procedure) && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-foreground">
                      {item.diagnosis || item.procedure}
                    </span>
                    {item.icd10cm_code && (
                      <code className="text-[11px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-mono">
                        {item.icd10cm_code}
                      </code>
                    )}
                    {item.icd9cm3_code && (
                      <code className="text-[11px] bg-accent text-accent-foreground px-1.5 py-0.5 rounded font-mono">
                        {item.icd9cm3_code}
                      </code>
                    )}
                    {item.status && (
                      <button
                        onClick={() => cycleStatus(section.key, i)}
                        title="点击切换状态：已确认 → 待确认 → 已排除"
                        className={`text-[10px] px-1.5 py-0.5 rounded-full cursor-pointer hover:ring-1 hover:ring-ring transition-all ${
                        item.status === 'confirmed' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                        item.status === 'suspected' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                        item.status === 'ruled_out' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                        'bg-muted text-muted-foreground'
                      }`}>
                        {item.status === 'confirmed' ? '已确认 ✓' :
                         item.status === 'suspected' ? '待确认 ?' :
                         item.status === 'ruled_out' ? '已排除 ✗' :
                         item.status === 'performed' ? '已执行' :
                         item.status === 'planned' ? '计划中' :
                         item.status === 'discussed' ? '已讨论' :
                         item.status}
                      </button>
                    )}
                  </div>
                  {item.evidence && (
                    <p className="text-xs text-muted-foreground italic">"{(item.evidence as string).slice(0, 200)}"</p>
                  )}
                </div>
              )}

              {/* Negated findings */}
              {item.finding && (
                <div className="space-y-1">
                  <span className="text-sm text-foreground">{item.finding}</span>
                  {item.evidence && (
                    <p className="text-xs text-muted-foreground italic">"{(item.evidence as string).slice(0, 200)}"</p>
                  )}
                </div>
              )}

              {/* Timing / Overview — 简单 KV */}
              {!item.diagnosis && !item.procedure && !item.finding && (
                <div className="space-y-1">
                  {Object.entries(item).map(([k, v]) => (
                    v ? (
                      <div key={k} className="flex items-baseline gap-2 text-xs">
                        <span className="text-muted-foreground capitalize min-w-[80px]">{k.replace(/_/g, ' ')}:</span>
                        <span className="text-foreground">{String(v)}</span>
                      </div>
                    ) : null
                  ))}
                </div>
              )}

              {/* Drug facts */}
              {item.drug_name && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-foreground">{item.drug_name}</span>
                    {item.dosage && <span className="text-[11px] text-muted-foreground">{item.dosage}</span>}
                    {item.route && <span className="text-[10px] bg-muted px-1 py-0.5 rounded">{item.route}</span>}
                    {item.status && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        item.status === 'current' ? 'bg-green-100 text-green-700' :
                        item.status === 'prescribed' ? 'bg-blue-100 text-blue-700' :
                        'bg-muted text-muted-foreground'
                      }`}>{item.status}</span>
                    )}
                  </div>
                  {item.evidence && <p className="text-xs text-muted-foreground italic">"{(item.evidence as string).slice(0, 200)}"</p>}
                </div>
              )}
              {/* Lab facts */}
              {item.test_name && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-foreground">{item.test_name}</span>
                    {item.result && <code className="text-[11px] font-mono text-foreground">{item.result} {item.unit || ''}</code>}
                    {item.interpretation && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        item.interpretation === 'high' ? 'bg-red-100 text-red-700' :
                        item.interpretation === 'low' ? 'bg-blue-100 text-blue-700' :
                        item.interpretation === 'normal' ? 'bg-green-100 text-green-700' :
                        'bg-yellow-100 text-yellow-700'
                      }`}>{item.interpretation}</span>
                    )}
                  </div>
                  {item.evidence && <p className="text-xs text-muted-foreground italic">"{(item.evidence as string).slice(0, 200)}"</p>}
                </div>
              )}
              {/* Allergy facts */}
              {item.allergen && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-foreground">{item.allergen}</span>
                    {item.severity && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        item.severity === 'severe' || item.severity === 'life_threatening' ? 'bg-red-100 text-red-700' :
                        'bg-yellow-100 text-yellow-700'
                      }`}>{item.severity}</span>
                    )}
                    {item.status && <span className="text-[10px] text-muted-foreground">{item.status}</span>}
                  </div>
                  {item.reaction && <p className="text-xs text-muted-foreground">{String(item.reaction).slice(0, 200)}</p>}
                  {item.evidence && <p className="text-xs text-muted-foreground italic">"{(item.evidence as string).slice(0, 200)}"</p>}
                </div>
              )}

              {/* 纯文本项 (chief_complaint) */}
              {item.text && (
                <p className="text-sm text-foreground">{item.text}</p>
              )}
            </div>
          ))}
        </div>
      </div>
    ));
  };

  return (
    <div className="flex h-full">
      {/* ===== LEFT: Main Content (75%) ===== */}
      <div className="flex flex-col overflow-hidden bg-muted/20" style={{ flex: '75 1 0px' }}>
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="flex h-full flex-col p-4">
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background rounded-xl shadow-sm ring-1 ring-border/20">
              {/* Input section */}
              <div className={`flex flex-col min-h-0 transition-all duration-300 ${output ? 'flex-1' : 'flex-[5]'}`}>
                <div className="flex items-center justify-between px-5 py-3 shrink-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">输入文本</span>
                  </div>
                  <div className="relative">
                    <button onClick={() => setShowSampleMenu(!showSampleMenu)}
                      className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border hover:bg-accent/50 transition-all">
                      <FileText size={13} />
                      <span>使用样例</span>
                      <ChevronDown size={10} />
                    </button>
                    {showSampleMenu && (
                      <div className="absolute right-0 top-full mt-1 bg-popover border border-border rounded-xl shadow-lg py-1 min-w-[170px] z-20">
                        {Object.entries(SAMPLES).map(([key, sample]) => (
                          <button key={key} onClick={() => { setInput(sample.text); setShowSampleMenu(false); }}
                            className="w-full text-left px-3 py-2 text-xs text-foreground hover:bg-accent transition-colors">
                            {sample.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                <textarea
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  placeholder="输入临床文本以提取结构化事实..."
                  className="flex-1 w-full resize-none bg-transparent px-5 pb-4 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none min-h-0 leading-relaxed"
                />
              </div>

              {/* Divider + Extract button */}
              <div className="flex items-center justify-between px-5 py-2.5 border-y border-border/20 bg-muted/20 shrink-0">
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">提取结果</span>
                <div className="flex items-center gap-2">
                  {output && (
                    <button onClick={() => { navigator.clipboard.writeText(rawOutput); setCopiedRaw(true); setTimeout(() => setCopiedRaw(false), 2000); }}
                      className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
                      {copiedRaw ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
                    </button>
                  )}
                  <button onClick={handleExtract} disabled={!input.trim() || loading}
                    className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-30 transition-all shadow-sm shadow-primary/20">
                    {loading ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                    提取事实
                  </button>
                </div>
              </div>

              {/* Output section */}
              <div className={`overflow-auto min-h-0 transition-all duration-300 ${output ? 'flex-1' : 'flex-1'}`}>
                {loading ? (
                  <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
                    <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                    <span className="text-sm">提取中...</span>
                  </div>
                ) : error ? (
                  <div className="flex items-center justify-center h-full px-5">
                    <p className="text-sm text-red-500">{error}</p>
                  </div>
                ) : output ? (
                  <div className="p-5">
                    {renderFacts(output)}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground/50">
                    <Wand2 size={28} />
                    <p className="text-sm">生成的事实将显示在这里</p>
                  </div>
                )}
              </div>
            </div>

            {/* Event Inspector */}
            <EventInspector events={extractEvents} creditsConsumed={creditsConsumed} />
          </div>
        </div>
      </div>

      {/* ===== Separator ===== */}
      <div className="h-full w-px bg-border/40" />

      {/* ===== RIGHT: Settings Panel (25%) ===== */}
      <div className="flex flex-col overflow-hidden bg-muted/10" style={{ flex: '25 1 0px' }}>
        <div className="flex h-full flex-col overflow-hidden">
          <SettingsCodeTab
            labels={{ settings: '设置', code: '代码' }}
            settings={
              <div className="flex flex-col">
                <div className="border-b border-border/20">
                  <div className="flex items-center gap-2 px-4 pt-4 pb-2">
                    <div className="w-1 h-4 rounded-full bg-primary/40" />
                    <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">提取设置</h3>
                  </div>
                  <div className="flex flex-col gap-3 px-4 pb-4">
                    <div className="flex items-center justify-between gap-4 min-h-[32px]">
                      <span className="text-sm text-foreground/80">输出语言</span>
                      <select value={outputLanguage} onChange={e => setOutputLanguage(e.target.value)}
                        className="h-8 text-xs border border-input bg-background rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-ring">
                        {Object.entries(LANGUAGES).map(([code, label]) => (
                          <option key={code} value={code}>{label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            }
            code={
              <CodeSnippet
                javascript={getSdkCode(outputLanguage, input || '...')}
                python={`from icoder_sdk import iCoDerClient\n\nclient = iCoDerClient(\n    auth={"access_token": "<access-token>"}\n)\n\ntry:\n    response = client.facts.extract(\n        context={"type": "text", "text": "${(input || '...').slice(0, 80).replace(/"/g, '\\"')}"},\n        output_language="${outputLanguage}",\n    )\n    print("Extracted facts:", response.facts)\nexcept Exception as error:\n    print("Error extracting facts:", error)`}
                json={`{\n  "context": {\n    "type": "text",\n    "text": "${(input || '临床文本...').slice(0, 60).replace(/"/g, '\\"')}"\n  },\n  "outputLanguage": "${outputLanguage}"\n}`}
              />
            }
          />
        </div>
      </div>
    </div>
  );
}
