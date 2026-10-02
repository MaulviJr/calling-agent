"""Vapi proposes actions; persisted Python state authorizes side effects."""
import hashlib
import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, time as daytime, timedelta
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from sqlalchemy import select, text

from .business import BusinessSettings, StrictModel
from .database import Appointment, Business, Call, Message, Operation, now, uid
from .dates import aware
from .vapi_trace import emit

_locks = [threading.RLock() for _ in range(64)]
log = logging.getLogger('ava.vapi')


class AvailabilityArgs(StrictModel):
    service_id: str = Field(min_length=1, max_length=40)
    date: date
    earliest: daytime | None = None
    latest: daytime | None = None
    appointment_id: str = Field(default='', max_length=32)
    caller_phone: str = Field(default='', max_length=50)


class AppointmentArgs(StrictModel):
    appointment_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    caller_phone: str = Field(min_length=7, max_length=50)

    @field_validator('caller_phone')
    @classmethod
    def valid_phone(cls, value):
        from .scheduling import Booking
        return Booking.phone(value)


class CreateArgs(StrictModel):
    caller_name: str = Field(min_length=1, max_length=120)
    caller_phone: str = Field(min_length=7, max_length=50)
    caller_email: str = Field(default='', max_length=254)
    service_id: str = Field(min_length=1, max_length=40)
    start_at: datetime

    @field_validator('start_at')
    @classmethod
    def zoned(cls, value):
        if value.tzinfo is None:
            raise ValueError('Timezone required.')
        return value


class RescheduleArgs(AppointmentArgs):
    start_at: datetime

    @field_validator('start_at')
    @classmethod
    def zoned(cls, value):
        return CreateArgs.zoned(value)


class MessageArgs(StrictModel):
    caller_name: str = Field(min_length=1, max_length=120)
    caller_phone: str = Field(min_length=7, max_length=50)
    content: str = Field(min_length=1, max_length=2000)

    @field_validator('caller_phone')
    @classmethod
    def valid_phone(cls, value):
        return AppointmentArgs.valid_phone(value)


class ConfirmArgs(StrictModel):
    action_token: str = Field(pattern=r'^[a-f0-9]{32}$')


ACTION_SCHEMAS = {
    'check_availability': AvailabilityArgs,
    'get_appointment': AppointmentArgs,
    'create_appointment': CreateArgs,
    'cancel_appointment': AppointmentArgs,
    'reschedule_appointment': RescheduleArgs,
    'leave_message': MessageArgs,
    'confirm_action': ConfirmArgs,
}


def normalize(value):
    return ' '.join(re.sub(r'[^\w\s]', ' ', value.casefold()).split())


def affirmative(value):
    # Narrow consent grammar. Never let an LLM-provided boolean authorize writes.
    return normalize(value) in {
        'yes', 'yes please', 'yes that is correct', 'yes that s correct',
        'that is correct', 'that s correct', 'i confirm', 'please proceed',
        'yes go ahead', 'go ahead', 'yes book it', 'yes cancel it', 'yes reschedule it',
        'yes i confirm', 'yes i confirm it', 'i confirm it',
        'yeah', 'yep', 'sure', 'okay', 'ok', 'yes sure', 'yes please go ahead',
    }


def fail(code, status='rejected'):
    return {'success': False, 'status': status, 'code': code}


def fingerprint(settings):
    return hashlib.sha256(settings.model_dump_json().encode()).hexdigest()


@contextmanager
def locked(sessions, bid, external_id):
    key = int.from_bytes(hashlib.sha256((bid + ':' + external_id).encode()).digest()[:8], 'big', signed=True)
    with _locks[key % len(_locks)]:
        engine = sessions.kw['bind']
        if engine.dialect.name != 'postgresql':
            yield
        else:
            with engine.connect() as connection:
                connection.execute(text('SELECT pg_advisory_lock(:key)'), {'key': key})
                try:
                    yield
                finally:
                    connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': key})


