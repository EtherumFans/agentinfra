import uuid
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query,UploadFile,File,Form
from pydantic import BaseModel,Field,model_validator,ConfigDict
from sqlalchemy import select,text,func,update
from sqlalchemy.orm import defer
from starlette.concurrency import run_in_threadpool
from app.database import get_db
from app.middleware.auth import get_current_user,get_current_organization,require_org_membership,require_org_role
from app.models.evaluation_dataset import EvaluationDataset as Dataset,EvaluationBatch as Batch,EvaluationBatchItem as Item,now
from app.services.release_evaluation import EvaluationCase,EvaluationPurpose,digest,draft_fingerprint
from app.api.agents import _owned_agent_for_lifecycle

router=APIRouter(prefix='/api/evaluation-datasets',tags=['evaluation-datasets'],dependencies=[Depends(require_org_membership)])

class SaveDataset(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=120)
    split:Literal['training','validation','acceptance']='validation'
    cases:list[EvaluationCase]=Field(min_length=1,max_length=2000)
    dataset_id:str|None=Field(default=None,max_length=36)
    expected_version:int|None=None
    append:bool=False
    @model_validator(mode='after')
    def valid(self):
        if not self.name.strip() or len({c.id for c in self.cases})!=len(self.cases):raise ValueError('名称不能为空，样例标识不能重复')
        return self

def metadata(d):return {k:getattr(d,k) for k in ('id','dataset_id','version','name','split','digest','case_count','review_status','reviews','created_by','created_at')}

async def owned(db,org,rid):
    d=(await db.execute(select(Dataset).where(Dataset.id==rid,Dataset.organization_id==org))).scalar_one_or_none()
    if not d:raise HTTPException(404,'dataset_not_found')
    return d

async def lock(db,org):await db.execute(text('UPDATE organizations SET id=id WHERE id=:org'),{'org':org})

async def save(body,db,user,org):
    await lock(db,org.id)
    cases=[c.model_dump() for c in body.cases];version=1;did=body.dataset_id or str(uuid.uuid4())
    if body.dataset_id:
        old=(await db.execute(select(Dataset).where(Dataset.organization_id==org.id,Dataset.dataset_id==did).order_by(Dataset.version.desc()).limit(1))).scalar_one_or_none()
        if not old:raise HTTPException(404,'dataset_not_found')
        if body.expected_version!=old.version:raise HTTPException(409,'dataset_changed_refresh_required')
        version=old.version+1
        if body.append:cases=[*old.cases,*cases]
    if len(cases)>2000 or len({c['id'] for c in cases})!=len(cases):raise HTTPException(422,'最多 2000 条，样例标识不可重复。')
    d=Dataset(dataset_id=did,version=version,name=body.name.strip(),split=body.split,cases=cases,digest=digest(cases),case_count=len(cases),organization_id=org.id,created_by=str(user.id),review_status='pending',reviews=[])
    db.add(d);await db.commit();await db.refresh(d);return metadata(d)

@router.post('')
async def create_dataset(body:SaveDataset,db=Depends(get_db),user=Depends(get_current_user),org=Depends(get_current_organization)):return await save(body,db,user,org)

@router.post('/import-xlsx')
async def import_dataset(file:UploadFile=File(...),name:str=Form(...,min_length=1,max_length=120),split:Literal['training','validation','acceptance']=Form('training'),db=Depends(get_db),user=Depends(get_current_user),org=Depends(get_current_organization)):
    from app.services.evaluation_import import preview_training_xlsx
    try:
        if not (file.filename or '').lower().endswith('.xlsx'):raise HTTPException(422,'请使用 XLSX 文件')
        content=await file.read(10*1024*1024+1)
        result=await run_in_threadpool(preview_training_xlsx,content,1,2000,2000)
        if result['total_rows']>2000:raise HTTPException(422,'最多保存 2000 条，请拆分工作簿。')
        if result['issues']:raise HTTPException(422,{'message':'存在无效记录，未保存任何样例','issues':result['issues'][:30]})
        return await save(SaveDataset(name=name,split=split,cases=result['cases']),db,user,org)
    except ValueError:raise HTTPException(422,'无法导入，请检查文件结构、记录长度及编码格式。') from None
    finally:await file.close()

@router.get('')
async def list_datasets(offset:int=Query(0,ge=0),q:str=Query('',max_length=120),db=Depends(get_db),org=Depends(get_current_organization)):
    query=select(Dataset).options(defer(Dataset.cases)).where(Dataset.organization_id==org.id)
    if q:query=query.where(Dataset.name.contains(q,autoescape=True))
    rows=list((await db.execute(query.order_by(Dataset.created_at.desc(),Dataset.id).offset(offset).limit(21))).scalars())
    return {'items':[metadata(d) for d in rows[:20]],'has_more':len(rows)>20}

@router.get('/{rid}')
async def get_dataset(rid:str,offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=2000),db=Depends(get_db),org=Depends(get_current_organization)):
    d=await owned(db,org.id,rid);return {**metadata(d),'cases':d.cases[offset:offset+limit],'has_more':offset+limit<d.case_count}

class Review(BaseModel):
    decision:Literal['approved','rejected']
    note:str=Field(min_length=1,max_length=2000)
    expected_reviews:int=Field(ge=0)

