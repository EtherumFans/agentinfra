"""DRG Grouper — CHS-DRG 1.1 grouping with surgery + diagnosis support.

Supports both surgical cases (procedure-code → ADRG/DRG) and medical cases
(diagnosis-code → MDC → medical ADRG). CC/MCC level determined from secondary
diagnoses when available.
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Path to OpenDRG knowledge base
KB_ROOT = Path(__file__).parent.parent.parent.parent.parent / "iCoDerA" / "data" / "procedure_coding"
MAPPING_PATH = KB_ROOT / "surgery_to_drg_mapping.json"
DRG_GROUPS_PATH = KB_ROOT / "drg_groups_chs11.json"
ADRG_PATH = KB_ROOT / "drg_adrg_mapping_chs11.json"

# Lazy-loaded singletons
_surgery_drg_map: dict = {}
_drg_groups: dict = {}
_adrg_map: dict = {}
_loaded = False


def _ensure_loaded():
    global _loaded, _surgery_drg_map, _drg_groups, _adrg_map
    if _loaded:
        return
    try:
        if MAPPING_PATH.exists():
            with open(MAPPING_PATH, "r", encoding="utf-8") as f:
                _surgery_drg_map = json.load(f)
            logger.info("DRG Grouper: loaded %d surgery-to-DRG mappings",
                        len(_surgery_drg_map.get("surgery_to_drg", [])))

        if DRG_GROUPS_PATH.exists():
            with open(DRG_GROUPS_PATH, "r", encoding="utf-8") as f:
                _drg_groups = json.load(f)
            logger.info("DRG Grouper: loaded %d DRG groups", len(_drg_groups))

        if ADRG_PATH.exists():
            with open(ADRG_PATH, "r", encoding="utf-8") as f:
                _adrg_map = json.load(f)
    except Exception as e:
        logger.error("DRG Grouper init failed: %s", e)
    _loaded = True


# ── MDC mapping: ICD-10 chapter letter → MDC ─────────────────────────────────
# Based on CHS-DRG 1.1 MDC definitions
# Special diagnosis code → MDC overrides (chapter A/B codes by body system)
_MDC_OVERRIDES: dict[str, tuple[str, str]] = {
    "A41": ("MDCZ", "感染性疾病"),  # 败血症
    "A40": ("MDCZ", "感染性疾病"),  # 链球菌败血症
    "B20": ("MDCZ", "感染性疾病"),  # HIV
    "B95": ("MDCZ", "感染性疾病"),  # 细菌感染
    "B96": ("MDCZ", "感染性疾病"),
    "B97": ("MDCZ", "感染性疾病"),
    "B98": ("MDCZ", "感染性疾病"),
    "B99": ("MDCZ", "感染性疾病"),
}

_MDC_MAP: dict[str, tuple[str, str]] = {
    "A": ("MDCZ", "感染性疾病"),
    "B": ("MDCZ", "感染性疾病"),
    "C": ("MDCB", "眼科疾病及功能障碍"),
    "D": ("MDCB", "眼科疾病及功能障碍"),
    "E": ("MDCC", "耳鼻喉疾病及功能障碍"),
    "F": ("MDCD", "精神疾病及功能障碍"),
    "G": ("MDCA", "神经系统疾病及功能障碍"),
    "H": ("MDCB", "眼科疾病及功能障碍"),
    "I": ("MDCF", "循环系统疾病及功能障碍"),
    "J": ("MDCE", "呼吸系统疾病及功能障碍"),
    "K": ("MDCG", "消化系统疾病及功能障碍"),
    "L": ("MDCH", "皮肤疾病及功能障碍"),
    "M": ("MDCI", "骨骼/肌肉疾病及功能障碍"),
    "N": ("MDCL", "泌尿系统疾病及功能障碍"),
    "O": ("MDCO", "妊娠/分娩疾病及功能障碍"),
    "P": ("MDCP", "新生儿疾病及功能障碍"),
    "Q": ("MDCP", "新生儿疾病及功能障碍"),
    "R": ("MDCZ", "症状/体征异常"),
    "S": ("MDCI", "骨骼/肌肉疾病及功能障碍"),
    "T": ("MDCI", "骨骼/肌肉疾病及功能障碍"),
    "Z": ("MDCY", "其他因素"),
}

# Medical ADRGs per MDC with diagnosis code prefix patterns
# Format: (adrg, adrg_name, [matching_prefixes])
_MEDICAL_ADRG: dict[str, list[tuple[str, str, list[str]]]] = {
    "MDCF": [  # 循环系统
        ("FV3", "高血压", ["I10", "I11", "I12", "I13", "I15"]),
        ("FU1", "心力衰竭", ["I50"]),
        ("FQ3", "冠心病", ["I20", "I24", "I25"]),
        ("FR3", "急性心肌梗死", ["I21", "I22"]),
        ("FW1", "心律失常", ["I44", "I45", "I46", "I47", "I48", "I49"]),
        ("BV3", "脑卒中", ["I60", "I61", "I62", "I63", "I64", "I65", "I66"]),
    ],
    "MDCE": [  # 呼吸系统
        ("EV3", "肺炎", ["J12", "J13", "J14", "J15", "J16", "J17", "J18"]),
        ("ET1", "慢性阻塞性肺疾病", ["J44"]),
        ("ER3", "支气管炎", ["J20", "J21", "J40", "J41", "J42"]),
        ("ES3", "呼吸衰竭", ["J96"]),
        ("EW1", "哮喘", ["J45", "J46"]),
    ],
    "MDCG": [  # 消化系统
        ("GV3", "胃炎", ["K29"]),
        ("GU3", "消化性溃疡", ["K25", "K26", "K27", "K28"]),
        ("GR3", "肝硬化", ["K74"]),
        ("GW1", "胰腺炎", ["K85"]),
        ("GZ1", "消化道出血", ["K92"]),
        ("GT3", "肠炎", ["K50", "K51", "K52"]),
    ],
    "MDCL": [  # 泌尿系统
        ("LU3", "急性肾功能衰竭", ["N17"]),
        ("LV3", "慢性肾脏病", ["N18"]),
        ("LW3", "尿路感染", ["N30", "N34", "N39"]),
        ("LX3", "肾结石", ["N20", "N21", "N22"]),
    ],
    "MDCA": [  # 神经系统
        ("BR3", "帕金森病", ["G20", "G21"]),
        ("BT3", "癫痫", ["G40", "G41"]),
        ("BX3", "头痛", ["G43", "G44"]),
    ],
    "MDCI": [  # 骨骼/肌肉
        ("IV3", "骨折", ["S02", "S12", "S22", "S32", "S42", "S52", "S62", "S72", "S82", "S92"]),
        ("IT3", "骨关节炎", ["M15", "M16", "M17", "M18", "M19"]),
        ("IU3", "椎间盘疾病", ["M50", "M51"]),
        ("IZ3", "风湿性关节炎", ["M05", "M06", "M08"]),
    ],
    "MDCH": [  # 皮肤
        ("JV3", "蜂窝织炎", ["L03"]),
        ("JZ3", "皮肤溃疡", ["L89", "L97"]),
    ],
    "MDCB": [  # 眼科
        ("CV3", "白内障", ["H25", "H26"]),
        ("CT3", "青光眼", ["H40", "H42"]),
    ],
    "MDCZ": [  # 感染/其他
        ("SZ1", "败血症", ["A40", "A41"]),
        ("SZ3", "HIV", ["B20", "B21", "B22", "B23", "B24"]),
    ],
}

# CC/MCC ICD-10 prefixes — codes starting with these indicate complications
_CC_PREFIXES = {
    "I10": 1, "I11": 2, "I12": 2, "I13": 2,  # 高血压
    "I50": 2,  # 心力衰竭 (MCC)
    "J96": 2,  # 呼吸衰竭 (MCC)
    "N17": 2, "N18": 1, "N19": 2,  # 肾功能衰竭
    "E11": 1,  # 糖尿病
    "J18": 1,  # 肺炎 (CC)
    "K72": 2, "K74": 2,  # 肝衰竭/肝硬化 (MCC)
    "I21": 2, "I22": 2,  # 急性心梗 (MCC)
    "I63": 1, "I64": 1,  # 脑卒中 (CC)
    "A41": 2,  # 败血症 (MCC)
    "D65": 2,  # DIC (MCC)
}


def normalize_code(code: str) -> str:
    """Normalize ICD code format for matching."""
    code = code.strip()
    code = re.sub(r'x\d+$', '', code)
    return code


def _assign_mdc(diagnosis_code: str) -> tuple[str, str]:
    """Determine MDC from ICD-10 code, with special overrides."""
    if not diagnosis_code:
        return ("", "")
    norm = normalize_code(diagnosis_code).upper()
    # Check overrides first (more specific)
    for prefix, (mdc, name) in _MDC_OVERRIDES.items():
        if norm.startswith(prefix):
            return (mdc, name)
    chapter = norm[0]
    return _MDC_MAP.get(chapter, ("", ""))


def _determine_cc_level(secondary_codes: list[str]) -> tuple[int, str]:
    """Determine CC/MCC level from secondary diagnosis codes.

    Returns (level, label) where level: 0=none, 1=CC, 2=MCC.
    """
    max_level = 0
    for code in secondary_codes:
        norm = normalize_code(code)
        for prefix, level in _CC_PREFIXES.items():
            if norm.startswith(prefix):
                max_level = max(max_level, level)
                if max_level >= 2:
                    return (2, "伴重要合并症/并发症 (MCC)")
    if max_level >= 2:
        return (2, "伴重要合并症/并发症 (MCC)")
    elif max_level >= 1:
        return (1, "伴一般合并症/并发症 (CC)")
    return (0, "不伴合并症/并发症")


def _assign_medical_adrg(primary_diag: str, mdc: str) -> tuple[str, str]:
    """Assign medical ADRG from primary diagnosis code.

    Matches diagnosis code prefix against known medical ADRG patterns
    for the MDC. Falls back to the first available medical ADRG.
    """
    if not primary_diag or mdc not in _MEDICAL_ADRG:
        return ("", "")
    norm = normalize_code(primary_diag).upper()
    adrgs = _MEDICAL_ADRG[mdc]
    # Prefix match: check against each ADRG's code prefixes
    for adrg_code, adrg_name, prefixes in adrgs:
        for prefix in prefixes:
            if norm.startswith(prefix):
                return (adrg_code, adrg_name)
    # Fallback: return first medical ADRG for this MDC
    return (adrgs[0][0], adrgs[0][1]) if adrgs else ("", "")


def _build_medical_drg(adrg: str, cc_level: int) -> str:
    """Build DRG code from ADRG + CC level suffix.

    CHS-DRG convention:
    - ADRG + 1 = with MCC
    - ADRG + 3 = with CC
    - ADRG + 5 = without CC/MCC
    """
    if not adrg:
        return ""
    base = re.sub(r'\d$', '', adrg)  # Strip trailing digit from ADRG
    if cc_level >= 2:
        return base + "1"
    elif cc_level >= 1:
        return base + "3"
    return base + "5"


def group_drg(
    diagnosis_codes: list[str],
    procedure_code: Optional[str] = None,
) -> dict:
    """Group a case into DRG using CHS-DRG 1.1 rules.

    Surgical cases: procedure_code → surgery-DRG mapping + CC refinement.
    Medical cases: primary diagnosis → MDC → medical ADRG + CC refinement.

    Args:
        diagnosis_codes: ICD-10-CN codes; first is primary diagnosis
        procedure_code: ICD-9-CM-3 procedure code (None for medical cases)

    Returns:
        {
            "mdc": "MDCF", "mdc_name": "循环系统疾病及功能障碍",
            "adrg": "FM1", "drg": "FM19",
            "drg_name": "...", "cc_level": "...",
            "grouping_method": "surgical" | "medical",
            "coverage": True/False
        }
    """
    _ensure_loaded()

    result = {
        "mdc": "", "mdc_name": "", "adrg": "", "drg": "",
        "drg_name": "", "cc_level": "", "grouping_method": "",
        "coverage": False,
    }

    primary_diag = diagnosis_codes[0] if diagnosis_codes else ""
    secondary_diags = diagnosis_codes[1:] if len(diagnosis_codes) > 1 else []

    # ── Determine MDC from primary diagnosis ──
    mdc, mdc_name = _assign_mdc(primary_diag)
    result["mdc"] = mdc
    result["mdc_name"] = mdc_name

    # ── Determine CC/MCC level from secondary diagnoses ──
    cc_level, cc_label = _determine_cc_level(secondary_diags)
    result["cc_level"] = cc_label

    # ── Surgical case: procedure-based grouping ──
    if procedure_code:
        norm_proc = normalize_code(procedure_code)
        surgeries = _surgery_drg_map.get("surgery_to_drg", [])

        match = None
        for surg in surgeries:
            if normalize_code(surg.get("icd9cm3_code", "")) == norm_proc:
                match = surg
                break

        if match:
            drg_groups = match.get("drg_groups", [])
            adrg_groups = match.get("adrg_groups", [])
            mdc_groups = match.get("mdc_groups", [])

            result["grouping_method"] = "surgical"
            result["coverage"] = True

            if drg_groups:
                # Refine DRG with CC level
                adrg = adrg_groups[0] if adrg_groups else ""
                result["adrg"] = adrg
                result["mdc"] = mdc_groups[0] if mdc_groups else mdc

                # Build refined DRG with CC suffix
                drg = _build_medical_drg(adrg, cc_level) if adrg else drg_groups[0]
                # Only refine if the surgery mapping doesn't already have a specific DRG
                if len(drg_groups) == 1 and not drg_groups[0][-1] in "1359":
                    pass  # Keep mapped DRG if it has no CC suffix
                else:
                    drg = _build_medical_drg(adrg, cc_level) if adrg else drg_groups[0]
                result["drg"] = drg

                if isinstance(_drg_groups, dict):
                    result["drg_name"] = _drg_groups.get(drg, drg_groups[0])

            if not result["drg_name"] and drg_groups:
                drg0 = drg_groups[0]
                if isinstance(_drg_groups, dict):
                    result["drg_name"] = _drg_groups.get(drg0, "")

            return result
        else:
            result["drg_name"] = f"手术编码 {procedure_code} 未匹配到DRG分组"
            return result

    # ── Medical case: diagnosis-based grouping ──
    result["grouping_method"] = "medical"

    adrg_code, adrg_name = _assign_medical_adrg(primary_diag, mdc)
    if adrg_code:
        result["adrg"] = adrg_code
        drg = _build_medical_drg(adrg_code, cc_level)
        result["drg"] = drg

        if isinstance(_drg_groups, dict):
            result["drg_name"] = _drg_groups.get(drg, adrg_name)
        if not result["drg_name"]:
            result["drg_name"] = adrg_name
        result["coverage"] = True
    else:
        result["drg_name"] = f"内科病例 (诊断 {primary_diag[:3]} 无对应 ADRG)"
        # Use MDC as fallback ADRG
        if mdc:
            result["adrg"] = mdc

    return result


def get_adrg_list() -> list[dict]:
    """Get all ADRG groups."""
    _ensure_loaded()
    result = []
    mappings = _adrg_map if isinstance(_adrg_map, list) else []
    for m in mappings[:50]:
        if isinstance(m, dict):
            result.append({
                "code": m.get("adrg", m.get("code", "")),
                "name": m.get("name", ""),
                "mdc": m.get("mdc", ""),
            })
    return result


def get_drg_list() -> list[dict]:
    """Get all DRG groups."""
    _ensure_loaded()
    result = []
    items = _drg_groups.items() if isinstance(_drg_groups, dict) else []
    for code, name in list(items)[:100]:
        result.append({"code": code, "name": name})
    return result
