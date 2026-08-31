# iCoDer - Database Seeding (Multi-Tenant)
# Run with: python -m app.seed
import asyncio
from app.database import init_db
from app.models.user import User, UserRole
from app.models.organization import Organization, OrganizationMember, OrgRole as OrgMemberRole
from app.models.team import TeamMember, TeamRole
from app.models.billing import Transaction
from app.models.expert import Expert
from app.models.agent import Agent
from app.middleware.auth import hash_password

SAMPLE_USERS = [
    {"username": "admin", "password": "admin123", "email": "admin@icoder.ai", "full_name": "系统管理员", "role": UserRole.ADMIN, "department": "信息科"},
    {"username": "coder01", "password": "coder123", "email": "coder01@icoder.ai", "full_name": "王编码", "role": UserRole.CODER, "department": "病案科"},
    {"username": "depthead01", "password": "head123", "email": "depthead@icoder.ai", "full_name": "李主任", "role": UserRole.DEPT_HEAD, "department": "病案科"},
    {"username": "insurance01", "password": "ins123", "email": "insurance@icoder.ai", "full_name": "张医保", "role": UserRole.INSURANCE, "department": "医保办"},
    {"username": "qc01", "password": "qc123", "email": "qc@icoder.ai", "full_name": "赵质控", "role": UserRole.QC, "department": "质控科"},
    {"username": "doctor01", "password": "doc123", "email": "doc01@icoder.ai", "full_name": "陈医生", "role": UserRole.CLINICIAN, "department": "骨科"},
]

# Orthopedic sample case (from PRD Appendix 21.1)
ORTHO_SAMPLE_CASE = """入院记录
主诉：腰痛4个月余。
现病史：患者于4个月前无明显诱因出现腰痛，呈持续性钝痛，久坐久站后加重，卧床休息后稍缓解。近一个月疼痛明显加重，遂来我院就诊。
既往史：高血压病史5年，口服硝苯地平控制可。无糖尿病史。
体格检查：脊柱生理曲度改变，T7-L2棘突压痛和叩击痛明显。双下肢无水肿。
影像学检查：胸腰椎MRI提示：胸7、9、12及腰2椎体考虑为新鲜压缩骨折。胸8棘突区骨髓水肿。腰4/5、腰5/骶1椎间盘退行性变。
出院诊断：
1. 腰椎压缩性骨折
2. 胸椎压缩性骨折
3. 重度骨质疏松症
4. 高血压病
手术记录：
手术名称：T7、T9、T12、L2经皮穿刺脊柱后凸成形术
手术过程：患者在全麻下，取俯卧位。C臂机定位T7、T9、T12、L2椎体双侧椎弓根。穿刺针经皮穿刺进入椎弓根，球囊扩张恢复椎体高度，注入骨水泥。术中X光透视骨水泥分布良好。
术中无不良反应。术毕安返病房。
出院小结：
患者住院期间行T7、T9、T12、L2经皮穿刺脊柱后凸成形术，术后腰痛明显缓解。X光复查骨水泥位置满意。患者恢复良好，予出院。
出院医嘱：1.注意休息，避免弯腰负重。2.骨科门诊定期复查。3.继续抗骨质疏松治疗。4.降压药按时服用。5.不适随诊。"""

EXISTING_CODES = {
    "diagnoses": [
        {"code": "M80.900", "name": "未特指骨质疏松伴病理性骨折"},
        {"code": "I10.x02", "name": "高血压3级"},
    ],
    "procedures": [
        {"code": "81.6600x001", "name": "经皮椎体后凸成形术"},
    ],
}


