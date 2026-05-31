# iCoDer - Rule Engine Service
# Retrieves and applies coding rules from various rule sets
import logging
from typing import Optional
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

# Embedded rule knowledge base (MVP)
CODING_RULES = [
    {
        "rule_id": "R001",
        "rule_set": "住院病案首页数据填写质量规范",
        "title": "主要诊断选择总则",
        "content": "主要诊断应选择对患者健康危害最大、消耗医疗资源最多、住院时间最长的疾病诊断。一般情况下，患者出院时主要治疗的疾病应作为主要诊断。",
        "category": "main_diag",
        "examples": "骨质疏松伴病理性椎体压缩骨折作为主要诊断，而不是单纯骨质疏松或单纯椎体骨折。",
    },
    {
        "rule_id": "R002",
        "rule_set": "住院病案首页数据填写质量规范",
        "title": "病因诊断优先原则",
        "content": "当疾病有明确的病因时，应选择病因诊断作为主要诊断。例如骨质疏松伴病理性骨折，应编码至M80类目，而非S32类目（创伤性骨折）。",
        "category": "main_diag",
        "examples": "M80.900（骨质疏松伴病理性骨折）vs S32.000（腰椎压缩骨折）：如骨折由骨质疏松引起，应选择M80。",
    },
    {
        "rule_id": "R003",
        "rule_set": "ICD10编码规则",
        "title": "M80类目编码规则",
        "content": "M80 骨质疏松伴病理性骨折：需明确骨质疏松类型（绝经后/特发性/药物性等）。当无法明确骨质疏松类型时，使用M80.900（未特指骨质疏松伴病理性骨折）。注意：如有明确的骨折部位信息，应考虑编码更特异的扩展码。",
        "category": "chapter",
        "examples": "确定为绝经后骨质疏松伴椎体病理性骨折 → M80.000；无法明确类型 → M80.900。",
    },
    {
        "rule_id": "R004",
        "rule_set": "住院病案首页数据填写质量规范",
        "title": "主要手术操作选择原则",
        "content": "主要手术操作选择本次住院期间实施的与主要诊断相对应的手术操作。通常选择风险最大、难度最高、花费最多的手术。多个手术操作时，按重要性排序。",
        "category": "main_proc",
        "examples": "多椎体后凸成形术作为主要手术，而不是难度较低的辅助操作。",
    },
    {
        "rule_id": "R005",
        "rule_set": "ICD10编码规则",
        "title": "合并编码规则",
        "content": "当两个疾病之间存在病因-结果关系时，应使用合并编码替代两个独立编码。例如高血压心脏病应编码至I11，而非分别编码高血压I10和心脏病。",
        "category": "general",
        "examples": "I11.0（高血压心脏病伴心力衰竭）替代 I10 + I50.9。",
    },
    {
        "rule_id": "R006",
        "rule_set": "ICD-9-CM-3编码规则",
        "title": "脊柱后凸成形术编码",
        "content": "经皮椎体后凸成形术编码为81.66。需注意：不同椎体节段的后凸成形术可能需要分别编码或使用扩展码。球囊扩张和骨水泥注入是该手术的标准步骤，不需要额外编码。",
        "category": "main_proc",
        "examples": "81.6600x001（经皮椎体后凸成形术），注意与81.6500（经皮椎体成形术）的区别。",
    },
    {
        "rule_id": "R007",
        "rule_set": "住院病案首页数据填写质量规范",
        "title": "其他诊断填写规则",
        "content": "除主要诊断外，所有影响患者治疗的本次住院诊治的疾病都应填写为其他诊断。包括：住院前已经存在、住院期间新发、或影响诊疗过程的疾病。",
        "category": "secondary",
        "examples": "患者既往高血压、糖尿病如需要继续治疗或影响本次治疗方案，应列为其他诊断。",
    },
    {
        "rule_id": "R008",
        "rule_set": "DRG/DIP 编码质量要求",
        "title": "MCC/CC捕获规则",
        "content": "编码审核应特别关注是否遗漏了影响DRG分组的重要合并症（MCC）或合并症（CC）。漏填MCC/CC可能导致分组较轻，影响医院收入。",
        "category": "drg",
        "examples": "遗漏急性肾衰竭（N17.9）、呼吸衰竭（J96.9）等MCC可能导致DRG分组显著偏差。",
    },
    {
        "rule_id": "R009",
        "rule_set": "ICD10编码规则",
        "title": "不宜直接编码的项目",
        "content": "以下项目不宜作为独立诊断编码：(1) 仅影像学描述而无临床意义的发现；(2) 已痊愈的既往疾病；(3) 正常检查结果；(4) 无临床诊断意义的症状体征。",
        "category": "filtering",
        "examples": "MRI报告中的'胸8棘突区骨髓水肿'如无临床诊断意义，不应编码。CT报告中'退行性变'如非本次治疗焦点，不应常规编码。",
    },
    {
        "rule_id": "R010",
        "rule_set": "医保结算清单填写规范",
        "title": "医保结算清单诊断填写要求",
        "content": "医保结算清单中的主要诊断应使用国家医保版ICD-10编码。诊断信息应与病案首页保持一致，但在主诊断选择上，医保结算清单更注重资源消耗。",
        "category": "insurance",
        "examples": "某些情况下，医保结算清单的主诊断可能与病案首页不同，需根据医保规则重新评估。",
    },
    {
        "rule_id": "R011",
        "rule_set": "编码质量监控规则",
        "title": "低质量编码标志",
        "content": "以下情形应标记为低质量编码：(1) 使用未特指编码（.9结尾）但病历中有更特异信息；(2) 遗漏明确的合并症；(3) 编码与手术记录不一致；(4) 主要诊断与主要手术不匹配。",
        "category": "quality",
        "examples": "明确为'绝经后骨质疏松伴椎体病理性骨折'却编码为M80.900（未特指）→ 应提升为M80.000。",
    },
    {
        "rule_id": "R012",
        "rule_set": "编码质量监控规则",
        "title": "多椎体骨折编码",
        "content": "当存在多椎体骨折时，应根据病因选择合适的类目。若是骨质疏松引起的多椎体压缩骨折，编码至M80类目；若是创伤引起，编码至S类目。除主诊断外，各节段椎体骨折可在其他诊断中体现。",
        "category": "main_diag",
        "examples": "T7/T9/T12/L2多椎体骨质疏松骨折 → 主诊断M80.900（骨质疏松伴病理性骨折），其他诊断可编码各椎体骨折位置。",
    },
    {
        "rule_id": "R013",
        "rule_set": "住院病案首页数据填写质量规范",
        "title": "肿瘤放化疗主诊断选择规则",
        "content": "当患者本次入院目的为恶性肿瘤化学治疗、放射治疗或免疫治疗时，应选择Z51.x编码为主要诊断，而非肿瘤本身的编码。",
        "category": "main_diag",
        "examples": "直肠癌术后化疗患者：主要诊断选Z51.102（恶性肿瘤化学治疗），而非C20.x（直肠恶性肿瘤）。",
    },
    {
        "rule_id": "R014",
        "rule_set": "住院病案首页数据填写质量规范",
        "title": "慢性肾病资源消耗优先规则",
        "content": "当患者同时存在慢性肾病(N18)和其他疾病时，如住院期间主要资源消耗在血液透析、电解质管理等肾病相关治疗，应选择N18为主要诊断。",
        "category": "main_diag",
        "examples": "痛风(M10) + CKD5期(N18.900x013)，住院主要做透析 → 主要诊断选N18.900x013。",
    },
    {
        "rule_id": "R015",
        "rule_set": "ICD10编码规则",
        "title": "合并编码优先原则",
        "content": "当ICD-10提供合并编码(combination code)时，应使用合并编码替代多个单一编码。例如E11.2（2型糖尿病伴肾病）替代分开的E11.9（糖尿病）和N18.9（肾病）。",
        "category": "main_diag",
        "examples": "糖尿病伴肾病: E11.2+N08.3替代E11.9+N18.9。高血压性心脏病: I11.0替代I10（高血压）+ I51.4（心肌炎）。",
    },
]


