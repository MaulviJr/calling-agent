"""Temporary data for frontend QA; does not load .env or touch ava-local.db."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
import copy
import tempfile
from datetime import datetime, timezone
import uvicorn
from backend.app.api import create_app, passwords
from backend.app.database import Base, database, Business, Admin, Call, TranscriptTurn, Message, Appointment
from backend.app.business import BusinessSettings, Service, Hours
from backend.app.agent import Decision
from fastapi import WebSocket


class OfflineCalendar:
    """In-memory provider for UI mutation checks, never a real calendar."""
    def __init__(self):
        self.events = {'qa-event': {'id': 'qa-event', 'etag': '1',
            'start': {'dateTime': '2026-10-12T10:00:00+00:00'},
            'end': {'dateTime': '2026-10-12T10:30:00+00:00'}}}

    def busy(self, start, end, exclude=None):
        return [(datetime.fromisoformat(event['start']['dateTime']),
                 datetime.fromisoformat(event['end']['dateTime']))
                for key, event in self.events.items() if key != exclude]

    def get(self, key):
        return copy.deepcopy(self.events.get(key))

    def create(self, key, body):
        self.events[key] = {**copy.deepcopy(body), 'id': key, 'etag': '1'}
        return self.get(key)

    def update(self, key, body, etag):
        self.events[key].update(copy.deepcopy(body))
        return self.get(key)

    def delete(self, key, etag):
        self.events.pop(key, None)


def add_transport_probe(app):
    """Opt-in echo endpoint tests the gateway, not the production voice agent."""
    app.router.routes = [route for route in app.router.routes if getattr(route, 'path', '') != '/api/voice']

    @app.websocket('/api/voice')
    async def echo(ws: WebSocket):
        # Report what arrived at the upstream. Only synthetic QA cookies are used.
        await ws.accept()
        await ws.send_json({'origin': ws.headers.get('origin'),
                            'cookie': ws.headers.get('cookie')})
        pcm = await ws.receive_bytes()
        await ws.send_bytes(pcm)
        await ws.send_json({'type': 'clear'})
        await ws.close()


class OfflineLLM:
    def decide(self, *args):
        return Decision(action='unknown')


def main():
    os.environ['APP_ORIGIN'] = 'http://localhost:8000'
    os.environ['COOKIE_SECURE'] = 'false'
    with tempfile.TemporaryDirectory(prefix='ava-frontend-qa-') as directory:
        engine, sessions = database('sqlite:///' + str(Path(directory) / 'qa.db'))
        Base.metadata.create_all(engine)
        with sessions.begin() as db:
            settings = BusinessSettings(
                name='Frontend QA clinic', timezone='UTC',
                services=[Service(id='pt', name='Physiotherapy', duration=30)],
                hours=[Hours(weekday=0, opens='09:00', closes='17:00')])
            business = Business(settings=settings.model_dump(mode='json'))
            db.add(business)
            db.flush()
            db.add(Admin(business_id=business.id, email='qa@example.test',
                         password_hash=passwords.hash('frontend-qa-only-123')))
            call = Call(id='qa-call', business_id=business.id, status='completed',
                        ended_at=datetime.now(timezone.utc), summary='Frontend fixture call.',
                        summary_status='deterministic')
            db.add(call)
            db.flush()
            db.add(TranscriptTurn(business_id=business.id, call_id=call.id,
                                  role='user', text='Where can I park?'))
            db.add(Message(id='qa-message', business_id=business.id, call_id=call.id,
                           key='qa-message', caller_name='QA caller', phone='+15551234567',
                           content='Please call back.', escalated=1))
            db.add(Appointment(id='qa-appointment', business_id=business.id,
                               caller_name='QA caller', caller_phone='+15551234567', service_id='pt',
                               start_at=datetime(2026, 10, 12, 10, tzinfo=timezone.utc),
                               end_at=datetime(2026, 10, 12, 10, 30, tzinfo=timezone.utc),
                               timezone='UTC', calendar_event_id='qa-event'))
        try:
            app = create_app(sessions, calendar=OfflineCalendar(), llm=OfflineLLM(), voice_enabled=False)
            if '--transport-echo' in sys.argv:
                add_transport_probe(app)
            uvicorn.run(app, host='127.0.0.1', port=8001)
        finally:
            engine.dispose()


if __name__ == '__main__':
    main()