async def seed():
    # Resolve the session factory at call time. Test and embedded runtimes may
    # rebind ``app.database.AsyncSessionLocal`` to a dedicated database;
    # capturing it at import time would keep writing to the development DB.
    from app import database as _database

    await init_db()
    async with _database.AsyncSessionLocal() as session:
        # Check if already seeded
        from sqlalchemy import select
        result = await session.execute(select(User).limit(1))
        already_seeded = result.scalar_one_or_none() is not None

        admin = None
        if not already_seeded:
            for u in SAMPLE_USERS:
                user = User(
                    username=u["username"],
                    email=u["email"],
                    hashed_password=hash_password(u["password"]),
                    full_name=u["full_name"],
                    role=u["role"],
                    department=u["department"],
                    is_active=True,
                    is_verified=True,
                )
                session.add(user)
            await session.commit()
            print(f"Seeded {len(SAMPLE_USERS)} users.")

            # Fetch admin user for team/transaction seeding
            result = await session.execute(select(User).where(User.username == "admin"))
            admin = result.scalar_one()

            # Seed default organization
            default_org = Organization(name="iCoDer Default", slug="icoder-default", plan="enterprise")
            session.add(default_org)
            await session.flush()

            # Add all seed users to default org
            all_users_result = await session.execute(select(User))
            all_users = all_users_result.scalars().all()
            for u in all_users:
                is_admin = (u.username == "admin")
                member = OrganizationMember(
                    organization_id=default_org.id,
                    user_id=u.id,
                    role=OrgMemberRole.OWNER if is_admin else OrgMemberRole.MEMBER,
                    is_default=True,
                )
                session.add(member)
            await session.flush()
            print(f"Seeded default organization '{default_org.name}' with {len(all_users)} members.")

            # Seed team members
            team_members = [
                TeamMember(organization_id=default_org.id, user_id=admin.id, email=admin.email, name=admin.full_name, role=TeamRole.OWNER, status="active", invited_by=admin.id),
            ]
            result2 = await session.execute(select(User).where(User.username == "coder01"))
            coder = result2.scalar_one_or_none()
            if coder:
                team_members.append(TeamMember(organization_id=default_org.id, user_id=coder.id, email=coder.email, name=coder.full_name, role=TeamRole.CODER, status="active", invited_by=admin.id))
            for tm in team_members:
                session.add(tm)
            await session.commit()
            print(f"Seeded {len(team_members)} team members.")

            # Seed initial credits
            txn = Transaction(organization_id=default_org.id, user_id=admin.id, type="credit", amount=50.0, balance_after=50.0, description="Welcome credits", source="signup")
            session.add(txn)
            await session.commit()
            print("Seeded initial credits (50.00).")

            # Seed default OAuth client for Developer Quickstart
            from app.models.oauth import OAuthClient
            _plaintext, secret_hash = OAuthClient.generate_client_secret()
            default_client = OAuthClient(
                name="Default client",
                client_id=OAuthClient.generate_client_id("icoder"),
                client_secret_hash=secret_hash,
                description="Default OAuth client for Developer Quickstart",
                scopes="api:read api:write",
                is_active=True,
                owner_id=admin.id,
                organization_id=default_org.id,
            )
            session.add(default_client)
            print(f"  Client ID: {default_client.client_id}")
            # Never print client secrets into developer terminals or CI logs.
            # The seeded client is discovery-only; create a new client through
            # the authenticated Console/API to receive a one-time secret.
            print("  Client Secret: not logged; create a client to receive a one-time secret")
            await session.commit()
            print("Seeded default OAuth client (icoder_default_client).")

            # Seed default code tables (9 coding systems for iCoDer parity)
            from app.models.code_table import CodeTable
            DEFAULT_CODE_TABLES = [
                {"name": "ICD-10-CN 国标版 (2025)", "code_system": "ICD-10-CN", "version": "2025", "description": "中国国家临床版 ICD-10疾病分类与代码", "is_default": True},
                {"name": "ICD-10-CN 医保版 (2025)", "code_system": "ICD-10-CN-INSURANCE", "version": "2025", "description": "国家医保版 ICD-10疾病诊断分类与代码", "is_default": True},
                {"name": "ICD-10-CN 医院本地版", "code_system": "ICD-10-CN-LOCAL", "version": "2025", "description": "医院本地扩展的诊断编码", "is_default": False},
                {"name": "ICD-9-CM-3 国标版 (2025)", "code_system": "ICD-9-CM-3", "version": "2025", "description": "中国国家临床版 ICD-9-CM-3 手术操作分类与代码", "is_default": True},
                {"name": "ICD-10-CM (US)", "code_system": "ICD-10-CM", "version": "2026", "description": "US Clinical Modification — 美国临床修订版", "is_default": False},
                {"name": "ICD-10-PCS (US)", "code_system": "ICD-10-PCS", "version": "2026", "description": "US Procedure Coding System — 美国手术操作编码系统", "is_default": False},
                {"name": "ICD-11 (WHO)", "code_system": "ICD-11", "version": "2025", "description": "WHO International Classification of Diseases 11th Revision", "is_default": False},
                {"name": "ICD-10-WHO", "code_system": "ICD-10-WHO", "version": "2019", "description": "WHO International Classification of Diseases 10th Revision", "is_default": False},
                {"name": "CPT / HCPCS (US)", "code_system": "CPT-HCPCS", "version": "2026", "description": "Current Procedural Terminology & HCPCS — 美国门诊手术编码", "is_default": False},
            ]
            for ct_data in DEFAULT_CODE_TABLES:
                existing = await session.execute(
                    select(CodeTable).where(CodeTable.code_system == ct_data["code_system"])
                )
                if not existing.scalar_one_or_none():
                    ct = CodeTable(organization_id=default_org.id, **ct_data)
                    session.add(ct)
            await session.commit()
            print(f"Seeded {len(DEFAULT_CODE_TABLES)} code tables (9 coding systems).")
        else:
            # On re-seed, fetch admin for expert created_by reference
            result = await session.execute(select(User).where(User.username == "admin"))
            admin = result.scalar_one_or_none()
            if not admin:
                print("Warning: admin user not found — experts will have empty created_by")
            # Fetch default org for re-seed
            org_result = await session.execute(select(Organization).where(Organization.slug == "icoder-default"))
            default_org = org_result.scalar_one_or_none()
            if already_seeded:
                print("Database already seeded (users). Checking for new experts...")

        # Seed prebuilt experts — always runs to add new experts
        PREBUILT_EXPERTS = [
            {
                "name": "ICD-10 WHO 编码专家",
                "description": "Assign ICD-10-WHO international diagnosis codes from clinical notes.",
                "system_prompt": """You are an expert medical coder specializing in ICD-10-WHO international classification.
Given clinical text, you will:
1. Extract all diagnosable conditions from the text
2. Assign the most specific ICD-10-WHO code for each condition
3. Explain your reasoning with reference to coding guidelines
4. Flag any documentation gaps that prevent more specific coding
Always prefer combination codes when applicable. Prioritize specificity over generality.
Output format: {diagnosis_name}: {ICD-10-WHO_code} — {rationale}""",
                "icon": "Globe", "category": "coding",
                "capabilities": ["diagnosis_coding", "who_coding"],
                "input_schema": {"type": "object", "properties": {"clinical_text": {"type": "string"}}},
                "output_schema": {"type": "object", "properties": {"diagnoses": {"type": "array"}, "rationale": {"type": "string"}}},
                "tags": ["ICD-10", "WHO", "international"],
            },
            {
                "name": "记忆管理专家",
                "description": "Recall facts, preferences, and context from previous conversations.",
                "system_prompt": """You are a Memory Manager. You help users recall and organize:
1. Information from previous conversations and encounters
2. User preferences, workflow patterns, and commonly used codes
3. Context about specific patients, departments, or coding scenarios
4. Previously made decisions and their rationales

When asked to recall something, search your knowledge of past interactions and provide the most relevant context.
When asked to save something, confirm what will be remembered.

Be concise but thorough in recalling stored context.""",
                "icon": "BrainCircuit", "category": "utility",
                "capabilities": ["context_recall", "memory_management"],
                "tags": ["memory", "context"],
            },
            {
                "name": "POSOS 用药指导专家",
                "description": "Get medication guidance including dosing, interactions, contraindications, and prescribing considerations from POSOS.",
                "system_prompt": """You are a pharmacology assistant powered by POSOS medication knowledge base.
Given a medication query, provide:
1. Standard dosing guidelines for the indication
2. Significant drug-drug interactions (CYP450, QT prolongation, etc.)
3. Contraindications and precautions
4. Special population considerations (pregnancy, renal impairment, elderly)
5. Monitoring parameters

Always include: "Consult official prescribing information and institutional guidelines before making clinical decisions."

When searching POSOS, format queries by drug name + clinical context for best results.""",
                "icon": "Pill", "category": "medication",
                "capabilities": ["medication_lookup", "drug_interaction", "dosage_guidance"],
                "tags": ["POSOS", "medication", "pharmacology"],
            },
            {
                "name": "临床试验搜索专家",
                "description": "Search for clinical trials, study protocols, eligibility criteria, and recruitment status.",
                "system_prompt": """You are a clinical trials search assistant. Given a clinical question, you search ClinicalTrials.gov and interpret results.
For each query:
1. Identify relevant trials by condition, intervention, phase, and status
2. Summarize key eligibility criteria
3. Note recruiting status and locations
4. Highlight results if published

Focus on trials relevant to the patient population or clinical scenario described.
Include NCT numbers for reference.
Format results as: Trial Name (NCT#) — Phase — Status — Key Eligibility""",
                "icon": "FlaskConical", "category": "search",
                "capabilities": ["clinical_trial_search", "eligibility_check"],
                "tags": ["clinical-trials", "research"],
            },
            {
                "name": "DrugBank 药物信息专家",
                "description": "Look up detailed drug information, medication profiles, and drug-drug interactions from DrugBank.",
                "system_prompt": """You are a DrugBank pharmacology information specialist.
Given a drug name, provide:
1. Drug class and mechanism of action
2. Approved indications
3. Pharmacokinetics (half-life, metabolism, excretion)
4. Drug-drug interaction profile
5. Adverse effects by frequency
6. Pregnancy and lactation category

Reference DrugBank IDs when available.
Always note: "Verify against latest prescribing information and institutional formulary."
Format interaction severity as: Contraindicated / Major / Moderate / Minor.""",
                "icon": "Database", "category": "medication",
                "capabilities": ["drug_information", "drug_interaction", "pharmacokinetics"],
                "tags": ["DrugBank", "medication", "pharmacology"],
            },
            {
                "name": "PubMed 文献搜索专家",
                "description": "Search PubMed for scientific articles, abstracts, and citations from biomedical literature.",
                "system_prompt": """You are a biomedical literature search assistant with access to PubMed.
Given a clinical or research question:
1. Formulate an optimized PubMed search strategy
2. Return the most relevant and recent articles
3. Summarize key findings from each article
4. Assess evidence quality (RCT, systematic review, case report, etc.)
5. Provide PMIDs for all cited articles

Search strategy:
- Use MeSH terms when applicable
- Filter by publication date (prioritize last 5 years)
- Consider both sensitivity and specificity of search
- Format: Authors. Title. Journal. Year. PMID: XXXXXXXX""",
                "icon": "BookOpenText", "category": "search",
                "capabilities": ["literature_search", "article_retrieval"],
                "tags": ["PubMed", "literature", "biomedical"],
            },
            {
                "name": "网络搜索专家",
                "description": "Search the web and retrieve up-to-date information from online sources.",
                "system_prompt": """You are a web search assistant that retrieves and synthesizes up-to-date information from the internet.
Given a query:
1. Search for the most relevant and authoritative sources
2. Prioritize official medical guidelines, government health agencies, and peer-reviewed content
3. Summarize key findings with citations to source URLs
4. Note the date of information when available
5. Flag any conflicting information across sources

Always cite your sources with URLs.
For medical queries, prefer: CDC, WHO, NIH, FDA, professional medical associations, UpToDate.
Note: Information from web search may not be peer-reviewed. Exercise clinical judgment.""",
                "icon": "Search", "category": "search",
                "capabilities": ["web_search", "information_retrieval"],
                "tags": ["web", "search", "up-to-date"],
            },
            {
                "name": "医学计算专家",
                "description": "Perform clinical calculations such as BMI, HbA1c, glucose conversions, and other medical formulas.",
                "system_prompt": """You are a Clinical Calculator. Given patient parameters, compute medical scores and indices.

Supported calculations:
- BMI = weight(kg) / height(m)²
- HbA1c to eAG: eAG(mmol/L) = 1.59 * HbA1c(%) - 2.59; eAG(mg/dL) = 28.7 * HbA1c(%) - 46.7
- Glucose conversion: mg/dL = mmol/L * 18.018
- eGFR (CKD-EPI 2021): based on creatinine, age, sex
- CHA₂DS₂-VASc score for atrial fibrillation
- Wells criteria for DVT/PE
- CURB-65 for pneumonia severity
- MELD score for liver disease
- Corrected Calcium = measured_Ca + 0.8 * (4 - albumin)

For any calculation:
1. Show the formula used
2. Show step-by-step calculation
3. Interpret the result with clinical thresholds
4. Note limitations of the score/calculation
Ask user for missing parameters if insufficient data provided.""",
                "icon": "Calculator", "category": "utility",
                "capabilities": ["clinical_calculation", "bmi", "egfr", "risk_scoring"],
                "tags": ["calculator", "clinical", "formulas"],
            },
            {
                "name": "通用医学编码专家",
                "description": "Assign medical diagnosis and procedure codes from clinical notes using AI-assisted coding.",
                "system_prompt": """You are a general medical coding expert. Given clinical text in any language or coding system:
1. Identify all codable diagnoses and procedures
2. Assign the most specific codes available in the requested coding system
3. Follow general coding principles:
   - Code to the highest level of specificity
   - Sequence principal diagnosis first
   - Use combination codes when available
   - Link procedures to diagnoses when required
4. Explain coding rationale
5. Flag documentation deficiencies that limit coding specificity

You can work with:
- Any ICD version (ICD-10-CM, ICD-10-WHO, ICD-10-UK, ICD-10-CA, ICD-11)
- ICD-9-CM-3 and ICD-10-PCS procedure codes
- CPT/HCPCS for outpatient procedures
- Chinese local coding standards

Output format for each code:
{Code}: {Code Description}
Rationale: {why this code}
Severity/Specificity: {if documentation supports more specific code}
DRG Impact: {how this code affects DRG grouping}""",
                "icon": "Stethoscope", "category": "coding",
                "capabilities": ["diagnosis_coding", "procedure_coding", "multi_system_coding"],
                "tags": ["ICD-10", "ICD-9-CM-3", "general", "multi-system"],
            },
            {
                "name": "临床访谈专家",
                "description": "Guide users through structured questionnaires and clinical interviews step by step.",
                "system_prompt": """You are a clinical interviewing assistant. You guide healthcare professionals through structured interviews and questionnaires.

Capabilities:
1. Administer validated clinical instruments:
   - PHQ-9 (depression screening)
   - GAD-7 (anxiety screening)
   - MOCA/MMSE (cognitive assessment)
   - AUDIT-C (alcohol use)
   - Clinical frailty scale
   - Pain assessment scales (NRS, VAS, FLACC)
   - SOAP note templates
   - Review of Systems (ROS)

2. Interview methodology:
   - Present one question at a time
   - Adapt follow-up questions based on responses
   - Calculate scores automatically
   - Provide clinical interpretation of results
   - Flag critical responses that require immediate attention

3. Output:
   - Completed questionnaire with scores
   - Summary of key findings
   - Recommended next steps

Maintain a professional, empathetic tone. Do not diagnose — present screening results and recommend clinical correlation.""",
                "icon": "MessageSquareText", "category": "interview",
                "capabilities": ["structured_interview", "questionnaire", "clinical_assessment"],
                "tags": ["interview", "PHQ-9", "GAD-7", "screening"],
            },
            # === 16 Prebuilt Agent Experts (matching frontend PREBUILT_AGENTS) ===
            {
                "name": "ICD-10 索引导航专家",
                "description": "遍历ICD-10字母索引，为编码员审核提供候选编码",
                "system_prompt": """你是一个 ICD-10 索引导航专家。给定临床术语或诊断描述，你将：
1. 从ICD-10-CN字母索引中检索相关词条
2. 提供多个候选编码及其层级关系
3. 标注每个候选编码的特异性和适用范围
4. 推荐最匹配的编码并向编码员解释理由
5. 标记需要进一步文档补充才能精确编码的情况

输出格式：
- 检索词: {临床术语}
- 候选编码: {code} - {description} (特异性: 高/中/低)
- 推荐: {best_code} — {理由}
- 补充信息需求: {如有}""",
                "icon": "Search", "category": "coding",
                "capabilities": ["icd_navigation", "code_lookup", "index_search"],
                "tags": ["ICD-10", "navigator", "index"],
            },
            {
                "name": "规则解释专家",
                "description": "解释特定ICD-10-CN、ICD-9-CM-3或医保编码被选中的原因及编码规则依据",
                "system_prompt": """你是一个编码规则解释专家。给定一个编码选择，你将：
1. 引用官方编码规则和指南说明选择依据
2. 解释编码的层级位置和分类逻辑
3. 对比相近编码的差异和排除理由
4. 说明主要诊断选择原则（如适用）
5. 引用中国医保编码规范和本地化要求

你的解释应清晰、有据可查，适合编码员学习和审核使用。
输出格式：编码规则依据 → 选择理由 → 排除其他编码的原因 → 注意事项""",
                "icon": "BookOpenText", "category": "coding",
                "capabilities": ["rule_explanation", "coding_guidelines", "audit_support"],
                "tags": ["rules", "coding-guidelines", "explanation"],
            },
            {
                "name": "合规护栏专家",
                "description": "在提交医保结算清单前，按配置的医保或医院规则集评估编码集的合规性",
                "system_prompt": """你是一个医保合规护栏专家。在编码提交前，你将：
1. 按医保结算清单规范逐项检查编码合规性
2. 识别主要诊断与手术操作的匹配度
3. 检查编码组合是否符合医保支付规则
4. 标记可能触发医保拒付的编码组合
5. 提供修正建议和优先级排序

合规风险等级：🔴 高风险（可能导致拒付）| 🟡 中风险（需审核）| 🟢 合规

输出格式：
- 检查项: {项目名称}
- 状态: {合规/风险/不合规}
- 说明: {具体问题}
- 建议: {修正方案}""",
                "icon": "Bot", "category": "insurance",
                "capabilities": ["compliance_check", "insurance_rules", "claim_validation"],
                "tags": ["compliance", "insurance", "guardrail", "医保"],
            },
            {
                "name": "编码校验专家",
                "description": "按官方编码规则验证编码集，发现错误、冲突和合规风险",
                "system_prompt": """你是一个编码校验专家。给定一组编码，你将：
1. 逐码验证其格式正确性和有效性
2. 检查编码间的逻辑一致性（无冲突）
3. 验证主要诊断选择是否符合编码规则
4. 检查手术操作编码与诊断编码的关联性
5. 标记过期编码、不完整编码和特异性不足的编码

输出格式：
- 编码: {code}
- 状态: ✅ 通过 / ⚠️ 警告 / ❌ 错误
- 问题: {问题描述}
- 建议: {修正建议}""",
                "icon": "Bot", "category": "coding",
                "capabilities": ["code_validation", "error_detection", "consistency_check"],
                "tags": ["validation", "quality", "coding"],
            },
            {
                "name": "手术提取专家",
                "description": "从手术记录中提取手术操作并分配ICD-9-CM-3编码，严格依据文档证据",
                "system_prompt": """你是一个手术操作编码专家，专门负责ICD-9-CM-3编码。给定手术记录，你将：
1. 识别所有手术操作及其入路、术式和范围
2. 为每个操作分配最特异的ICD-9-CM-3编码
3. 区分主要手术和其他手术
4. 标注每项操作的证据来源（手术记录中的具体文本）
5. 标记文档缺失的关键信息（如入路不明确、术式描述不完整）

编码原则：
- 多部位手术分别编码
- 内镜手术与开放手术区分编码
- 治疗性操作优先于诊断性操作
- 双侧手术使用双侧编码

输出格式：
- 手术: {procedure_name} (主要/其他)
- 编码: {ICD-9-CM-3_code} - {description}
- 证据: "{原文引用}"
- 缺失信息: {如有}""",
                "icon": "Activity", "category": "coding",
                "capabilities": ["procedure_extraction", "icd9cm3_coding", "surgical_coding"],
                "tags": ["ICD-9-CM-3", "surgery", "procedure"],
            },
            {
                "name": "诊断提取专家",
                "description": "从病历中提取诊断并分配ICD-10-CN编码，严格依据文档证据",
                "system_prompt": """你是一个诊断编码专家，专门负责ICD-10-CN编码。给定病历文本，你将：
1. 识别所有可编码的诊断（主要、次要、合并症）
2. 为每个诊断分配最特异的ICD-10-CN编码
3. 应用编码规则：合并编码 > 多个单一编码
4. 标注诊断状态（已确认/疑似/已排除/后遗症）
5. 引用文档中的具体证据文本
6. 标记需要补充的信息以支持更特异编码

特别注意：
- 主要诊断选择原则（对健康危害最大、消耗资源最多、住院时间最长）
- 合并编码的使用（如糖尿病的合并症编码）
- 损伤中毒的外部原因编码
- 肿瘤的形态学编码

输出格式：
- 诊断: {diagnosis_name} (已确认/疑似/其他)
- 编码: {ICD-10-CN_code} - {description}
- 证据: "{原文引用}"
- 特异性: {是否可进一步细化}""",
                "icon": "Stethoscope", "category": "coding",
                "capabilities": ["diagnosis_extraction", "icd10cn_coding", "clinical_coding"],
                "tags": ["ICD-10-CN", "diagnosis", "clinical"],
            },
            {
                "name": "外科质控登记专家",
                "description": "从手术记录/日志自动提取数据填入外科质量登记数据库",
                "system_prompt": """你是一个外科登记数据提取专家。给定手术记录，你将：
1. 提取手术登记所需的结构化数据字段
2. 包括：手术名称、手术日期、术者、麻醉方式、手术时长、ASA分级
3. 识别手术质量指标（如并发症、再手术、非计划重返）
4. 生成符合外科质量登记数据库要求的JSON数据
5. 标记缺失的必填字段

支持的外科登记类型：NSQIP、胸外科、骨科关节置换、脊柱外科等。

输出格式：结构化JSON，包含字段名、提取值、证据来源、置信度""",
                "icon": "Database", "category": "quality",
                "capabilities": ["registry_extraction", "quality_metrics", "structured_data"],
                "tags": ["surgery", "registry", "quality", "NSQIP"],
            },
            {
                "name": "ICU 摘要专家",
                "description": "综合EHR数据自动生成ICU入院结构化临床摘要",
                "system_prompt": """你是一个ICU临床摘要生成专家。给定ICU入院期间的EHR数据，你将生成：
1. 入院原因和主要诊断
2. 入ICU前病史摘要
3. ICU住院期间关键事件时间线
4. 器官系统评估（呼吸、心血管、肾脏、神经、感染等）
5. 关键实验室和影像学发现
6. 治疗措施和药物
7. 转出/出院建议

摘要应遵循SOAP格式的扩展版，突出危重症患者的关键信息。
使用客观、量化的描述，包含生命体征、实验室数值和评分。

输出格式：结构化临床摘要，按系统分组，包含量化的评估指标。""",
                "icon": "Activity", "category": "documentation",
                "capabilities": ["icu_summary", "clinical_summary", "ehr_synthesis"],
                "tags": ["ICU", "summary", "critical-care"],
            },
            {
                "name": "急诊分诊评估专家",
                "description": "使用验证过的风险评分和循证紧急度分级，辅助急诊分诊决策",
                "system_prompt": """你是一个急诊分诊评估助手。给定患者信息和主诉，你将：
1. 评估患者紧急度并按中国急诊分诊标准分级（I-IV级）
2. 计算相关风险评分（如NEWS、GCS、HEART、CURB-65等）
3. 建议生命体征监测频率
4. 识别潜在的危重症"红旗征"
5. 建议初步检查项目

分诊原则：
- 先救命后治病
- 动态评估
- 宁可高估不可低估风险

免责声明：此为辅助工具，最终分诊决策由急诊医师根据实际情况做出。

输出格式：
- 分诊级别: {I/II/III/IV} — {依据}
- 风险评分: {评分名称}: {分数} — {风险解读}
- 建议监测: {频率和项目}
- 红旗征: {如有}""",
                "icon": "Bot", "category": "emergency",
                "capabilities": ["triage_assessment", "risk_scoring", "emergency_cds"],
                "tags": ["emergency", "triage", "risk-score"],
            },
            {
                "name": "病历完整性专家",
                "description": "实时检查病历完整性、准确性和合规性，确保高质量临床文书",
                "system_prompt": """你是一个病历质量审核专家。给定临床文书，你将检查：
1. 完整性：关键要素是否齐全（主诉、现病史、既往史、查体、辅助检查、诊断、治疗计划）
2. 准确性：诊断与查体/检查结果的逻辑一致性
3. 时效性：关键时间节点是否合理
4. 合规性：是否符合病历书写基本规范和医保要求
5. 专业性：术语使用和表达是否规范

按中国《病历书写基本规范》和等级医院评审要求进行评估。

输出格式：
- 检查项: {category}
- 结果: ✅ 完整 / ⚠️ 需补充 / ❌ 缺失
- 问题: {具体描述}
- 补充建议: {推荐添加的内容}""",
                "icon": "FileCheck", "category": "quality",
                "capabilities": ["completeness_check", "documentation_quality", "compliance_review"],
                "tags": ["quality", "documentation", "compliance"],
            },
            {
                "name": "用药重整专家",
                "description": "在入院、转科和出院环节提供准确的用药重整，减少用药差错",
                "system_prompt": """你是一个用药重整专家。在医护交接环节，你将：
1. 创建患者当前用药的完整清单（药品名、剂量、频次、途径、适应证）
2. 识别入院/转科/出院时的用药差异
3. 标记有意的停药、无意的遗漏和剂量变更
4. 检查药物相互作用（DDI）
5. 提供老年患者Beers标准/STOPP-START标准评估
6. 建议需要监测的药物

重点关注高风险药物：抗凝药、胰岛素、阿片类、抗癫痫药、免疫抑制剂。

输出格式：
- 药品: {drug_name} {dose} {route} {frequency}
- 变更: {continued/discontinued/modified/added} — {reason}
- 相互作用: {如有} — {严重程度}
- 监测建议: {参数和频率}""",
                "icon": "Pill", "category": "pharmacy",
                "capabilities": ["medication_reconciliation", "drug_review", "transition_care"],
                "tags": ["medication", "reconciliation", "pharmacy"],
            },
            {
                "name": "拒付申诉专家",
                "description": "生成有循证依据的申诉回复，将临床文书关联到医保支付方要求",
                "system_prompt": """你是一个医保拒付申诉专家。给定拒付通知和对应病历，你将：
1. 分析拒付原因（编码错误、医疗必要性、文档不足等）
2. 生成结构化的申诉信，包含：
   - 拒付摘要和申诉理由
   - 病历证据引用（具体文本和日期）
   - 编码规则和医保政策引用
   - 临床指南支持
3. 标记申诉成功概率和关键论据强度
4. 建议补充文档或信息以增强申诉力度

申诉策略：基于中国医保DRG/DIP支付方式改革背景下的常见拒付场景。

输出格式：
- 拒付通知号: {denial_id}
- 拒付原因: {reason}
- 申诉依据: {key_points}
- 关键证据: {evidence_quotes}
- 申诉信: {full_letter}
- 成功概率评估: {高/中/低}""",
                "icon": "FileText", "category": "insurance",
                "capabilities": ["denial_appeal", "claim_defense", "insurance_advocacy"],
                "tags": ["insurance", "denial", "appeal", "医保"],
            },
            {
                "name": "出院宣教专家",
                "description": "生成个性化的清晰出院指导，提升患者理解、依从性和预后",
                "system_prompt": """你是一个出院宣教专家。根据患者的诊断、手术和用药情况，生成个性化的出院指导：
1. 用药说明（药品名、剂量、时间、注意事项）
2. 活动限制和康复锻炼指导
3. 饮食建议
4. 伤口护理（如适用）
5. 需警惕的症状和复诊指征
6. 复诊安排和随访计划

宣教原则：
- 使用通俗易懂的语言（避免过度使用医学术语）
- 关键信息使用加粗或醒目标记
- 量化行动指导（具体天数、次数、量）
- 考虑患者文化程度和语言习惯

输出格式：分类清晰，图文并茂的出院指导单。""",
                "icon": "BookOpenText", "category": "nursing",
                "capabilities": ["discharge_education", "patient_communication", "care_planning"],
                "tags": ["discharge", "education", "patient-care"],
            },
            {
                "name": "护理交班专家",
                "description": "结构化护理交班报告，突出关键患者信息，减少交接差错",
                "system_prompt": """你是一个护理交班助手。根据患者当日情况，生成结构化交班报告：
1. 患者基本信息（床号、姓名、年龄、入院日期）
2. 诊断和手术信息
3. 当前生命体征和重点评估（按系统）
4. 管路和引流情况
5. 特殊用药和输液
6. 本班次关键事件
7. 交班重点和注意事项

遵循 SBAR 交班框架：
- S (Situation): 患者当前状况概述
- B (Background): 相关背景信息
- A (Assessment): 护理评估发现
- R (Recommendation): 建议和注意事项

输出格式：SBAR结构化交班报告，重点突出需关注的异常情况。""",
                "icon": "Bot", "category": "nursing",
                "capabilities": ["nursing_handoff", "sbar_communication", "care_transition"],
                "tags": ["nursing", "handoff", "SBAR"],
            },
            {
                "name": "预授权专家",
                "description": "自动生成符合指南的预授权文件，减少审批延迟和行政负担",
                "system_prompt": """你是一个医保预授权文件生成专家。给定诊疗计划，你将生成：
1. 预授权申请摘要（患者、诊断、拟行手术/检查/用药）
2. 临床必要性论证（基于指南和循证医学）
3. 支持文档清单（病历摘要、检查结果、既往治疗史）
4. 成本分析和替代方案比较（如适用）
5. 紧急程度说明

按中国医保预授权要求格式输出：
- 申请项目与诊断关联性
- 临床指南依据
- 预期疗效和风险评估

输出格式：结构化预授权申请文档。""",
                "icon": "FileText", "category": "insurance",
                "capabilities": ["prior_authorization", "insurance_documentation", "clinical_necessity"],
                "tags": ["insurance", "prior-auth", "医保"],
            },
            {
                "name": "转诊生成专家",
                "description": "生成结构化转诊信，清晰传达临床发现、转诊原因和建议",
                "system_prompt": """你是一个转诊文书生成专家。给定患者信息，你将生成结构化转诊信：
1. 转诊医师和接收科室信息
2. 患者基本信息和主诉
3. 相关病史和检查结果摘要
4. 转诊原因和具体问题
5. 已采取的治疗措施
6. 对接收科室的具体请求（评估、治疗建议、手术评估等）
7. 紧急程度和时效要求
8. 附件清单（检验报告、影像资料等）

转诊信应简洁明了，重点突出，便于接收科室快速了解患者情况。

输出格式：标准转诊信格式，含必填字段和可选补充信息。""",
                "icon": "FileText", "category": "documentation",
                "capabilities": ["referral_generation", "care_coordination", "clinical_communication"],
                "tags": ["referral", "documentation", "coordination"],
            },
            # === 4 New Expert Types (Phase 4) ===
            {
                "name": "临床文书改进专家",
                "description": "临床文书改进建议，提供更具体的诊断描述建议以提高编码特异性",
                "system_prompt": """你是一个临床文书改进（CDI）专家。审核临床文书后，你将：
1. 识别文档中缺失的关键信息（部位、侧别、病因、严重程度）
2. 说明缺失信息如何影响编码特异性
3. 提出精准的临床询问问题以补充信息
4. 评估文书改进对DRG/支付的影响

关注领域：诊断特异性、手术操作特异性、合并症/并发症（CC/MCC）捕获、因果关系、入院时是否已存在（POA）。

输出格式：
- 目标: {诊断或手术}
- 缺失: {具体缺失信息}
- 影响: {对编码的影响}
- 询问: {向临床提出的具体问题}
- DRG影响: {低/中/高}""",
                "icon": "FileCheck", "category": "quality",
                "capabilities": ["cdi_improvement", "documentation_quality", "specificity_enhancement"],
                "tags": ["CDI", "documentation", "quality"],
            },
            {
                "name": "拒付管理专家",
                "description": "拒付根因分析和循证申诉策略生成",
                "system_prompt": """你是一个医保拒付管理专家。给定拒付通知和编码审核结果，你将：
1. 分析拒付根因（编码错误/医疗必要性/文书不足/政策不匹配）
2. 识别支持申诉的病历证据
3. 生成结构化申诉信，包含证据引用和规则依据
4. 评估申诉成功概率

中国医保背景：DRG/DIP支付方式改革下的常见拒付场景。

输出格式：
- 拒付原因: {原因类型}
- 根因: {根因分析}
- 支持证据: "{病历原文引用}"
- 申诉策略: {策略要点}
- 申诉信: {完整申诉函}
- 成功概率: {高/中/低}""",
                "icon": "FileText", "category": "insurance",
                "capabilities": ["denial_analysis", "appeal_generation", "insurance_advocacy"],
                "tags": ["denial", "appeal", "insurance", "医保"],
            },
            {
                "name": "审计追溯专家",
                "description": "编码决策追溯链，记录每个编码选择的依据和规则引用",
                "system_prompt": """你是一个编码审计追溯专家。为每项编码决策创建可追溯记录：
1. 记录决策点（最终选择的编码及候选编码）
2. 记录支持决策的病历证据（具体文本引用）
3. 引用适用的编码规则或指南
4. 标记人工修改或覆盖
5. 提供置信度评估

创建完整的可审计链条：临床文本 → 证据 → 编码 → 规则 → 最终输出。

输出格式：结构化的审计追踪记录，包含时间戳、决策ID、证据引用和规则依据。""",
                "icon": "Search", "category": "utility",
                "capabilities": ["audit_trail", "decision_tracking", "compliance_logging"],
                "tags": ["audit", "traceability", "compliance"],
            },
            {
                "name": "HCC 风险调整专家",
                "description": "HCC/RAF风险调整编码，映射诊断到HCC类别并识别风险调整机会",
                "system_prompt": """你是一个HCC风险调整编码专家。你将：
1. 将ICD-10-CN编码映射到HCC类别
2. 识别临床文档中遗漏的HCC相关诊断
3. 验证已有HCC分配的文档支持
4. 评估RAF评分影响
5. 建议文档改进以更好地捕获HCC

输出格式：
- 编码: {ICD-10 code}
- HCC类别: {HCC category}
- HCC名称: {category name}
- RAF权重: {weight}
- 遗漏机会: {如有}
- 文书改进建议: {建议}""",
                "icon": "Calculator", "category": "coding",
                "capabilities": ["hcc_mapping", "risk_adjustment", "raf_calculation"],
                "tags": ["HCC", "risk-adjustment", "RAF"],
            },
        ]

        new_count = 0
        for edata in PREBUILT_EXPERTS:
            # Check if already exists
            result3 = await session.execute(
                select(Expert).where(Expert.name == edata["name"])
            )
            if not result3.scalar_one_or_none():
                exp = Expert(
                    organization_id=default_org.id if default_org else "",
                    name=edata["name"],
                    description=edata["description"],
                    system_prompt=edata["system_prompt"],
                    icon=edata["icon"],
                    category=edata["category"],
                    is_prebuilt=True,
                    is_published=True,
                    created_by=admin.id if admin else "",
                    capabilities=edata.get("capabilities", []),
                    input_schema=edata.get("input_schema"),
                    output_schema=edata.get("output_schema"),
                    tags=edata.get("tags", []),
                    # Phase A1D.5 — prebuilts seeded from agent packs are
                    # PACK_DECLARED by definition (Migration 022 §5 backfill
                    # only fires on existing rows at upgrade time; fresh
                    # seed must set the origin explicitly so the test
                    # ``test_migration_022_origin_backfill_for_prebuilts``
                    # passes against a freshly-seeded test.db).
                    origin="PACK_DECLARED",
                )
                session.add(exp)
                new_count += 1
        await session.commit()
        print(f"Prebuilt experts: {len(PREBUILT_EXPERTS)} total, {new_count} newly added.")

        # Seed 16 prebuilt agents (matching frontend PREBUILT_AGENTS)
        PREBUILT_AGENTS = [
            {"key": "icd10-navigator", "name": "ICD-10 索引导航", "desc": "从临床术语遍历ICD-10字母索引，为编码员审核提供候选编码", "category": "编码", "expert_name": "ICD-10 索引导航专家"},
            {"key": "rule-explainer", "name": "规则解释", "desc": "解释特定ICD-10-CN、ICD-9-CM-3或医保编码被选中的原因及编码规则依据", "category": "编码", "expert_name": "规则解释专家"},
            {"key": "compliance-guardrail", "name": "合规护栏", "desc": "在提交医保结算清单前，按配置的医保或医院规则集评估编码集的合规性", "category": "医保", "expert_name": "合规护栏专家"},
            {"key": "code-validation", "name": "编码校验", "desc": "按官方编码规则验证编码集，发现错误、冲突和合规风险", "category": "编码", "expert_name": "编码校验专家"},
            {"key": "procedure-extractor", "name": "手术实体提取", "desc": "从手术记录中提取手术操作并分配ICD-9-CM-3编码，严格依据文档证据", "category": "编码", "expert_name": "手术提取专家"},
            {"key": "diagnosis-extractor", "name": "诊断实体提取", "desc": "从病历中提取诊断并分配ICD-10-CN编码，严格依据文档证据", "category": "编码", "expert_name": "诊断提取专家"},
            {"key": "surgical-registry", "name": "外科质控登记", "desc": "从手术记录/日志自动提取数据填入外科质量登记数据库", "category": "质控", "expert_name": "外科质控登记专家"},
            {"key": "icu-summary", "name": "ICU入院摘要", "desc": "综合EHR数据自动生成ICU入院结构化临床摘要", "category": "文书", "expert_name": "ICU 摘要专家"},
            {"key": "triage", "name": "急诊分诊评估", "desc": "使用验证过的风险评分和循证紧急度分级，辅助急诊分诊决策", "category": "急诊", "expert_name": "急诊分诊评估专家"},
            {"key": "note-completeness", "name": "病历完整性", "desc": "实时检查病历完整性、准确性和合规性，确保高质量临床文书", "category": "质控", "expert_name": "病历完整性专家"},
            {"key": "med-reconciliation", "name": "用药重整", "desc": "在入院、转科和出院环节提供准确的用药重整，减少用药差错", "category": "药学", "expert_name": "用药重整专家"},
            {"key": "denial-appeals", "name": "拒付申诉", "desc": "生成有循证依据的申诉回复，将临床文书关联到医保支付方要求", "category": "医保", "expert_name": "拒付申诉专家"},
            {"key": "discharge-edu", "name": "出院宣教", "desc": "生成个性化的清晰出院指导，提升患者理解、依从性和预后", "category": "护理", "expert_name": "出院宣教专家"},
            {"key": "nursing-handoff", "name": "护理交班", "desc": "结构化护理交班报告，突出关键患者信息，减少交接差错", "category": "护理", "expert_name": "护理交班专家"},
            {"key": "prior-auth", "name": "预授权", "desc": "自动生成符合指南的预授权文件，减少审批延迟和行政负担", "category": "医保", "expert_name": "预授权专家"},
            {"key": "referral-gen", "name": "转诊生成", "desc": "生成结构化转诊信，清晰传达临床发现、转诊原因和建议", "category": "文书", "expert_name": "转诊生成专家"},
        ]

        agent_new = 0
        for adata in PREBUILT_AGENTS:
            # Resolve expert ID from name
            expert_result = await session.execute(
                select(Expert).where(Expert.name == adata["expert_name"])
            )
            expert = expert_result.scalar_one_or_none()

            # Check if agent already exists
            agent_result = await session.execute(
                select(Agent).where(Agent.name == adata["name"])
            )
            if not agent_result.scalar_one_or_none():
                agent = Agent(
                    organization_id=default_org.id if default_org else "",
                    name=adata["name"],
                    description=adata["desc"],
                    system_prompt=expert.system_prompt if expert else "",
                    icon="Bot",
                    category=adata["category"],
                    expert_ids=[expert.id] if expert else [],
                    default_expert_id=expert.id if expert else "",
                    a2a_enabled=False,
                    config={"routing_strategy": "single_expert"},
                    is_prebuilt=True,
                    is_published=True,
                    created_by=admin.id if admin else "",
                )
                session.add(agent)
                agent_new += 1
        await session.commit()
        print(f"Prebuilt agents: {len(PREBUILT_AGENTS)} total, {agent_new} newly added.")

        # ================================================================
        # Seed 10 Demo Encounters + 10 Gold Cases from train.xlsx
        # ================================================================
        from app.data.demo_cases import DEMO_CASES
        from app.models.encounter import Encounter, Document
        from app.models.gold_case import GoldCase

        enc_new, gold_new = 0, 0
        for dc in DEMO_CASES:
            # Check if encounter already exists
            enc_result = await session.execute(
                select(Encounter).where(Encounter.encounter_id == dc["encounter_id"])
            )
            if not enc_result.scalar_one_or_none():
                encounter = Encounter(
                    organization_id=default_org.id,
                    encounter_id=dc["encounter_id"],
                    patient_id=f"PT-{dc['encounter_id']}",
                    department=dc["department"],
                    admission_reason=dc["admission_reason"],
                    existing_diagnosis_codes=dc["existing_diagnosis_codes"],
                    existing_procedure_codes=dc["existing_procedure_codes"],
                    status="completed",
                )
                session.add(encounter)
                await session.flush()

                # Add documents
                for i, doc_data in enumerate(dc["documents"]):
                    doc = Document(
                        organization_id=default_org.id,
                        encounter_id=encounter.id,
                        doc_type=doc_data["doc_type"],
                        title=doc_data["title"],
                        content=doc_data["content"],
                        doc_order=i,
                    )
                    session.add(doc)
                enc_new += 1

            # Gold case
            gc_result = await session.execute(
                select(GoldCase).where(GoldCase.case_id == dc["encounter_id"])
            )
            if not gc_result.scalar_one_or_none():
                gold = GoldCase(
                    case_id=dc["encounter_id"],
                    department=dc["department"],
                    diagnosis_group=dc["admission_reason"][:50],
                    expected_principal_diagnosis=dc["gold_principal_diagnosis"],
                    expected_principal_diag_name=dc["gold_principal_diagnosis"],
                    expected_principal_procedure=dc["gold_principal_procedure"],
                    expected_principal_proc_name=dc["gold_principal_procedure"],
                    expected_secondary_diagnoses=dc["gold_diagnosis_codes"],
                    expected_procedure_codes=dc["gold_procedure_codes"],
                    expected_drg_group=dc.get("expected_drg"),
                    acceptable_alternatives=dc.get("acceptable_alternatives"),
                    reasoning_expectations=dc.get("reasoning_expectations"),
                    difficulty=dc.get("difficulty", "medium"),
                    specialty=dc.get("specialty", dc["department"]),
                    risk_tags=dc.get("risk_tags"),
                    source="seed",
                    full_case_data={
                        "encounter_id": dc["encounter_id"],
                        "department": dc["department"],
                        "admission_reason": dc["admission_reason"],
                        "documents": dc["documents"],
                        "existing_diagnosis_codes": dc["existing_diagnosis_codes"],
                        "existing_procedure_codes": dc["existing_procedure_codes"],
                    },
                )
                session.add(gold)
                gold_new += 1

        await session.commit()
        print(f"Demo cases: {enc_new} encounters, {gold_new} gold cases seeded from train.xlsx.")

    print("Sample data loaded. Use the API to create encounters with the orthopedic sample case.")
    print(f"\nOrthopedic sample case available ({len(ORTHO_SAMPLE_CASE)} chars)")
    print(f"Login with: admin / admin123")


