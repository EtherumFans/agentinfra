from copy import deepcopy
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import defer
from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization, require_org_membership, require_org_role
from app.models.document_review import DocumentReview

router=APIRouter(prefix='/api/document-reviews',tags=['document-reviews'],dependencies=[Depends(require_org_membership)])
writer=Depends(require_org_role('owner','admin','member'))
def now():return datetime.now(timezone.utc).isoformat()
def metadata(row):return {k:getattr(row,k) for k in ('id','version','status','created_at','created_by')}
def snapshot(row):return {**metadata(row),**row.content}
async def owned(db,org,rid):
    row=(await db.execute(select(DocumentReview).where(DocumentReview.id==rid,DocumentReview.organization_id==org))).scalar_one_or_none()
    if not row:raise HTTPException(404,'复核记录不存在。')
    return row
async def lock(db,org):await db.execute(text('UPDATE organizations SET id=id WHERE id=:org'),{'org':org})

class CreateReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source:str=Field(min_length=1,max_length=200000)
    draft:str=Field(min_length=1,max_length=200000)
    title:str=Field(default='文书复核',max_length=120)
    request_id:str=Field(min_length=1,max_length=80)

@router.post('')
async def create(body:CreateReview,user=Depends(get_current_user),org=Depends(get_current_organization),db=Depends(get_db),_write=writer):
    if not body.source.strip() or not body.draft.strip():raise HTTPException(422,'原文与初稿不能为空。')
    sections=[s for s in body.draft.split('\n\n') if s.strip()]
    if len(sections)>100 or any(len(s)>20000 for s in sections):raise HTTPException(422,'请将文书分为不超过 100 段，每段不超过 20000 字。')
    await lock(db,org.id)
    old=(await db.execute(select(DocumentReview).where(DocumentReview.organization_id==org.id,DocumentReview.created_by==str(user.id),DocumentReview.request_id==body.request_id))).scalar_one_or_none()
    if old:
        if any(old.content[k]!=getattr(body,k) for k in ('source','draft','title')):raise HTTPException(409,'保存标识已用于其他内容，请重新保存。')
        return snapshot(old)
    row=DocumentReview(organization_id=org.id,created_by=str(user.id),request_id=body.request_id,content={'source':body.source,'draft':body.draft,'title':body.title,'provenance':'workbench_submitted_snapshot','sections':[{'id':str(i),'original':s,'text':s,'decision':'pending'} for i,s in enumerate(sections)],'history':[]})
    db.add(row);await db.commit();await db.refresh(row);return snapshot(row)

@router.get('')
async def listing(offset:int=Query(0,ge=0),org=Depends(get_current_organization),db=Depends(get_db)):
    rows=list((await db.execute(select(DocumentReview).options(defer(DocumentReview.content)).where(DocumentReview.organization_id==org.id).order_by(DocumentReview.created_at.desc(),DocumentReview.id.desc()).offset(offset).limit(21))).scalars())
    return {'items':[metadata(r) for r in rows[:20]],'has_more':len(rows)>20}

@router.get('/{rid}')
async def detail(rid:str,org=Depends(get_current_organization),db=Depends(get_db)):
    return snapshot(await owned(db,org.id,rid))

class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=1)
    decision:Literal['accepted','modified','rejected']
    text:str|None=Field(default=None,max_length=20000)
    note:str=Field(default='',max_length=2000)

@router.post('/{rid}/sections/{sid}')
async def decide(rid:str,sid:str,body:Decision,user=Depends(get_current_user),org=Depends(get_current_organization),db=Depends(get_db),_write=writer):
    await lock(db,org.id);row=await owned(db,org.id,rid)
    if row.status=='confirmed' or row.version!=body.expected_version:raise HTTPException(409,'记录已更新或已确认，请刷新后查看。')
    data=deepcopy(row.content);section=next((s for s in data['sections'] if s['id']==sid),None)
    if section is None:raise HTTPException(404,'段落不存在。')
    if len(data['history'])>=500:raise HTTPException(409,'复核记录已达到修改次数上限。')
    if body.decision in ('modified','rejected') and not body.note.strip():raise HTTPException(422,'修改或驳回时请填写原因。')
    if body.decision=='modified' and not (body.text or '').strip():raise HTTPException(422,'修改后的内容不能为空。')
    if body.decision!='modified' and body.text is not None:raise HTTPException(422,'只有修改操作可以提交新内容。')
    before=deepcopy(section)
    section.update(decision=body.decision,text=body.text if body.decision=='modified' else section['original'])
    data['history'].append({'section_id':sid,'before':before,'after':deepcopy(section),'note':body.note.strip(),'actor':str(user.id),'at':now(),'version':row.version+1})
    row.content=data;row.version+=1;row.status='in_review';await db.commit();return snapshot(row)

class Finalize(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=1)

@router.post('/{rid}/confirm')
async def confirm(rid:str,body:Finalize,user=Depends(get_current_user),org=Depends(get_current_organization),db=Depends(get_db),_write=writer):
    await lock(db,org.id);row=await owned(db,org.id,rid)
    if row.version!=body.expected_version or row.status=='confirmed':raise HTTPException(409,'记录已更新或已确认，请刷新后查看。')
    data=deepcopy(row.content)
    if any(s['decision']=='pending' for s in data['sections']):raise HTTPException(409,'请先处理所有段落。')
    if all(s['decision']=='rejected' for s in data['sections']):raise HTTPException(409,'全部内容已驳回，无法生成确认稿。')
    data['confirmed_by']=str(user.id);data['confirmed_at']=now()
    row.content=data;row.version+=1;row.status='confirmed';await db.commit();return snapshot(row)

@router.get('/{rid}/export')
async def export(rid:str,kind:Literal['draft','confirmed']='draft',org=Depends(get_current_organization),db=Depends(get_db)):
    row=await owned(db,org.id,rid);data=row.content
    if kind=='confirmed' and row.status!='confirmed':raise HTTPException(409,'完成复核确认后才能导出确认稿。')
    content=data['draft'] if kind=='draft' else '\n\n'.join(s['text'] for s in data['sections'] if s['decision']!='rejected')
    label='初稿 · 未经人工确认' if kind=='draft' else '人工确认稿'
    audit='' if kind=='draft' else f"\n确认人：{data['confirmed_by']}\n确认时间：{data['confirmed_at']}"
    return PlainTextResponse(f"{data['title']}\n{label}\n记录：{row.id} · 版本：{row.version}{audit}\n\n{content}",headers={'Content-Disposition':f'attachment; filename="document-{rid}-{kind}.txt"','Cache-Control':'no-store'})
