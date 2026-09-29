from io import BytesIO
import uuid
import pytest
from openpyxl import Workbook
from app.services.evaluation_import import preview_training_xlsx, LABELS

def workbook(rows=None):
    w=Workbook();s=w.active
    s.append(['病案标识','主诉',*LABELS])
    for row in rows or [['PRIVATE-ID','合成头痛','I10.x00','E11.900;J18.900',None,None],['PRIVATE-2','合成咳嗽','J18.900',None,'01.0100',None]]:s.append(row)
    b=BytesIO();w.save(b);return b.getvalue()

def test_xlsx_separates_answers_and_identifiers_and_selects_range():
    r=preview_training_xlsx(workbook(),2,1)
    assert r['total_rows']==2 and len(r['cases'])==1 and not r['issues']
    case=r['cases'][0]
    assert case['id']=='row-00002' and '合成咳嗽' in case['text']
    assert 'PRIVATE' not in str(case) and 'J18.900' not in case['text']
    assert case['expected_json']['primary_procedure_code']=='01.0100'
    assert case['expected_json']['other_diagnosis_codes']==[]

@pytest.mark.parametrize('value',[123,'=1+1'])
def test_xlsx_rejects_numeric_codes_and_formulas(value):
    r=preview_training_xlsx(workbook([['id','合成资料',value,None,None,None]]))
    assert r['issues'] and not r['cases']

def test_bad_workbook_and_bounds():
    with pytest.raises(ValueError):preview_training_xlsx(b'not zip')
    with pytest.raises(ValueError):preview_training_xlsx(workbook(),3)
    with pytest.raises(ValueError):preview_training_xlsx(workbook(),1,11)

def test_compound_labels_preserve_components_suffixes_case_and_order():
    r=preview_training_xlsx(workbook([['private','合成资料','A01.001+B02.002*','N18.810+D63.8*;B44.100x004+J99.8*','01.0100','02.0200']]))
    assert not r['issues']
    case=r['cases'][0]
    assert case['expected_json']=={'primary_diagnosis_code':'A01.001+B02.002*','other_diagnosis_codes':['N18.810+D63.8*','B44.100x004+J99.8*'],'primary_procedure_code':'01.0100','other_procedure_codes':['02.0200']}
    assert 'N18.810' not in case['text'] and 'private' not in case['text']

@pytest.mark.parametrize('value',['+A01','A01+','A01++B02','A*01','A01**','A01+B02**','A01+B02=1','A01/<script>','A01 + B02'])
def test_malformed_compound_labels_are_rejected(value):
    r=preview_training_xlsx(workbook([['id','合成资料','A01',value,None,None]]))
    assert len(r['issues'])==1 and not r['cases']

def test_compound_does_not_relax_primary_cardinality():
    r=preview_training_xlsx(workbook([['id','合成资料','A01+B02*;C03',None,None,None]]))
    assert len(r['issues'])==1 and not r['cases']

@pytest.mark.asyncio
async def test_preview_requires_owned_agent_and_does_not_run_model(client,needs_auth,monkeypatch):
    from app.api import agent_run
    async def forbidden(*args,**kwargs):raise AssertionError('Import must not call model')
    monkeypatch.setattr(agent_run,'run_agent',forbidden)
    async def register():
        name=uuid.uuid4().hex[:12]
        r=await client.post('/api/auth/register',json={'username':name,'email':name+'@example.com','password':'ImportTest!2026','full_name':'Synthetic','organization_name':name})
        assert r.status_code==201
        return {'Authorization':'Bearer '+r.json()['access_token']}
    h=await register();other=await register()
    r=await client.post('/api/rest/v1/agent_definitions',headers=h,json={'name':'Import fixture','system_prompt':'Synthetic'})
    url='/api/rest/v1/agent_definitions/'+r.json()['id']+'/evaluation-import'
    files={'file':('train.xlsx',workbook(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    assert (await client.post(url,headers=other,files=files)).status_code==404
    r=await client.post(url,headers=h,files=files,data={'start':'1','limit':'1'})
    assert r.status_code==200 and len(r.json()['cases'])==1
    assert (await client.post(url,headers=h,files={'file':('bad.json',b'{}')})).status_code==422
