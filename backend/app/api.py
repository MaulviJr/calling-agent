"""Same-origin staff API. Every data route derives business_id from login."""
import hashlib
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from pwdlib import PasswordHash
from sqlalchemy import select, func
from .business import StrictModel, BusinessSettings
from .database import Business, Admin, LoginSession, Call, Appointment, Message, TranscriptTurn, Operation, record, now
from .dates import aware
from .calendar import UnconfiguredCalendar, CalendarUnavailable
from .scheduling import Scheduling
from .calendars import FixedCalendar
log=logging.getLogger('ava')
passwords=PasswordHash.recommended()
dummy_hash=passwords.hash('not-a-real-user-password')


class Login(StrictModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class MessageStatus(StrictModel):
    status: Literal['new','reviewed','resolved']


class Mutation(StrictModel):
    key: str = Field(min_length=1,max_length=100)
    confirmed: bool = False
    start_at: str | None = None




def create_app(sessions,calendar=None,llm=None,voice_enabled=False,legacy_enabled=False,calendars=None):
    app=FastAPI(title='Ava',docs_url=None,redoc_url=None)
    scheduler=Scheduling(sessions,calendar or UnconfiguredCalendar())   # unchanged: used for locking + legacy
    router=calendars or FixedCalendar(sessions,calendar or UnconfiguredCalendar())

    app.state.scheduler=scheduler
    app.state.router=router
    origin=os.getenv('APP_ORIGIN','http://localhost:8000').rstrip('/')
    secure=os.getenv('COOKIE_SECURE','false').lower()=='true'
    if not origin.startswith(('http://localhost:','http://127.0.0.1:')) and not secure:
        raise RuntimeError('Remote deployments require COOKIE_SECURE=true and HTTPS.')
    attempts=defaultdict(deque); throttle_lock=threading.Lock()

    @app.middleware('http')
    async def security(request,call_next):
        if request.method not in ('GET','HEAD','OPTIONS'):
            if request.headers.get('origin')!=origin:
                return JSONResponse({'detail':'Request origin rejected.'},status_code=403)
            try: size=int(request.headers.get('content-length','0'))
            except ValueError: size=262145
            if size>262144:
                return JSONResponse({'detail':'Request too large.'},status_code=413)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'"
        return response

    @app.exception_handler(ValueError)
    async def bad_input(request,exc):
        return JSONResponse({'detail':str(exc)},status_code=400)

    @app.exception_handler(CalendarUnavailable)
    async def calendar_error(request,exc):
        return JSONResponse({'detail':str(exc)},status_code=503)

    @app.exception_handler(Exception)
    async def server_error(request,exc):
        return JSONResponse({'detail':'The request could not be completed. Please try again or contact staff.'},status_code=503)

    def authenticate(token):
        if not token: raise HTTPException(401,'Sign in required.')
        hashed=hashlib.sha256(token.encode()).hexdigest()
        with sessions() as db:
            login=db.get(LoginSession,hashed)
            if not login or aware(login.expires_at)<now(): raise HTTPException(401,'Session expired.')
            admin=db.get(Admin,login.admin_id)
            if not admin: raise HTTPException(401,'Sign in required.')
            return admin

    def current(request:Request): return authenticate(request.cookies.get('ava_session'))

    @app.get('/health')
    def health(): return {'status':'ok'}

    @app.post('/api/login')
    def login(data:Login,request:Request,response:Response):
        print('Login attempt from',request.client.host, 'email',data.email, 'password length',len(data.password))
        address=request.client.host
        with throttle_lock:
            if len(attempts)>5000: attempts.clear()
            queue=attempts[address]
            while queue and queue[0]<time.monotonic()-300: queue.popleft()
            if len(queue)>=10: raise HTTPException(429,'Too many attempts. Try again in five minutes.')
            queue.append(time.monotonic())
        with sessions.begin() as db:
            admin=db.scalar(select(Admin).where(Admin.email==data.email.lower()))
            valid=passwords.verify(data.password,admin.password_hash if admin else dummy_hash)
            if not admin or not valid: raise HTTPException(401,'Invalid email or password.')
            token=secrets.token_urlsafe(32)
            db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),admin_id=admin.id,expires_at=now()+timedelta(hours=8)))
        response.set_cookie('ava_session',token,httponly=True,secure=secure,samesite='strict',max_age=28800,path='/')
        return {'email':admin.email}

    @app.post('/api/logout')
    def logout(request:Request,response:Response,admin=Depends(current)):
        with sessions.begin() as db:
            row=db.get(LoginSession,hashlib.sha256(request.cookies['ava_session'].encode()).hexdigest())
            if row: db.delete(row)
        response.delete_cookie('ava_session',path='/')
        return {'ok':True}

    @app.get('/api/me')
    def me(admin=Depends(current)): return {'email':admin.email}

    @app.get('/api/settings')
    def settings(admin=Depends(current)):
        with sessions() as db: return db.get(Business,admin.business_id).settings

    @app.put('/api/settings')
    def save_settings(data:BusinessSettings,admin=Depends(current)):
        with scheduler.locked(admin.business_id) as (db,_):
            pending=db.scalar(select(Operation).where(Operation.business_id==admin.business_id,Operation.status.in_(['pending','uncertain'])))
            if pending: raise HTTPException(409,'Reconcile pending calendar operations before changing settings.')
            db.get(Business,admin.business_id).settings=data.model_dump(mode='json')
        return data

    @app.get('/api/calendar/status')
    def calendar_status(admin=Depends(current)):
        try:
            router.calendar_for(admin.business_id).busy(now(),now()+timedelta(minutes=1))
            return {'connected':True}
        except CalendarUnavailable as exc:
            return {'connected':False,'message':str(exc)}
        except Exception:
            return {'connected':False,'message':'Check calendar credentials and sharing permissions.'}

    @app.get('/api/calls')
    def calls(limit:int=50,offset:int=0,admin=Depends(current)):
        with sessions() as db:
            return [{k:v for k,v in record(c).items() if k!='state'} for c in db.scalars(select(Call).where(Call.business_id==admin.business_id).order_by(Call.started_at.desc()).limit(max(1,min(limit,100))).offset(max(0,offset)))]

    @app.get('/api/calls/{call_id}')
    def call_detail(call_id:str,admin=Depends(current)):
        with sessions() as db:
            call=db.scalar(select(Call).where(Call.id==call_id,Call.business_id==admin.business_id))
            if not call: raise HTTPException(404,'Call not found.')
            result=record(call); result.pop('state')
            result['turns']=[record(t) for t in db.scalars(select(TranscriptTurn).where(TranscriptTurn.call_id==call_id,TranscriptTurn.business_id==admin.business_id).order_by(TranscriptTurn.created_at))]
            return result

    @app.get('/api/appointments')
    def appointments(limit:int=50,offset:int=0,admin=Depends(current)):
        with sessions() as db:
            return [record(a) for a in db.scalars(select(Appointment).where(Appointment.business_id==admin.business_id).order_by(Appointment.start_at.desc()).limit(max(1,min(limit,100))).offset(max(0,offset)))]

    @app.post('/api/appointments/{appointment_id}/{action}')
    def change_appointment(appointment_id:str,action:Literal['reschedule','cancel'],data:Mutation,admin=Depends(current)):
        payload={'appointment_id':appointment_id}
        if action=='reschedule':
            from datetime import datetime
            if not data.start_at: raise ValueError('New start time is required.')
            start=datetime.fromisoformat(data.start_at)
            if start.tzinfo is None: raise ValueError('Include a timezone offset.')
            payload['start_at']=start.isoformat()
        return router.scheduler_for(admin.business_id).mutate(admin.business_id,data.key,action,payload,data.confirmed)

    @app.get('/api/messages')
    def messages(limit:int=50,offset:int=0,admin=Depends(current)):
        with sessions() as db:
            return [record(m) for m in db.scalars(select(Message).where(Message.business_id==admin.business_id).order_by(Message.created_at.desc()).limit(max(1,min(limit,100))).offset(max(0,offset)))]

    @app.patch('/api/messages/{message_id}')
    def update_message(message_id:str,data:MessageStatus,admin=Depends(current)):
        with sessions.begin() as db:
            message=db.scalar(select(Message).where(Message.id==message_id,Message.business_id==admin.business_id))
            if not message: raise HTTPException(404,'Message not found.')
            message.status=data.status
        return {'ok':True}

    @app.get('/api/overview')
    def overview(admin=Depends(current)):
        from zoneinfo import ZoneInfo
        with sessions() as db:
            bid=admin.business_id
            settings=BusinessSettings.model_validate(db.get(Business,bid).settings)
            midnight=now().astimezone(ZoneInfo(settings.timezone)).replace(hour=0,minute=0,second=0,microsecond=0)
            total=db.scalar(select(func.count()).select_from(Call).where(Call.business_id==bid))
            today=db.scalar(select(func.count()).select_from(Call).where(Call.business_id==bid,Call.started_at>=midnight))
            booked=db.scalar(select(func.count()).select_from(Appointment).where(Appointment.business_id==bid))
            converted=db.scalar(select(func.count(func.distinct(Appointment.call_id))).where(Appointment.business_id==bid))
            average=db.scalar(select(func.avg(Call.duration_seconds)).where(Call.business_id==bid,Call.ended_at.is_not(None)))
            unresolved=db.scalar(select(func.count()).select_from(Message).where(Message.business_id==bid,Message.status!='resolved'))
            escalations=db.scalar(select(func.count()).select_from(Message).where(Message.business_id==bid,Message.escalated==1))
            return {'total_calls':total,'calls_today':today,'appointments_booked':booked,
                'conversion_rate':round(100*converted/total,1) if total else 0,'average_duration':round(average or 0),
                'unresolved_messages':unresolved,'escalations':escalations}

    @app.get('/api/operations')
    def operations(admin=Depends(current)):
        with sessions() as db:
            return [{'id':o.id,'kind':o.kind,'status':o.status,'created_at':o.created_at} for o in db.scalars(select(Operation).where(Operation.business_id==admin.business_id,Operation.status.in_(['pending','uncertain'])))]

    @app.post('/api/operations/{operation_id}/reconcile')
    def reconcile(operation_id:str,admin=Depends(current)):
        with sessions() as db:
            op=db.scalar(select(Operation).where(Operation.id==operation_id,Operation.business_id==admin.business_id))
            if not op: raise HTTPException(404,'Operation not found.')
        return router.scheduler_for(admin.business_id).mutate(admin.business_id,op.key,op.kind,op.payload,True)

    if legacy_enabled:
        from legacy.app.routes import mount
        mount(app, sessions, scheduler, current, authenticate, origin, llm, voice_enabled)

    dist=Path(__file__).resolve().parents[2]/'frontend'/'dist'
    if dist.exists():
        app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
        @app.get('/audio-worklet.js')
        def worklet(): return FileResponse(dist/'audio-worklet.js',media_type='text/javascript')
        @app.get('/')
        def index(): return FileResponse(dist/'index.html')
    return app
