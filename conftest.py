import copy
from datetime import datetime, timezone
import pytest
from backend.app.database import Base, database, Business
from backend.app.business import BusinessSettings, Service, Hours
from backend.app.scheduling import Scheduling


class FakeCalendar:
    def __init__(self):
        self.events={}; self.extra_busy=[]; self.fail=False; self.after_create=False
    def get(self,key):
        if self.fail: raise RuntimeError('provider down')
        return copy.deepcopy(self.events.get(key))
    def busy(self,start,end,exclude=None):
        if self.fail: raise RuntimeError('provider down')
        return self.extra_busy+[(datetime.fromisoformat(e['start']['dateTime']),datetime.fromisoformat(e['end']['dateTime'])) for k,e in self.events.items() if k!=exclude]
    def create(self,key,body):
        if self.fail: raise RuntimeError('provider down')
        self.events[key]={**copy.deepcopy(body),'id':key,'etag':'1'}
        if self.after_create: raise TimeoutError('response lost')
        return self.get(key)
    def update(self,key,body,etag):
        self.events[key].update(copy.deepcopy(body)); return self.get(key)
    def delete(self,key,etag): self.events.pop(key,None)


@pytest.fixture
def system(tmp_path):
    engine,sessions=database('sqlite:///'+str(tmp_path/'test.db'))
    Base.metadata.create_all(engine)
    settings=BusinessSettings(name='Test clinic',timezone='UTC',minimum_notice_minutes=0,
        services=[Service(id='pt',name='Physiotherapy',duration=30)],
        hours=[Hours(weekday=i,opens='09:00',closes='18:00') for i in range(7)])
    with sessions.begin() as db:
        business=Business(settings=settings.model_dump(mode='json')); db.add(business); db.flush(); bid=business.id
    calendar=FakeCalendar()
    scheduler=Scheduling(sessions,calendar,clock=lambda: datetime(2026,9,27,tzinfo=timezone.utc))
    yield sessions,bid,calendar,scheduler
    engine.dispose()
