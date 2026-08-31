"""Evidence-bound local medication reconciliation.

This baseline compares only explicitly labelled home, inpatient/MAR, and
discharge medication sources. It performs exact-name alignment and documented
dose/route/frequency comparison. It does not infer indications, brand/generic
equivalence, therapeutic class duplication, interactions, contraindications,
renal/hepatic dose suitability, or a safe prescribing plan.
"""

from __future__ import annotations

from collections import defaultdict
import json
import re
import uuid
from typing import Any


AGENT_REF = "icoder/med-reconciliation@1.1.0"
LOCAL_RUNTIME_MODE = "governed_local_documented_medication_reconciliation"
OUTPUT_CONTRACT_REF = "icoder/MedicationReconciliationOutput/v4"
MAX_INPUT_CHARS = 20_000
MAX_MEDICATIONS_PER_SOURCE = 100

_SOURCE_RE = re.compile(
    r"(?P<label>"
    r"入院前(?:用药|药物)?(?:服用)?|家庭用药|既往用药|"
    r"住院(?:中|期间)(?:用药|药物|MAR)?|"
    r"(?:拟)?出院(?:医嘱|用药|带药|药物)(?:仅列|仅有|包括)?"
    r")\s*(?:为|是)?\s*[：:]?",
    re.I,
)
_ALLERGY_RE = re.compile(
    r"(?:药物过敏史?|过敏史)\s*[：:]\s*(?P<value>[^。；;\n]{1,200})",
    re.I,
)
_CLAUSE_SPLIT_RE = re.compile(r"[。；;\n]+")
_DOSE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<dose>\d+(?:\.\d+)?\s*"
    r"(?:mg|g|μg|ug|mcg|ml|mL|片|粒|支|单位|IU|U))",
    re.I,
)
_FREQUENCY_RE = re.compile(
    r"(?P<frequency>bid|tid|qid|qd|qod|qhs|prn|q\d{1,2}h|"
    r"每日\s*\d+\s*次|每天\s*\d+\s*次|日\s*\d+\s*次|"
    r"每\s*\d+\s*小时(?:一次)?|早晚各?\s*\d*\s*次?)",
    re.I,
)
_ROUTE_RE = re.compile(
    r"(?P<route>口服|静脉滴注|静滴|静脉注射|皮下注射|肌内注射|"
    r"肌肉注射|外用|吸入|舌下含服|鼻饲)",
    re.I,
)
_STATUS_RULES = (
    (re.compile(r"暂停|暂缓"), "HELD"),
    (re.compile(r"拒绝|拒服"), "REFUSED"),
    (re.compile(r"停用|停止|撤除"), "STOPPED"),
    (re.compile(r"恢复|继续"), "CONTINUED"),
    (re.compile(r"新增|新开|开始"), "STARTED"),
    (re.compile(r"已给|给予|给药|使用中"), "GIVEN"),
)
_NAME_STOP_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg|g|μg|ug|mcg|ml|mL|片|粒|支|单位|IU|U)|"
    r"bid|tid|qid|qd|qod|qhs|prn|q\d{1,2}h|"
    r"口服|静脉滴注|静滴|静脉注射|皮下注射|肌内注射|肌肉注射|"
    r"外用|吸入|舌下含服|鼻饲|按|因|由于|暂停|暂缓|停用|停止|"
    r"拒绝|拒服|恢复|继续|新增|新开|开始|调整|改为|，|,",
    re.I,
)
_LEADING_NOISE_RE = re.compile(
    r"^(?:药物|用药|服用|使用|予以|给予|仅列|仅有|包括|记录|"
    r"医嘱|拟|患者|长期|规律|目前|现|口服)+",
)
_NO_NAME_PREFIXES = (
    "因", "由于", "按", "未写", "未说明", "缺失", "无", "请",
    "复查", "计划", "原因", "医嘱", "记录",
)
_MISSING_MARKERS = ("缺失", "未提供", "未列", "无用药", "未记录")
_UNTRUSTED_BOUNDARIES = (
    "\n病历中的转录噪声",
    "\n不可信原文",
    "\n忽略上文",
    "ICODER_PROMPT_CANARY_",
)
_PUBLIC_FIELDS = (
    "reconciliation_status",
    "home_medications",
    "inpatient_medications",
    "discharge_medications",
    "reconciliation_summary",
    "discrepancies",
    "interaction_screening_status",
    "interaction_risks",
    "allergy_review_status",
    "allergy_conflicts",
    "missing_rationale",
    "follow_up_items",
    "unresolved_mentions",
    "source_completeness",
    "limitations",
    "manual_review_required",
    "trace_refs",
)