class RuleEngineService:
    """Rule retrieval and application engine."""

    RULE_SETS = [
        "住院病案首页数据填写质量规范",
        "ICD10编码规则",
        "ICD-9-CM-3编码规则",
        "医保结算清单填写规范",
        "DRG/DIP 编码质量要求",
        "编码质量监控规则",
        "医院本地编码规则",
    ]

    def __init__(self):
        self._rules: dict[str, list[dict]] = {}
        for rule in CODING_RULES:
            rs = rule["rule_set"]
            if rs not in self._rules:
                self._rules[rs] = []
            self._rules[rs].append(rule)

    async def retrieve_rules(
        self,
        topic: str,
        rule_sets: Optional[list[str]] = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Retrieve relevant rules for a topic using fuzzy matching."""
        candidates = []
        if rule_sets:
            for rs in rule_sets:
                candidates.extend(self._rules.get(rs, []))
        else:
            for rules in self._rules.values():
                candidates.extend(rules)

        if not candidates:
            return []

        # Search in title, content, and examples
        texts = []
        for r in candidates:
            search_text = f"{r['title']} {r['content']} {r.get('examples', '')}"
            texts.append(search_text)

        results = process.extract(
            topic.lower(),
            texts,
            scorer=fuzz.partial_ratio,
            limit=min(top_k, len(texts)),
        )

        output = []
        for _, score, idx in results:
            r = candidates[idx]
            output.append({
                "rule_id": r["rule_id"],
                "rule_set": r["rule_set"],
                "title": r["title"],
                "content": r["content"],
                "relevance": round(score / 100.0, 4),
                "category": r.get("category"),
                "examples": r.get("examples"),
            })
        return sorted(output, key=lambda x: x["relevance"], reverse=True)

    async def add_custom_rule(self, rule_set: str, title: str, content: str,
                              category: str = "custom", examples: str = "") -> dict:
        """Add a user-defined custom rule (in-memory, lost on restart).

        Note: Production should persist rules to a database table.
        """
        import uuid
        rule_id = f"CUST-{uuid.uuid4().hex[:8].upper()}"
        rule = {
            "rule_id": rule_id,
            "rule_set": rule_set,
            "title": title,
            "content": content,
            "category": category,
            "examples": examples,
        }
        self._rules.setdefault(rule_set, []).append(rule)
        logger.info(f"Custom rule added: {rule_id} '{title}' in set '{rule_set}'")
        return rule

    async def get_all_rule_sets(self) -> list[dict]:
        """List all available rule sets with counts."""
        return [
            {"name": rs, "rule_count": len(rules)}
            for rs, rules in self._rules.items()
        ]

    async def check_code_against_rules(
        self, code: str, code_name: str, context: dict
    ) -> list[dict]:
        """Check a specific code against relevant rules."""
        topic = f"{code} {code_name}"
        rules = await self.retrieve_rules(topic, top_k=10)
        checks = []
        for rule in rules:
            status = "pass"  # Simplified - real impl would do deeper analysis
            checks.append({
                "rule_id": rule["rule_id"],
                "rule_name": rule["title"],
                "status": status,
                "message": rule["content"][:200],
            })
        return checks


# Singleton
rule_engine_service = RuleEngineService()
