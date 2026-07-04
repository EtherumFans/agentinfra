import { useLocaleStore } from '../i18n';
import { useT } from '../i18n';
// iCoDer Text Generation — Apple Minimalist Design
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen, Sparkles, Loader2,
  Copy, Check,
  X, Plus, Trash2, Pencil, Info, Shield, ChevronRight,
} from 'lucide-react';
import { authApi } from '../services/api';
import EventInspector from '../components/common/EventInspector';
import CodeSnippet from '../components/common/CodeSnippet';
import SettingsCodeTab from '../components/common/SettingsCodeTab';
import WorkbenchLayout from '../components/layout/WorkbenchLayout';

// Medical document template types from backend
interface MedDocSection { key: string; label: string; value: string; required: boolean; filled: boolean; }

// 文书模板 — 支持用户编辑
type Template = { key: string; name: string; desc: string; category: string; sample: string };

const DEFAULT_TEMPLATES: Template[] = [
  { key: 'discharge_summary', name: '出院小结', desc: '标准出院小结，包含入院情况、诊疗经过、出院诊断、出院医嘱', category: '住院',
    sample: '患者，男，65岁，因"反复胸闷、心悸3年，加重1周"入院。\n既往史：高血压病史10年，口服氨氯地平5mg qd；2型糖尿病史5年，口服二甲双胍0.5g tid。\n入院查体：T 36.5°C，P 78次/分，R 18次/分，BP 138/86mmHg。双肺呼吸音清，未闻及干湿啰音。心率78次/分，律齐，各瓣膜听诊区未闻及病理性杂音。\n辅助检查：冠脉造影示LAD中段狭窄75%。\n诊疗经过：行PCI术，于LAD中段植入药物洗脱支架1枚，术后抗血小板、调脂稳定斑块等治疗。\n出院诊断：1. 冠状动脉粥样硬化性心脏病 不稳定型心绞痛 PCI术后\n出院医嘱：1. 低盐低脂饮食，适当运动；2. 规律服药，定期门诊复查；3. 不适随诊。' },
  { key: 'admission_record', name: '入院记录', desc: '完整入院记录，含主诉、现病史、既往史、体格检查、初步诊断', category: '住院',
    sample: '主诉：腰痛4个月余。\n现病史：患者4月前无明显诱因出现腰痛，呈持续性钝痛，久坐久站后加重，卧床休息后稍缓解。近1月疼痛明显加重，VAS评分7分。否认外伤史。\n既往史：高血压病史5年，口服硝苯地平控制可。否认糖尿病史，否认肝炎、结核等传染病史。否认手术外伤史，否认药物过敏史。\n体格检查：T 36.3°C，P 72次/分，R 18次/分，BP 132/82mmHg。脊柱生理曲度改变，T7-L2棘突压痛和叩击痛明显，双下肢无水肿，双侧膝腱反射对称存在。\n辅助检查：胸腰椎MRI示：T7、T9、T12及L2椎体考虑为新鲜压缩骨折。\n初步诊断：1. 腰椎压缩性骨折 2. 胸椎压缩性骨折 3. 重度骨质疏松症 4. 高血压病' },
  { key: 'progress_note', name: '日常病程记录', desc: 'SOAP格式病程记录：主观、客观、评估、计划', category: '住院',
    sample: 'S（主观）：患者诉腰痛较前缓解，VAS评分3-4分，可自行翻身，无下肢放射痛及麻木感。\nO（客观）：T 36.2°C，P 70次/分，R 18次/分，BP 130/80mmHg。腰部敷料干燥，无渗血渗液，双下肢感觉运动正常。\nA（评估）：术后恢复良好，疼痛明显缓解，生命体征平稳，无并发症征象。\nP（计划）：1. 继续抗骨质疏松治疗；2. 指导功能锻炼；3. 明日复查X光片评估骨水泥位置。' },
  { key: 'preop_discussion', name: '术前讨论记录', desc: '术前讨论：手术指征、手术方案、风险评估、替代方案', category: '手术',
    sample: '讨论时间：2026年5月9日\n主持人：李主任（骨科主任医师）\n参加人员：张主治医师、王住院医师、麻醉科刘医师\n手术指征：患者L4/5椎间盘突出，左侧神经根受压，保守治疗3月无效，疼痛影响日常生活。\n手术方案：拟行L4/5椎间盘髓核摘除术（PLIF）。\n风险评估：ASA II级，心肺功能可耐受手术，术中出血风险可控。\n替代方案：已向患者说明保守治疗及微创方案，患者选择手术治疗。\n术前准备：备血2U，预防性抗生素皮试已做。' },
  { key: 'operation_record', name: '手术记录', desc: '手术经过、术中所见、标本送检、术中特殊情况', category: '手术',
    sample: '手术名称：T7、T9、T12、L2经皮穿刺脊柱后凸成形术\n手术日期：2026年5月9日\n麻醉方式：全麻\n手术经过：患者全麻后取俯卧位，C臂机定位T7、T9、T12、L2椎体双侧椎弓根。常规消毒铺巾后，穿刺针经皮穿刺进入椎弓根，球囊扩张恢复椎体高度，注入骨水泥。术中X光透视骨水泥分布良好，无渗漏。\n术中所见：椎体压缩约30-40%，骨水泥填充满意。\n术中出血：约50ml。\n标本送检：无。\n术者：李主任 助手：张主治医师' },
  { key: 'referral_letter', name: '转诊信', desc: '转诊至其他科室或医院，含转诊原因、已有检查、治疗建议', category: '门诊',
    sample: '转诊科室：心血管内科\n转诊原因：患者因"反复胸闷、胸痛2月"在我科就诊，心电图示ST-T改变，运动平板试验阳性，考虑冠心病可能，需进一步冠脉造影明确诊断。\n已有检查：血常规、心肌酶谱正常；心电图示V4-V6导联ST段下移0.1mV；心脏彩超示左室舒张功能减退。\n当前用药：阿司匹林100mg qd，阿托伐他汀20mg qn。\n建议：请贵科协助行冠脉造影检查，明确冠脉病变情况。' },
  { key: 'outpatient_note', name: '门诊就诊记录', desc: '通用门诊就诊记录，含主诉、查体、诊断、处理意见', category: '门诊',
    sample: '主诉：咳嗽、咳痰3天。\n现病史：3天前受凉后出现咳嗽，咳黄色黏痰，无发热，无胸闷气促。\n查体：T 36.8°C，咽部充血，双肺呼吸音粗，未闻及干湿啰音。\n诊断：急性支气管炎\n处理意见：1. 头孢呋辛酯 0.25g bid ×5天；2. 氨溴索30mg tid；3. 多饮水，注意休息；4. 如症状加重随时复诊。' },
  { key: 'emergency_note', name: '急诊记录', desc: '急诊就诊记录：来院方式、生命体征、急诊处理、离院方式', category: '急诊',
    sample: '来院方式：120急救车送入。\n主诉：突发胸痛2小时。\n生命体征：T 36.5°C，P 96次/分，R 22次/分，BP 160/95mmHg，SpO2 96%。\n急诊查体：神清，痛苦貌，双肺呼吸音清，心率96次/分，律齐。\n急诊心电图：V1-V4导联ST段抬高0.2-0.4mV。\n急诊处理：1. 吸氧；2. 阿司匹林300mg嚼服；3. 氯吡格雷600mg口服；4. 硝酸甘油0.5mg舌下含服；5. 通知心内科急会诊。\n离院方式：转CCU住院。' },
  { key: 'consultation_record', name: '会诊记录', desc: '科间会诊申请与意见：会诊目的、病史摘要、会诊意见', category: '住院',
    sample: '会诊申请科室：骨科 申请会诊科室：心内科\n会诊目的：患者拟行腰椎手术，既往冠心病史，请评估手术风险。\n病史摘要：患者，男，68岁，因腰椎间盘突出症拟行手术治疗。既往冠心病史3年，曾行冠脉支架植入术（LAD 1枚），目前口服阿司匹林+氯吡格雷双抗治疗中。\n会诊意见：患者冠心病 PCI术后，心功能I级，可耐受手术。建议：1. 术前停用双抗5天，改用低分子肝素桥接；2. 术中监测心电图和血压；3. 术后24小时恢复双抗治疗。\n会诊医师：刘主任医师' },
  { key: 'nursing_note', name: '护理记录', desc: '护理观察记录：生命体征、护理措施、病情变化、交班要点', category: '护理',
    sample: '生命体征：T 36.5°C，P 78次/分，R 18次/分，BP 135/82mmHg，SpO2 98%。\n护理措施：1. 术后卧床休息，轴线翻身q2h；2. 腰部伤口敷料观察，无渗血渗液；3. 双下肢感觉运动正常，足趾活动自如；4. 指导踝泵运动，预防DVT。\n病情变化：患者诉切口轻度疼痛，NRS评分3分，已通知医师。\n交班要点：1. 注意观察双下肢感觉运动；2. 指导功能锻炼循序渐进；3. 明日拔除尿管。' },
  { key: 'patient_summary', name: '患者摘要', desc: '面向非医学专业人士的患者就诊摘要，通俗易懂', category: '通用',
    sample: '就诊日期：2026年5月9日\n就诊科室：骨科\n您此次就诊的主要原因是：腰痛4个多月，最近1个月加重。\n经过MRI等检查，医生发现您的胸椎和腰椎有4个椎体存在压缩性骨折，同时伴有重度骨质疏松和高血压。\n医生为您进行了微创手术（椎体成形术），手术很顺利。术后您的腰痛明显缓解。\n您出院后需要注意：1. 避免弯腰、搬重物；2. 按时服用降压药和抗骨质疏松药物；3. 定期到骨科门诊复查；4. 如出现新的腰背痛或下肢麻木无力，请及时就医。' },
  { key: 'surgery_consent', name: '手术知情同意书', desc: '含手术名称、风险、并发症、替代方案，需医患双方签字', category: '手术',
    sample: '患者姓名：XXX 性别：男 年龄：65岁 病历号：XXXXXX\n疾病诊断：冠状动脉粥样硬化性心脏病 三支病变\n建议手术名称：冠状动脉旁路移植术（CABG）\n手术风险及并发症：1. 麻醉意外；2. 术中出血，可能需要输血；3. 术后感染（切口感染、肺部感染等）；4. 心律失常、心肌梗死；5. 脑卒中；6. 肾功能损伤；7. 桥血管闭塞需再次手术；8. 死亡风险约1-2%。\n替代医疗方案：1. 药物保守治疗；2. PCI支架植入术；3. 杂交手术。\n上述情况已向患者及家属详细说明，患者及家属表示理解并同意手术。\n患者签名：XXX 家属签名：XXX 医师签名：XXX\n日期：2026年5月10日' },
  { key: 'nursing_handoff', name: '护理交班报告', desc: '结构化交班：患者基本信息、病情变化、重点观察、待办事项', category: '护理',
    sample: '交班日期：2026年5月9日 班次：白班→夜班\n患者：张三，男，65岁，骨科6床，住院号123456\n诊断：腰椎压缩性骨折 PKP术后第2天\n生命体征：T 36.3°C，P 72次/分，R 18次/分，BP 132/82mmHg，SpO2 98%\n本班病情变化：患者诉腰部切口疼痛NRS 3分，已予曲马多50mg肌注后缓解。下午自行排尿1次，量约400ml。\n重点观察：1. 双下肢感觉运动q2h；2. 切口敷料有无渗血；3. 疼痛评分\n待办事项：1. 明晨抽血复查电解质；2. 指导佩戴腰围下床活动；3. 拔除尿管\n交班护士：李护士 接班护士：王护士' },
  { key: 'discharge_education', name: '出院健康宣教', desc: '出院指导：用药、饮食、活动、复查、危险信号', category: '护理',
    sample: '患者：王五，诊断：2型糖尿病，住院号：789012\n一、用药指导\n1. 二甲双胍0.5g 每日2次（早晚餐后口服）\n2. 甘精胰岛素10U 每晚22:00皮下注射\n3. 请勿自行停药或调整剂量\n二、饮食指导\n1. 低糖、低脂、适量优质蛋白饮食；2. 定时定量，少食多餐；3. 每日食盐<6g；4. 戒烟限酒\n三、活动指导\n1. 每日步行30分钟；2. 避免空腹运动；3. 运动前后监测血糖\n四、复查计划\n1. 出院后1周到内分泌科门诊复查；2. 每3个月查糖化血红蛋白；3. 每年查眼底、肾功能\n五、危险信号（出现以下情况立即就医）\n1. 血糖<3.9mmol/L或>16.7mmol/L；2. 意识模糊、恶心呕吐；3. 足部破溃感染' },
  { key: 'medication_reconciliation', name: '用药重整记录', desc: '入院/转科/出院时用药核对与调整，减少用药差错', category: '住院',
    sample: '重整节点：入院重整\n患者：李四，男，72岁\n入院前用药：\n1. 氨氯地平5mg qd（降压）\n2. 阿司匹林100mg qd（抗血小板）\n3. 二甲双胍0.5g tid（降糖）\n4. 布洛芬200mg tid（关节疼痛，自行购买）\n入院后调整：\n1. 氨氯地平5mg qd —— 继续\n2. 阿司匹林100mg qd —— 继续\n3. 二甲双胍0.5g tid —— 继续，加测HbA1c\n4. 布洛芬 —— 停用（可能影响肾功能，改为对乙酰氨基酚必要时）\n新增：\n5. 胰岛素（根据血糖调整）\n6. 奥美拉唑20mg qd（护胃）\n药师审核：张药师 医师确认：刘主治' },
  { key: 'imaging_report', name: '影像检查报告', desc: 'CT/MRI/X光检查所见、影像诊断、建议', category: '检查',
    sample: '检查项目：胸部CT平扫\n检查日期：2026年5月9日\n检查所见：双肺纹理增粗、紊乱，右肺上叶后段见片状高密度影，边界模糊，大小约3.2×2.8cm，其内可见支气管充气征。双肺散在多发小结节影，直径约3-5mm。纵隔居中，纵隔内未见明显肿大淋巴结。双侧胸腔无积液。\n影像诊断：\n1. 右肺上叶后段炎症，考虑感染性病变可能性大，建议治疗后复查\n2. 双肺多发小结节，建议随访观察\n3. 慢性支气管炎改变\n报告医师：赵医生 审核医师：钱主任' },
  { key: 'pathology_report', name: '病理检查报告', desc: '大体所见、镜下所见、病理诊断、免疫组化', category: '检查',
    sample: '送检标本：右肺上叶切除标本\n大体所见：肺叶大小15×10×5cm，切面见一灰白色结节，大小3.0×2.5×2.0cm，边界不清，质地硬，距支气管切缘2.0cm。\n镜下所见：肿瘤细胞呈腺管状、乳头状排列，细胞异型性明显，核分裂象易见。肿瘤侵犯脏层胸膜。支气管切缘未见肿瘤。淋巴结：第7组（0/3），第10组（1/5）见肿瘤转移。\n病理诊断：\n1. 右肺上叶中分化腺癌，腺泡型为主，部分乳头型\n2. 肿瘤大小3.0×2.5×2.0cm\n3. 脏层胸膜受侵（+）\n4. 支气管切缘（-）\n5. 淋巴结转移：第10组（1/5）\n6. pTNM分期：pT2aN1M0，IIB期\n免疫组化：TTF-1(+)，Napsin A(+)，CK7(+)，CK5/6(-)，P40(-)，Ki-67(30%+)\n报告日期：2026年5月12日' },
  { key: 'icu_daily_note', name: 'ICU日常记录', desc: 'ICU每日评估：器官功能、液体管理、感染指标、镇静评分', category: '住院',
    sample: '日期：2026年5月10日 ICU第3天\n意识状态：镇静状态，RASS评分-2，GCS评分E3VTM5\n呼吸：呼吸机辅助通气，模式SIMV+PS，FiO2 0.35，PEEP 5cmH2O，RR 16次/分，SpO2 97%\n循环：HR 88次/分，BP 115/70mmHg（去甲肾上腺素0.05μg/kg/min维持），CVP 8mmHg\n24h入量：晶体1500ml + 胶体500ml + 肠内营养500ml = 2500ml\n24h出量：尿量1200ml + 胃管引流100ml + 伤口引流50ml = 1350ml\n平衡：+1150ml\n感染指标：WBC 12.3×10⁹/L，PCT 1.8ng/mL，CRP 86mg/L\n抗生素：头孢哌酮舒巴坦3.0g q8h ivgtt（第3天）\n计划：1. 继续目前呼吸机支持，评估脱机条件；2. 维持液体平衡；3. 明日复查PCT。' },
  { key: 'death_summary', name: '死亡记录', desc: '入院情况、诊疗经过、死亡原因、死亡诊断', category: '住院',
    sample: '患者：赵六，男，78岁，住院号：345678\n入院日期：2026年5月1日 死亡日期：2026年5月15日 住院天数：15天\n入院情况：因突发胸痛2小时入院。既往冠心病史5年，2型糖尿病史10年。\n诊疗经过：入院后心电图示急性广泛前壁心肌梗死，急诊行PCI术，于LAD植入支架1枚。术后第5天出现心源性休克，予IABP辅助，多巴胺+去甲肾上腺素维持血压。第10天出现急性肾损伤，予CRRT治疗。第14天出现多器官功能衰竭。\n死亡原因：1. 急性心肌梗死；2. 心源性休克；3. 多器官功能衰竭\n死亡诊断：1. 冠状动脉粥样硬化性心脏病 急性广泛前壁心肌梗死 PCI术后；2. 心源性休克；3. 急性肾损伤；4. 2型糖尿病\n家属告知：已通知家属，家属表示理解。\n记录医师：孙主任' },
];

