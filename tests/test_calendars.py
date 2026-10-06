import pytest
from sqlalchemy.exc import IntegrityError
from backend.app.business import BusinessSettings
from backend.app.calendar import CalendarUnavailable
from backend.app.calendars import CalendarRouter
from backend.app.database import Business, CalendarConnection


def second_business(sessions):
    with sessions.begin() as db:
        other = Business(settings=BusinessSettings().model_dump(mode='json'))
        db.add(other); db.flush()
        return other.id


def test_each_business_gets_its_own_calendar(system):
    sessions, bid, *_ = system
    other = second_business(sessions)
    with sessions.begin() as db:
        db.add_all([CalendarConnection(business_id=bid, calendar_id='a@group.calendar.google.com'),
                    CalendarConnection(business_id=other, calendar_id='b@group.calendar.google.com')])
    router = CalendarRouter(sessions, factory=lambda calendar_id: ('calendar', calendar_id))
    assert router.calendar_for(bid) == ('calendar', 'a@group.calendar.google.com')
    assert router.calendar_for(other) == ('calendar', 'b@group.calendar.google.com')
    assert router.calendar_for(bid) is router.calendar_for(bid)


def test_business_without_calendar_fails_closed(system):
    sessions, bid, *_ = system
    with pytest.raises(CalendarUnavailable):
        CalendarRouter(sessions, factory=lambda c: c).calendar_for(bid)


def test_two_businesses_cannot_share_a_calendar(system):
    sessions, bid, *_ = system
    other = second_business(sessions)
    with sessions.begin() as db:
        db.add(CalendarConnection(business_id=bid, calendar_id='same@group.calendar.google.com'))
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            db.add(CalendarConnection(business_id=other, calendar_id='same@group.calendar.google.com'))