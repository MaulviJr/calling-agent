import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pydantic import Field, field_validator
from sqlalchemy import select
from .business import StrictModel, BusinessSettings
from .database import Business, Appointment, Operation, Call, uid, now, record
from .dates import aware, wall_time
from .calendar import CalendarUnavailable
from .lookup import calendar_read
from .vapi_trace import emit

log = logging.getLogger('ava')
_sqlite_lock = threading.RLock()


class Booking(StrictModel):
    caller_name: str = Field(min_length=1, max_length=120)
    caller_phone: str = Field(min_length=7, max_length=50)
    caller_email: str = Field(default='', max_length=254)
    service_id: str = Field(min_length=1, max_length=40)
    start_at: datetime
    call_id: str | None = None

    @field_validator('caller_phone')
    @classmethod
    def phone(cls, value):
        import re
        if not re.fullmatch(r'[+\d ()-]+',value) or not 7 <= len(re.sub(r'\D','',value)) <= 15:
            raise ValueError('Please provide a valid phone number including country/area code.')
        return value

    @field_validator('caller_email')
    @classmethod
    def email(cls, value):
        if value and ('@' not in value or '.' not in value.rsplit('@',1)[-1]):
            raise ValueError('Please provide a valid email address.')
        return value

    @field_validator('start_at')
    @classmethod
    def zoned(cls, value):
        if value.tzinfo is None: raise ValueError('Appointment time must include a timezone offset.')
        return value


