"""Versioned built-in section definitions for Guided assembly requests."""

from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any


SECTION_VERSION_NAMESPACE = uuid.UUID("29d813b5-e5a4-4c69-9fc7-87f685856f12")

CURATED_SECTION_DEFINITIONS: dict[str, dict[str, Any]] = {
    "44444444-aaaa-bbbb-cccc-444444444444": {
        "heading": "Subjective",
        "instructions": {
            "contentPrompt": "Summarize patient-reported symptoms, history, and concerns.",
            "writingStylePrompt": "Use concise clinical prose and preserve uncertainty.",
        },
        "outputSchema": {"type": "string"},
    },
    "55555555-aaaa-bbbb-cccc-555555555555": {
        "heading": "Plan",
        "instructions": {
            "contentPrompt": "Summarize documented treatment, follow-up, and safety-net plans.",
            "writingStylePrompt": "Do not invent orders or recommendations.",
        },
        "outputSchema": {"type": "string"},
    },
    "10000001-aaaa-4c01-8c01-100000000001": {
        "heading": "主诉",
        "instructions": {
            "contentPrompt": "仅概括促使患者本次就诊的主要症状或体征及持续时间；来源未记录时留空，不得推测。",
            "writingStylePrompt": "使用简明、规范的中文医学术语。",
        },
        "outputSchema": {"type": "string"},
    },
    "10000002-aaaa-4c02-8c02-100000000002": {
        "heading": "现病史",
        "instructions": {
            "contentPrompt": "按时间顺序整理本次疾病的发生、演变、主要症状、伴随症状及已记录的诊疗经过；不得补造阴性资料。",
            "writingStylePrompt": "保持时间线清晰，并保留来源中的不确定性。",
        },
        "outputSchema": {"type": "string"},
    },
    "10000003-aaaa-4c03-8c03-100000000003": {
        "heading": "既往史",
        "instructions": {
            "contentPrompt": "整理来源中明确记录的一般健康状况、疾病史、传染病史、预防接种史、手术外伤史及输血史；未提及不得写作无。",
            "writingStylePrompt": "采用客观、可核对的中文临床表述。",
        },
        "outputSchema": {"type": "string"},
    },
    "10000004-aaaa-4c04-8c04-100000000004": {
        "heading": "过敏史",
        "instructions": {
            "contentPrompt": "仅记录来源中明确的药物、食物或其他过敏及反应；未记录时留空，不得自动填写否认过敏。",
            "writingStylePrompt": "药物名称与反应分开表达，保留原始不确定性。",
        },
        "outputSchema": {"type": "string"},
    },
    "10000005-aaaa-4c05-8c05-100000000005": {
        "heading": "体格检查",
        "instructions": {
            "contentPrompt": "仅整理实际记录的生命体征、阳性体征、必要阴性体征和专科检查结果；不得生成未实施的查体。",
            "writingStylePrompt": "按系统或专科顺序使用规范医学术语。",
        },
        "outputSchema": {"type": "string"},
    },
    "10000006-aaaa-4c06-8c06-100000000006": {
        "heading": "辅助检查",
        "instructions": {
            "contentPrompt": "整理来源中与本次诊疗相关的检验、影像和其他检查结果，并保留日期、机构及异常标记等已有信息。",
            "writingStylePrompt": "不得解释或补充来源未给出的检查结论。",
        },
        "outputSchema": {"type": "string"},
    },
    "10000007-aaaa-4c07-8c07-100000000007": {
        "heading": "诊断与评估",
        "instructions": {
            "contentPrompt": "仅整理临床来源中明确记录的诊断、待查问题及鉴别诊断；不得自主新增或确认诊断。",
            "writingStylePrompt": "多项诊断按来源中的主次关系表达，保留待查与疑似措辞。",
        },
        "outputSchema": {"type": "string"},
    },
    "10000008-aaaa-4c08-8c08-100000000008": {
        "heading": "诊疗计划",
        "instructions": {
            "contentPrompt": "仅整理已经记录的检查、治疗、用药、随访和安全提示；不得生成新的医嘱、处方或剂量。",
            "writingStylePrompt": "使用清晰条目并区分已执行事项与计划事项。",
        },
        "outputSchema": {"type": "string"},
    },
    "10000009-aaaa-4c09-8c09-100000000009": {
        "heading": "出院情况与医嘱",
        "instructions": {
            "contentPrompt": "仅整理来源中明确记录的出院时状况、出院诊断、用药、复诊和注意事项；不得生成未经医师确认的出院医嘱。",
            "writingStylePrompt": "区分出院情况、出院用药、复诊安排和警示事项。",
        },
        "outputSchema": {"type": "string"},
    },
}


def section_version_id(section_id: str) -> str:
    return str(uuid.uuid5(SECTION_VERSION_NAMESPACE, section_id))


def resolve_curated_section(
    section_id: str,
    section_version: str | None = None,
) -> dict[str, Any] | None:
    definition = CURATED_SECTION_DEFINITIONS.get(section_id)
    if definition is None:
        return None
    expected = section_version_id(section_id)
    if section_version is not None and section_version != expected:
        return None
    value = deepcopy(definition)
    value["sectionId"] = section_id
    value["sectionVersionId"] = expected
    return value