class Actions:
    def __init__(self, sessions, scheduler_for_business):
        self.sessions = sessions
        self.scheduler_for_business = scheduler_for_business

    def load(self, bid, external_id):
        with self.sessions.begin() as db:
            business = db.get(Business, bid)
            if business is None:
                raise ValueError('Business unavailable.')
            call = db.scalar(select(Call).where(Call.business_id == bid, Call.external_id == external_id))
            if call is None:
                call = Call(business_id=bid, external_id=external_id, transport='vapi')
                db.add(call); db.flush()
            state = dict(call.state.get('vapi', {}))
            return call.id, state, BusinessSettings.model_validate(business.settings), call.status

    def save(self, cid, state, outcome=None):
        with self.sessions.begin() as db:
            call = db.get(Call, cid)
            call.state = {**call.state, 'vapi': state}
            if outcome:
                call.outcome = outcome

    def owned(self, bid, reference, phone):
        with self.sessions() as db:
            row = db.scalar(select(Appointment).where(Appointment.business_id == bid,
                Appointment.id == reference, Appointment.status == 'booked'))
            if row is None or re.sub(r'\D', '', row.caller_phone) != re.sub(r'\D', '', phone):
                return None
            return row

    def details(self, row):
        return {'appointment_id': row.id, 'service_id': row.service_id,
                'start_at': aware(row.start_at).isoformat(), 'end_at': aware(row.end_at).isoformat(),
                'timezone': row.timezone, 'status': row.status}

    def handle(self, bid, external_id, tool_id, name, arguments):
        digest = hashlib.sha256(json.dumps(arguments, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with locked(self.sessions, bid, external_id):
            cid, state, settings, status = self.load(bid, external_id)
            emit('action.state', internal_call_id=cid, call_status=status,
                 pending_token=(state.get('pending') or {}).get('token'),
                 pending_kind=(state.get('pending') or {}).get('kind'),
                 affirmed_ms=(state.get('pending') or {}).get('affirmed_ms'))
            if status != 'active':
                return fail('call_ended')
            receipts = state.setdefault('receipts', {})
            if tool_id in receipts:
                emit('action.receipt_replay')
                previous = receipts[tool_id]
                if previous['name'] != name or previous['digest'] != digest:
                    return fail('tool_id_reused')
                result = previous['result']
                token = result.get('data', {}).get('action_token')
                if token and token != (state.get('pending') or {}).get('token'):
                    return fail('action_expired')
                return result
            if len(receipts) >= 300:
                return fail('call_tool_limit')
            preparing = name in ('create_appointment', 'cancel_appointment', 'reschedule_appointment', 'leave_message')
            pending = state.get('pending')
            if preparing and pending and pending.get('request_digest') != digest:
                state.pop('pending', None)
            try:
                args = ACTION_SCHEMAS[name].model_validate(arguments)
                result = self.execute(bid, cid, state, settings, name, args)
            except Exception as exc:
                from pydantic import ValidationError
                errors = [{'field': list(e['loc']), 'type': e['type']} for e in exc.errors()] if isinstance(exc, ValidationError) else []
                emit('action.exception', exception_type=type(exc).__name__, validation_errors=errors)
                from .calendar import CalendarUnavailable
                if isinstance(exc, CalendarUnavailable):
                    result = fail('calendar_unavailable_or_needs_review', 'unavailable')
                elif isinstance(exc, ValueError):
                    result = fail('invalid_details_or_slot_unavailable')
                else:
                    result = fail('action_unavailable', 'unavailable')
            if preparing and result.get('status') == 'confirmation_required':
                state['pending']['request_digest'] = digest
            # Confirmation evidence may arrive after this request. Allow retries
            # without caching that transient rejection forever.
            if result.get('code') != 'confirmation_not_verified':
                receipts[tool_id] = {'name': name, 'digest': digest, 'result': result}
            self.save(cid, state)
            return result

    def execute(self, bid, cid, state, settings, name, args):
        if name == 'confirm_action':
            return self.confirm(bid, cid, state, settings, args.action_token)
        if name in ('get_appointment', 'cancel_appointment', 'reschedule_appointment'):
            row = self.owned(bid, args.appointment_id, args.caller_phone)
            if row is None:
                state.pop('pending', None)
                return fail('appointment_unverified', 'unverified')
            if name == 'get_appointment':
                return {'success': True, 'status': 'completed', 'data': self.details(row)}
        if name == 'check_availability':
            scheduler = self.scheduler_for_business(bid)
            if not any(s.id == args.service_id and s.active for s in settings.services):
                return fail('invalid_service')
            exclude = None
            if args.appointment_id:
                row = self.owned(bid, args.appointment_id, args.caller_phone)
                if row is None or row.service_id != args.service_id:
                    return fail('appointment_unverified', 'unverified')
                exclude = row.calendar_event_id
            if args.earliest and args.latest and args.earliest > args.latest:
                return fail('invalid_time_window')
            slots = scheduler.slots(bid, args.service_id, args.date, args.earliest, args.latest, exclude=exclude)
            emit('availability.result', service_id=args.service_id, date=args.date,
                 timezone=settings.timezone, slots=slots, reservation_created=False)
            state['offered'] = {'service_id': args.service_id, 'slots': slots,
                                'fingerprint': fingerprint(settings)}
            return {'success': True, 'status': 'available' if slots else 'unavailable',
                    'data': {'date': args.date.isoformat(), 'timezone': settings.timezone,
                             'service_id': args.service_id, 'slots': slots, 'booked': False}}
        payload = args.model_dump(mode='json')
        kind = {'create_appointment': 'create', 'cancel_appointment': 'cancel',
                'reschedule_appointment': 'reschedule', 'leave_message': 'message'}[name]
        if kind in ('create', 'reschedule'):
            scheduler = self.scheduler_for_business(bid)
            service_id = args.service_id if kind == 'create' else row.service_id
            offered = state.get('offered', {})
            if (offered.get('service_id') != service_id or offered.get('fingerprint') != fingerprint(settings)
                    or not any(datetime.fromisoformat(s) == args.start_at for s in offered.get('slots', []))):
                state.pop('pending', None)
                return fail('select_checked_slot')
            end = scheduler.validate(settings, service_id, args.start_at)
            with self.sessions() as db:
                if not scheduler.free(db, bid, settings, args.start_at, end,
                        row.calendar_event_id if kind == 'reschedule' else None):
                    state.pop('pending', None)
                    return fail('slot_unavailable')
            if kind == 'create':
                from .scheduling import Booking
                booking = Booking(**payload, call_id=cid)
                if settings.require_email and not booking.caller_email:
                    return fail('email_required')
                payload = booking.model_dump(mode='json')
        elif kind == 'message':
            payload['content'] = re.sub(r'(?<!\d)(?:\d[ -]?){13,19}(?!\d)', '[number omitted]', args.content)
        pending = state.get('pending')
        if not pending or pending['kind'] != kind or pending['payload'] != payload:
            pending = {'token': uid(), 'kind': kind, 'payload': payload,
                       'created_ms': int(time.time() * 1000), 'fingerprint': fingerprint(settings),
                       'affirmed_ms': None}
            state['pending'] = pending
        return {'success': True, 'status': 'confirmation_required',
                'data': {'action_token': pending['token'], 'confirmation_prompt': 'Shall I proceed?',
                         'committed': False}}

    def confirm(self, bid, cid, state, settings, token):
        emit('confirmation.request', action_token=token)
        completed = state.get('completed', {})
        if token in completed:
            emit('confirmation.completed_replay')
            return completed[token]
        pending = state.get('pending')
        if not pending or pending['token'] != token:
            emit('confirmation.rejected', reason='pending_missing' if not pending else 'token_mismatch')
            return fail('action_expired')
        if pending['fingerprint'] != fingerprint(settings) or int(time.time() * 1000) - pending['created_ms'] > 600000:
            emit('confirmation.rejected', reason='settings_changed' if pending['fingerprint'] != fingerprint(settings) else 'ten_minute_expiry')
            state.pop('pending', None)
            return fail('action_expired')
        if not pending.get('affirmed_ms'):
            emit('confirmation.rejected', reason='caller_agreement_missing')
            reason = pending.get('confirmation_reason', 'caller_agreement_missing')
            log.info('VAPI_CONFIRMATION_BLOCKED call_id=%s reason=%s', cid, reason)
            return {**fail('confirmation_not_verified'), 'reason': reason}
        payload, kind = pending['payload'], pending['kind']
        emit('confirmation.authorized', kind=kind, payload=payload, affirmed_ms=pending['affirmed_ms'])
        # A calendar write may have committed before the call receipt did.
        # Returning the durable result must not re-run ownership against an
        # appointment that this very operation already cancelled.
        with self.sessions() as db:
            op = db.scalar(select(Operation).where(Operation.business_id == bid, Operation.key == token))
            recovering = bool(op and op.kind == kind and op.status == 'completed')
        if kind in ('cancel', 'reschedule') and not recovering:
            if self.owned(bid, payload['appointment_id'], payload['caller_phone']) is None:
                return fail('appointment_unverified', 'unverified')
        if kind == 'message':
            with self.sessions.begin() as db:
                row = db.scalar(select(Message).where(Message.business_id == bid, Message.key == token))
                if row is None:
                    row = Message(business_id=bid, call_id=cid, key=token, caller_name=payload['caller_name'],
                                  phone=payload['caller_phone'], content=payload['content'])
                    db.add(row); db.flush()
                data = {'message_id': row.id, 'status': 'saved'}
            outcome = 'message_taken'
        else:
            scheduler = self.scheduler_for_business(bid)
            mutation = dict(payload)
            if kind in ('cancel', 'reschedule'):
                mutation.pop('caller_phone')
            result = scheduler.mutate(bid, token, kind, mutation, True)
            data = {key: result[key] for key in ('id', 'service_id', 'start_at', 'end_at', 'timezone', 'status')}
            data = json.loads(json.dumps(data, default=lambda x: x.isoformat()))
            outcome = {'create': 'appointment_booked', 'cancel': 'appointment_cancelled',
                       'reschedule': 'appointment_rescheduled'}[kind]
        result = {'success': True, 'status': 'completed', 'data': data}
        emit('action.completed', kind=kind, result=result)
        state.setdefault('completed', {})[token] = result
        state.pop('pending', None)
        self.save(cid, state, outcome)
        return result

    def event(self, bid, external_id, message):
        kind = message.get('type')
        if kind == 'transcript[transcriptType="final"]':
            kind = 'transcript'
            message = {**message, 'transcriptType': 'final'}
        if kind not in ('transcript', 'status-update'):
            return False
        stamp = message.get('timestamp')
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or stamp <= 0:
            return False
        with locked(self.sessions, bid, external_id):
            cid, state, _, status = self.load(bid, external_id)
            if kind == 'status-update' and message.get('status') == 'ended':
                state.pop('pending', None)
                self.save(cid, state)
                with self.sessions.begin() as db:
                    call = db.get(Call, cid)
                    if call.ended_at is None:
                        call.ended_at = now(); call.status = 'completed'
                        call.duration_seconds = max(0, int((now() - aware(call.started_at)).total_seconds()))
                return True
            pending = state.get('pending')
            if status != 'active' or not pending or stamp <= pending['created_ms']:
                return False
            if kind != 'transcript' or message.get('role') != 'user' or message.get('transcriptType') != 'final':
                return False
            if stamp <= state.get('last_user_ms', 0):
                return False
            state['last_user_ms'] = stamp
            if affirmative(message.get('transcript', '')):
                pending['affirmed_ms'] = stamp
                reason = 'verified'
            else:
                # A correction, question or conditional response revokes consent.
                # Keep the draft; changed details require a new preparation.
                pending.pop('affirmed_ms', None)
                reason = 'caller_agreement_missing'
            emit('confirmation.evidence', event_timestamp=stamp, accepted=reason == 'verified',
                 action_token=pending['token'], reason=reason)
            if reason != pending.get('confirmation_reason'):
                log.info('VAPI_CONFIRMATION_STATE call_id=%s reason=%s', external_id, reason)
            pending['confirmation_reason'] = reason
            self.save(cid, state)
            return True
