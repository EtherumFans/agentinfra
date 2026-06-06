// iCoDer Expert Library — browse, search, create, and run experts
import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Search, Plus, Bot, Globe, BrainCircuit, Pill, FlaskConical,
  Database, BookOpenText, Calculator, Stethoscope, MessageSquareText,
  Loader2, X, ArrowUpRight, ChevronRight, Home, Play, Trash2,
  Wrench, ExternalLink,
} from 'lucide-react';
import { expertsApi, byoExpertApi } from '../services/api';
import AddExpertModal from '../components/AddExpertModal';
import { useT } from '../i18n';

const ICON_MAP: Record<string, React.ComponentType<any>> = {
  Globe, BrainCircuit, Pill, FlaskConical, Database, BookOpenText,
  Calculator, Stethoscope, MessageSquareText, Search, Bot,
};

const CATEGORY_LABELS: Record<string, string> = {
  coding: '医学编码',
  medication: '用药知识库',
  search: '文献与搜索',
  utility: '工具',
  interview: '访谈',
  general: '通用',
  documentation: '文书',
  emergency: '急诊',
  insurance: '医保',
  nursing: '护理',
  pharmacy: '药学',
  quality: '质控',
};

// Documentation links for prebuilt experts
const EXPERT_DOCS: Record<string, string> = {
  'ICD-10 WHO 编码专家': 'https://icd.who.int/browse10/2019/en',
  'ICD-9-CM-3 编码专家': 'https://www.cms.gov/medicare/coding-billing/icd-10-codes',
  'PubMed 文献搜索专家': 'https://pubmed.ncbi.nlm.nih.gov/',
  '网络搜索专家': 'https://en.wikipedia.org/wiki/Medical_coding',
  '医学计算专家': 'https://www.mdcalc.com/',
  '药品编码专家': 'https://www.drugs.com/',
  '病历文书生成专家': 'https://www.hl7.org/fhir/',
  '急诊分诊评估专家': 'https://www.esintriage.org/',
  '合规护栏专家': 'https://www.aapc.com/',
  '诊断提取专家': 'https://icd.who.int/browse10/2019/en',
  '手术提取专家': 'https://www.cms.gov/medicare/coding-billing/icd-10-codes',
  'ICD-10 索引导航专家': 'https://icd.who.int/browse10/2019/en',
  '规则解释专家': 'https://www.cms.gov/medicare/coding-billing/icd-10-codes',
  '编码校验专家': 'https://www.ahima.org/',
  'DRG 分组专家': 'https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/ms-drg-classifications-and-software',
  '病历完整性专家': 'https://www.hl7.org/fhir/',
  '拒付申诉专家': 'https://www.aapc.com/',
  '出院宣教专家': 'https://www.ahrq.gov/',
  '护理交班专家': 'https://www.nursingworld.org/',
  '预授权专家': 'https://www.cms.gov/',
  '转诊生成专家': 'https://www.ama-assn.org/',
  '用药重整专家': 'https://www.ismp.org/',
  'ICU 摘要专家': 'https://www.sccm.org/',
  '外科质控登记专家': 'https://www.facs.org/',
  '临床文书改进专家': 'https://www.ahima.org/',
};

