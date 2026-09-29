"""SPA authentication: HttpOnly refresh cookie, short memory-only access token."""
import secrets
from datetime import datetime,timedelta,timezone
from urllib.parse import urlsplit
import jwt
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.api import auth
from app.schemas.user import UserLogin,UserCreate,TokenRefresh,SwitchOrgRequest
from app.middleware.auth import decode_token,get_current_user
from app.models.user import User
from app.models.browser_session import BrowserSession
from app.services.browser_sessions import validate_browser_session

router=APIRouter(prefix='/api/auth/browser',tags=['browser-auth'])
COOKIE='icoder_browser_refresh'
PATH='/api/auth/browser'

def guard(request):
    origin=request.headers.get('origin','')
    allowed=set(settings.CORS_ORIGINS)|{str(request.base_url).rstrip('/')}
    if request.headers.get('X-iCoDer-Browser')!='1' or origin not in allowed or request.headers.get('sec-fetch-site')=='cross-site':
        raise HTTPException(403,'Browser request origin rejected')
    secure=request.url.scheme=='https' or settings.ICODER_DEPLOYMENT_MODE=='cloud'
    if secure and urlsplit(origin).scheme != 'https':
        raise HTTPException(400,'HTTPS required for browser sessions')
    if not secure and urlsplit(origin).hostname not in ('localhost','127.0.0.1','::1','test'):
        raise HTTPException(400,'HTTPS required for browser sessions')
    return secure

def issue(result,response,secure,sid,expiry):
    access=decode_token(result.access_token)
    access.update(browser_session_id=sid,exp=int((datetime.now(timezone.utc)+timedelta(minutes=5)).timestamp()))
    refresh=decode_token(result.refresh_token)
    refresh.update(browser_session_id=sid,exp=int(expiry.timestamp()))
    response.set_cookie(COOKIE,jwt.encode(refresh,settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM),httponly=True,secure=secure,samesite='strict',path=PATH,max_age=max(0,int((expiry-datetime.now(timezone.utc)).total_seconds())))
    return {**result.model_dump(mode='json'),'access_token':jwt.encode(access,settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM),'refresh_token':'','expires_in':300}

async def start_session(result,response,secure,db):
    row=BrowserSession(id=secrets.token_urlsafe(32),user_id=result.user.id,expires_at=datetime.now(timezone.utc)+timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS))
    db.add(row);await db.commit()
    return issue(result,response,secure,row.id,row.expires_at.replace(tzinfo=timezone.utc))

@router.post('/login')
async def login(data:UserLogin,request:Request,response:Response,db:AsyncSession=Depends(get_db)):
    secure=guard(request)
    return await start_session(await auth.login(data,request,db),response,secure,db)

@router.post('/register',status_code=201)
async def register(data:UserCreate,request:Request,response:Response,db:AsyncSession=Depends(get_db)):
    secure=guard(request)
    return await start_session(await auth.register(data,request,db),response,secure,db)

@router.post('/refresh')
async def refresh(request:Request,response:Response,db:AsyncSession=Depends(get_db)):
    secure=guard(request);token=request.cookies.get(COOKIE)
    if not token:raise HTTPException(401,'No browser session')
    payload=decode_token(token)
    if payload.get('type')!='refresh' or not payload.get('browser_session_id'):raise HTTPException(401,'Invalid browser refresh token')
    row=await validate_browser_session(db,payload)
    result=await auth.refresh_token(TokenRefresh(refresh_token=token),db)
    return issue(result,response,secure,row.id,row.expires_at.replace(tzinfo=timezone.utc))

@router.post('/switch-org')
async def switch(data:SwitchOrgRequest,request:Request,response:Response,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    secure=guard(request);payload=decode_token(request.cookies.get(COOKIE) or '')
    row=await validate_browser_session(db,payload)
    if row is None or row.user_id!=user.id:raise HTTPException(401,'Browser session mismatch')
    result=await auth.switch_org(data,request,user,db)
    await db.commit()
    return issue(result,response,secure,row.id,row.expires_at.replace(tzinfo=timezone.utc))

@router.post('/logout')
async def logout(request:Request,response:Response,db:AsyncSession=Depends(get_db)):
    secure=guard(request);token=request.cookies.get(COOKIE)
    if token:
        try:
            payload=decode_token(token)
            row=await validate_browser_session(db,payload)
            if row:row.revoked_at=datetime.now(timezone.utc);await db.commit()
        except HTTPException:pass
    response.delete_cookie(COOKIE,path=PATH,httponly=True,secure=secure,samesite='strict')
    return {'logged_out':True}
