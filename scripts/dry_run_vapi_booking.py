"""Trace real Vapi booking code using temporary SQLite and a fake calendar only."""
import copy
import inspect
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from backend.app.business import BusinessSettings, Hours, Service
from backend.app.database import Base, Business, Appointment, Operation, database
from backend.app.scheduling import Scheduling
from backend.app.vapi_actions import Actions
from backend.app.vapi_api import WebhookSettings, create_app

REPORT = Path('docs/VAPI_BOOKING_DRY_RUN.txt')
lines = []


def emit(value):
    lines.append(value)


class TraceCalendar:
    def __init__(self):
        self.events = {}
        self.writes = 0

    def get(self, key):
        emit('FAKE calendar.get: existing event=' + str(key in self.events))
        return copy.deepcopy(self.events.get(key))

    def busy(self, start, end, exclude=None):
        emit('FAKE calendar.busy: checking availability')
        return [(datetime.fromisoformat(e['start']['dateTime']), datetime.fromisoformat(e['end']['dateTime']))
                for k, e in self.events.items() if k != exclude]

    def create(self, key, body):
        self.writes += 1
        emit('FAKE calendar.create: ' + json.dumps(body, sort_keys=True))
        self.events[key] = {**copy.deepcopy(body), 'id': key, 'etag': '1'}
        return self.get(key)


def trace(frame, event, arg):
    file = Path(frame.f_code.co_filename)
    name = frame.f_code.co_name
    if file.name not in ('vapi_actions.py', 'scheduling.py', 'vapi_api.py'):
        return trace
    if name not in ('tool_results', 'handle', 'execute', 'confirm', 'mutate', '_execute', 'validate', 'free', 'event'):
        return trace
    location = f'{file.name}:{frame.f_lineno} {name}'
    if event == 'call':
        emit('ENTER ' + location)
    elif event == 'line' and name in ('confirm', 'mutate', '_execute'):
        source = file.read_text(encoding='utf-8').splitlines()[frame.f_lineno - 1].strip()
        emit('LINE ' + location + ' | ' + source)
    elif event == 'return':
        if isinstance(arg, dict) and 'success' in arg:
            emit('RETURN ' + location + ' | ' + json.dumps(arg, default=str))
        else:
            emit('RETURN ' + location)
    elif event == 'exception':
        emit('EXCEPTION ' + location + ' | ' + arg[0].__name__)
    return trace


def main():
    with tempfile.TemporaryDirectory(prefix='ava-vapi-dry-run-') as temporary:
        engine, sessions = database('sqlite:///' + str(Path(temporary) / 'dry-run.db'))
        Base.metadata.create_all(engine)
        settings = BusinessSettings(name='Dry run clinic', timezone='UTC', minimum_notice_minutes=0,
            services=[Service(id='pt', name='Physiotherapy', duration=30)],
            hours=[Hours(weekday=i, opens='09:00', closes='18:00') for i in range(7)])
        with sessions.begin() as db:
            business = Business(settings=settings.model_dump(mode='json'))
            db.add(business); db.flush(); bid = business.id
        calendar = TraceCalendar()
        scheduler = Scheduling(sessions, calendar, clock=lambda: datetime(2026, 9, 27, tzinfo=timezone.utc))
        actions = Actions(sessions, lambda business_id: scheduler)
        token = 'dry-run-authentication-token-only'
        client = TestClient(create_app(sessions, WebhookSettings(token=token,
            assistant_business_map={'dry-run-assistant': bid}), actions))
        counter = 0

        def invoke(call, name, arguments):
            nonlocal counter
            counter += 1
            response = client.post('/api/vapi/tools', headers={'Authorization': 'Bearer ' + token}, json={
                'message': {'type': 'tool-calls', 'call': {'id': call, 'assistantId': 'dry-run-assistant'},
                    'toolCallList': [{'id': 'dry-tool-' + str(counter), 'name': name, 'parameters': arguments}]}})
            item = response.json()['results'][0]
            return json.loads(item.get('result', item.get('error')))

        def prepare(call):
            slots = invoke(call, 'check_availability', {'service_id': 'pt', 'date': '2026-10-03'})
            return invoke(call, 'create_appointment', {'caller_name': 'Test Caller',
                'caller_phone': '+15551234567', 'service_id': 'pt', 'start_at': slots['data']['slots'][0]})

        def event(call, kind, stamp, **fields):
            return client.post('/api/vapi/events', headers={'Authorization': 'Bearer ' + token}, json={
                'message': {'type': kind, 'timestamp': stamp,
                    'call': {'id': call, 'assistantId': 'dry-run-assistant'}, **fields}})

        outcomes = {}
        emit('SAFETY: isolated temporary database; fake calendar; no Vapi/Google network calls.')
        for scenario in ('interrupted_without_readback', 'missing_evidence', 'valid_confirmation'):
            emit('\nSCENARIO: ' + scenario)
            prepared = prepare(scenario)
            action_token = prepared['data']['action_token']
            pending = actions.load(bid, scenario)[1]['pending']
            stamp = pending['created_ms'] + 100
            if scenario == 'interrupted_without_readback':
                event(scenario, 'user-interrupted', stamp)
                emit('Interruption recorded; draft retained, confirmation still required.')
            elif scenario == 'valid_confirmation':
                event(scenario, 'transcript', stamp + 200, role='user', transcriptType='final', transcript='Yes, please.')
            state = actions.load(bid, scenario)[1].get('pending', {})
            emit('BEFORE CONFIRM: ' + json.dumps({k: state.get(k) for k in
                ('kind', 'turn', 'speech_ms', 'ready_ms', 'agreement_ms', 'affirmed_ms')}))
            before = calendar.writes
            # Trace executes within FastAPI's worker thread as well.
            import threading
            threading.settrace(trace)
            try:
                outcomes[scenario] = invoke(scenario, 'confirm_action', {'action_token': action_token})
            finally:
                threading.settrace(None)
            emit('RESULT: ' + json.dumps(outcomes[scenario]))
            emit('CALENDAR WRITES THIS CONFIRM: ' + str(calendar.writes - before))
        assert outcomes['interrupted_without_readback']['code'] == 'confirmation_not_verified'
        assert outcomes['missing_evidence']['code'] == 'confirmation_not_verified'
        assert outcomes['valid_confirmation']['status'] == 'completed'
        assert calendar.writes == 1
        retry = invoke('valid_confirmation', 'confirm_action',
                       {'action_token': prepared['data']['action_token']})
        assert retry == outcomes['valid_confirmation'] and calendar.writes == 1
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Appointment)) == 1
            op = db.scalar(select(Operation))
            assert op.status == 'completed'
            emit('\nFINAL: one fake calendar event, one appointment, one completed operation; retry made no additional write.')
        client.close(); engine.dispose()
    REPORT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    for scenario, result in outcomes.items():
        print(scenario + ': ' + result.get('code', result['status']))
    print('Trace saved: ' + str(REPORT.resolve()))


if __name__ == '__main__':
    main()
