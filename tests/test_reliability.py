from datetime import datetime, timezone
from sqlalchemy import select
from backend.app.agent import Decision, Receptionist
from backend.app.database import Call, Business, TranscriptTurn, Appointment
from backend.app.calendar import GoogleCalendar, CalendarUnavailable
from backend.app.scheduling import Booking
import pytest


class Scripted:
    def __init__(self,*items): self.items=list(items)
    def decide(self,*args): return self.items.pop(0)


def test_missing_details_asked_one_at_a_time(system):
    sessions,bid,cal,s=system
    agent=Receptionist(sessions,s,Scripted(Decision(action='book',date_phrase='2026-10-02',time_phrase='10:00'),
        Decision(action='book',caller_name='Caller'),Decision(action='book',phone='+15551234567')))
    cid=agent.start(bid)
    assert 'full name' in agent.respond(bid,cid,'book','1')
    assert 'phone number' in agent.respond(bid,cid,'Caller','2')
    assert 'confirm' in agent.respond(bid,cid,'my phone','3')
    assert not cal.events


def test_interrupted_confirmation_cannot_book(system):
    sessions,bid,cal,s=system
    agent=Receptionist(sessions,s,Scripted(Decision(action='book',date_phrase='2026-10-02',time_phrase='10:00',caller_name='Caller',phone='+15551234567')))
    cid=agent.start(bid,'local')
    agent.respond(bid,cid,'book','1')
    agent.delivered(bid,cid,True)
    assert 'finish the confirmation' in agent.respond(bid,cid,'yes','2')
    assert not cal.events
    agent.delivered(bid,cid,False)
    assert 'booked' in agent.respond(bid,cid,'yes','3')


def test_changed_date_and_settings_force_new_confirmation(system):
    sessions,bid,cal,s=system
    agent=Receptionist(sessions,s,Scripted(Decision(action='book',date_phrase='2026-10-02',time_phrase='10:00',caller_name='Caller',phone='+15551234567'),
        Decision(action='book',date_phrase='2026-10-03')))
    cid=agent.start(bid)
    agent.respond(bid,cid,'book','1')
    result=agent.respond(bid,cid,'actually Saturday','2')
    assert 'October 03' in result and not cal.events
    with sessions.begin() as db:
        business=db.get(Business,bid)
        business.settings={**business.settings,'buffer_minutes':15}
    assert 'settings changed' in agent.respond(bid,cid,'yes','3')
    assert not cal.events


def test_approved_faq_and_emergency(system):
    sessions,bid,cal,s=system
    with sessions.begin() as db:
        business=db.get(Business,bid)
        business.settings={**business.settings,'knowledge':[{'question':'Parking?','answer':'Use the north entrance.'}]}
    agent=Receptionist(sessions,s,Scripted(Decision(action='faq',faq_index=0),Decision(action='faq',faq_index=50)))
    cid=agent.start(bid)
    assert agent.respond(bid,cid,'parking','1')=='Use the north entrance.'
    assert 'do not have approved' in agent.respond(bid,cid,'What insurance does the clinic accept?','2')
    assert 'emergency service' in agent.respond(bid,cid,'I cannot breathe','3')


def test_ai_summary_failure_preserves_durable_call(system):
    sessions,bid,cal,s=system
    class Model:
        def summarize(self,turns): raise RuntimeError('unavailable')
    agent=Receptionist(sessions,s,Model()); cid=agent.start(bid)
    agent.end(bid,cid)
    with sessions() as db:
        call=db.get(Call,cid)
        assert call.status=='completed' and call.summary and call.summary_status=='deterministic'


def test_ai_summary_is_labelled(system):
    sessions,bid,cal,s=system
    class Model:
        def summarize(self,turns): return 'Caller asked about parking.'
    agent=Receptionist(sessions,s,Model()); cid=agent.start(bid); agent.end(bid,cid)
    with sessions() as db: assert db.get(Call,cid).summary_status=='ai'


def test_google_adapter_rejects_partial_freebusy_error():
    calendar=object.__new__(GoogleCalendar); calendar.calendar_id='clinic'
    calendar._request=lambda *a,**kw: {'calendars':{'clinic':{'busy':[],'errors':[{'reason':'forbidden'}]}}}
    with pytest.raises(CalendarUnavailable): calendar.busy(datetime.now(timezone.utc),datetime.now(timezone.utc))


def test_google_reschedule_excludes_only_own_event_and_paginates():
    calendar=object.__new__(GoogleCalendar); calendar.calendar_id='clinic'; calendar.events='/events'
    pages=[{'items':[{'id':'own','start':{'dateTime':'2026-10-02T10:00:00+00:00'},'end':{'dateTime':'2026-10-02T10:30:00+00:00'}}],'nextPageToken':'next'},
           {'items':[{'id':'other','start':{'dateTime':'2026-10-02T10:00:00+00:00'},'end':{'dateTime':'2026-10-02T10:30:00+00:00'}}]}]
    calendar._request=lambda *a,**kw: pages.pop(0)
    assert len(calendar.busy(datetime.now(timezone.utc),datetime.now(timezone.utc),'own'))==1
