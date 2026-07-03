"""Sample ICD-10-CN / ICD-9-CM-3 catalog for the thin slice.

This is a *demo sample* (~15 codes) — production binds the 37,897-code
``icd10cn_code_catalog.json`` + 75,968-synonym map at E:\\iCoDerA. It covers one coherent
encounter (心衰 + CKD + 糖尿病 + 肺炎 + 房颤) plus the 5 documented high-risk / 易错 codes
so the compliance gate and human-review loop are demonstrable.

The 5 high-risk codes (from the M3-0 样板 Agent spec):
  I66.901 / J98.414 / M80.900 / 45.1600x001 / Z51.102
"""
from __future__ import annotations

CATALOG_VERSION = "icd10cn-sample@0.1.0"
ICD10CN = "ICD-10-CN"
ICD9CM3 = "ICD-9-CM-3"

# code -> entry
CATALOG: dict[str, dict] = {
    "I50.900": {
        "display": "慢性心力衰竭",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["慢性心力衰竭", "慢性心衰", "心力衰竭", "心功能不全", "心衰"],
        "notes": [
            ("code_first", "先编码导致心力衰竭的基础心脏病（如高血压性心脏病 I11.0）"),
            ("use_additional", "如记录心功能分级，附加编码标明（NYHA 分级）"),
        ],
        "guideline": "心力衰竭作为其他疾病的并发症时，按主要疾病与并发症的顺序编码；单独就诊以心衰为主要诊断。",
        "parent": "I50",
        "siblings": ["I50.000", "I50.100"],
        "children": ["I50.907"],
        "high_risk": False,
        "differentiation": [],
    },
    "I50.907": {
        "display": "心功能Ⅲ级",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["心功能Ⅲ级", "心功能III级", "心功能3级"],
        "notes": [],
        "guideline": "心功能分级为心衰的补充描述，通常作为附加编码。",
        "parent": "I50",
        "siblings": ["I50.900"],
        "children": [],
        "high_risk": False,
        "differentiation": [],
    },
    "I10.x00": {
        "display": "高血压",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["高血压", "原发性高血压", "高血压病", "高血压2级", "高血压3级"],
        "notes": [("use_additional", "如有靶器官损害（心、肾），分别附加编码")],
        "guideline": "原发性高血压编码至 I10；若合并心/肾损害，按 I11–I13 合并编码规则处理。",
        "parent": "I10",
        "siblings": [],
        "children": [],
        "high_risk": False,
        "differentiation": [],
    },
    "E11.900": {
        "display": "2型糖尿病",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["2型糖尿病", "Ⅱ型糖尿病", "II型糖尿病", "糖尿病", "2型糖尿病性"],
        "notes": [("use_additional", "如有糖尿病并发症（肾病、视网膜病变等），使用 E11 第四位亚目并附加编码")],
        "guideline": "糖尿病伴并发症时优先使用合并编码（E11.2–E11.8），不可拆为 E11.9 + 并发症独立码。",
        "parent": "E11",
        "siblings": ["E10.900"],
        "children": [],
        "high_risk": False,
        "differentiation": [],
    },
    "N18.900": {
        "display": "慢性肾脏病",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["慢性肾脏病", "慢性肾病", "慢性肾功能不全", "CKD"],
        "notes": [("use_additional", "如已知 CKD 分期，使用 N18.1–N18.5 具体亚目")],
        "guideline": "CKD 应尽量编码至分期亚目；N18.9 仅在分期未记录时使用。",
        "parent": "N18",
        "siblings": ["N18.500"],
        "children": ["N18.500"],
        "high_risk": False,
        "differentiation": [],
    },
    "N18.500": {
        "display": "慢性肾脏病5期",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["慢性肾脏病5期", "CKD5期", "尿毒症期", "肾衰竭终末期"],
        "notes": [],
        "guideline": "CKD 5 期（含透析依赖）应附加透析状态编码（如 Z99.2）。",
        "parent": "N18",
        "siblings": ["N18.900"],
        "children": [],
        "high_risk": False,
        "differentiation": [],
    },
    "J18.900": {
        "display": "肺炎",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["肺炎", "社区获得性肺炎", "细菌性肺炎"],
        "notes": [("excludes1", "新生儿肺炎 (P23.-)"), ("excludes2", "吸入性肺炎 (J69.-)")],
        "guideline": "病原体明确时优先编码至具体病原（如 J15.-）；未明确者编码 J18.9。",
        "parent": "J18",
        "siblings": ["J15.900"],
        "children": [],
        "high_risk": False,
        "differentiation": [],
    },
    "I48.x00": {
        "display": "心房颤动",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["心房颤动", "房颤", "持续性房颤", "阵发性房颤"],
        "notes": [],
        "guideline": "房颤作为并发症时按主诊断+并发症顺序编码。",
        "parent": "I48",
        "siblings": [],
        "children": [],
        "high_risk": False,
        "differentiation": [],
    },
    # ---- 5 high-risk / 易错 codes ----
    "I66.901": {
        "display": "大脑中动脉狭窄",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["大脑中动脉狭窄", "大脑动脉狭窄", "脑动脉狭窄", "大脑中动脉闭塞"],
        "notes": [("excludes1", "大脑动脉栓塞致脑梗死 (I63.-)")],
        "guideline": "I66 为脑动脉狭窄/闭塞未致梗死；若已发生脑梗死应编码至 I63.-。",
        "parent": "I66",
        "siblings": ["I63.900"],
        "children": [],
        "high_risk": True,
        "differentiation": [
            {"vs": "I63.900", "vs_display": "脑梗死", "level": "P0",
             "note": "狭窄(I66) vs 已致梗死(I63) 易混；以是否有梗死灶/缺血证据为准"},
        ],
    },
    "J98.414": {
        "display": "肺其他疾患（肺部阴影）",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["肺部阴影", "肺部占位", "肺占位", "肺部结节影"],
        "notes": [("excludes1", "肺部恶性肿瘤 (C34.-)"), ("code_first", "如已病理确诊肿瘤，先编码肿瘤")],
        "guideline": "影像学“肺部阴影/占位”在未定性前不可直接编码为肿瘤或肺炎。",
        "parent": "J98",
        "siblings": ["J18.900"],
        "children": [],
        "high_risk": True,
        "differentiation": [
            {"vs": "C34.900", "vs_display": "肺恶性肿瘤", "level": "P0",
             "note": "影像阴影 vs 病理确诊肿瘤；未定性前禁止上靠至 C34"},
            {"vs": "J18.900", "vs_display": "肺炎", "level": "P1",
             "note": "炎性 vs 占位；以临床/影像随访为准"},
        ],
    },
    "M80.900": {
        "display": "老年性骨质疏松伴病理性骨折",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["骨质疏松伴病理性骨折", "骨质疏松性骨折", "病理性骨折", "骨质疏松骨折"],
        "notes": [("use_additional", "附加编码标明骨折部位")],
        "guideline": "M80 必须有病理性骨折证据；无骨折的骨质疏松编码 M81.-。",
        "parent": "M80",
        "siblings": ["M81.900"],
        "children": [],
        "high_risk": True,
        "differentiation": [
            {"vs": "M81.900", "vs_display": "骨质疏松(无骨折)", "level": "P0",
             "note": "M80(伴病理性骨折) vs M81(无骨折)；缺骨折证据严禁编 M80"},
        ],
    },
    "45.1600x001": {
        "display": "经胃镜食管十二指肠活检",
        "system": ICD9CM3,
        "code_type": "procedure",
        "synonyms": ["经胃镜活检", "胃镜活检", "食管胃十二指肠镜检查及活检", "胃镜检查", "胃镜"],
        "notes": [("excludes2", "单纯食管胃十二指肠镜检查(无活检) (45.13)")],
        "guideline": "含活检的内镜操作编码 45.16；单纯诊断性内镜编码 45.13。",
        "parent": "45.16",
        "siblings": ["45.1300x001"],
        "children": [],
        "high_risk": True,
        "differentiation": [
            {"vs": "45.1300x001", "vs_display": "单纯胃镜检查", "level": "P1",
             "note": "有无活检决定 45.16 vs 45.13；以操作记录是否取材为准"},
        ],
    },
    "Z51.102": {
        "display": "恶性肿瘤维持性化学治疗",
        "system": ICD10CN,
        "code_type": "diagnosis",
        "synonyms": ["维持化疗", "化学治疗", "化疗", "肿瘤化疗", "维持性化学治疗"],
        "notes": [("code_first", "先编码接受化疗的恶性肿瘤")],
        "guideline": "以化疗为目的的住院，Z51.1 作为主要诊断，恶性肿瘤作为附加；放疗为 Z51.0。",
        "parent": "Z51",
        "siblings": ["Z51.002"],
        "children": [],
        "high_risk": True,
        "differentiation": [
            {"vs": "Z51.002", "vs_display": "放射治疗疗程", "level": "P1",
             "note": "化疗(Z51.1) vs 放疗(Z51.0) 易错；以治疗方式为准"},
        ],
    },
}