const EXPERT_EXAMPLES: Record<string, string> = {
  'ICD-10 WHO 编码专家':
    'Clinical text: Patient is a 65-year-old male with a 10-year history of type 2 diabetes mellitus with diabetic nephropathy (eGFR 42 mL/min). He also has essential hypertension, well-controlled on lisinopril 20mg daily. Recent HbA1c 8.2%. BMI 31.2. Smoker, 30 pack-years. Please assign ICD-10-WHO codes.',
  '记忆管理专家':
    '请回忆我上次查询的关于"冠心病合并心力衰竭"的编码审核结果，以及我常用的心血管疾病编码列表。',
  'POSOS 用药指导专家':
    '请查询阿托伐他汀 (Atorvastatin) 20mg 与克拉霉素 (Clarithromycin) 500mg 的相互作用风险，以及肾功能不全患者的剂量调整建议。',
  '临床试验搜索专家':
    'Search for Phase III clinical trials for SGLT2 inhibitors in patients with chronic kidney disease (non-diabetic). Filter for recruiting trials in China.',
  'DrugBank 药物信息专家':
    'Look up Metformin HCl: mechanism of action, pharmacokinetics, major drug interactions, contraindications, and pregnancy category.',
  'PubMed 文献搜索专家':
    'Search PubMed for articles on "ICD-10 coding accuracy in Chinese hospitals" published in the last 5 years. Summarize the top 3 most relevant articles with PMIDs.',
  '网络搜索专家':
    '搜索 2025年国家医保局发布的关于DRG/DIP支付方式改革的最新政策文件和编码规范要求。',
  '医学计算专家':
    '请计算以下患者的BMI和eGFR：男性，68岁，体重78kg，身高172cm，血清肌酐1.4mg/dL。同时计算CHA₂DS₂-VASc评分（高血压、糖尿病、65岁以上 = 3分）。',
  '通用医学编码专家':
    '患者因"反复胸闷、心悸3年，加重1周"入院。心电图示ST-T改变，冠脉造影示LAD中段狭窄75%，行PCI术植入药物支架1枚。既往有高血压病史10年、2型糖尿病病史5年。请进行ICD-10-CN编码。',
  '临床访谈专家':
    '请模拟一次针对糖尿病患者的初次问诊访谈，收集主诉、现病史、既往史、家族史、用药史和社会史信息。',
  'ICD-10 索引导航专家':
    '请在ICD-10-CN字母索引中检索以下临床术语：冠状动脉粥样硬化性心脏病、骨质疏松伴病理性椎体压缩骨折、2型糖尿病伴周围神经病变。请提供每个术语的候选编码和推荐编码。',
  '规则解释专家':
    '请解释为什么主要诊断选择了I25.101（冠状动脉粥样硬化性心脏病）而非I10.x02（高血压3级）。参考《住院病案首页数据填写质量规范》中的主要诊断选择总则。',
  '合规护栏专家':
    '请评估以下编码组合的医保合规性：\n主要诊断：I25.101 冠状动脉粥样硬化性心脏病\n主要手术：36.0700x001 经皮冠状动脉药物洗脱支架植入术\n其他诊断：I10.x02 高血压3级, E11.900 2型糖尿病',
  '编码校验专家':
    '请验证以下编码集的有效性和一致性：\n主要诊断：M80.900（骨质疏松伴病理性骨折）\n主要手术：81.6600x001（经皮椎体后凸成形术）\n其他诊断：I10.x02（高血压）, E11.900（2型糖尿病）, N18.900x013（慢性肾病5期）',
  '手术提取专家':
    '手术记录：患者在全麻下行经皮穿刺球囊扩张椎体后凸成形术（PKP）。C臂X光机定位T12椎体，穿刺针经双侧椎弓根进入椎体，球囊扩张后注入骨水泥约4ml。手术顺利，出血量约5ml。请提取手术操作并分配ICD-9-CM-3编码。',
  '诊断提取专家':
    '出院小结：患者因"腰背部疼痛2月，加重伴双下肢麻木1周"入院。MRI示L4/5、L5/S1椎间盘突出，压迫硬膜囊及神经根。经保守治疗后症状缓解出院。既往有高血压病史5年。请提取诊断并分配ICD-10-CN编码。',
  '外科质控登记专家':
    '请从以下手术记录中提取数据填入外科质量登记表：\n手术名称：腹腔镜胆囊切除术\n手术时间：2025-03-15 14:30-16:00\n主刀：张主任\n术中出血：30ml\n抗生素使用：头孢唑林2g术前30min\n术后诊断：慢性结石性胆囊炎\n病理号：B2025-03842',
  'ICU 摘要专家':
    '请根据以下ICU病例生成结构化入院摘要：患者男性72岁，因急性呼吸衰竭入ICU。既往COPD病史15年，长期家庭氧疗。入院血气分析：pH 7.25, PaCO2 68mmHg, PaO2 52mmHg。予无创正压通气、支气管扩张剂雾化和糖皮质激素治疗。入ICU时APACHE II评分22分，SOFA评分6分。',
  '急诊分诊评估专家':
    '请使用ESI（急诊严重指数）分诊标准评估以下患者：女性45岁，突发胸痛30分钟，放射至左臂，伴大汗和呼吸困难。生命体征：BP 160/95, HR 112, RR 24, SpO2 94%, T 36.8°C。既往史：高血压、高脂血症，父亲55岁死于心肌梗死。',
  '病历完整性专家':
    '请检查以下入院记录的完整性：\n【主诉】胸闷3天\n【现病史】患者3天前无明显诱因出现胸闷，活动后加重\n【既往史】高血压\n【查体】BP 150/90mmHg\n【诊断】冠心病\n请指出缺失的关键信息项。',
  '用药重整专家':
    '患者入院前用药方案：阿司匹林100mg qd、氯吡格雷75mg qd、阿托伐他汀20mg qn、美托洛尔25mg bid、呋塞米20mg qd、氯化钾缓释片0.5g tid。入院后拟行PCI手术。请进行入院用药重整，识别需要调整的药物。',
  '拒付申诉专家':
    '医保拒付理由：主要诊断I25.101与收费明细中的检查项目不匹配，认为缺乏充分诊断依据。\n病例摘要：患者因胸闷入院，冠脉CTA示LAD中段狭窄70%，心电图ST-T改变。\n请生成申诉理由和支撑证据。',
  '出院宣教专家':
    '请为以下PCI术后患者生成个性化出院指导：男性62岁，急性前壁心肌梗死行急诊PCI（LAD植入DES 1枚），术后恢复良好。合并高血压、2型糖尿病。出院带药：阿司匹林、替格瑞洛、瑞舒伐他汀、美托洛尔、培哚普利。',
  '护理交班专家':
    '请生成结构化的护理交班报告：心内科CCU，患者张某，男，78岁。因急性左心衰入院，目前心功能III级（NYHA）。留置导尿管、外周静脉通路。24小时入量1850ml，出量2200ml。血压波动140-160/80-90mmHg。需重点关注呼吸和液体平衡。',
  '预授权专家':
    '请为以下病例生成符合医保规范的预授权申请文件：患者因腰椎间盘突出症（L4/5, L5/S1）拟行椎间孔镜下椎间盘摘除术。已行保守治疗（物理治疗+NSAIDs）3个月无效。MRI明确椎间盘突出压迫神经根。',
  '转诊生成专家':
    '请生成从社区医院转诊至三甲医院心内科的结构化转诊信：患者因反复胸痛2周就诊，动态心电图示频发室性早搏（24h: 8326次），短阵室速1次。社区医院建议转诊进行心内电生理检查和射频消融治疗。',
  '临床文书改进专家':
    '请审查以下病程记录的文书质量并改进：\n患者今日一般情况可，查体无特殊变化。继续原方案治疗。\n请指出文书缺陷并提供改进版本。',
  '拒付管理专家':
    '请分析以下医保拒付案例的根因并提出系统改进方案：\n近3个月拒付统计：共15例，其中编码错误8例（53%），诊断依据不足4例（27%），手术编码缺失3例（20%）。最高频拒付编码：I25.101（3次）, M80.900（2次）, J18.900（2次）。',
  '审计追溯专家':
    '请追溯编码审核 ID REV-2025-001284 的完整审计链：谁在什么时间对哪个编码做了什么变更，变更前后的状态，以及变更依据。',
  'HCC 风险调整专家':
    '请评估以下患者的HCC风险评分并识别所有可捕获的HCC编码：\n患者女性76岁，诊断包括：2型糖尿病伴肾病（E11.21）、高血压（I10）、慢性心衰（I50.9）、慢性阻塞性肺病（J44.9）、骨质疏松伴病理性椎体骨折（M80.00）、重度抑郁（F32.2）。',
  'DRG/DIP Expert':
    '请分析以下病例的DRG分组风险：主要诊断M80.900（骨质疏松伴病理性骨折），主要手术81.6600x001（经皮椎体后凸成形术），其他诊断I10.x02（高血压）, E11.900（2型糖尿病）。请评估是否存在MCC/CC缺失风险。',
  'Documentation Gap Expert':
    '请审查以下编码结果中的文书缺口：主要诊断为J18.900（未特指肺炎），但病历中提到痰培养结果为肺炎克雷伯菌。请指出文书缺口并提供改进建议。',
  'Evidence Verification Expert':
    '请验证以下编码的证据支撑情况：\n1. I25.101（冠心病）- 证据：冠脉CTA示LAD中段狭窄70%\n2. I10.x02（高血压3级）- 证据：既往史提及\n3. E11.900（2型糖尿病）- 无直接证据\n请标注每个编码的证据等级。',
};

