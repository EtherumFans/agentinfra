from types import SimpleNamespace
import json
import pytest
from app.services.coding_difference import comparison
from app.services.release_evaluation import EvaluationCase, check_result

@pytest.mark.parametrize('expected,actual,categories', [
    (['A01','B02'],['B02','A01'],['order_only']),
    (['A01','A01'],['A01'],['missing_codes']),
    ('A01.001','A01',['missing_codes','extra_codes','possible_extension']),
    ('A01+ B02*','A01',['missing_codes','extra_codes','possible_extension']),
    ('A01',['A01'],['type_mismatch']),
    ([],[],[]),
    ('A01',None,['missing_codes']),
    (None,None,[]),
])
def test_diagnostic_categories_do_not_normalize(expected,actual,categories):
    d=comparison('other_diagnosis_codes',expected,actual)
    assert d['categories']==categories
    assert d['exact_match']==(type(expected) is type(actual) and expected==actual)

def test_missing_field_and_sensitive_values():
    assert comparison('primary_diagnosis_code','A01',None,False)['categories']==['missing_field']
    assert not comparison('primary_diagnosis_code','A01','患者张某')['available']
    assert not comparison('primary_diagnosis_code','A01','13812345678')['available']
    assert comparison('free_text','private','private') is None

def test_real_checker_retains_score_and_detects_role_difference():
    expected={'primary_diagnosis_code':'A01','other_diagnosis_codes':['B02']}
    actual={'primary_diagnosis_code':'B02','other_diagnosis_codes':['A01']}
    case=EvaluationCase(id='synthetic',text='synthetic',expected_json=expected)
    response=SimpleNamespace(result={'markdown':json.dumps(actual)},error=False,run_id='r',executed_agent_version='draft',runtime_mode='test',latency_ms=1,manual_review_required=True)
    result=check_result(case,response)
    assert not result['passed']
    fields=[c for c in result['checks'] if 'coding_comparison' in c]
    assert len(fields)==2
    assert all('possible_role' in c['coding_comparison']['categories'] for c in fields)
    response.result={'markdown':'invalid'}
    assert not check_result(case,response)['passed']
