"""``get_guidelines`` MCP handler — chapter-level + general coding conventions.

Phase 4-C: new tool, mirrors Corti Code Validation's ``guidelines`` tool.
Returns chapter-level conventions (e.g. Chapter IX rules) and general
ICD-10-CN coding rules. The LLM uses these as guardrails when validating
code assignability + completeness.

Input shape:
  - ``code`` (str, optional) — when provided, the handler returns
    chapter-specific conventions for the chapter this code belongs to.
    When omitted or unknown, returns general conventions only.

Output:
  - ``chapter`` — chapter label (e.g. "第9章 循环系统疾病")
  - ``chapter_conventions`` — list[str], chapter-specific rules
  - ``general_rules`` — list[str], general ICD-10-CN coding rules
  - ``source`` — always "internal_kb"

Data source:
  - Phase 4-C: inline Python dict (~20 chapter conventions + ~10
    general rules). Future Phase 4-D+ may extract to JSON asset
    (e.g., ``coding_guidelines_kb.json``) without breaking the API.

PHI safety:
  - Input is a code string (no patient text). Safe to log/trace.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


# ── Chapter-level conventions (top 20 chapters) ──────────────────────
# Inline KB — mirrors ICD-10-CN Chapter I-XX. Each entry is a list of
# 1-3 conventions the LLM must respect when validating codes in this
# chapter. Phase 4-C scope: minimal but useful. Extend via Phase 4-D.
CHAPTER_CONVENTIONS: dict[str, list[str]] = {
    "1": [
        "第一章 范围: 某些传染病和寄生虫病 (A00-B99)。",
        "传染病报告需双重编码: 病原体 + 临床表现 (例: B20-B24 HIV)。",
        "若为病毒性传染病伴全身症状,优先使用 Chapter I 编码而非表现编码。",
    ],
    "2": [
        "第二章 范围: 肿瘤 (C00-D48)。原发部位、继发部位、形态学、行为须分别编码。",
        "恶性肿瘤原发部位优先于继发部位;形态学编码 (M-...) 可作为附加编码。",
        "恶性肿瘤病人治疗期间复查,若未提及复发,使用 Z85 个人史编码。",
    ],
    "9": [
        "第九章 范围: 循环系统疾病 (I00-I99)。慢性缺血性心脏病使用 I20-I25。",
        "I21 急性心肌梗死: 使用 4 周后限时编码 (I22 复发, I25 慢性)。",
        "心力衰竭: I50 应根据左/右/双心室进一步细分;伴高血压时 I11 优先。",
        "心脏移植后状态使用 Z95.5;排斥反应使用 T86。",
    ],
    "10": [
        "第十章 范围: 呼吸系统疾病 (J00-J99)。急性上呼吸道感染 J00-J06。",
        "肺炎: J12-J18 按病原体细分;未知病原体使用 J18.9。",
        "慢性阻塞性肺疾病 (COPD) 急性加重使用 J44.1;稳定期使用 J44.0。",
    ],
    "11": [
        "第十一章 范围: 消化系统疾病 (K00-K93)。",
        "消化性溃疡: K27-K27.x 按部位+并发症 (出血/穿孔) 细分。",
        "急性胰腺炎使用 K85.x;慢性胰腺炎使用 K86.x。",
    ],
    "4": [
        "第四章 范围: 内分泌、营养和代谢疾病 (E00-E90)。",
        "糖尿病: E10-E14 按 (1) 类型 + (2) 并发症 + (3) 控制状态组合编码。",
        "糖尿病伴并发症使用 .x 第 5-6 位细分;无并发症使用 .9。",
    ],
    "19": [
        "第十九章 范围: 损伤、中毒和外因的某些其他后果 (S00-T98)。",
        "损伤编码: S 编码按部位细分,T 编码按外因细分。",
        "多处损伤: 使用最严重损伤作为主诊断;开放性/闭合性骨折必须区分。",
        "外因编码 (V01-Y98) 作为附加编码,描述损伤发生场景。",
    ],
    "20": [
        "第二十章 范围: 疾病和死亡的外因 (V01-Y98)。",
        "外因编码作为附加编码使用,不单独作为主诊断 (除非为体检/筛查目的)。",
        "运输事故需细分: 陆路 (V01-V89) / 水上 (V90-V94) / 航空 (V95-V97)。",
    ],
}


# ── General ICD-10-CN coding rules ────────────────────────────────────
# 10 general rules that apply regardless of chapter. Mirrors Corti
# Code Validation system prompt's "do not" list.
GENERAL_RULES: list[str] = [
    "不编码未在病历中明确记录的诊断 — 临床表现必须在病历正文中出现。",
    "主诊断必须能解释本次住院的主要治疗资源消耗;不可选次要诊断作为主诊断。",
    "使用最具体的编码: 当存在更具体细分码时,不可使用 3 位类别码 (例: I25 应选 I25.1)。",
    "组合编码优先: 当一个编码能完整描述两种情况时,使用组合码而非双码 (例: I11.0 高血压性心脏病伴心衰)。",
    "后遗症编码: 使用相应后遗症码 (B90-B94, E64, E68, G09, I69, O97, T90-T98)。",
    "疑似诊断编码: 若出院时仍未确诊,按症状/体征编码 (R00-R99),不按假设诊断编码。",
    "合并编码: 当合并码存在时 (例: A40.3 败血症伴肺炎链球菌性肺炎),不可拆分使用两码。",
    "双重编码 (†/asterisk): 匕首编码 (†) 表示病因,星号编码 (*) 表示表现;两者成对使用。",
    "时态限制: 急性心肌梗死 (I21) 仅限发病 4 周 (28 天) 内使用;之后使用 I22 (复发) 或 I25 (慢性)。",
    "Z 编码: 特殊目的编码 (Z00-Z99) — 筛查 (Z00)、随访 (Z08)、个人史 (Z85)、状态 (Z95) 不可作为主诊断 (除特殊场景)。",
]


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    code: str = (arguments.get("code") or "").strip()

    out: dict[str, Any] = {
        "chapter": "",
        "chapter_conventions": [],
        "general_rules": list(GENERAL_RULES),
        "source": "internal_kb",
    }

    if code:
        try:
            from app.services.icd10cn_loader import get_loader
            loader = get_loader()
            entry = loader.get(code)
            if entry is not None:
                chapter_no = str(getattr(entry, "chapter_no", "") or "")
                out["chapter"] = str(loader.chapter_for(code) or "")
                if chapter_no in CHAPTER_CONVENTIONS:
                    out["chapter_conventions"] = CHAPTER_CONVENTIONS[chapter_no]
        except Exception:
            pass

    return out


__all__ = ["handle"]