HIGH_RISK = {code for code, e in CATALOG.items() if e.get("high_risk")}

# The curated sample doubles as the deterministic extractor's vocabulary AND the
# authoritative retrieval mappings. Snapshot it here so ``lexicon()`` stays small + precise
# and search can prefer these verified codes even when the real national catalog is overlaid
# below — otherwise offline extraction would scan 75k national synonyms and retrieval would
# drift to near-duplicate sibling codes (e.g. I50.900 -> I50.908).
SAMPLE: dict[str, dict] = dict(CATALOG)
SAMPLE_CODES: frozenset[str] = frozenset(SAMPLE)


def lexicon() -> list[str]:
    """Curated display names + synonyms — feeds the deterministic extraction provider.

    Intentionally the *sample* vocabulary, not the merged catalog: the real catalog widens
    membership / search / verify (below), but deterministic extraction stays pinned to the
    curated terms so the offline demo is precise. Real extraction (DeepSeek) is lexicon-free.
    """
    terms: list[str] = []
    for e in SAMPLE.values():
        terms.append(e["display"])
        terms.extend(e["synonyms"])
    return terms


def system_of(code: str) -> str | None:
    e = CATALOG.get(code)
    return e["system"] if e else None


# --- optional: overlay the real ICD-10-CN + ICD-9-CM-3 national catalogs ---------------
# Off by default (no ICODER_ICD_CATALOG_DIR -> sample only -> tests stay offline). When the
# read-only asset dir is configured + present, the curated sample overlays the real base so
# the demonstrable codes keep their high-risk flags / notes / differentiation, while R003
# membership, search, and verify gain the full national code space (37,897 + 13,617 codes).
from . import real_catalog as _real_catalog  # noqa: E402  (stdlib-only; no import cycle)

if _real_catalog.available():
    _base = _real_catalog.load()
    CATALOG = _real_catalog.overlay(_base, CATALOG)
    HIGH_RISK = {code for code, e in CATALOG.items() if e.get("high_risk")}
    CATALOG_VERSION = "icd10cn-2.0+icd9cm3-3.0(real)+sample-overlay@0.1.0"
