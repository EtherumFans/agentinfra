"""Opt-in, version-bound catalog retrieval. Never reads evaluation answers."""
import json
import re
from functools import lru_cache
from collections import Counter, defaultdict
from rapidfuzz import fuzz, process

PROFILE = 'cn-catalog-assistance-v1'
CATALOG_RELEASE = 'icoder-cn-runtime-2026-08-27.2'

@lru_cache(maxsize=1)
def catalogs():
    from data.code_dicts.icd_data import ICD10_CN_CODES, ICD9_CM3_CODES, CATALOG_RELEASE as installed
    if installed != CATALOG_RELEASE:
        raise ValueError('coding_catalog_version_mismatch')
    return {'diagnosis': {c:n for c,n,_ in ICD10_CN_CODES},
            'procedure': {c:n for c,n,_ in ICD9_CM3_CODES}}

def profile(config):
    selected = (config or {}).get('coding_catalog_assistance')
    if selected in (None, False, ''):
        return None
    if selected != PROFILE:
        raise ValueError('unsupported_coding_catalog_assistance')
    return {'profile': PROFILE, 'catalog_release': CATALOG_RELEASE}

@lru_cache(maxsize=4)
def search_index(rows):
    index = defaultdict(list)
    for i, (_, name) in enumerate(rows):
        for gram in {name[j:j+2] for j in range(len(name)-1)}:
            index[gram].append(i)
    return index

def candidates(text, catalog, limit=60):
    # Bound input and retrieval. Names/codes are evidence candidates, not diagnoses.
    text = text[:16000]
    scored = {}
    for code, name in catalog.items():
        if len(name) >= 3 and name in text:
            scored[code] = (100 + min(len(name), 40), text.find(name))
    terms = [s.strip() for s in re.split(r'[\n，,。；;：:、]', text) if 3 <= len(s.strip()) <= 60]
    names = list(catalog.values()); codes = list(catalog)
    index = search_index(tuple(catalog.items()))
    for term in dict.fromkeys(terms[:64]):
        overlap = Counter(i for gram in {term[j:j+2] for j in range(len(term)-1)} for i in index.get(gram, []))
        pool = {i:names[i] for i,_ in overlap.most_common(250)}
        for _, score, match_index in process.extract(term, pool, scorer=fuzz.WRatio, limit=2, score_cutoff=82):
            code = codes[match_index]
            scored.setdefault(code, (score, text.find(term)))
    ordered = sorted(scored, key=lambda code: (-scored[code][0], scored[code][1], code))[:limit]
    return [{'code':c, 'name':catalog[c]} for c in ordered]

def augment(text, binding):
    if binding != {'profile': PROFILE, 'catalog_release': CATALOG_RELEASE}:
        raise ValueError('coding_catalog_binding_mismatch')
    found = {kind:candidates(text, codes) for kind,codes in catalogs().items()}
    guidance = ('\n\n本地编码目录候选（仅供检索参考，不是患者诊断、不是标准答案，也不能证明临床适用）：\n'
        + json.dumps(found, ensure_ascii=False) + '\n'
        '只根据病历中有依据的诊断和已完成操作选择编码。候选可能不完整或不相关，不能因为命中而新增诊断。'
        '结合诊疗经过核对主次，排除否定、仅计划的操作。保留编码扩展位与组合符号，不能自行截短或拼造。'
        '输出 primary_diagnosis_code、primary_procedure_code 字符串或 null，'
        'other_diagnosis_codes、other_procedure_codes 字符串数组。仅输出该 JSON 对象。')
    return text + guidance

def validate_output(text):
    """Check membership without replacing, truncating or silently removing model codes."""
    raw = re.sub(r'^```(?:json)?\s*\n?(.*?)\n?```$', r'\1', text.strip(), flags=re.DOTALL)
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {'catalog_release':CATALOG_RELEASE, 'status':'invalid_json', 'fields':{}}
    if not isinstance(parsed, dict):
        return {'catalog_release':CATALOG_RELEASE, 'status':'invalid_json', 'fields':{}}
    fields = {}
    for key, kind in [('primary_diagnosis_code','diagnosis'), ('other_diagnosis_codes','diagnosis'),
                      ('primary_procedure_code','procedure'), ('other_procedure_codes','procedure')]:
        value = parsed.get(key)
        valid_type = key in parsed and ((value is None or isinstance(value,str)) if key.startswith('primary_') else isinstance(value,list))
        values = ([] if value is None else [value]) if key.startswith('primary_') else value
        if not valid_type or not isinstance(values,list) or len(values)>100 or any(not isinstance(v,str) for v in values):
            fields[key] = {'status':'invalid_type'}
            continue
        # Composite strings remain intact; each component must exist exactly.
        unknown = sum(not v or any(part.rstrip('*†‡') not in catalogs()[kind] for part in v.split('+')) for v in values)
        fields[key] = {'status':'not_in_catalog' if unknown else 'in_catalog', 'checked':len(values), 'unknown':unknown}
    return {'catalog_release':CATALOG_RELEASE, 'status':'review_required', 'fields':fields,
            'clinical_validity_verified':False}