def verify_medication_reconciliation_health() -> dict[str, Any]:
    return {
        "state": "ok",
        "network_required": False,
        "llm_required": False,
        "drug_knowledge_base_used": False,
        "interaction_screening_available": False,
        "brand_generic_normalization_available": False,
        "exact_documented_comparison_available": True,
        "production_writeback_blocked": True,
    }


def _bounded_text(value: Any) -> str:
    text = str(value or "")
    for marker in _UNTRUSTED_BOUNDARIES:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text[:MAX_INPUT_CHARS]


def _source_for_label(label: str) -> str:
    if "入院前" in label or "家庭" in label or "既往" in label:
        return "home"
    if "住院" in label:
        return "inpatient"
    return "discharge"


def _source_sections(text: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bool]]:
    matches = list(_SOURCE_RE.finditer(text))
    sections: dict[str, list[dict[str, Any]]] = defaultdict(list)
    explicitly_complete = {"home": False, "inpatient": False, "discharge": False}
    for index, match in enumerate(matches):
        source = _source_for_label(match.group("label"))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end]
        sections[source].append({
            "label": match.group("label"),
            "content": content,
            "start": start,
            "end": end,
            "declared_missing": any(marker in content[:80] for marker in _MISSING_MARKERS),
        })
        if any(marker in match.group("label") for marker in ("仅列", "仅有")):
            explicitly_complete[source] = True
    return dict(sections), explicitly_complete


def _normalize_identity(value: str) -> str:
    return re.sub(r"[\s\-—_（）()\[\]【】]", "", str(value or "")).casefold()


def _extract_name(clause: str) -> str:
    candidate = clause.strip(" ‘'\"“”。，；;:：")
    candidate = _LEADING_NOISE_RE.sub("", candidate).strip()
    if not candidate or candidate.startswith(_NO_NAME_PREFIXES):
        return ""
    stop = _NAME_STOP_RE.search(candidate)
    name = candidate[: stop.start()] if stop else candidate
    name = name.strip(" ‘'\"“”。，；;:：")
    if not (2 <= len(name) <= 80):
        return ""
    if name.startswith(_NO_NAME_PREFIXES) or name in {
        "药物", "用药", "造影", "血糖", "复查计划", "出院医嘱",
    }:
        return ""
    if not any(char.isalpha() or "\u4e00" <= char <= "\u9fff" for char in name):
        return ""
    return name


def _documented_status(clause: str) -> str:
    for pattern, status in _STATUS_RULES:
        if pattern.search(clause):
            return status
    return "LISTED"


def _reason(clause: str) -> str:
    patterns = (
        r"(?:因|由于)(?P<reason>[^，,。；;]{1,80}?)(?:而)?(?:暂停|暂缓|停用|停止|调整|改为)",
        r"(?:暂停|暂缓|停用|停止)[^，,。；;]{0,20}(?:因|由于)(?P<reason>[^，,。；;]{1,80})",
    )
    for pattern in patterns:
        match = re.search(pattern, clause)
        if match:
            return match.group("reason").strip()
    return ""


def _one_medication(
    clause: str,
    *,
    source: str,
    start: int,
    inherited_name: str = "",
) -> dict[str, Any] | None:
    stripped = clause.strip()
    if not stripped:
        return None
    leading = len(clause) - len(clause.lstrip())
    absolute_start = start + leading
    explicit_name = _extract_name(stripped)
    name = explicit_name or inherited_name
    if not name:
        return None
    dose_match = _DOSE_RE.search(stripped)
    frequency_match = _FREQUENCY_RE.search(stripped)
    route_match = _ROUTE_RE.search(stripped)
    return {
        "drug_name": name,
        "dose": dose_match.group("dose") if dose_match else "",
        "route": route_match.group("route") if route_match else "",
        "frequency": frequency_match.group("frequency") if frequency_match else "",
        "status": _documented_status(stripped),
        "reason": _reason(stripped),
        "instructions": stripped,
        "source": source,
        "identity_basis": (
            "verbatim_name" if explicit_name else "adjacent_single_medication_reference"
        ),
        "evidence_text": stripped,
        "char_span": [absolute_start, absolute_start + len(stripped)],
    }


