from backend.app.agent import Receptionist, Decision
from backend.app.database import Appointment, Message, Call
from sqlalchemy import select
import pytest


class Scripted:
    def __init__(self,*decisions): self.decisions=list(decisions)
    def decide(self,*args): return self.decisions.pop(0)


def test_booking_requires_confirmation_and_duplicate_turn(system):
    sessions,bid,cal,s=system
    agent=Receptionist(sessions,s,Scripted(Decision(action='book',date_phrase='2026-10-02',time_phrase='10:00',caller_name='Caller',phone='+15551234567')))
    cid=agent.start(bid)
    reply=agent.respond(bid,cid,'Book October 2 at ten am. My name is Caller and phone is +15551234567.','1')
    assert 'confirm' in reply and not cal.events
    reply=agent.respond(bid,cid,'yes','2')
    assert 'booked' in reply and len(cal.events)==1
    assert agent.respond(bid,cid,'yes','2')==reply
    agent.end(bid,cid)
    with sessions() as db: assert db.get(Call,cid).summary


def test_changed_time_invalidates_confirmation(system):
    sessions,bid,cal,s=system
    agent=Receptionist(sessions,s,Scripted(
        Decision(action='book',date_phrase='2026-10-02',time_phrase='10:00',caller_name='Caller',phone='+15551234567'),
        Decision(action='confirm',time_phrase='11:00')))
    cid=agent.start(bid)
    agent.respond(bid,cid,'booking','1')
    response=agent.respond(bid,cid,'Actually eleven','2')
    assert '11:00' in response and not cal.events
    agent.respond(bid,cid,'yes','3')
    assert next(iter(cal.events.values()))['start']['dateTime'].startswith('2026-10-02T11:00')


def test_message_escalation_and_failure(system):
    sessions,bid,cal,s=system
    agent=Receptionist(sessions,s,Scripted(Decision(action='message',caller_name='Caller',phone='+15551234567',message_text='Please call back')))
    cid=agent.start(bid)
    assert 'live transfer is not available' in agent.respond(bid,cid,'human','1')
    agent.respond(bid,cid,'Call me back','2')
    agent.respond(bid,cid,'yes','3')
    with sessions() as db: assert db.scalar(select(Message)).escalated==1


def test_llm_cannot_invent_slot(system):
    sessions,bid,cal,s=system
    agent=Receptionist(sessions,s,Scripted(Decision(action='book',selected_slot='2026-10-02T10:00:00+00:00')))
    cid=agent.start(bid)
    assert 'choose one' in agent.respond(bid,cid,'book','1')
    assert not cal.events


def test_calendar_failure_never_claims_success(system):
    sessions,bid,cal,s=system
    agent=Receptionist(sessions,s,Scripted(Decision(action='book',date_phrase='2026-10-02',time_phrase='10:00',caller_name='Caller',phone='+15551234567')))
    cid=agent.start(bid)
    agent.respond(bid,cid,'booking','1'); cal.fail=True
    result=agent.respond(bid,cid,'yes','2')
    assert "couldn't complete" in result and 'booked' not in result