export default function ExpertLibraryPage() {
  const navigate = useNavigate();
  const t = useT();
  const [experts, setExperts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('');
  const [activeType, setActiveType] = useState<'all' | 'prebuilt' | 'custom'>('all');
  const [categories, setCategories] = useState<{ name: string; count: number }[]>([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [expandedExpertId, setExpandedExpertId] = useState<string | null>(null);
  const [selectedExpert, setSelectedExpert] = useState<any>(null);
  const [runInput, setRunInput] = useState('');
  const [runOutput, setRunOutput] = useState('');
  const [running, setRunning] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleteName, setDeleteName] = useState('');

  // BYO Expert state
  const [showByo, setShowByo] = useState(false);
  const [byoUrl, setByoUrl] = useState('');
  const [byoName, setByoName] = useState('');
  const [byoPrompt, setByoPrompt] = useState('');
  const [byoDiscovered, setByoDiscovered] = useState(0);
  const [discovering, setDiscovering] = useState(false);
  const [creating, setCreating] = useState(false);
  const [byoError, setByoError] = useState('');

  const handleDiscoverTools = async () => {
    setDiscovering(true); setByoError('');
    try {
      const res = await byoExpertApi.discover(byoUrl.trim());
      setByoDiscovered(res.data.count || res.data.tools?.length || 0);
    } catch (err: any) { setByoError(err?.response?.data?.detail || t.discoverToolsFailed); }
    finally { setDiscovering(false); }
  };

  const handleCreateByo = async () => {
    setCreating(true); setByoError('');
    try {
      await byoExpertApi.create(byoUrl.trim(), byoPrompt.trim(), byoName.trim() || t.customMcpExpert);
      setShowByo(false); setByoUrl(''); setByoPrompt(''); setByoName(''); setByoDiscovered(0);
      fetchExperts();
    } catch (err: any) { setByoError(err?.response?.data?.detail || t.createFailed); }
    finally { setCreating(false); }
  };

  const fetchExperts = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [expRes, catRes] = await Promise.allSettled([
        expertsApi.list(activeCategory, searchQuery, activeType),
        expertsApi.categories(),
      ]);
      if (expRes.status === 'fulfilled') setExperts(expRes.value.data.experts || []);
      if (catRes.status === 'fulfilled') setCategories(catRes.value.data.categories || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || t.loadExpertsFailed);
    } finally {
      setLoading(false);
    }
  }, [activeCategory, searchQuery, activeType]);

  useEffect(() => { fetchExperts(); }, [fetchExperts]);

  const handleDelete = async (id: string, name: string) => {
    setDeleteConfirm(id);
    setDeleteName(name);
  };
  const confirmDelete = async () => {
    if (!deleteConfirm) return;
    try {
      await expertsApi.delete(deleteConfirm);
      setExperts(experts.filter(e => e.id !== deleteConfirm));
      setDeleteConfirm(null);
      setDeleteName('');
    } catch (err: any) {
      setDeleteConfirm(null);
      setDeleteName('');
      setError(err?.response?.data?.detail || err.message || t.deleteFailed);
    }
  };

  const handleRun = async (expert: any) => {
    if (!runInput.trim()) return;
    setRunning(true);
    setRunOutput('');
    try {
      const res = await expertsApi.run(expert.id, runInput);
      setRunOutput(res.data.output);
    } catch (err: any) {
      setRunOutput(`${t.errorPrefix}${err?.response?.data?.detail || err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const handleOpenRun = (expert: any) => {
    setSelectedExpert(expert);
    setRunInput('');
    setRunOutput('');
  };

  const getIcon = (iconName: string) => {
    const Comp = ICON_MAP[iconName] || Bot;
    return <Comp size={20} />;
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="animate-spin h-8 w-8 text-muted-foreground" />
    </div>
  );

  return (
    <div className="p-6 bg-muted/20 h-full overflow-y-auto">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 mb-4 text-xs text-muted-foreground">
        <Link to="/" className="hover:text-foreground transition-colors flex items-center gap-1">
          <Home size={12} /> {t.home}
        </Link>
        <ChevronRight size={12} />
        <span className="text-foreground font-medium">{t.expertLibrary}</span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-foreground mb-2">{t.expertLibrary}</h2>
          <p className="text-sm text-muted-foreground max-w-xl">{t.expertLibraryDesc}</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowByo(!showByo)} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium border border-border text-foreground hover:bg-accent transition-colors">
            <Wrench size={14} /> {t.byoMcpExpert}
          </button>
          <button onClick={() => setShowAddModal(true)} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-sm shadow-primary/20">
            <Plus size={16} /> {t.addCustomExpert}
          </button>
        </div>
      </div>

      {/* BYO MCP Expert Panel */}
      {showByo && (
        <div className="bg-background rounded-xl shadow-sm ring-1 ring-primary/10 p-5 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-foreground">{t.bringYourOwnMcpExpert}</h3>
              <p className="text-xs text-muted-foreground mt-0.5">{t.byoMcpDesc}</p>
            </div>
            <button onClick={() => setShowByo(false)} className="text-muted-foreground hover:text-foreground"><X size={14} /></button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">{t.mcpServerUrl}</label>
              <input value={byoUrl} onChange={e => setByoUrl(e.target.value)} placeholder={t.mcpServerUrlPlaceholder} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring text-xs font-mono" />
            </div>
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">{t.expertName}</label>
              <input value={byoName} onChange={e => setByoName(e.target.value)} placeholder={t.myMcpExpert} className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring text-xs" />
            </div>
          </div>
          <div className="mt-3">
            <label className="text-xs font-medium text-foreground block mb-1">{t.systemPrompt}</label>
            <textarea value={byoPrompt} onChange={e => setByoPrompt(e.target.value)} placeholder={t.systemPromptPlaceholder} rows={3} className="w-full text-xs border border-border rounded-lg p-3 bg-transparent resize-none focus:outline-none focus:ring-1 focus:ring-ring" />
          </div>
          <div className="flex items-center gap-2 mt-3">
            <button onClick={handleDiscoverTools} disabled={!byoUrl.trim() || discovering} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-foreground hover:bg-accent transition-colors">
              {discovering ? <Loader2 size={12} className="animate-spin mr-1" /> : null}
              {discovering ? t.discoveringTools : t.discoverTools}
            </button>
            <button onClick={handleCreateByo} disabled={!byoUrl.trim() || !byoPrompt.trim() || creating} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-all shadow-sm shadow-primary/20">
              {creating ? t.creatingExpert : t.createExpert}
            </button>
          </div>
          {byoDiscovered > 0 && (
            <p className="text-xs text-secondary mt-2">{t.discoveredToolsCount.replace('{count}', String(byoDiscovered))}</p>
          )}
          {byoError && <p className="text-xs text-destructive mt-2">{byoError}</p>}
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        {/* Type filter */}
        <div className="flex items-center rounded-lg border border-border p-0.5">
          {([
            { id: 'all', label: t.all },
            { id: 'prebuilt', label: t.prebuilt },
            { id: 'custom', label: t.myExperts },
          ] as const).map((f) => (
            <button
              key={f.id}
              onClick={() => setActiveType(f.id)}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                activeType === f.id ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Category filter */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setActiveCategory('')}
            className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
              !activeCategory ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground hover:bg-accent'
            }`}
          >
            {t.allCategories}
          </button>
          {categories.map((cat) => (
            <button
              key={cat.name}
              onClick={() => setActiveCategory(cat.name)}
              className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                activeCategory === cat.name ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground hover:bg-accent'
              }`}
            >
              {CATEGORY_LABELS[cat.name] || cat.name} ({cat.count})
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {/* Search */}
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t.searchExperts}
            className="pl-7 pr-3 py-1.5 text-sm border border-border rounded-md bg-transparent focus:outline-none focus:ring-1 focus:ring-ring w-56"
          />
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError('')} className="text-destructive/60 hover:text-destructive">&times;</button>
        </div>
      )}

      {/* Expert Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {experts.map((expert) => (
          <div
            key={expert.id}
            className="bg-background rounded-xl shadow-sm ring-1 ring-border/20 p-5 hover:ring-primary/30 hover:shadow-md transition-all flex flex-col"
          >
            <div className="flex items-start gap-3 mb-3">
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                expert.is_prebuilt ? 'bg-primary/10 text-primary' : 'bg-accent text-foreground'
              }`}>
                {getIcon(expert.icon)}
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-foreground leading-tight">{expert.name}</h3>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  {CATEGORY_LABELS[expert.category] || expert.category}
                  {expert.is_prebuilt && t.prebuiltTag}
                  {expert.mcp_servers?.length > 0 && t.mcpCount.replace('{count}', String(expert.mcp_servers.length))}
                </p>
              </div>
            </div>

            <p className="text-xs text-muted-foreground line-clamp-3 mb-4 flex-1">{expert.description}</p>

            {expert.mcp_servers?.length > 0 && (
              <div className="mb-3">
                <div className="flex flex-wrap gap-1">
                  {expert.mcp_servers.map((srv: any) => (
                    <span key={srv.id} className="text-[10px] px-1.5 py-0.5 rounded bg-accent text-muted-foreground">
                      {srv.transport_type}: {srv.name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {expandedExpertId === expert.id && (
              <div className="mb-3 p-3 rounded-lg bg-muted/20 border border-border/50">
                <p className="text-[10px] text-muted-foreground leading-relaxed mb-2">{expert.description}</p>
                {expert.system_prompt && (
                  <pre className="text-[9px] text-muted-foreground whitespace-pre-wrap font-mono leading-relaxed max-h-24 overflow-y-auto">
                    {expert.system_prompt.slice(0, 300)}{expert.system_prompt.length > 300 ? '...' : ''}
                  </pre>
                )}
              </div>
            )}
            <div className="flex items-center gap-2 mt-auto pt-3 border-t border-border">
              <button
                onClick={() => setExpandedExpertId(expandedExpertId === expert.id ? null : expert.id)}
                className="text-[10px] text-primary hover:underline transition-colors shrink-0"
              >
                {expandedExpertId === expert.id ? t.showLess : t.readMore}
              </button>
              {EXPERT_DOCS[expert.name] && (
                <a
                  href={EXPERT_DOCS[expert.name]}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1 shrink-0"
                  title={t.viewDocumentation}
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink size={10} /> {t.documentation}
                </a>
              )}
              <button
                onClick={() => handleOpenRun(expert)}
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-sm shadow-primary/20 h-8"
              >
                <Play size={12} /> {t.run}
              </button>
              {!expert.is_prebuilt ? (
                <button
                  onClick={() => handleDelete(expert.id, expert.name)}
                  className="text-xs text-destructive/80 hover:text-destructive p-1.5 rounded hover:bg-destructive/10 transition-colors"
                  title={t.delete}
                >
                  <Trash2 size={14} />
                </button>
              ) : (
                <button
                  onClick={() => handleOpenRun(expert)}
                  className="text-xs text-muted-foreground hover:text-foreground p-1.5 rounded hover:bg-accent transition-colors"
                  title={t.viewDetails}
                >
                  <ArrowUpRight size={14} />
                </button>
              )}
            </div>
          </div>
        ))}

        {experts.length === 0 && (
          <div className="col-span-full text-center py-12 bg-background rounded-xl shadow-sm ring-1 ring-border/20">
            <Bot size={48} className="mx-auto mb-3 text-muted-foreground/30" />
            <p className="text-sm font-medium text-foreground mb-2">还没有专家</p>
            <p className="text-xs text-muted-foreground mb-4 max-w-md mx-auto leading-relaxed">
              专家是 Agent 的能力单元。每个专家擅长特定领域（如 ICD-10 编码、DRG 分析、病历质控）。
              创建专家后，可在 Agent 设置中绑定使用。
            </p>
            <button onClick={() => setShowAddModal(true)} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-sm shadow-primary/20">
              <Plus size={14} /> 创建第一个专家
            </button>
          </div>
        )}
      </div>

      {/* Run Expert Modal */}
      {selectedExpert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setSelectedExpert(null)}>
          <div
            className="bg-card rounded-xl border border-border shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-border">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                  {getIcon(selectedExpert.icon)}
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{selectedExpert.name}</h3>
                  <p className="text-[10px] text-muted-foreground">{CATEGORY_LABELS[selectedExpert.category] || selectedExpert.category} · {t.usageLabel}{selectedExpert.usage_count}</p>
                </div>
              </div>
              <button onClick={() => setSelectedExpert(null)} className="p-1 rounded hover:bg-accent transition-colors">
                <X size={16} className="text-muted-foreground" />
              </button>
            </div>

            <div className="p-4 flex-1 overflow-y-auto space-y-4">
              {selectedExpert.system_prompt && (
                <div>
                  <h4 className="text-xs font-semibold text-foreground mb-1.5 flex items-center gap-1">
                    <Wrench size={12} /> {t.systemPrompt}
                  </h4>
                  <pre className="text-xs font-mono bg-muted p-3 rounded border border-border whitespace-pre-wrap max-h-36 overflow-y-auto">
                    {selectedExpert.system_prompt.slice(0, 500)}{selectedExpert.system_prompt.length > 500 ? '...' : ''}
                  </pre>
                </div>
              )}

              {selectedExpert.mcp_servers?.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-foreground mb-1.5">{t.mcpServers} ({selectedExpert.mcp_servers.length})</h4>
                  <div className="space-y-1">
                    {selectedExpert.mcp_servers.map((srv: any) => (
                      <div key={srv.id} className="text-xs flex items-center gap-2 text-muted-foreground bg-muted/50 rounded px-2 py-1">
                        <span className="font-mono">{srv.name}</span>
                        <span>→</span>
                        <span className="text-[10px]">{srv.url}</span>
                        <span className="text-[10px] bg-accent px-1 rounded">{srv.transport_type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-xs font-semibold text-foreground">{t.inputLabel}</label>
                  <button
                    onClick={() => {
                      const example = EXPERT_EXAMPLES[selectedExpert?.name] || '';
                      if (example) setRunInput(example);
                    }}
                    className="text-[10px] text-primary hover:underline"
                  >
                    {t.useSample}
                  </button>
                </div>
                <textarea
                  value={runInput}
                  onChange={(e) => setRunInput(e.target.value)}
                  placeholder={EXPERT_EXAMPLES[selectedExpert?.name]
                    ? `${t.examplePrefix}${EXPERT_EXAMPLES[selectedExpert.name].slice(0, 80)}...`
                    : t.enterQueryOrClinicalText}
                  className="w-full h-24 resize-none border border-border rounded-lg p-3 text-sm bg-transparent focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>

              <button
                onClick={() => handleRun(selectedExpert)}
                disabled={!runInput.trim() || running}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-all shadow-sm shadow-primary/20"
              >
                {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                {running ? t.running : t.runExpert}
              </button>

              {runOutput && (
                <div className="border border-border rounded-lg p-4 bg-muted/30 max-h-60 overflow-y-auto">
                  <p className="text-sm text-foreground whitespace-pre-wrap">{runOutput}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Add Expert Modal */}
      {showAddModal && (
        <AddExpertModal
          onClose={() => setShowAddModal(false)}
          onCreated={() => { setShowAddModal(false); fetchExperts(); }}
        />
      )}

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setDeleteConfirm(null)}>
          <div className="bg-card rounded-xl border border-border shadow-xl w-full max-w-sm mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-5">
              <p className="text-sm font-medium text-foreground">{t.confirmDeleteExpert.replace('{name}', deleteName)}</p>
              <p className="text-xs text-muted-foreground mt-1">此操作不可撤销。</p>
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-muted/20">
              <button onClick={() => setDeleteConfirm(null)} className="text-xs px-4 py-2 rounded-lg hover:bg-accent transition-colors">取消</button>
              <button onClick={confirmDelete} className="text-xs px-4 py-2 rounded-lg bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors">确认</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
