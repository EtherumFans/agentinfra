"""Versioned synthetic business fixtures. Not a clinical gold-standard corpus."""
from copy import deepcopy

SUITES = {
    'documentation-v1': {'name':'文书处理', 'description':'已知事实保留、缺失信息与禁止补写', 'cases':[
        {'id':'doc-missing', 'text':'合成病例：主诉为咳嗽3天。未提供过敏史、既往史及确诊诊断。整理资料，仅输出 JSON 对象，字段 chief_complaint（照录主诉）、allergies（未提供为 null）、diagnosis（未提供为 null）。不要补写。',
         'expected_json':{'chief_complaint':'咳嗽3天','allergies':None,'diagnosis':None}},
        {'id':'doc-known', 'text':'合成病例：主诉为头痛1天。明确记录青霉素过敏，未提供确诊诊断。仅输出 JSON，字段 chief_complaint（照录主诉）、allergies（已知过敏药物字符串数组）、diagnosis（未提供为 null）。不要根据症状推断诊断。',
         'expected_json':{'chief_complaint':'头痛1天','allergies':['青霉素'],'diagnosis':None}},
    ]},
    'coding-v1': {'name':'医学编码', 'description':'依据给定候选字典匹配确诊信息，排除疑似诊断', 'cases':[
        {'id':'code-confirmed', 'text':'合成编码测试，候选字典：I10.x00=高血压；E11.900=2型糖尿病。文书明确诊断高血压，仅怀疑2型糖尿病。只对明确诊断匹配给定候选，不编码疑似诊断。仅输出 JSON：codes（编码字符串数组）、has_unconfirmed_diagnosis（是否含疑似诊断的布尔值）。',
         'expected_json':{'codes':['I10.x00'],'has_unconfirmed_diagnosis':True}},
        {'id':'code-insufficient', 'text':'合成编码测试，候选字典：I10.x00=高血压；E11.900=2型糖尿病。文书没有确诊诊断，仅记载头痛，不能由症状推断疾病编码。仅输出 JSON：codes（匹配的确诊疾病编码数组）、needs_review（资料不足时为 true）。',
         'expected_json':{'codes':[],'needs_review':True}},
    ]},
    'quality-v1': {'name':'质量审核', 'description':'识别明确缺项和矛盾，不制造质控问题', 'cases':[
        {'id':'quality-missing', 'text':'合成质控任务。规则：必须记录出院日期；文书同时出现“否认药物过敏”和“青霉素过敏”即为过敏史矛盾。文书：未记录出院日期，第一段称否认药物过敏，第二段称青霉素过敏。仅输出 JSON：missing_discharge_date、allergy_conflict，两字段均为布尔值。',
         'expected_json':{'missing_discharge_date':True,'allergy_conflict':True}},
        {'id':'quality-clean', 'text':'合成质控任务。规则：必须记录出院日期；过敏史互相矛盾才报错。文书已明确记录出院日期为2026年1月2日，全文仅记载青霉素过敏，无相反记录。仅输出 JSON：missing_discharge_date、allergy_conflict，两字段均为布尔值。不要增加其他问题。',
         'expected_json':{'missing_discharge_date':False,'allergy_conflict':False}},
    ]},
}


def suite_cases(key):
    return deepcopy(SUITES[key]['cases'])


async def model_binding(db, organization_id):
    """Fingerprint effective configuration without disclosing credentials."""
    import os
    from app.config import settings
    from app.models.model_connection import ModelConnection
    from app.models.organization import Organization
    from app.services.tenant_model_routing import selection_from_settings
    from app.services.release_evaluation import digest
    connection = await db.get(ModelConnection, organization_id, populate_existing=True)
    if connection and connection.enabled:
        return {'source':'organization','provider':'deepseek','model':connection.model,
                'version':connection.version}
    org = await db.get(Organization, organization_id, populate_existing=True)
    return {'source':'deployment', 'selection':selection_from_settings(org.settings if org else {}).to_public_dict(),
            'provider':os.environ.get('LLM_PROVIDER',settings.LLM_PROVIDER), 'model':settings.LLM_MODEL,
            'configuration_digest':digest({'endpoint':settings.LLM_BASE_URL,
                'credential':os.environ.get('ICODER_CREDENTIAL_LLM','') or settings.LLM_API_KEY,
                'named_credentials':{k:v for k,v in os.environ.items() if k.startswith('ICODER_CREDENTIAL_LLM_')},
                'deployments':os.environ.get('ICODER_LLM_DEPLOYMENTS_JSON','')})}