const INPUT_TYPES = [
  { key: 'string', label: '字符串' },
  { key: 'text', label: '自由文本' },
  { key: 'transcript', label: '对话转录' },
  { key: 'facts', label: '结构化事实' },
  { key: 'json', label: 'JSON' },
];

const LANGUAGES = [
  { code: 'zh-CN', label: '简体中文' },
  { code: 'en-US', label: '英文 (美国)' },
];

const TEMPLATE_CATEGORIES = ['全部', '住院', '门诊', '手术', '急诊', '护理', '通用'];

export default function TextGenerationPage() {
  const locale = useLocaleStore(s => s.locale);
  const t = useT();
  const [templates, setTemplates] = useState<Template[]>(() => {
    const saved = localStorage.getItem('icoder-textgen-templates');
    return saved ? JSON.parse(saved) : DEFAULT_TEMPLATES;
  });
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [cost, setCost] = useState('0.000000');

  const [inputType, setInputType] = useState('text');
  const [activeTemplate, setActiveTemplate] = useState('');
  const [outputLang, setOutputLang] = useState('zh-CN');
  const [docName, setDocName] = useState('');
  const [showGuardrails, setShowGuardrails] = useState(true);
  const [docMode, setDocMode] = useState('standard');
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [templateSearch, setTemplateSearch] = useState('');
  const [templateCategory, setTemplateCategory] = useState('全部');
  const [copied, setCopied] = useState(false);
  const [genEvents, setGenEvents] = useState<{type:string;data:Record<string,unknown>;timestamp:string;credits?:number}[]>([]);
  const [genCredits, setGenCredits] = useState(0);

  // Template editing
  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null);
  const [showTemplateEditor, setShowTemplateEditor] = useState(false);
  const [editKey, setEditKey] = useState('');
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [editCategory, setEditCategory] = useState('住院');
  const [editSample, setEditSample] = useState('');

  // Delete confirmation state (replaces confirm())
  const [deleteConfirmKey, setDeleteConfirmKey] = useState<string | null>(null);

  // Fetch templates from API on mount, merging with user customizations
  useEffect(() => {
    // text-gen router deleted in Phase 2.1-B Step 4 — keep localStorage templates
    const prevStr = localStorage.getItem('icoder-textgen-templates');
    if (prevStr) {
      try { setTemplates(JSON.parse(prevStr)); } catch { /* keep defaults */ }
    }
  }, []);

  // Persist templates to localStorage
  useEffect(() => {
    localStorage.setItem('icoder-textgen-templates', JSON.stringify(templates));
  }, [templates]);

  const filteredTemplates = templates.filter(t => {
    if (templateCategory !== '全部' && t.category !== templateCategory) return false;
    if (templateSearch && !t.name.includes(templateSearch) && !t.key.includes(templateSearch) && !t.desc.includes(templateSearch)) return false;
    return true;
  });

  const currentTemplate = templates.find(t => t.key === activeTemplate);

  const handleGenerate = async () => {
    if (!input.trim() || !activeTemplate) return;
    setLoading(true); setError(''); setOutput('');
    setGenEvents(prev => [...prev.slice(-50), { type: 'generate_start', data: { template: activeTemplate, inputLength: input.length }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }), credits: 0.000001 }]);
    setGenCredits(c => c + 0.000001);
    try {
      // text-gen router deleted in Phase 2.1-B Step 4 — use /api/v2/tools/guided-documents for document generation
      throw new Error('Text Generation API has been deprecated. Use /api/v2/tools/guided-documents for document generation.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || '生成失败');
      setGenEvents(prev => [...prev.slice(-50), { type: 'generate_error', data: { error: err?.response?.data?.detail || err.message || '未知错误', template: activeTemplate }, timestamp: new Date().toLocaleTimeString(locale, { hour12: false }) }]);
    } finally {
      setLoading(false);
    }
  };

  const handleUseSample = () => {
    if (!currentTemplate) return;
    setInput(currentTemplate.sample);
    setInputType('text');
  };

  // Template CRUD
  const openNewTemplate = () => {
    setEditingTemplate(null);
    setEditKey(''); setEditName(''); setEditDesc(''); setEditCategory('住院'); setEditSample('');
    setShowTemplateEditor(true);
  };

  const openEditTemplate = (t: Template) => {
    setEditingTemplate(t);
    setEditKey(t.key); setEditName(t.name); setEditDesc(t.desc);
    setEditCategory(t.category); setEditSample(t.sample);
    setShowTemplateEditor(true);
  };

  const saveTemplate = () => {
    if (!editKey.trim() || !editName.trim()) return;
    const t: Template = {
      key: editKey.trim().replace(/\s+/g, '_').toLowerCase(),
      name: editName.trim(),
      desc: editDesc.trim(),
      category: editCategory,
      sample: editSample,
    };
    if (editingTemplate) {
      setTemplates(prev => prev.map(x => x.key === editingTemplate.key ? t : x));
    } else {
      setTemplates(prev => [...prev, t]);
    }
    setShowTemplateEditor(false);
  };

  const handleDeleteTemplate = (key: string) => {
    setTemplates(prev => prev.filter(t => t.key !== key));
    if (activeTemplate === key) setActiveTemplate('');
    setDeleteConfirmKey(null);
  };

  const embedCode = `import { iCoDerClient } from "@icoder/sdk";
const client = new iCoDerClient({ apiKey: "YOUR_API_KEY" });
const result = await client.textGen.generate({
  input: "临床文本...",
  template: "${activeTemplate || 'discharge_summary'}",
  language: "${outputLang}",
  mode: "${docMode}",
});`;

  const embedCodePython = `from icoder_sdk import iCoDerClient

client = iCoDerClient(api_key="YOUR_API_KEY")

result = client.text_generation.generate(
    input="临床文本...",
    template="${activeTemplate || 'discharge_summary'}",
    language="${outputLang}",
    mode="${docMode}",
)
print(result.output)`;

  const embedCodeJson = `{
  "apiKey": "YOUR_API_KEY",
  "input": "临床文本...",
  "template": "${activeTemplate || 'discharge_summary'}",
  "language": "${outputLang}",
  "mode": "${docMode}"
}`;

  const settingsPanel = (
    <div className="flex flex-col">
      {/* 模板 section */}
      <div className="border-b border-border/20">
        <div className="flex items-center gap-2 px-4 pt-4 pb-2">
          <div className="w-1 h-4 rounded-full bg-primary/40" />
          <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">模板</h3>
        </div>
        <div className="px-4 pb-4">
          <button onClick={() => setShowTemplateModal(true)}
            className="w-full py-2 rounded-lg border border-border hover:bg-accent transition-colors text-sm flex items-center justify-center gap-2">
            <BookOpen size={14} /> 选择模板
          </button>
          {activeTemplate && (
            <p className="text-xs text-center text-muted-foreground mt-2">当前: {currentTemplate?.name}</p>
          )}
        </div>
      </div>

      {/* 文书设置 section */}
      <div className="border-b border-border/20">
        <div className="flex items-center gap-2 px-4 pt-4 pb-2">
          <div className="w-1 h-4 rounded-full bg-primary/40" />
          <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">文书设置</h3>
        </div>
        <div className="flex flex-col gap-3 px-4 pb-4 pt-1">
          <div className="flex items-center justify-between gap-4 min-h-[32px]">
            <span className="text-sm text-foreground/80">输出语言</span>
            <select value={outputLang} onChange={e => setOutputLang(e.target.value)}
              className="h-8 text-xs border border-input bg-background rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-ring">
              {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </div>
          <div className="flex items-center justify-between gap-4 min-h-[32px]">
            <span className="text-sm text-foreground/80">文书名称</span>
            <input value={docName} onChange={e => setDocName(e.target.value)} placeholder="自定义..."
              className="h-8 text-xs border border-input bg-background rounded-md px-2 py-1 w-28 focus:outline-none focus:ring-2 focus:ring-ring" />
          </div>
          <div className="flex items-center justify-between gap-4 min-h-[32px]">
            <span className="text-sm text-foreground/80">质控模式</span>
            <select value={docMode} onChange={e => setDocMode(e.target.value)}
              className="h-8 text-xs border border-input bg-background rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-ring">
              <option value="standard">标准</option>
              <option value="strict">严格</option>
              <option value="draft">草稿</option>
            </select>
          </div>
        </div>
      </div>

      {/* 安全护栏 section */}
      <div className="px-4 pt-4 pb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-1 h-4 rounded-full bg-primary/40" />
            <h3 className="font-medium text-xs uppercase tracking-wider text-muted-foreground">安全护栏</h3>
          </div>
          <span className="relative group">
            <Info size={12} className="text-muted-foreground cursor-help" />
            <div className="absolute bottom-full right-0 mb-1.5 w-56 p-2 text-[10px] leading-relaxed bg-popover text-popover-foreground rounded-lg shadow-lg border border-border opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
              护栏规则在每次请求前后执行检查。关闭后请求将跳过所有护栏验证，建议仅在调试时使用。
            </div>
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-foreground/80 flex items-center gap-1">
            <Shield size={12} className="text-primary" /> 护栏
          </span>
          <button onClick={() => setShowGuardrails(!showGuardrails)}
            className={`relative w-9 h-5 rounded-full transition-colors shrink-0 ${showGuardrails ? 'bg-primary' : 'bg-muted border border-border'}`}>
            <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-all ${showGuardrails ? 'left-[18px]' : 'left-0.5'}`} />
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground mt-2">{showGuardrails ? '护栏已启用 — 请求将经过安全规则检查' : '护栏已禁用 — 请求跳过安全检查'}</p>
      </div>
    </div>
  );

  const codePanel = (
    <CodeSnippet
      javascript={embedCode}
      python={embedCodePython}
      json={embedCodeJson}
    />
  );

  const inputSlot = (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between shrink-0 mb-2">
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-border p-0.5">
            {INPUT_TYPES.map(t => (
              <button key={t.key} onClick={() => setInputType(t.key)}
                className={`px-2.5 py-1 text-[11px] rounded-md transition-colors ${inputType === t.key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>{t.label}</button>
            ))}
          </div>
          <button onClick={handleUseSample} disabled={!activeTemplate}
            className="text-xs border border-border rounded px-2 py-1 hover:bg-accent disabled:opacity-30 transition-colors">使用样例</button>
        </div>
      </div>
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={inputType === 'transcript' ? '输入对话转录文本...' : inputType === 'facts' ? '输入结构化临床事实...' : '输入临床文本...'}
        className="flex-1 w-full resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none min-h-0 leading-relaxed"
      />
    </div>
  );

  const outputSlot = (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between shrink-0 mb-2">
        <div className="flex items-center gap-2">
          {activeTemplate && currentTemplate && (
            <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary">{currentTemplate.name}</span>
          )}
          {!activeTemplate && (
            <span className="text-[11px] text-muted-foreground">请选择模板</span>
          )}
        </div>
        <button onClick={handleGenerate} disabled={!input.trim() || !activeTemplate || loading}
          className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-30 transition-all shadow-sm shadow-primary/20">
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
          {loading ? '生成中...' : '生成文书'}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
            <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
            <span className="text-sm">生成中...</span>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full px-5">
            <p className="text-sm text-red-500">{error}</p>
          </div>
        ) : output ? (
          <div className="p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="w-1 h-4 rounded-full bg-primary/40" />
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">生成结果</span>
              </div>
              <button onClick={() => { navigator.clipboard.writeText(output); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
                {copied ? <Check size={12} /> : <Copy size={12} />}
                {copied ? '已复制' : '复制'}
              </button>
            </div>
            <div className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">{output}</div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground/50">
            <Sparkles size={28} />
            <p className="text-sm">生成的文书将显示在这里</p>
          </div>
        )}
      </div>
    </div>
  );

  const settingsSlot = (
    <SettingsCodeTab
      labels={{ settings: '设置', code: '代码' }}
      settings={settingsPanel}
      code={codePanel}
    />
  );

  const inspectorSlot = (
    <EventInspector events={genEvents} creditsConsumed={genCredits} />
  );

  return (
    <>
      <WorkbenchLayout
        title={t.textGenBreadcrumb}
        description="基于医疗文书模板快速生成结构化临床文档"
        inputLabel="输入"
        outputLabel="输出"
        input={inputSlot}
        output={outputSlot}
        settings={settingsSlot}
        eventInspector={inspectorSlot}
      />

      {/* Template Editor Modal */}
      {showTemplateEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowTemplateEditor(false)}>
          <div className="bg-card rounded-xl border border-border shadow-2xl w-full max-w-lg max-h-[80vh] overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-border">
              <h3 className="text-sm font-semibold">{editingTemplate ? '编辑模板' : '新建模板'}</h3>
              <button onClick={() => setShowTemplateEditor(false)} className="p-1 rounded hover:bg-accent"><X size={14} className="text-muted-foreground" /></button>
            </div>
            <div className="px-5 py-4 space-y-4 overflow-y-auto max-h-[60vh]">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium block mb-1">模板键 <span className="text-red-400">*</span></label>
                  <input value={editKey} onChange={e => setEditKey(e.target.value)} placeholder="discharge_summary" className="w-full text-xs border border-border rounded-lg px-3 py-2 bg-transparent font-mono" />
                </div>
                <div>
                  <label className="text-xs font-medium block mb-1">名称 <span className="text-red-400">*</span></label>
                  <input value={editName} onChange={e => setEditName(e.target.value)} placeholder="出院小结" className="w-full text-xs border border-border rounded-lg px-3 py-2 bg-transparent" />
                </div>
              </div>
              <div>
                <label className="text-xs font-medium block mb-1">描述</label>
                <input value={editDesc} onChange={e => setEditDesc(e.target.value)} placeholder="简要描述模板用途" className="w-full text-xs border border-border rounded-lg px-3 py-2 bg-transparent" />
              </div>
              <div>
                <label className="text-xs font-medium block mb-1">分类</label>
                <select value={editCategory} onChange={e => setEditCategory(e.target.value)} className="w-full text-xs border border-border rounded-lg px-3 py-2 bg-transparent">
                  {TEMPLATE_CATEGORIES.filter(c => c !== '全部').map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs font-medium block mb-1">样例文本 <span className="text-muted-foreground font-normal">（点击"使用样例"时填入编辑器的内容）</span></label>
                <textarea value={editSample} onChange={e => setEditSample(e.target.value)}
                  placeholder="输入格式化的示例临床文本..."
                  rows={8}
                  className="w-full text-xs border border-border rounded-lg px-3 py-2 bg-transparent resize-none focus:outline-none focus:ring-1 focus:ring-ring font-mono" />
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-muted/30">
              <button onClick={() => setShowTemplateEditor(false)} className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-accent">取消</button>
              <button onClick={saveTemplate} disabled={!editKey.trim() || !editName.trim()}
                className="text-xs px-4 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 flex items-center gap-1.5">
                <Plus size={12} /> {editingTemplate ? '保存' : '添加模板'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Template Selection Modal */}
      {showTemplateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowTemplateModal(false)}>
          <div className="bg-card border border-border rounded-2xl shadow-xl w-[480px] max-h-[600px] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-border">
              <h3 className="text-sm font-semibold text-foreground">选择模板</h3>
              <div className="flex items-center gap-2">
                <button onClick={(e) => { e.stopPropagation(); openNewTemplate(); setShowTemplateModal(false); }}
                  className="text-xs px-2 py-1 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-1">
                  <Plus size={12} /> 新建
                </button>
                <button onClick={() => setShowTemplateModal(false)} className="p-1 rounded hover:bg-accent"><X size={16} /></button>
              </div>
            </div>
            <div className="p-3 border-b border-border">
              <input value={templateSearch} onChange={e => setTemplateSearch(e.target.value)}
                placeholder="搜索模板..." className="w-full text-xs border border-border rounded-lg px-3 py-2 bg-card" />
            </div>
            <div className="flex gap-1 px-4 py-2 flex-wrap border-b border-border">
              {TEMPLATE_CATEGORIES.map(c => (
                <button key={c} onClick={() => setTemplateCategory(c)}
                  className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${templateCategory === c ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground hover:bg-accent'}`}>{c}</button>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto py-1">
              {templates.filter(t => {
                if (templateCategory !== '全部' && t.category !== templateCategory) return false;
                if (templateSearch && !t.name.includes(templateSearch) && !t.desc.includes(templateSearch)) return false;
                return true;
              }).map(t => (
                <div key={t.key}
                  onClick={() => { setActiveTemplate(t.key); setShowTemplateModal(false); }}
                  className={`w-full text-left px-5 py-3 hover:bg-accent transition-colors border-b border-border/30 last:border-0 cursor-pointer group ${activeTemplate === t.key ? 'bg-primary/5' : ''}`}>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{t.name}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{t.category}</span>
                    <div className="flex-1" />
                    {deleteConfirmKey === t.key ? (
                      <span className="flex items-center gap-1 text-[10px]" onClick={e => e.stopPropagation()}>
                        <button onClick={() => handleDeleteTemplate(t.key)}
                          className="px-1.5 py-0.5 rounded bg-destructive text-destructive-foreground">确认删除</button>
                        <button onClick={() => setDeleteConfirmKey(null)}
                          className="px-1.5 py-0.5 rounded border border-border">取消</button>
                      </span>
                    ) : (
                      <span className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
                        <button onClick={() => openEditTemplate(t)}
                          className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors" title="编辑模板">
                          <Pencil size={12} />
                        </button>
                        <button onClick={() => setDeleteConfirmKey(t.key)}
                          className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors" title="删除模板">
                          <Trash2 size={12} />
                        </button>
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{t.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
