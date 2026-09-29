from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.models.browser_session import BrowserSession

async def validate_browser_session(db,payload):
    sid=payload.get('browser_session_id')
    if sid is None:return
    if not isinstance(sid,str):raise HTTPException(401,'Invalid browser session')
    row=(await db.execute(select(BrowserSession).where(BrowserSession.id==sid,BrowserSession.user_id==payload.get('sub')))).scalar_one_or_none()
    if row is None or row.revoked_at is not None or row.expires_at.replace(tzinfo=timezone.utc)<=datetime.now(timezone.utc):
        raise HTTPException(401,'Browser session expired or revoked')
    return row