@router.post('/{rid}/review')
async def review_dataset(rid:str,body:Review,db=Depends(get_db),org=Depends(get_current_organization),user=Depends(get_current_user),admin=Depends(require_org_role('owner','admin'))):
    await lock(db,org.id);d=await owned(db,org.id,rid)
    if len(d.reviews)!=body.expected_reviews:raise HTTPException(409,'review_changed_refresh_required')
    if not body.note.strip():raise HTTPException(422,'请填写审核意见')
    d.reviews=[*d.reviews,{'decision':body.decision,'note':body.note.strip(),'by':str(user.id),'at':now().isoformat()}];d.review_status=body.decision
    await db.commit();return metadata(d)

class StartBatch(BaseModel):
    agent_id:str=Field(min_length=1,max_length=128)
    request_id:str=Field(min_length=1,max_length=80)
    purpose:EvaluationPurpose='quality_improvement'

@router.post('/{rid}/batches')
async def start_batch(rid:str,body:StartBatch,db=Depends(get_db),org=Depends(get_current_organization),user=Depends(get_current_user)):
    await lock(db,org.id);d=await owned(db,org.id,rid)
    old=(await db.execute(select(Batch).where(Batch.organization_id==org.id,Batch.created_by==str(user.id),Batch.request_id==body.request_id))).scalar_one_or_none()
    if old:
        if (old.dataset_revision_id,old.agent_id,old.purpose)!=(rid,body.agent_id,body.purpose):raise HTTPException(409,'idempotency_conflict')
        return {'id':old.id,'replayed':True}
    if d.review_status!='approved':raise HTTPException(409,'请先审核评测集版本')
    agent=await _owned_agent_for_lifecycle(body.agent_id,org=org,db=db)
    b=Batch(organization_id=org.id,agent_id=agent.id,dataset_revision_id=d.id,draft_digest=await draft_fingerprint(db,agent),purpose=body.purpose,request_id=body.request_id,created_by=str(user.id),state='active')
    db.add(b);await db.flush()
    db.add_all([Item(organization_id=org.id,batch_id=b.id,case_index=i,case_id=c['id'],state='queued',attempts=[]) for i,c in enumerate(d.cases)])
    await db.commit();return {'id':b.id,'replayed':False}

@router.get('/{rid}/batches')
async def list_batches(rid:str,db=Depends(get_db),org=Depends(get_current_organization)):
    await owned(db,org.id,rid)
    rows=(await db.execute(select(Batch).where(Batch.organization_id==org.id,Batch.dataset_revision_id==rid).order_by(Batch.created_at.desc()).limit(20))).scalars()
    return [{'id':b.id,'state':b.state,'created_at':b.created_at,'agent_id':b.agent_id} for b in rows]

async def batch_owned(db,org,rid,bid):
    b=(await db.execute(select(Batch).where(Batch.id==bid,Batch.organization_id==org,Batch.dataset_revision_id==rid))).scalar_one_or_none()
    if not b:raise HTTPException(404,'batch_not_found')
    return b

@router.get('/{rid}/batches/{bid}')
async def batch_result(rid:str,bid:str,offset:int=Query(0,ge=0),failed_only:bool=False,db=Depends(get_db),org=Depends(get_current_organization)):
    b=await batch_owned(db,org.id,rid,bid)
    rows=list((await db.execute(select(Item).where(Item.organization_id==org.id,Item.batch_id==bid).order_by(Item.case_index))).scalars())
    states={s:sum(i.state==s for i in rows) for s in ('queued','running','completed','failed','interrupted','cancelled')}
    passed=sum(bool(i.result and i.result.get('checks_passed')) for i in rows if i.state=='completed')
    fields={}
    for i in rows:
        if i.state!='completed' or not i.result:continue
        for case in i.result.get('cases',[]):
            for check in case['candidate'].get('checks',[]):
                if check['kind']=='json_field_equals':
                    key=check['path'];stat=fields.setdefault(key,{'matched':0,'checked':0});stat['checked']+=1;stat['matched']+=int(check['passed'])
    visible=[i for i in rows if not failed_only or i.state in ('failed','interrupted') or i.state=='completed' and not (i.result or {}).get('checks_passed')]
    return {'id':b.id,'state':b.state,'draft_digest':b.draft_digest,'total':len(rows),'states':states,'passed':passed,'field_matches':fields,'has_more':offset+20<len(visible),'items':[{'id':i.id,'case_id':i.case_id,'state':i.state,'error_code':i.error_code,'attempts':i.attempts,'result':i.result} for i in visible[offset:offset+20]]}

@router.post('/{rid}/batches/{bid}/{action}')
async def batch_action(rid:str,bid:str,action:Literal['cancel','retry'],db=Depends(get_db),org=Depends(get_current_organization),user=Depends(get_current_user),member=Depends(require_org_membership)):
    await lock(db,org.id);b=await batch_owned(db,org.id,rid,bid)
    if b.created_by!=str(user.id) and member.role.value not in ('owner','admin'):raise HTTPException(403,'batch_owner_required')
    if action=='cancel':
        b.state='cancelled';await db.execute(update(Item).where(Item.batch_id==bid,Item.organization_id==org.id,Item.state=='queued').values(state='cancelled'))
    else:
        if b.state=='cancelled':raise HTTPException(409,'已取消任务不可重试，请新建批次')
        d=await owned(db,org.id,rid);agent=await _owned_agent_for_lifecycle(b.agent_id,org=org,db=db)
        if d.review_status!='approved' or b.draft_digest!=await draft_fingerprint(db,agent):raise HTTPException(409,'配置或审核已变化，请新建批次')
        await db.execute(update(Item).where(Item.batch_id==bid,Item.organization_id==org.id,Item.state.in_(('failed','interrupted'))).values(state='queued',claim_token=None,lease_until=None,error_code=None))
        b.state='active'
    await db.commit();return {'state':b.state}
