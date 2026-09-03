"""Lightweight keyword extraction + ICD-10 dictionary lookup for prompt injection.

Why this exists:
  - DeepSeekCodingAdapter and PromptLLMAdapter previously sent a static
    Chinese prompt to the LLM with no real-time reference to the 33,304-code
    ICD-10 dictionary. The LLM had to recall codes from training alone.
  - This module extracts clinical keywords from the encounter text and
    retrieves the top-N candidate codes from CodeDictionaryService to inject
    as a "候选编码参考" block in the system prompt.
  - No heavy NLP (no jieba, no embeddings). A curated trigger list catches
    high-specificity terms; a stopword-stripped n-gram fallback catches the rest.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


# Curated high-specificity medical terms. When these appear in the encounter,
# the whole phrase is preferred over n-gram tokenization (better signal).
_TRIGGER_TERMS = [
    # 骨骼/肌肉
    "骨质疏松", "椎体压缩骨折", "病理性骨折", "腰椎压缩", "胸椎压缩",
    "骨折不愈合", "股骨颈骨折", "粗隆间骨折",
    # 心血管
    "高血压", "冠心病", "心绞痛", "急性心肌梗死", "ST段抬高", "ST段抬高型心肌梗死",
    "非ST段抬高", "心力衰竭", "充血性心力衰竭", "心房颤动", "房颤", "阵发性房颤",
    "持续性房颤", "心律失常", "室性早搏", "房性早搏", "起搏器", "ICD植入",
    "冠状动脉支架", "经皮冠状动脉", "冠状动脉旁路移植", "冠状动脉搭桥",
    # 呼吸
    "肺炎", "细菌性肺炎", "病毒性肺炎", "吸入性肺炎", "慢性阻塞性肺疾病",
    "慢性支气管炎", "肺气肿", "支气管哮喘", "过敏性哮喘", "呼吸衰竭",
    "急性呼吸窘迫综合征", "肺栓塞",
    # 消化
    "胃炎", "慢性胃炎", "消化性溃疡", "胃溃疡", "十二指肠溃疡",
    "肝硬化", "肝炎", "胰腺炎", "急性胰腺炎", "慢性胰腺炎",
    "胆囊炎", "胆石症", "胆总管结石", "阑尾炎", "急性阑尾炎",
    "肠梗阻", "消化道出血", "上消化道出血", "下消化道出血",
    "胃食管反流", "克罗恩病", "溃疡性结肠炎",
    # 泌尿
    "尿路感染", "膀胱炎", "肾盂肾炎", "急性肾功能衰竭", "慢性肾功能衰竭",
    "尿毒症", "肾结石", "输尿管结石", "膀胱结石",
    # 内分泌
    "糖尿病", "2型糖尿病", "1型糖尿病", "糖尿病周围神经病变",
    "糖尿病肾病", "糖尿病视网膜病变", "酮症酸中毒",
    "甲状腺功能亢进", "甲状腺功能减退", "高脂血症", "痛风",
    # 神经
    "脑梗死", "脑出血", "脑卒中", "短暂性脑缺血", "TIA",
    "帕金森病", "癫痫", "偏头痛", "紧张性头痛", "阿尔茨海默病",
    "痴呆", "吉兰-巴雷综合征",
    # 肿瘤
    "恶性肿瘤", "癌症", "腺癌", "鳞癌", "淋巴瘤", "白血病",
    "骨髓瘤", "原位癌", "转移癌", "化疗", "放疗", "免疫治疗", "靶向治疗",
    "乳腺恶性肿瘤", "肺恶性肿瘤", "胃恶性肿瘤", "肝恶性肿瘤",
    "结直肠恶性肿瘤", "前列腺恶性肿瘤", "宫颈恶性肿瘤", "卵巢恶性肿瘤",
    # 手术
    "手术", "切除", "置换", "植入", "成形", "重建", "吻合", "穿刺",
    "支架", "起搏器植入", "输液港", "植入术",
    # 损伤
    "骨折", "脱位", "扭伤", "创伤", "挫伤", "撕裂伤", "烧伤",
    # 关节
    "骨关节炎", "类风湿性关节炎", "强直性脊柱炎", "椎间盘突出", "椎管狭窄",
    "颈椎病", "腰椎间盘突出",
    # 眼/耳鼻喉
    "白内障", "青光眼", "视网膜脱离", "黄斑变性", "中耳炎", "鼻窦炎",
    # 妊娠
    "妊娠", "分娩", "剖宫产", "异位妊娠", "先兆流产", "产后出血",
    # 血液
    "贫血", "缺铁性贫血", "再生障碍性贫血", "血小板减少", "DIC",
    # 精神
    "抑郁症", "焦虑症", "精神分裂症", "双相情感障碍", "失眠症",
]

# Generic words that should not become keywords even if they survive n-gram split.
_STOPWORDS = {
    "患者", "因", "于", "行", "给予", "治疗", "入院", "出院", "诊断", "检查",
    "后", "前", "中", "为", "以", "无", "有", "及", "的", "了", "和", "是",
    "现", "病史", "主诉", "查体", "辅助", "处理", "情况", "症状", "体征",
    "并", "术", "未见", "明确", "示", "提示", "不伴", "未见明显", "请结合临床",
    "考虑", "可能", "建议", "完善", "进一步", "继续", "好转", "加重", "稳定",
    "转入", "转出", "上级", "医师", "主任", "主治", "住院", "门诊", "急诊",
    "今日", "昨日", "前日", "目前", "既往", "否认", "无明显", "无特殊", "无诉",
}

# Cross-language clinical aliases are retrieval queries, not coding rules.
# They let parallel English records reach the same governed Chinese catalogs
# as their Chinese counterparts, reducing language-dependent code drift.
_BILINGUAL_SEARCH_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("vertebral compression fracture", "t12 compression fracture", "椎体压缩性骨折", "t12椎体压缩性骨折"), "胸椎压缩性骨折"),
    (("osteoporosis", "骨质疏松"), "骨质疏松"),
    (("essential hypertension", "原发性高血压"), "原发性高血压"),
    (("type 2 diabetes", "type 2 diabetes mellitus", "2型糖尿病"), "2型糖尿病"),
    (("acute simple appendicitis", "acute appendicitis", "急性单纯性阑尾炎"), "急性阑尾炎"),
    (("community-acquired pneumonia", "社区获得性肺炎"), "肺炎"),
    (("diabetic ketoacidosis", "type 2 diabetic ketoacidosis", "2型糖尿病性酮症酸中毒"), "2型糖尿病伴有酮症酸中毒"),
    (("inferior st-elevation myocardial infarction", "inferior stemi", "急性下壁st段抬高型心肌梗死"), "下壁急性透壁性心肌梗死"),
    (("hyperlipidemia", "高脂血症"), "高脂血症"),
    (("tobacco dependence",), "烟草依赖"),
    (("open reduction and internal fixation", "脊椎骨折切开复位内固定术", "椎体切开复位内固定术"), "脊椎骨折切开复位内固定术"),
    (("laparoscopic appendectomy", "腹腔镜阑尾切除术"), "腹腔镜下阑尾切除术"),
    (("drug-eluting stent", "drug eluting stent", "药物涂层支架植入"), "冠状动脉药物涂层支架置入术"),
)


def extract_keywords(encounter_text: str, max_keywords: int = 8) -> list[str]:
    """Return top medical noun phrases (longest match first)."""
    if not encounter_text:
        return []
    seen: set[str] = set()
    out: list[str] = []

    # Equivalent Chinese and English charts frequently differ only in spaces
    # around Latin letters or digits ("2 型" vs "type 2").  Alias matching
    # must not let that typography select a different coding catalog path.
    folded = re.sub(r"\s+", "", encounter_text.casefold())
    for aliases, search_term in _BILINGUAL_SEARCH_ALIASES:
        if any(re.sub(r"\s+", "", alias.casefold()) in folded for alias in aliases) and search_term not in seen:
            seen.add(search_term)
            out.append(search_term)
            if len(out) >= max_keywords:
                return out

    # Prefer trigger terms first (high specificity)
    for term in _TRIGGER_TERMS:
        if term in encounter_text and term not in seen:
            seen.add(term)
            out.append(term)
            if len(out) >= max_keywords:
                return out

    # When curated bilingual aliases or clinical triggers matched, avoid
    # sending arbitrary English word fragments into the Chinese catalogs;
    # those fragments can receive spuriously high fuzzy scores and displace
    # the exact governed procedure candidate.
    if out:
        return out[:max_keywords]

    # Fallback: longest unique tokens not in stopwords
    tokens = re.findall(r"[一-鿿A-Za-z]{2,8}", encounter_text)
    for t in tokens:
        if t in _STOPWORDS or t in seen:
            continue
        if t.isdigit():
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= max_keywords:
            break
    return out


async def lookup_candidate_codes(
    encounter_text: str,
    top_k_per_keyword: int = 3,
    max_total: int = 8,
    coding_systems: Iterable[str] | None = None,
) -> list[dict]:
    """Run dictionary search for each keyword, return deduplicated candidates.

    Args:
        encounter_text: raw 病案首页 / 病程记录 text
        top_k_per_keyword: how many candidates per keyword search
        max_total: global cap on returned candidates (sorted by score desc)

    Returns:
        List of dicts with keys: code, name, score, chapter, parent_code, valid.
        Empty list if encounter_text is empty or dictionary is unavailable.
    """
    if not encounter_text:
        return []
    try:
        from app.services.code_dictionary import code_dict_service
    except Exception as e:
        logger.warning("dictionary_rag: code_dict_service unavailable: %s", e)
        return []

    keywords = extract_keywords(encounter_text)
    if not keywords:
        return []

    requested = {str(item).lower() for item in (coding_systems or ("icd10cn",))}
    systems = [
        pair for pair in (("icd10cn", "ICD10_CN"), ("icd9cm3", "ICD9_CM3"))
        if pair[0] in requested
    ] or [("icd10cn", "ICD10_CN")]
    per_system: dict[str, dict[str, dict]] = {key: {} for key, _ in systems}
    for system_key, dictionary_key in systems:
        candidates = per_system[system_key]
        for kw in keywords:
            try:
                results = await code_dict_service.search_codes(
                    kw, dictionary_key, top_k=top_k_per_keyword
                )
            except Exception as e:
                logger.debug(
                    "dictionary_rag: search failed for %r system=%s: %s",
                    kw, system_key, e,
                )
                continue
            for result in results:
                code = result.get("code", "")
                if not code:
                    continue
                # CodeDictionaryService uses partial-ratio search.  Without a
                # full-string component, a short parent label (for example
                # "阑尾炎") scores 1.0 and displaces the explicitly documented
                # child ("急性阑尾炎").  Re-rank locally by both partial and
                # whole-name similarity; exact names remain 1.0.
                name = str(result.get("name") or "")
                normalized_kw = re.sub(r"\s+", "", kw.casefold())
                normalized_name = re.sub(r"\s+", "", name.casefold())
                if normalized_kw and normalized_name:
                    whole = fuzz.ratio(normalized_kw, normalized_name) / 100.0
                    partial = float(result.get("score", 0) or 0)
                    reranked_score = round((0.35 * partial) + (0.65 * whole), 4)
                else:
                    reranked_score = float(result.get("score", 0) or 0)
                item = {
                    **result,
                    "score": reranked_score,
                    "coding_system": system_key,
                }
                if (
                    code not in candidates
                    or item.get("score", 0) > candidates[code].get("score", 0)
                ):
                    candidates[code] = item

    # Preserve representation from every explicitly requested system. A
    # single global sort could otherwise spend the entire budget on common
    # diagnosis candidates and starve procedure retrieval.
    quota = max(1, max_total // len(systems))
    ranked: list[dict] = []
    for system_key, _ in systems:
        ranked.extend(sorted(
            per_system[system_key].values(),
            key=lambda item: item.get("score", 0),
            reverse=True,
        )[:quota])
    return ranked[:max_total]


def format_candidates_block(candidates: Iterable[dict]) -> str:
    """Format candidates as a Chinese few-shot reference block for the system prompt.

    Returns empty string if no candidates. The block is intentionally a soft
    hint — the LLM is told it must still verify against encounter evidence.
    """
    candidates = list(candidates)
    if not candidates:
        return ""

    lines = [
        "候选编码参考（来自受控 ICD-10-CN / ICD-9-CM-3 目录；仍须以病历证据为准）：",
    ]
    for i, c in enumerate(candidates, 1):
        code = c.get("code", "")
        name = c.get("name", "")
        score = c.get("score", 0)
        chapter = c.get("chapter", "")
        system = c.get("coding_system", "icd10cn")
        lines.append(
            f"  {i}. [{system}] {code}  {name}  "
            f"(relevance={score:.2f}, chapter={chapter})"
        )
    lines.append(
        "提示：优先从以上候选中选择，并原样复制完整编码（包括 x 占位位），"
        "不得缩写、扩写或凭记忆制造目录外编码。只有病历明确支持时才可选择更具体子码；"
        "病历未指明具体类型时允许使用未特指编码。"
    )
    return "\n".join(lines)


def _extract_user_text(messages: list[dict[str, str]] | None) -> str:
    """Pull the encounter text out of chat messages (last user message wins)."""
    if not messages:
        return ""
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""