def _parse_source(
    text: str,
    source: str,
    sections: list[dict[str, Any]],
    *,
    inherited_name: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    medications: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for section in sections:
        content = str(section["content"])
        cursor = 0
        for match in _CLAUSE_SPLIT_RE.finditer(content + "\n"):
            clause = content[cursor:match.start()]
            clause_start = int(section["start"]) + cursor
            cursor = match.end()
            stripped = clause.strip()
            if not stripped or stripped.startswith("请"):
                continue
            inherited = ""
            if (
                not _extract_name(stripped)
                and inherited_name
                and any(token in stripped for token in ("暂停", "暂缓", "停用", "停止", "恢复", "继续"))
            ):
                inherited = inherited_name
            item = _one_medication(
                clause,
                source=source,
                start=clause_start,
                inherited_name=inherited,
            )
            if item is not None:
                medications.append(item)
            elif any(token in stripped for token in ("药", "暂停", "停用", "给药", "医嘱")):
                leading = len(clause) - len(clause.lstrip())
                absolute_start = clause_start + leading
                unresolved.append({
                    "source": source,
                    "evidence_text": stripped,
                    "char_span": [absolute_start, absolute_start + len(stripped)],
                    "reason": "未获得明确药名；保留原文，不归属于任何药物。",
                })
            if len(medications) >= MAX_MEDICATIONS_PER_SOURCE:
                break
    return medications, unresolved


def _source_record(medication: dict[str, Any] | None) -> str:
    if medication is None:
        return "未列出"
    fields = [
        medication.get("dose") or "剂量未记录",
        medication.get("route") or "途径未记录",
        medication.get("frequency") or "频次未记录",
        medication.get("status") or "状态未记录",
    ]
    return "/".join(str(item) for item in fields)


def _differences(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    labels = {"dose": "剂量", "route": "途径", "frequency": "频次"}
    differences: list[str] = []
    for field, label in labels.items():
        a = str(left.get(field) or "")
        b = str(right.get(field) or "")
        if a and b and a.casefold() != b.casefold():
            differences.append(f"{label}：{a} → {b}")
    return differences


def _comparison(
    medications: dict[str, list[dict[str, Any]]],
    *,
    source_present: dict[str, bool],
    explicitly_complete: dict[str, bool],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    by_source: dict[str, dict[str, list[dict[str, Any]]]] = {}
    display_by_identity: dict[str, str] = {}
    for source, items in medications.items():
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            identity = _normalize_identity(str(item["drug_name"]))
            grouped[identity].append(item)
            display_by_identity.setdefault(identity, str(item["drug_name"]))
        by_source[source] = dict(grouped)

    identities = sorted(display_by_identity, key=lambda key: display_by_identity[key])
    summary: list[dict[str, Any]] = []
    discrepancies: list[dict[str, Any]] = []
    missing_rationale: list[str] = []
    follow_up: list[str] = []

    for identity in identities:
        home_rows = by_source.get("home", {}).get(identity, [])
        inpatient_rows = by_source.get("inpatient", {}).get(identity, [])
        discharge_rows = by_source.get("discharge", {}).get(identity, [])
        home = home_rows[0] if home_rows else None
        inpatient = inpatient_rows[0] if inpatient_rows else None
        discharge = discharge_rows[0] if discharge_rows else None
        name = display_by_identity[identity]
        differences = _differences(home, discharge) if home and discharge else []
        category = "NEEDS_CLARIFICATION"
        clarification = True

        held_inpatient = bool(
            inpatient and inpatient.get("status") in {"HELD", "STOPPED", "REFUSED"}
        )
        if home and discharge:
            if differences:
                category = "CHANGE"
            elif held_inpatient:
                category = "NEEDS_CLARIFICATION"
            else:
                category = "CONTINUE"
                clarification = False
        elif discharge and source_present.get("home"):
            category = "START"
        elif home and source_present.get("discharge") and explicitly_complete.get("discharge"):
            category = "STOP"
        elif inpatient and not discharge:
            category = "NEEDS_CLARIFICATION"

        evidence_refs = [
            f"{row['source']}:{row['char_span'][0]}-{row['char_span'][1]}:{row['evidence_text']}"
            for row in (home, inpatient, discharge)
            if row is not None
        ]
        summary.append({
            "drug_name": name,
            "category": category,
            "home": _source_record(home),
            "inpatient": _source_record(inpatient),
            "discharge": _source_record(discharge),
            "differences": differences,
            "clarification_required": clarification,
            "evidence_refs": evidence_refs,
        })

        for source, rows in (
            ("home", home_rows), ("inpatient", inpatient_rows), ("discharge", discharge_rows)
        ):
            if len(rows) > 1:
                discrepancies.append({
                    "drug_name": name,
                    "type": "EXACT_NAME_DUPLICATE",
                    "description": f"{source} 来源中同一字面药名出现 {len(rows)} 次；未判断是否治疗重复。",
                    "evidence_refs": [str(row["evidence_text"]) for row in rows],
                })

        for source, row in (("home", home), ("inpatient", inpatient), ("discharge", discharge)):
            if row is None:
                continue
            missing = [
                label for field, label in (("dose", "剂量"), ("route", "途径"), ("frequency", "频次"))
                if not row.get(field)
            ]
            if missing:
                discrepancies.append({
                    "drug_name": name,
                    "type": "MISSING_DOCUMENTED_DETAILS",
                    "description": f"{source} 来源未记录：{'、'.join(missing)}。",
                    "evidence_refs": [str(row["evidence_text"])],
                })

        if differences:
            discrepancies.append({
                "drug_name": name,
                "type": "DOCUMENTED_FIELD_CHANGE",
                "description": "入院前与出院来源存在明确字段变化：" + "；".join(differences),
                "evidence_refs": [str(home["evidence_text"]), str(discharge["evidence_text"])],
            })
            if discharge and not discharge.get("reason"):
                missing_rationale.append(f"{name} 的已记录字段变化未附变更原因。")

        if held_inpatient and discharge:
            discrepancies.append({
                "drug_name": name,
                "type": "HELD_THEN_RELISTED",
                "description": "住院来源记录暂停/停用/拒绝，出院来源再次列出；恢复或继续依据未在输入中说明。",
                "evidence_refs": [str(inpatient["evidence_text"]), str(discharge["evidence_text"])],
            })
            missing_rationale.append(f"{name} 住院暂停/停用后在出院来源再次列出，恢复或继续依据缺失。")

        if inpatient and not discharge:
            discrepancies.append({
                "drug_name": name,
                "type": "MISSING_DISCHARGE_DISPOSITION",
                "description": "住院来源列出该药，但出院来源未列出其继续、停止或变更去向。",
                "evidence_refs": [str(inpatient["evidence_text"])],
            })
            missing_rationale.append(f"{name} 缺少出院继续、停止或变更去向及原因。")

        if home and not discharge and source_present.get("discharge"):
            discrepancies.append({
                "drug_name": name,
                "type": "HOME_NOT_ON_DISCHARGE_LIST",
                "description": "入院前来源列出该药，出院来源未列出；仅报告清单差异，不推断临床停药决定。",
                "evidence_refs": [str(home["evidence_text"])],
            })
            missing_rationale.append(f"{name} 未出现在出院来源，输入未说明继续或停用意图。")

        if clarification:
            follow_up.append(
                f"请医师或药师确认 {name} 的转衔分类、完整剂量/途径/频次及变更理由。"
            )

    return summary, discrepancies, list(dict.fromkeys(missing_rationale)), list(dict.fromkeys(follow_up))


def _allergies(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in _ALLERGY_RE.finditer(text):
        raw_value = match.group("value")
        value = raw_value.strip()
        if any(marker in value for marker in ("否认", "无", "未发现", "不详")):
            continue
        for item_match in re.finditer(r"[^、，,/]+", raw_value):
            item = item_match.group()
            name = item.strip(" \t‘'\"“”")
            if name:
                start = (
                    match.start("value")
                    + item_match.start()
                    + item.find(name)
                )
                rows.append({
                    "allergen": name,
                    "evidence_text": name,
                    "char_span": [start, start + len(name)],
                })
    return rows[:100]


def _allergy_conflicts(
    allergies: list[dict[str, Any]],
    medications: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    active = medications.get("inpatient", []) + medications.get("discharge", [])
    for allergy in allergies:
        allergy_id = _normalize_identity(allergy["allergen"])
        for medication in active:
            if allergy_id and allergy_id == _normalize_identity(medication["drug_name"]):
                conflicts.append({
                    "drug_name": medication["drug_name"],
                    "allergen": allergy["allergen"],
                    "match_basis": "EXACT_LITERAL_NAME_ONLY",
                    "evidence_refs": [allergy["evidence_text"], medication["evidence_text"]],
                })
    return conflicts


def _empty_response(run_id: str) -> dict[str, Any]:
    return {
        "reconciliation_status": "INPUT_REQUIRED",
        "home_medications": [],
        "inpatient_medications": [],
        "discharge_medications": [],
        "reconciliation_summary": [],
        "discrepancies": [],
        "interaction_screening_status": "NOT_ASSESSED_LICENSED_SOURCE_REQUIRED",
        "interaction_risks": [],
        "allergy_review_status": "NO_ALLERGY_SOURCE",
        "allergy_conflicts": [],
        "missing_rationale": ["未提供明确标注的入院前、住院中或出院用药来源。"],
        "follow_up_items": ["请提供至少一个明确标注的药物来源清单。"],
        "unresolved_mentions": [],
        "source_completeness": {
            "home_source_present": False,
            "inpatient_source_present": False,
            "discharge_source_present": False,
            "comparison_ready": False,
        },
        "limitations": [
            "未执行用药重整；没有从一般病历叙述推断药物。",
            "相互作用、同类重复、禁忌和剂量适宜性需要授权 DrugBank/医院药品库。",
        ],
        "manual_review_required": True,
        "trace_refs": {"run_id": run_id or str(uuid.uuid4()), "provider_trace_refs": []},
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "_trace": {"evidence_items_count": 0, "valid_spans_count": 0},
    }


def reconcile_medications(text: str, *, run_id: str = "") -> dict[str, Any]:
    source_text = _bounded_text(text)
    sections, explicitly_complete = _source_sections(source_text)
    if not sections:
        return _empty_response(run_id)

    home, unresolved_home = _parse_source(source_text, "home", sections.get("home", []))
    inherited_home_name = home[0]["drug_name"] if len(home) == 1 else ""
    inpatient, unresolved_inpatient = _parse_source(
        source_text,
        "inpatient",
        sections.get("inpatient", []),
        inherited_name=inherited_home_name,
    )
    discharge, unresolved_discharge = _parse_source(
        source_text,
        "discharge",
        sections.get("discharge", []),
    )
    medications = {
        "home": home,
        "inpatient": inpatient,
        "discharge": discharge,
    }
    unresolved = unresolved_home + unresolved_inpatient + unresolved_discharge
    source_present = {
        source: bool(sections.get(source)) and not all(
            bool(section.get("declared_missing")) for section in sections.get(source, [])
        )
        for source in ("home", "inpatient", "discharge")
    }
    summary, discrepancies, missing_rationale, follow_up = _comparison(
        medications,
        source_present=source_present,
        explicitly_complete=explicitly_complete,
    )
    allergies = _allergies(source_text)
    allergy_conflicts = _allergy_conflicts(allergies, medications)
    comparison_ready = sum(source_present.values()) >= 2
    status = "COMPLETED" if comparison_ready and summary else "PARTIAL"
    if not summary:
        missing_rationale.append("明确来源标签内未提取到具有明确药名的药物。")
        follow_up.append("请核对来源标签和药名是否完整。")

    evidence_items = home + inpatient + discharge + unresolved + allergies
    result = {
        "reconciliation_status": status,
        "home_medications": home,
        "inpatient_medications": inpatient,
        "discharge_medications": discharge,
        "reconciliation_summary": summary,
        "discrepancies": discrepancies,
        "interaction_screening_status": "NOT_ASSESSED_LICENSED_SOURCE_REQUIRED",
        "interaction_risks": [],
        "allergy_review_status": (
            "EXACT_LITERAL_SCREEN_ONLY" if allergies else "NO_ALLERGY_SOURCE"
        ),
        "allergy_conflicts": allergy_conflicts,
        "missing_rationale": list(dict.fromkeys(missing_rationale)),
        "follow_up_items": list(dict.fromkeys(follow_up)),
        "unresolved_mentions": unresolved,
        "source_completeness": {
            "home_source_present": source_present["home"],
            "inpatient_source_present": source_present["inpatient"],
            "discharge_source_present": source_present["discharge"],
            "comparison_ready": comparison_ready,
        },
        "limitations": [
            "只按明确来源和药名字面值比较；未对品牌名/通用名、盐型、剂型或同类药物做归一化。",
            "未使用授权 DrugBank/医院药品库；相互作用、同类重复、禁忌和肾/肝功能剂量适宜性均未评估。",
            "START/STOP/CONTINUE/CHANGE 仅表示来源清单比较，不是处方或停药建议。",
            "所有差异、过敏字面冲突和缺失项必须由医师或药师复核。",
        ],
        "manual_review_required": True,
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "provider_trace_refs": [
                f"{run_id}:governed-medication-reconciliation"
            ] if run_id else [],
        },
        "runtime_mode": LOCAL_RUNTIME_MODE,
        "_trace": {
            "evidence_items_count": len(evidence_items),
            "valid_spans_count": sum(
                source_text[slice(*item["char_span"])] == item["evidence_text"]
                for item in evidence_items
            ),
            "source_count": sum(source_present.values()),
            "medication_count": len(home) + len(inpatient) + len(discharge),
            "discrepancy_count": len(discrepancies),
            "interaction_screening_used": False,
            "drug_knowledge_base_used": False,
        },
    }
    return result


def to_pack_output(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result.get(key) for key in _PUBLIC_FIELDS}


__all__ = [
    "AGENT_REF",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "reconcile_medications",
    "to_pack_output",
    "verify_medication_reconciliation_health",
]