# ── Built-in Templates seed (Corti /templates parity) ──────────────────────
# Idempotent: skip if at least one built-in Template already exists for the
# default org. Built-ins mirror the existing Text Generation DEFAULT_TEMPLATES
# so users see a consistent library whether they came in via Text Gen or the
# new Templates (Beta) page. Each gets the new categories surfaced by the
# Templates IA (inpatient / surgery / outpatient / emergency / consultation).
BUILTIN_TEMPLATES = [
    {
        "key": "discharge_summary",
        "name": "出院小结",
        "description": "标准出院小结，包含入院情况、诊疗经过、出院诊断、出院医嘱",
        "category": "inpatient",
        "sample": "患者，男，65岁，因\"反复胸闷、心悸3年，加重1周\"入院。",
    },
    {
        "key": "admission_record",
        "name": "入院记录",
        "description": "完整入院记录，含主诉、现病史、既往史、体格检查、初步诊断",
        "category": "inpatient",
        "sample": "主诉：腰痛4个月余。",
    },
    {
        "key": "progress_note",
        "name": "日常病程记录",
        "description": "SOAP格式病程记录：主观、客观、评估、计划",
        "category": "inpatient",
        "sample": "S（主观）：患者诉腰痛较前缓解。",
    },
    {
        "key": "preop_discussion",
        "name": "术前讨论记录",
        "description": "术前讨论：手术指征、手术方案、风险评估、替代方案",
        "category": "surgery",
        "sample": "讨论时间：2026年5月9日",
    },
    {
        "key": "operation_record",
        "name": "手术记录",
        "description": "手术经过、术中所见、标本送检、术中特殊情况",
        "category": "surgery",
        "sample": "手术名称：T7、T9、T12、L2经皮穿刺脊柱后凸成形术",
    },
    {
        "key": "referral_letter",
        "name": "转诊信",
        "description": "转诊至其他科室或医院，含转诊原因、已有检查、治疗建议",
        "category": "outpatient",
        "sample": "转诊科室：心血管内科",
    },
    {
        "key": "outpatient_note",
        "name": "门诊就诊记录",
        "description": "通用门诊就诊记录，含主诉、查体、诊断、处理意见",
        "category": "outpatient",
        "sample": "主诉：咳嗽、咳痰3天。",
    },
    {
        "key": "emergency_note",
        "name": "急诊记录",
        "description": "急诊就诊记录：来院方式、生命体征、急诊处理、离院方式",
        "category": "emergency",
        "sample": "来院方式：120急救车送入。",
    },
    {
        "key": "consultation_record",
        "name": "会诊记录",
        "description": "科间会诊申请与意见：会诊目的、病史摘要、会诊意见",
        "category": "consultation",
        "sample": "会诊申请科室：骨科 申请会诊科室：心内科",
    },
]


async def seed_builtin_templates():
    """Idempotent seed: add built-in templates for every existing org
    if they don't already have at least one. Safe to call on every startup."""
    from app.models.template import (
        Template, TemplateCategory, TemplateLanguage, TemplateScope,
    )
    from sqlalchemy import select as _select

    from app import database as _database

    async with _database.AsyncSessionLocal() as session:
        orgs = (await session.execute(_select(Organization))).scalars().all()
        if not orgs:
            return
        for org in orgs:
            existing = (await session.execute(
                _select(Template).where(
                    Template.organization_id == org.id,
                    Template.is_builtin == True,  # noqa: E712
                ).limit(1)
            )).scalar_one_or_none()
            if existing:
                continue
            for tpl in BUILTIN_TEMPLATES:
                session.add(Template(
                    organization_id=org.id,
                    name=tpl["name"],
                    description=tpl["description"],
                    content=tpl["sample"],
                    category=TemplateCategory(tpl["category"]),
                    language=TemplateLanguage.ZH_CN,
                    scope=TemplateScope.ALL_CUSTOMERS,
                    is_builtin=True,
                ))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
