"""Phase 5 Track B-2 — Fixtures Generator

Generates 12 synthetic de-identified clinical case fixtures per PDF §4 spec.
Each fixture covers a distinct clinical scenario and supports the 9 runnable iCoDer agents.

Output: fixtures/phase5_track_b2/01-12_*.json
Quality report: outputs/phase5_track_b2/fixture_quality_report.json

Fixtures are SYNTHETIC_FIXTURE — Claude-generated with medical knowledge, NOT real patient data.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "fixtures" / "phase5_track_b2"
OUTPUTS_DIR = ROOT / "outputs" / "phase5_track_b2"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

SYNTHETIC_TAG = "SYNTHETIC_FIXTURE"

# All 9 runnable iCoDer agents
ALL_AGENTS = [
    "medical-coding-agent",
    "code-validation-agent",
    "compliance-guardrail-agent",
    "note-completeness-agent",
    "procedure-extractor",
    "evidence-extractor",
    "principal-diagnosis-review",
    "discharge-summary-structuring",
    "drg-analyzer",
]


def _record(
    fixture_id: str,
    department: str,
    intended_agents: list[str],
    input_text: str,
    structured_context: dict[str, Any],
    known_facts: list[str],
    negated_facts: list[str] | None = None,
    historical_facts: list[str] | None = None,
    missing_information: list[str] | None = None,
    expected_risks: list[str] | None = None,
    gold_codes: list[str] | None = None,
    not_for_quality_scoring: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "tag": SYNTHETIC_TAG,
        "department": department,
        "intended_agents": intended_agents,
        "input_text": input_text,
        "structured_context": structured_context,
        "known_facts": known_facts,
        "negated_facts": negated_facts or [],
        "historical_facts": historical_facts or [],
        "missing_information": missing_information or [],
        "expected_risks": expected_risks or [],
        "gold_codes": gold_codes or [],
        "not_for_quality_scoring": not_for_quality_scoring,
        "notes": notes,
    }


# ============================================================================
# 12 fixtures — clinical scenarios
# ============================================================================

FIXTURES: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# 01 — Orthopedics (T12 compression fracture, reuse Phase 4-F3 gold case)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="01_orthopedics",
    department="骨科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者男性,78岁,因「摔伤后腰背部疼痛伴活动受限 1 天」入院。"
        "1 天前在家不慎滑倒,臀部着地,当即感腰背部剧痛,活动受限,无法自行起身。"
        "否认昏迷史,否认头痛、恶心、呕吐,否认胸闷、气促,否认腹部外伤。"
        "既往有高血压病史 10 年,长期口服氨氯地平 5mg qd,血压控制可。"
        "否认糖尿病、冠心病史。否认手术史。否认药物过敏史。"
        "查体:T 36.5℃,P 82 次/分,R 18 次/分,BP 145/85mmHg。"
        "神清,心肺查体未见明显异常。腹软,无压痛反跳痛。"
        "腰背部 T12 棘突压痛(+),叩击痛(+),双下肢感觉运动正常,末梢血运可。"
        "辅助检查:MRI 显示 T12 椎体压缩性骨折,椎体高度丢失约 1/3;CT 未见椎管狭窄。"
        "骨密度 T 值 -3.2(骨质疏松)。"
        "入院诊断:T12 椎体压缩性骨折;骨质疏松性骨折;高血压病 3 级(很高危)。"
        "治疗计划:卧床休息;镇痛;抗骨质疏松治疗(唑来膦酸);必要时行 PKP/PVP。"
    ),
    structured_context={
        "age": 78,
        "sex": "男",
        "encounter_type": "inpatient",
        "admission_type": "急诊",
        "primary_complaint": "腰背部疼痛伴活动受限 1 天",
        "los_days": 7,
    },
    known_facts=[
        "T12 椎体压缩性骨折",
        "骨质疏松性骨折",
        "高血压病 3 级",
        "MRI 确诊",
        "骨密度 T 值 -3.2",
    ],
    negated_facts=["否认昏迷史", "否认糖尿病", "否认冠心病", "否认手术史", "否认药物过敏"],
    historical_facts=["高血压病史 10 年"],
    expected_risks=[
        "osteoporosis_pathologic_fracture",
        "elderly_fall_risk",
        "anticoagulation_due_to_hypertension_medication",
    ],
    gold_codes=["S22.000", "M80.900", "I10.x00"],
    notes="Phase 4-F3 gold case; expected primary S22.000 (T12 compression fracture).",
))


# ---------------------------------------------------------------------------
# 02 — Cardiology (AMI + PCI)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="02_cardiology",
    department="心血管内科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者男性,62岁,因「突发胸骨后压榨样疼痛 3 小时」急诊入院。"
        "3 小时前无明显诱因出现胸骨后压榨样疼痛,向左肩、左上肢放射,伴大汗、恶心,"
        "无呕吐,含服硝酸甘油未缓解。"
        "急诊心电图示:V1-V4 ST 段弓背向上抬高 0.3-0.5mV,II/III/aVF ST 段压低。"
        "肌钙蛋白 I 12.5 ng/mL(参考值 <0.04)。"
        "急诊冠脉造影:LAD 近段 100% 闭塞,RCA 中段 80% 狭窄,LCX 30% 狭窄。"
        "行 LAD PCI 术,植入药物洗脱支架 1 枚,术后 TIMI 血流 3 级。"
        "既往:吸烟 40 年,每日 20 支;否认高血压、糖尿病史。"
        "父亲 65 岁心肌梗死病史。"
        "查体:BP 110/70mmHg,HR 96 次/分,双肺底未闻及啰音。"
        "入院诊断:急性前壁 ST 段抬高型心肌梗死(Killip II 级);冠状动脉单支病变(PCI 术后);"
        "高脂血症;吸烟者。"
    ),
    structured_context={
        "age": 62,
        "sex": "男",
        "encounter_type": "inpatient",
        "admission_type": "急诊",
        "primary_complaint": "突发胸骨后压榨样疼痛 3 小时",
        "procedure": "PCI (LAD DES × 1)",
        "los_days": 7,
    },
    known_facts=[
        "急性前壁 STEMI",
        "LAD 100% 闭塞",
        "PCI 植入 DES 1 枚",
        "cTnI 12.5 ng/mL",
        "Killip II 级",
    ],
    negated_facts=["否认高血压", "否认糖尿病", "无呕吐"],
    historical_facts=["吸烟 40 年", "父亲 65 岁 MI"],
    expected_risks=[
        "stent_thrombosis",
        "post_mi_heart_failure",
        "contraindication_of_anticoagulation",
    ],
    gold_codes=["I21.001", "I25.100", "Z95.500", "E78.500"],
    notes="STEMI + PCI case; primary I21.001 (acute anterior STEMI).",
))


# ---------------------------------------------------------------------------
# 03 — Respiratory (COPD exacerbation + pneumonia)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="03_respiratory",
    department="呼吸内科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者女性,72岁,因「反复咳嗽、咳痰 20 年,加重伴发热、气促 5 天」入院。"
        "20 年来反复咳嗽、咳白粘痰,冬春季节好发,曾诊断「慢性阻塞性肺疾病」。"
        "5 天前受凉后症状加重,咳黄脓痰,量多,伴发热(T 38.5℃),"
        "活动后气促明显,夜间不能平卧。"
        "3 天前开始使用家庭无创呼吸机辅助通气。"
        "既往:高血压史 15 年。否认结核、哮喘、糖尿病史。吸烟 30 年,每日 15 支,已戒 5 年。"
        "查体:T 38.2℃,P 102 次/分,R 26 次/分,BP 145/80mmHg,SpO2 88%(室内空气)。"
        "神清,口唇轻度紫绀,桶状胸,双肺呼吸音低,双下肺可闻及湿啰音及哮鸣音。"
        "血常规:WBC 13.2×10^9/L,N 85%,CRP 86 mg/L。"
        "胸部 CT:双肺弥漫性肺气肿,右下肺斑片状渗出影,双侧少量胸腔积液。"
        "痰培养:铜绿假单胞菌 2+。肺功能:FEV1/FVC 56%,FEV1 占预计值 48%。"
        "入院诊断:慢性阻塞性肺疾病急性加重期(II 级);社区获得性肺炎(重症);"
        "呼吸衰竭(II 型);高血压病 2 级。"
    ),
    structured_context={
        "age": 72,
        "sex": "女",
        "encounter_type": "inpatient",
        "admission_type": "急诊",
        "primary_complaint": "咳嗽咳痰加重伴发热气促 5 天",
        "los_days": 10,
    },
    known_facts=[
        "COPD 急性加重",
        "社区获得性肺炎",
        "铜绿假单胞菌感染",
        "II 型呼吸衰竭",
        "肺气肿",
    ],
    negated_facts=["否认结核", "否认哮喘", "否认糖尿病"],
    historical_facts=["高血压史 15 年", "吸烟 30 年(已戒 5 年)"],
    expected_risks=[
        "respiratory_failure_progression",
        "pseudomonas_antibiotic_resistance",
        "non_invasive_ventilation_failure",
    ],
    gold_codes=["J44.100", "J18.900", "J96.000", "I10.x00"],
    notes="COPD + CAP dual diagnosis; primary J44.100 (COPD acute exacerbation).",
))


# ---------------------------------------------------------------------------
# 04 — Gastroenterology (acute cholecystitis + laparoscopic cholecystectomy)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="04_gastroenterology",
    department="肝胆外科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者女性,45岁,因「右上腹持续性疼痛伴恶心、呕吐 1 天」入院。"
        "1 天前饱餐后突发右上腹持续性绞痛,向右肩背部放射,伴恶心、呕吐胃内容物 3 次。"
        "无发热、寒战,无皮肤巩膜黄染。"
        "既往:2 型糖尿病 5 年,口服二甲双胍控制可。否认手术史。"
        "查体:T 37.8℃,P 90 次/分,BP 125/75mmHg。"
        "皮肤巩膜无黄染,腹平,右上腹压痛(+),Murphy 征(+),反跳痛(-)。"
        "血常规:WBC 11.5×10^9/L,N 78%。肝功能:ALT 56 U/L,AST 45 U/L,TBIL 22 μmol/L。"
        "腹部超声:胆囊 9×4cm,壁厚 5mm,胆囊颈部见 1 枚 1.5cm 强回声光团伴声影,胆总管 6mm。"
        "入院诊断:急性结石性胆囊炎;2 型糖尿病。"
        "治疗:入院第 2 天行腹腔镜胆囊切除术,手术顺利,术中见胆囊与大网膜粘连,胆囊壁充血水肿,"
        "胆囊颈部结石嵌顿,胆囊内另见 3 枚小结石(0.5-0.8cm)。"
        "术后病理:急性胆囊炎,胆固醇性息肉。术后第 3 天出院。"
    ),
    structured_context={
        "age": 45,
        "sex": "女",
        "encounter_type": "inpatient",
        "admission_type": "择期手术",
        "primary_complaint": "右上腹痛伴恶心呕吐 1 天",
        "procedure": "腹腔镜胆囊切除术",
        "los_days": 5,
    },
    known_facts=[
        "急性结石性胆囊炎",
        "胆囊颈部结石嵌顿",
        "Murphy 征阳性",
        "腹腔镜胆囊切除术",
    ],
    negated_facts=["无发热寒战", "无黄疸", "否认手术史"],
    historical_facts=["2 型糖尿病 5 年"],
    expected_risks=[
        "bile_duct_injury",
        "post_op_bleeding",
        "diabetes_wound_healing_delay",
    ],
    gold_codes=["K81.000", "K80.000", "E11.900", "Z90.700"],
    notes="Acute cholecystitis + lap cholecystectomy; primary K81.000.",
))


# ---------------------------------------------------------------------------
# 05 — Oncology (post-gastric-cancer chemo admission)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="05_oncology",
    department="肿瘤科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者男性,58岁,因「胃癌术后 4 月,拟行第 3 周期化疗」入院。"
        "4 月前因「胃窦腺癌(cT3N2M0,III A 期)」行远端胃切除术(Billroth II),"
        "术后病理:胃窦低分化腺癌,侵及浆膜层,淋巴结 5/16 转移,切缘阴性。"
        "术后行 SOX 方案化疗 2 周期(奥沙利铂 + 替吉奥),"
        "无明显不良反应,KPS 评分 80 分。本次为行第 3 周期化疗入院。"
        "既往:否认高血压、糖尿病、冠心病史。否认药物过敏史。"
        "查体:T 36.4℃,P 76 次/分,R 16 次/分,BP 118/72mmHg。"
        "神清,营养中等,浅表淋巴结未及肿大。腹平,上腹正中见手术瘢痕,愈合好,"
        "腹软,无压痛,肝脾肋下未及,移动性浊音(-)。"
        "辅助检查:血常规、肝肾功能基本正常。CEA 2.1 ng/mL(参考值 <5),"
        "CA19-9 14 U/mL。腹部 CT:胃癌术后改变,未见明显复发或转移征象。"
        "入院诊断:胃窦低分化腺癌(pT3N2M0 III A 期,术后);化疗后。"
        "计划:完善化疗前评估,行第 3 周期 SOX 方案化疗。"
    ),
    structured_context={
        "age": 58,
        "sex": "男",
        "encounter_type": "inpatient",
        "admission_type": "择期化疗",
        "primary_complaint": "胃癌术后 4 月,化疗入院",
        "procedure": "远端胃切除术(Billroth II) + SOX 化疗",
        "los_days": 5,
    },
    known_facts=[
        "胃窦低分化腺癌",
        "pT3N2M0 III A 期",
        "淋巴结 5/16 转移",
        "SOX 方案化疗 2 周期完成",
        "KPS 80 分",
    ],
    negated_facts=["否认高血压", "否认糖尿病", "否认冠心病"],
    historical_facts=["4 月前远端胃切除术"],
    expected_risks=[
        "chemotherapy_myelosuppression",
        "tumor_recurrence",
        "post_gastrectomy_nutrition_deficiency",
    ],
    gold_codes=["C16.200", "Z51.100", "Z85.000"],
    notes="Oncology case with chemo admission; primary C16.200 (gastric antrum cancer).",
))


# ---------------------------------------------------------------------------
# 06 — Obstetrics (cesarean + postpartum hemorrhage)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="06_obstetrics",
    department="产科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者女性,29岁,G2P0,因「停经 39 周,规律下腹痛 6 小时」入院。"
        "孕期定期产检,无妊娠期糖尿病、妊娠期高血压疾病。"
        "既往:2018 年人工流产 1 次。否认慢性病史。"
        "查体:T 36.8℃,P 88 次/分,BP 115/70mmHg。"
        "宫高 35cm,腹围 102cm,胎位 LOA,胎心 142 次/分,规律宫缩 30''/3-4'。"
        "肛查:宫口开大 3cm,S-1。骨盆外测量正常。"
        "产程进展:活跃期停滞(宫口开大 6cm 后 4 小时无进展),"
        "疑头盆不称,急诊行子宫下段剖宫产术。"
        "术中见羊水清,娩出一活女婴,体重 3650g,Apgar 10-10-10 分。"
        "胎盘娩出后子宫收缩乏力,出血约 800mL,给予缩宫素、卡前列素氨丁三醇,"
        "B-Lynch 缝合,宫腔球囊压迫,出血逐渐停止,总出血约 1200mL。"
        "术中输红细胞悬液 2U,血浆 400mL。术后 BP 100/60mmHg,HR 96 次/分。"
        "入院诊断:G2P0 孕 39 周临产;活跃期停滞;产后出血(中度);"
        "剖宫产术后;单活产。"
    ),
    structured_context={
        "age": 29,
        "sex": "女",
        "encounter_type": "inpatient",
        "admission_type": "急诊",
        "primary_complaint": "停经 39 周,规律下腹痛 6 小时",
        "procedure": "子宫下段剖宫产术 + B-Lynch 缝合 + 宫腔球囊",
        "los_days": 6,
    },
    known_facts=[
        "G2P0 孕 39 周",
        "活跃期停滞",
        "产后出血(约 1200mL)",
        "剖宫产术",
        "子宫收缩乏力",
    ],
    negated_facts=["否认妊娠期糖尿病", "否认妊娠期高血压"],
    historical_facts=["2018 年人工流产 1 次"],
    expected_risks=[
        "postpartum_hemorrhage_recurrence",
        "sheehan_syndrome_risk",
        "subsequent_uterine_rupture",
    ],
    gold_codes=["O82.000", "O72.000", "O62.100", "Z37.000"],
    notes="Cesarean + PPH; primary O82.000 (cesarean) or O72.000 (PPH).",
))


# ---------------------------------------------------------------------------
# 07 — Pediatrics (pediatric pneumonia, age 5)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="07_pediatrics",
    department="儿科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患儿,男,5 岁,因「发热、咳嗽 5 天,气促 2 天」入院。"
        "5 天前受凉后出现发热,体温最高 39.2℃,伴阵发性连声咳嗽,咳黄粘痰,不易咳出。"
        "2 天前出现气促,呼吸 50 次/分,伴鼻翼煽动、三凹征阳性。"
        "在外院静脉点滴「头孢呋辛」3 天效果不佳。"
        "既往:足月剖宫产,出生体重 3200g。否认反复喘息史,否认先天性心脏病。"
        "按时接种疫苗。父母体健。"
        "查体:T 38.8℃,P 130 次/分,R 52 次/分,BP 90/60mmHg,SpO2 92%(室内空气)。"
        "神清,精神稍差,口周轻度发绀。咽充血,双肺呼吸音粗,双下肺可闻及固定中细湿啰音。"
        "血常规:WBC 15.6×10^9/L,N 75%,CRP 65 mg/L。"
        "胸片:双下肺斑片状渗出影。肺炎支原体抗体 IgM 1:160(阳性)。"
        "入院诊断:重症支原体肺炎;低氧血症。"
        "治疗计划:阿奇霉素抗感染;雾化吸入;对症支持。"
    ),
    structured_context={
        "age": 5,
        "sex": "男",
        "encounter_type": "inpatient",
        "admission_type": "急诊",
        "primary_complaint": "发热咳嗽 5 天,气促 2 天",
        "los_days": 7,
    },
    known_facts=[
        "支原体肺炎",
        "肺炎支原体抗体 IgM 阳性",
        "双下肺斑片状渗出",
        "重症肺炎",
        "低氧血症",
    ],
    negated_facts=["否认反复喘息", "否认先天性心脏病"],
    historical_facts=["足月剖宫产", "按时接种疫苗"],
    expected_risks=[
        "mycoplasma_resistance_to_macrolide",
        "pleural_effusion_progression",
        "acute_respiratory_distress",
    ],
    gold_codes=["J15.700", "J18.900"],
    notes="Pediatric mycoplasma pneumonia; primary J15.700 (Mycoplasma pneumoniae pneumonia).",
))


# ---------------------------------------------------------------------------
# 08 — General surgery (appendectomy + laparoscopic)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="08_general_surgery",
    department="普通外科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者男性,28岁,因「转移性右下腹痛 12 小时」入院。"
        "12 小时前无明显诱因出现上腹部隐痛,4 小时后转移并固定至右下腹,呈持续性胀痛,"
        "伴恶心、呕吐胃内容物 1 次。无发热、腹泻。"
        "既往:体健。否认手术史、外伤史。否认药物过敏。"
        "查体:T 37.6℃,P 95 次/分,BP 120/75mmHg。"
        "腹平,右下腹麦氏点压痛(+),反跳痛(+),腰大肌征(+),闭孔内肌征(-)。"
        "血常规:WBC 13.8×10^9/L,N 82%,CRP 50 mg/L。"
        "腹部超声:阑尾肿胀,直径 9mm,壁增厚,周围少量渗液。"
        "入院诊断:急性阑尾炎。"
        "治疗:急诊行腹腔镜阑尾切除术。术中见阑尾位于盲肠后位,长 8cm,直径 1cm,"
        "充血水肿明显,表面脓苔附着,未穿孔。逆行切除阑尾,标本送病理。"
        "术后病理:急性化脓性阑尾炎,未穿孔。术后第 2 天排气,第 4 天出院。"
    ),
    structured_context={
        "age": 28,
        "sex": "男",
        "encounter_type": "inpatient",
        "admission_type": "急诊手术",
        "primary_complaint": "转移性右下腹痛 12 小时",
        "procedure": "腹腔镜阑尾切除术",
        "los_days": 4,
    },
    known_facts=[
        "急性化脓性阑尾炎",
        "麦氏点压痛阳性",
        "腹腔镜阑尾切除术",
        "阑尾未穿孔",
    ],
    negated_facts=["无发热腹泻", "否认手术史", "否认药物过敏"],
    historical_facts=[],
    expected_risks=[
        "appendix_perforation_risk_post_op",
        "wound_infection",
        "intra_abdominal_abscess",
    ],
    gold_codes=["K35.800", "K35.801"],
    notes="Classic appendicitis + lap app; primary K35.800.",
))


# ---------------------------------------------------------------------------
# 09 — Complex comorbidity (diabetes + HTN + CHD + CKD)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="09_complex_comorbidity",
    department="老年医学科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者男性,75岁,因「反复胸闷、气促 3 年,加重伴双下肢水肿 1 周」入院。"
        "3 年前活动后胸闷气促,曾诊断「冠心病 劳力性心绞痛」,2019 年行 LAD PCI 术(植入 DES 1 枚)。"
        "1 周前受凉后胸闷气促加重,夜间端坐呼吸,双下肢凹陷性水肿。"
        "既往:2 型糖尿病 20 年(胰岛素 + 二甲双胍,HbA1c 8.2%);高血压病 25 年(氨氯地平 + 缬沙坦);"
        "冠心病 PCI 术后 7 年;慢性肾脏病 3 期(eGFR 45);腔隙性脑梗死 3 年。"
        "否认结核、肝炎。否认药物过敏。吸烟 30 年(已戒 10 年),偶饮酒。"
        "查体:T 36.5℃,P 92 次/分,R 22 次/分,BP 165/95mmHg。"
        "颈静脉怒张,双肺底湿啰音,心界左下扩大,心率 92 次/分,律齐,A2>P2,心尖部 SM 2/6。"
        "腹软,肝肋下 2cm,移动性浊音(-),双下肢凹陷性水肿 II°。"
        "辅助检查:NT-proBNP 4500 pg/mL;cTnT 0.05 ng/mL;Cr 158 μmol/L,BUN 12 mmol/L;"
        "血钾 5.2 mmol/L;HbA1c 8.2%。心脏超声:EF 38%,左房、左室扩大,二尖瓣反流(中-重度)。"
        "入院诊断:慢性心力衰竭急性加重(NYHA IV 级);冠心病 PCI 术后;"
        "2 型糖尿病;高血压病 3 级(很高危);慢性肾脏病 3 期;腔隙性脑梗死后遗症。"
    ),
    structured_context={
        "age": 75,
        "sex": "男",
        "encounter_type": "inpatient",
        "admission_type": "急诊",
        "primary_complaint": "反复胸闷气促 3 年,加重伴双下肢水肿 1 周",
        "procedure": "",
        "los_days": 12,
    },
    known_facts=[
        "慢性心力衰竭急性加重",
        "NYHA IV 级",
        "EF 38%",
        "2 型糖尿病 20 年",
        "高血压病 25 年",
        "CKD 3 期",
        "PCI 术后 7 年",
        "腔隙性脑梗死后遗症",
    ],
    negated_facts=["否认结核", "否认肝炎", "否认药物过敏"],
    historical_facts=[
        "2019 年 LAD PCI",
        "吸烟 30 年(已戒 10 年)",
        "腔隙性脑梗死 3 年",
    ],
    expected_risks=[
        "acute_decompensated_heart_failure_progression",
        "ckd_progression_with_diabetes",
        "hypoglycemia_in_ckd",
        "drug_drug_interaction_polypharmacy",
        "hyperkalemia_under_raasi",
    ],
    gold_codes=[
        "I50.900",
        "I25.100",
        "Z95.500",
        "E11.900",
        "I10.x00",
        "N18.300",
        "I69.300",
    ],
    notes="Complex multi-morbidity elderly case; primary I50.900 (CHF acute exacerbation).",
))


# ---------------------------------------------------------------------------
# 10 — Negation and history (focus on negation/historical wording)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="10_negation_and_history",
    department="呼吸内科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者男性,68岁,因「咳嗽 2 周」入院。"
        "2 周前无明显诱因出现干咳,无痰,无咯血,无胸痛、胸闷。"
        "患者否认发热,否认盗汗,否认消瘦,否认结核病史,否认恶性肿瘤家族史。"
        "既往史:高血压 10 年(氨氯地平控制可)。曾患肺结核,30 年前已治愈。"
        "否认糖尿病、冠心病。"
        "个人史:吸烟 40 年,每日 20 支。否认饮酒。"
        "家族史:父亲 70 岁诊断肺癌(已去世),母亲糖尿病。"
        "查体:T 36.4℃,P 80 次/分,BP 138/85mmHg。"
        "双肺呼吸音清,未闻及干湿性啰音。"
        "胸部 CT:右肺上叶见一枚 8mm 混合磨玻璃结节,边界清楚,可见分叶征。"
        "患者及家属拒绝 PET-CT,要求 3 月后复查。"
        "疑诊肺恶性肿瘤,待排肺结核复发。"
        "入院诊断:右肺上叶结节(疑肺癌,待排结核复发);高血压病 2 级。"
    ),
    structured_context={
        "age": 68,
        "sex": "男",
        "encounter_type": "inpatient",
        "admission_type": "择期",
        "primary_complaint": "咳嗽 2 周",
        "los_days": 3,
    },
    known_facts=[
        "右肺上叶 8mm 混合磨玻璃结节",
        "高血压 10 年",
        "吸烟 40 年",
        "父亲肺癌家族史",
    ],
    negated_facts=[
        "否认发热",
        "否认盗汗",
        "否认消瘦",
        "否认结核病史(注意:与既往史「曾患肺结核」冲突,以既往史为准)",
        "否认恶性肿瘤家族史(注意:与家族史「父亲肺癌」冲突,以家族史为准)",
        "否认糖尿病",
        "否认冠心病",
        "否认饮酒",
        "无咯血",
        "无胸痛胸闷",
    ],
    historical_facts=[
        "30 年前曾患肺结核(已治愈)",
        "高血压 10 年",
        "父亲 70 岁诊断肺癌",
    ],
    expected_risks=[
        "lung_cancer_suspicion",
        "tuberculosis_reactivation",
        "false_negative_due_to_negation_complexity",
    ],
    gold_codes=["R91.x00", "D49.100", "I10.x00"],
    notes=(
        "Negation/history stress test: 12+ negation/historical terms. "
        "Agent must distinguish CURRENT dx (right lung nodule) from HISTORICAL (TB 30yr cured) "
        "from FAMILY (father lung cancer) from RULED-OUT (denies fever, weight loss). "
        "Set not_for_quality_scoring=true because gold codes are uncertain (8mm GGO not biopsy-proven)."
    ),
    not_for_quality_scoring=True,
))


# ---------------------------------------------------------------------------
# 11 — Conflicting documentation (admission vs discharge mismatch)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="11_conflicting_documentation",
    department="普通外科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者男性,55岁,因「左侧腹股沟可复性包块 1 年,增大 1 月」入院。"
        "1 年前发现左侧腹股沟可复性包块,站立时出现,平卧后消失。"
        "1 月来包块逐渐增大,坠入阴囊,平卧后回纳困难。"
        "既往:慢性便秘 5 年。否认慢性咳嗽、前列腺增生。"
        "查体:腹平,左侧腹股沟区见一梨形包块,约 5×3cm,进入阴囊,质软,"
        "无明显压痛,平卧推挤可回纳腹腔,压迫内环口包块不再出现。"
        "右侧腹股沟区未见异常。"
        "入院诊断:左侧腹股沟斜疝。"
        "治疗经过:入院第 2 天行腹股沟疝无张力修补术(腹腔镜,TEP 术式)。"
        "术中记录:见右侧腹股沟斜疝,疝囊约 4×3cm,内容物为小肠,可回纳,"
        "植入聚丙烯补片 10×15cm,手术顺利。"
        "出院诊断:右侧腹股沟斜疝;慢性便秘。"
        "术后第 1 天恢复可,第 3 天出院。"
        "病程记录护士书写笔误:左侧腹股沟斜疝(与主治医师口头确认实际为右侧)。"
    ),
    structured_context={
        "age": 55,
        "sex": "男",
        "encounter_type": "inpatient",
        "admission_type": "择期手术",
        "primary_complaint": "左侧腹股沟可复性包块 1 年,增大 1 月",
        "procedure": "腹股沟疝无张力修补术(TEP)",
        "los_days": 3,
    },
    known_facts=[
        "入院诊断:左侧腹股沟斜疝",
        "术中记录:右侧腹股沟斜疝",
        "出院诊断:右侧腹股沟斜疝",
        "腹股沟疝无张力修补术(TEP)",
    ],
    negated_facts=["否认慢性咳嗽", "否认前列腺增生"],
    historical_facts=["慢性便秘 5 年"],
    expected_risks=[
        "left_right_side_documentation_conflict",
        "admission_discharge_dx_mismatch",
        "nursing_note_vs_surgical_record_inconsistency",
    ],
    gold_codes=["K40.900"],
    notes=(
        "Conflict stress test: admission dx = LEFT, surgical/discharge dx = RIGHT, "
        "nursing note retains LEFT. Agent should flag documentation inconsistency "
        "and request clarification. Set not_for_quality_scoring=true because the "
        "correct side is genuinely ambiguous (medical record contains the conflict)."
    ),
    not_for_quality_scoring=True,
))


# ---------------------------------------------------------------------------
# 12 — Incomplete documentation (missing fields)
# ---------------------------------------------------------------------------
FIXTURES.append(_record(
    fixture_id="12_incomplete_documentation",
    department="内科",
    intended_agents=ALL_AGENTS,
    input_text=(
        "患者,性别不详,年龄不详。"
        "因「腹部不适」入院。"
        "病程不详。"
        "查体未记录。"
        "辅助检查:腹部超声示「肝区回声增粗」。"
        "诊断:腹痛待查。"
        "治疗:对症处理。"
    ),
    structured_context={
        "age": None,
        "sex": None,
        "encounter_type": "inpatient",
        "admission_type": "未知",
        "primary_complaint": "腹部不适",
        "los_days": None,
    },
    known_facts=["腹痛待查", "腹部超声肝区回声增粗"],
    negated_facts=[],
    historical_facts=[],
    missing_information=[
        "无主诉详细描述",
        "无现病史",
        "无体格检查记录",
        "无生命体征",
        "无既往史",
        "无个人史",
        "无家族史",
        "无辅助检查完整结果",
        "无最终诊断",
        "无治疗计划细节",
    ],
    expected_risks=[
        "incomplete_documentation_blocks_coding",
        "missing_age_sex_blocks_drg_grouping",
        "missing_pe_blocks_clinical_validation",
    ],
    gold_codes=[],
    notes=(
        "Missing-data stress test: 10+ critical fields missing. Agent should "
        "REJECT inference (not guess codes) and emit a documentation gap warning. "
        "Set not_for_quality_scoring=true because there are no gold codes to score against."
    ),
    not_for_quality_scoring=True,
))


# ============================================================================
# Write fixtures + quality report
# ============================================================================

def write_fixture(fixture: dict[str, Any]) -> Path:
    path = FIXTURES_DIR / f"{fixture['fixture_id']}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)
    return path


def quality_check() -> dict[str, Any]:
    """Run PDF §4 data gating checks."""
    issues: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []

    # Length cap per PDF §4 (input_text ≤ 4000 chars)
    MAX_LEN = 4000

    required_fields = {
        "fixture_id", "tag", "department", "intended_agents", "input_text",
        "structured_context", "known_facts", "negated_facts",
        "historical_facts", "missing_information", "expected_risks",
        "gold_codes", "not_for_quality_scoring", "notes",
    }

    for fx in FIXTURES:
        fx_id = fx["fixture_id"]
        record: dict[str, Any] = {"fixture_id": fx_id, "issues": []}

        # Missing fields
        missing = required_fields - set(fx.keys())
        if missing:
            record["issues"].append(f"MISSING_FIELDS: {sorted(missing)}")

        # Tag
        if fx.get("tag") != SYNTHETIC_TAG:
            record["issues"].append(f"WRONG_TAG: expected {SYNTHETIC_TAG}, got {fx.get('tag')}")

        # Length
        text_len = len(fx["input_text"])
        record["input_text_length"] = text_len
        if text_len > MAX_LEN:
            record["issues"].append(f"INPUT_TOO_LONG: {text_len} > {MAX_LEN}")

        # Intended agents must be from ALL_AGENTS
        unknown_agents = set(fx["intended_agents"]) - set(ALL_AGENTS)
        if unknown_agents:
            record["issues"].append(f"UNKNOWN_AGENTS: {sorted(unknown_agents)}")

        # Gold codes format (basic — ICD-10-CN pattern: letter + 2 digits + . + alphanumeric)
        for code in fx["gold_codes"]:
            if not code:
                continue
            # Accept formats like "S22.000", "I10.x00", "Z95.500", "E11.900"
            if len(code) < 4 or not code[0].isalpha() or not code[1:3].isdigit():
                record["issues"].append(f"INVALID_GOLD_CODE: {code}")

        # not_for_quality_scoring fixtures must not be used in F1 evaluation
        record["not_for_quality_scoring"] = fx["not_for_quality_scoring"]

        # Department coverage
        record["department"] = fx["department"]

        # Negation word distribution (for fixture 10 specifically)
        neg_words_present = []
        for w in ["否认", "排除", "既往", "已治愈", "家族史", "疑似", "待排", "无"]:
            if w in fx["input_text"]:
                neg_words_present.append(w)
        record["negation_words_in_input"] = neg_words_present

        # Conflict check (for fixture 11)
        if "11_" in fx_id:
            has_conflict = "左" in fx["input_text"] and "右" in fx["input_text"]
            record["conflict_documentation_present"] = has_conflict

        # Missing info count (for fixture 12)
        record["missing_info_count"] = len(fx["missing_information"])

        summary.append(record)
        if record["issues"]:
            issues.extend([{**r, "fixture_id": fx_id} for r in record["issues"]])

    return {
        "total_fixtures": len(FIXTURES),
        "total_issues": len(issues),
        "issues": issues,
        "summary": summary,
        "all_synthetic_tagged": all(f["tag"] == SYNTHETIC_TAG for f in FIXTURES),
        "all_required_fields_present": all(
            required_fields.issubset(set(f.keys())) for f in FIXTURES
        ),
        "all_input_under_max_len": all(len(f["input_text"]) <= MAX_LEN for f in FIXTURES),
        "fixture_id_list": [f["fixture_id"] for f in FIXTURES],
        "department_distribution": {
            dept: sum(1 for f in FIXTURES if f["department"] == dept)
            for dept in {f["department"] for f in FIXTURES}
        },
        "scoring_eligible_count": sum(1 for f in FIXTURES if not f["not_for_quality_scoring"]),
        "not_scoring_count": sum(1 for f in FIXTURES if f["not_for_quality_scoring"]),
    }


def main() -> int:
    print(f"Generating {len(FIXTURES)} fixtures to {FIXTURES_DIR}")
    paths = []
    for fx in FIXTURES:
        paths.append(write_fixture(fx))
        print(f"  [OK] {fx['fixture_id']}: {paths[-1].name}")

    print(f"\nRunning data gating quality checks")
    report = quality_check()
    report_path = OUTPUTS_DIR / "fixture_quality_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nQuality report: {report_path}")
    print(f"  total_fixtures: {report['total_fixtures']}")
    print(f"  total_issues: {report['total_issues']}")
    print(f"  all_synthetic_tagged: {report['all_synthetic_tagged']}")
    print(f"  all_required_fields_present: {report['all_required_fields_present']}")
    print(f"  all_input_under_max_len: {report['all_input_under_max_len']}")
    print(f"  scoring_eligible: {report['scoring_eligible_count']} / not_scoring: {report['not_scoring_count']}")
    print(f"  departments: {report['department_distribution']}")

    if report["total_issues"] > 0:
        print("\nIssues found:")
        for issue in report["issues"]:
            print(f"  - {issue}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
