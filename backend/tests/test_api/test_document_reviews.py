import uuid
import pytest
from sqlalchemy import text

async def register(client):
    name=uuid.uuid4().hex[:12]
    r=await client.post('/api/auth/register',json={'username':name,'email':name+'@example.com','password':'ReviewTest!2026','full_name':'Synthetic reviewer','organization_name':name})
    assert r.status_code==201,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}

@pytest.mark.asyncio
async def test_document_review_full_cycle_and_isolation(client,needs_auth):
    h=await register(client);other=await register(client)
    payload={'source':'合成原文：第一项。第二项。','draft':'第一项初稿\n\n第二项初稿','title':'合成复核','request_id':uuid.uuid4().hex}
    r=await client.post('/api/document-reviews',headers=h,json=payload);assert r.status_code==200,r.text
    record=r.json();base='/api/document-reviews/'+record['id']
    assert (await client.post('/api/document-reviews',headers=h,json=payload)).json()['id']==record['id']
    assert (await client.post('/api/document-reviews',headers=h,json={**payload,'draft':'changed'})).status_code==409
    assert (await client.get(base,headers=other)).status_code==404
    assert (await client.get(base+'/export',headers=other)).status_code==404
    assert (await client.get(base+'/export?kind=confirmed',headers=h)).status_code==409
    assert (await client.post(base+'/confirm',headers=h,json={'expected_version':1})).status_code==409
    body={'expected_version':1,'decision':'modified','text':'第一项已核对','note':'合成测试修改原因'}
    assert (await client.post(base+'/sections/0',headers=other,json=body)).status_code==404
    assert (await client.post(base+'/sections/0',headers=h,json={**body,'note':''})).status_code==422
    r=await client.post(base+'/sections/0',headers=h,json=body);assert r.status_code==200,r.text
    assert r.json()['history'][0]['before']['text']=='第一项初稿'
    assert (await client.post(base+'/sections/0',headers=h,json=body)).status_code==409
    r=await client.post(base+'/sections/1',headers=h,json={'expected_version':2,'decision':'rejected','note':'合成测试：无依据'});assert r.status_code==200,r.text
    assert (await client.post(base+'/confirm',headers=h,json={'expected_version':3})).status_code==200
    assert (await client.post(base+'/sections/0',headers=h,json={**body,'expected_version':4})).status_code==409
    final=await client.get(base+'/export?kind=confirmed',headers=h)
    assert '第一项已核对' in final.text and '第二项初稿' not in final.text and '人工确认稿' in final.text
    assert '第一项初稿\n\n第二项初稿' in (await client.get(base+'/export',headers=h)).text
    fresh=(await client.get(base,headers=h)).json()
    assert fresh['source']==payload['source'] and len(fresh['history'])==2 and fresh['confirmed_by']
    from app.middleware.auth import decode_token
    from app.database import AsyncSessionLocal
    org=decode_token(h['Authorization'][7:])['org_id']
    async with AsyncSessionLocal() as db:
        from app.services.database_tenancy import bind_tenant_to_transaction
        await bind_tenant_to_transaction(db,org)
        raw=(await db.execute(text('SELECT content FROM document_reviews WHERE id=:id'),{'id':record['id']})).scalar_one()
        if db.bind.dialect.name=='postgresql':assert str(raw).startswith(('v1:','v2:')) and '合成原文' not in raw

@pytest.mark.asyncio
async def test_all_rejected_cannot_confirm_and_viewer_cannot_write(client,needs_auth):
    h=await register(client)
    r=await client.post('/api/document-reviews',headers=h,json={'source':'合成','draft':'合成','request_id':uuid.uuid4().hex});assert r.status_code==200,r.text
    base='/api/document-reviews/'+r.json()['id']
    assert (await client.post(base+'/sections/0',headers=h,json={'expected_version':1,'decision':'rejected','note':'合成原因'})).status_code==200
    assert (await client.post(base+'/confirm',headers=h,json={'expected_version':2})).status_code==409
    from app.middleware.auth import decode_token
    from app.database import AsyncSessionLocal
    token=decode_token(h['Authorization'][7:])
    async with AsyncSessionLocal() as db:
        from app.services.database_tenancy import bind_tenant_to_transaction
        await bind_tenant_to_transaction(db,token['org_id'])
        await db.execute(text("UPDATE organization_members SET role='viewer' WHERE organization_id=:org"),{'org':token['org_id']});await db.commit()
    assert (await client.get(base,headers=h)).status_code==200
    assert (await client.post(base+'/sections/0',headers=h,json={'expected_version':2,'decision':'accepted'})).status_code==403
