# iCoDer ICD Data — loaded from iCoDerA knowledge base
# 33,304 ICD-10-CN diagnosis codes + 23,165 ICD-9-CM-3 procedure codes
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

KB_ROOT = Path(__file__).parent.parent.parent.parent.parent / "iCoDerA" / "data"

ICD10_CN_CHAPTERS = {
    "A00-B99": "某些传染病和寄生虫病",
    "C00-D48": "肿瘤", "D50-D89": "血液及造血器官疾病",
    "E00-E90": "内分泌、营养和代谢疾病", "F00-F99": "精神和行为障碍",
    "G00-G99": "神经系统疾病", "H00-H59": "眼和附器疾病",
    "H60-H95": "耳和乳突疾病", "I00-I99": "循环系统疾病",
    "J00-J99": "呼吸系统疾病", "K00-K93": "消化系统疾病",
    "L00-L99": "皮肤和皮下组织疾病",
    "M00-M99": "肌肉骨骼系统和结缔组织疾病",
    "N00-N99": "泌尿生殖系统疾病", "O00-O99": "妊娠、分娩和产褥期",
    "P00-P96": "起源于围生期的某些情况",
    "Q00-Q99": "先天性畸形、变形和染色体异常",
    "R00-R99": "症状、体征和临床与实验室异常所见",
    "S00-T98": "损伤、中毒和外因的某些其他后果",
    "V01-Y98": "疾病和死亡的外因",
    "Z00-Z99": "影响健康状态和与保健机构接触的因素",
    "U00-U99": "用于特殊目的的编码",
}

def _load_icd10():
    path = KB_ROOT / "icd10_opendrg_v1.json"
    if not path.exists():
        logger.warning("ICD-10 KB not found, using fallback")
        return [("M80.900","重度骨质疏松症","肌肉骨骼系统和结缔组织疾病"),("I10.x02","高血压3级","循环系统疾病")]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    codes = [(item.get("icd10_code",""), item.get("disease_name",""), item.get("chapter_name","")) for item in data if item.get("icd10_code") and item.get("disease_name")]
    logger.info("Loaded %d ICD-10-CN codes from knowledge base", len(codes))
    return codes

def _load_icd9():
    names_path = KB_ROOT / "procedure_coding" / "procedure_icd9cm3_knowledge_v8_with_opendrg.json"
    proc_path = KB_ROOT / "procedure_coding" / "surgery_to_drg_mapping.json"
    
    code_names = {}
    if names_path.exists():
        with open(names_path, "r", encoding="utf-8") as f:
            for item in json.load(f):
                c = item.get("icd9cm3_code","").strip()
                n = item.get("procedure_name","").strip()
                if c and n: code_names[c] = n
    
    codes = []
    if proc_path.exists():
        with open(proc_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("surgery_to_drg", []):
            code = item.get("icd9cm3_code","").strip()
            name = code_names.get(code, "")
            drg = item.get("drg_groups", [])
            if code: codes.append((code, name, drg[0] if drg else ""))
    logger.info("Loaded %d ICD-9-CM-3 codes from knowledge base", len(codes))
    return codes if codes else [("81.6600x001","经皮椎体后凸成形术",""),("00.6600x002","经皮冠状动脉支架植入术","")]

ICD10_CN_CODES = _load_icd10()
ICD9_CM3_CODES = _load_icd9()
