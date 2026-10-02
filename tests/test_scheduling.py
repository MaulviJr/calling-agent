from concurrent.futures import ThreadPoolExecutor
from datetime import date
import pytest
from backend.app.calendar import CalendarUnavailable
from backend.app.scheduling import Booking


def payload(**changes):
    return Booking(caller_name='Test caller',caller_phone='+15551234567',service_id='pt',
        start_at='2026-10-02T10:00:00+00:00',**changes).model_dump(mode='json')


def test_booking_duplicate_and_conflict(system):
    _,bid,cal,s=system
    with pytest.raises(ValueError): s.mutate(bid,'a','create',payload())
    result=s.mutate(bid,'a','create',payload(),True)
    assert s.mutate(bid,'a','create',payload(),True)['id']==result['id']
    assert len(cal.events)==1
    with pytest.raises(ValueError): s.mutate(bid,'b','create',payload(),True)


def test_concurrent_booking(system):
    _,bid,cal,s=system
    def attempt(key):
        try: return s.mutate(bid,key,'create',payload(),True)['id']
        except (ValueError,CalendarUnavailable): return None
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(attempt,['a','b']))
    assert sum(x is not None for x in results)==1
    assert len(cal.events)==1


def test_reschedule_cancel(system):
    _,bid,cal,s=system
    row=s.mutate(bid,'a','create',payload(),True)
    moved=s.mutate(bid,'b','reschedule',{'appointment_id':row['id'],'start_at':'2026-10-02T11:00:00+00:00'},True)
    assert moved['start_at'].hour==11
    cancelled=s.mutate(bid,'c','cancel',{'appointment_id':row['id']},True)
    assert cancelled['status']=='cancelled' and not cal.events


def test_timeout_reconciles_without_duplicate(system):
    _,bid,cal,s=system
    cal.after_create=True
    with pytest.raises(CalendarUnavailable): s.mutate(bid,'a','create',payload(),True)
    assert len(cal.events)==1
    with pytest.raises(CalendarUnavailable): s.mutate(bid,'b','create',payload(),True)
    cal.after_create=False
    assert s.mutate(bid,'a','create',payload(),True)['status']=='booked'
    assert len(cal.events)==1


def test_slots_and_invalid_data(system):
    _,bid,cal,s=system
    s.mutate(bid,'a','create',payload(),True)
    slots=s.slots(bid,'pt',date(2026,10,2))
    assert '2026-10-02T10:00:00+00:00' not in slots
    assert '2026-10-02T10:30:00+00:00' in slots
    with pytest.raises(ValueError): Booking.model_validate({**payload(),'caller_name':''})
    with pytest.raises(ValueError): Booking.model_validate({**payload(),'caller_phone':''})
    with pytest.raises(ValueError): Booking.model_validate({**payload(),'start_at':'invalid'})
    with pytest.raises(ValueError): s.mutate(bid,'past','create',{**payload(),'start_at':'2026-09-01T10:00:00+00:00'},True)