class Scheduling:
    def __init__(self, sessions, calendar, clock=now):
        self.sessions, self.calendar, self.clock = sessions, calendar, clock

    @contextmanager
    def locked(self, business_id):
        # PostgreSQL row locks serialize all Ava writers for this business across
        # processes. SQLite uses a process lock ONLY for offline testing.
        with _sqlite_lock if self.sessions.kw['bind'].dialect.name == 'sqlite' else _NoLock():
            with self.sessions.begin() as db:
                business = db.scalar(select(Business).where(Business.id==business_id).with_for_update())
                if business is None: raise ValueError('Business not found.')
                yield db, BusinessSettings.model_validate(business.settings)

    def validate(self, settings, service_id, start):
        service = next((s for s in settings.services if s.id==service_id and s.active),None)
        if service is None: raise ValueError('Please choose an active service.')
        if start.tzinfo is None: raise ValueError('A timezone offset is required.')
        local = start.astimezone(ZoneInfo(settings.timezone))
        wall_time(local.date(),local.time().replace(tzinfo=None),ZoneInfo(settings.timezone))
        current = self.clock()
        if start < current+timedelta(minutes=settings.minimum_notice_minutes):
            raise ValueError('That time is in the past or too soon to book.')
        if start > current+timedelta(days=settings.maximum_advance_days):
            raise ValueError('That date is beyond the advance booking window.')
        end = start+timedelta(minutes=service.duration)
        hours = next((h for h in settings.hours if h.weekday==local.weekday()),None)
        local_end = end.astimezone(ZoneInfo(settings.timezone))
        if not hours or local.date()!=local_end.date() or local.time()<hours.opens or local_end.time()>hours.closes:
            raise ValueError('That appointment falls outside opening hours.')
        if local.second or local.microsecond or local.minute % 5:
            raise ValueError('Choose a time on a five-minute boundary.')
        return end

    def free(self, db, business_id, settings, start, end, exclude=None):
        buffer = timedelta(minutes=settings.buffer_minutes)
        for a,b in calendar_read(self.calendar.busy,start-buffer,end+buffer,exclude):
            if a < end+buffer and b > start-buffer:
                emit('slot.conflict', source='calendar', start_at=start, end_at=end, busy_start=a, busy_end=b)
                return False
        for row in db.scalars(select(Appointment).where(Appointment.business_id==business_id,Appointment.status=='booked')):
            if row.calendar_event_id != exclude and aware(row.start_at)<end+buffer and aware(row.end_at)>start-buffer:
                emit('slot.conflict', source='database', appointment_id=row.id, start_at=start, end_at=end)
                return False
        emit('slot.free', start_at=start, end_at=end)
        return True

    def slots(self, business_id, service_id, day, earliest=None, latest=None, exclude=None):
        from datetime import time
        with self.sessions() as db:
            settings = BusinessSettings.model_validate(db.get(Business,business_id).settings)
            hours = next((h for h in settings.hours if h.weekday==day.weekday()),None)
            emit('availability.rules', date=day, current_time=self.clock(), timezone=settings.timezone,
                 service_id=service_id, services=[{'id':s.id, 'duration':s.duration, 'active':s.active} for s in settings.services],
                 hours=hours.model_dump(mode='json') if hours else None,
                 minimum_notice_minutes=settings.minimum_notice_minutes,
                 maximum_advance_days=settings.maximum_advance_days, buffer_minutes=settings.buffer_minutes)
            if not hours:
                emit('availability.closed', date=day)
                return []
            start = wall_time(day,max(hours.opens,earliest or time()),ZoneInfo(settings.timezone))
            stop = wall_time(day,min(hours.closes,latest or time(23,59)),ZoneInfo(settings.timezone))
            # One provider request per search, not one request per proposed slot.
            buffer = timedelta(minutes=settings.buffer_minutes)
            busy = calendar_read(self.calendar.busy,start-buffer,stop+timedelta(hours=4)+buffer,exclude)
            busy += [(aware(a.start_at),aware(a.end_at)) for a in db.scalars(select(Appointment).where(
                Appointment.business_id==business_id,Appointment.status=='booked')) if a.calendar_event_id != exclude]
            emit('availability.busy_intervals', intervals=busy, window_start=start, window_end=stop)
            result = []
            while start <= stop and len(result)<12:
                try:
                    end = self.validate(settings,service_id,start)
                    if not any(a<end+buffer and b>start-buffer for a,b in busy): result.append(start.isoformat())
                except ValueError as exc:
                    emit('availability.candidate_rejected', start_at=start, reason=str(exc))
                start += timedelta(minutes=15)
            return result

    def mutate(self, business_id, key, kind, payload, confirmed=False):
        if not confirmed: raise ValueError('Explicit confirmation is required.')
        if kind not in ('create','reschedule','cancel'): raise ValueError('Unknown action.')
        if not key or len(key)>100: raise ValueError('Invalid idempotency key.')
        # Commit the intent BEFORE the network request. A process crash leaves a
        # durable pending record that blocks competing mutations until reconciled.
        with self.locked(business_id) as (db,settings):
            op = db.scalar(select(Operation).where(Operation.business_id==business_id,Operation.key==key))
            if op:
                if op.kind!=kind or op.payload!=payload: raise ValueError('Idempotency key reused for different details.')
                if op.status=='completed': return record(db.get(Appointment,op.result_id))
                if op.status=='rejected': raise ValueError('This request was rejected. Select a new slot.')
            else:
                unresolved = db.scalar(select(Operation).where(Operation.business_id==business_id,Operation.status.in_(['pending','uncertain'])))
                if unresolved: raise CalendarUnavailable('A previous calendar change needs reconciliation by staff.')
                op = Operation(business_id=business_id,key=key,kind=kind,payload=payload)
                db.add(op); db.flush()
            operation_id = op.id
            emit('calendar.operation_intent', operation_id=op.id, status=op.status, kind=kind)
        error = None
        with self.locked(business_id) as (db,settings):
            op = db.get(Operation,operation_id)
            if op.status=='completed': return record(db.get(Appointment,op.result_id))
            try:
                result = self._execute(db,settings,op)
                op.result_id,op.status = result.id,'completed'
                emit('calendar.operation_completed', operation_id=op.id, appointment_id=result.id)
                db.flush()
                result_data = record(result)
            except ValueError as exc:
                emit('calendar.operation_rejected', operation_id=op.id, exception_type=type(exc).__name__)
                op.status='rejected'; error=exc
            except Exception:
                emit('calendar.operation_uncertain', operation_id=op.id)
                op.status='uncertain'
                error=CalendarUnavailable('The calendar change could not be verified. Staff must reconcile it before retrying.')
        if error: raise error
        return result_data

    def _execute(self, db, settings, op):
        payload = op.payload
        existing = None
        if op.kind=='create':
            booking = Booking.model_validate(payload)
            if booking.call_id:
                call=db.get(Call,booking.call_id)
                if not call or call.business_id!=op.business_id: raise ValueError('Call not found.')
            if settings.require_email and not booking.caller_email: raise ValueError('Email is required.')
            event_id = op.id  # hex is valid Google base32hex; stable across retries.
        else:
            existing=db.scalar(select(Appointment).where(Appointment.id==payload['appointment_id'],Appointment.business_id==op.business_id))
            if not existing: raise ValueError('Appointment not found.')
            event_id=existing.calendar_event_id
            booking=Booking(caller_name=existing.caller_name,caller_phone=existing.caller_phone,
                caller_email=existing.caller_email,service_id=existing.service_id,
                start_at=payload.get('start_at') or aware(existing.start_at),call_id=existing.call_id)
        event=calendar_read(self.calendar.get,event_id)
        marker=(event or {}).get('extendedProperties',{}).get('private',{}).get('ava_operation')
        if op.kind=='cancel':
            if event: self.calendar.delete(event_id,event['etag'])
            existing.status='cancelled'; return existing
        if existing and existing.status!='booked': raise ValueError('Appointment is not active.')
        end=booking.start_at+timedelta(minutes=next((s.duration for s in settings.services if s.id==booking.service_id),30))
        if marker != op.id:
            if op.kind=='create' and event: raise CalendarUnavailable('Event ID exists with different ownership.')
            if op.kind=='reschedule' and not event: raise ValueError('Calendar event is missing; staff must review.')
            end=self.validate(settings,booking.service_id,booking.start_at)
            if not self.free(db,op.business_id,settings,booking.start_at,end,event_id if existing else None):
                raise ValueError('That time is no longer available. Please select another slot.')
            body={'summary':'Ava appointment', 'start':{'dateTime':booking.start_at.isoformat(),'timeZone':settings.timezone},
                  'end':{'dateTime':end.isoformat(),'timeZone':settings.timezone},
                  'extendedProperties':{'private':{'ava_operation':op.id,'ava_business':op.business_id}}}
            event=(self.calendar.update(event_id,body,event['etag']) if existing else self.calendar.create(event_id,body))
        # On recovery use the remote event's committed times, even if settings
        # changed while the operation was pending.
        start=datetime.fromisoformat(event['start']['dateTime'])
        end=datetime.fromisoformat(event['end']['dateTime'])
        if not existing:
            existing=Appointment(business_id=op.business_id,call_id=booking.call_id,
                caller_name=booking.caller_name,caller_phone=booking.caller_phone,
                caller_email=booking.caller_email,service_id=booking.service_id,
                start_at=start,end_at=end,timezone=settings.timezone,calendar_event_id=event_id)
            db.add(existing)
        else:
            existing.start_at,existing.end_at=start,end
        db.flush()
        return existing


class _NoLock:
    def __enter__(self): return self
    def __exit__(self,*args): pass
