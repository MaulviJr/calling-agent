from datetime import datetime, timezone, date, time
from zoneinfo import ZoneInfo
import pytest
from backend.app.dates import resolve_date, time_window, wall_time
from backend.app.business import BusinessSettings


def test_relative_business_date():
    now = datetime(2026, 9, 27, 23, tzinfo=timezone.utc)
    assert resolve_date('tomorrow','Asia/Karachi',now) == date(2026,9,29)
    assert resolve_date('next Friday','Asia/Karachi',now) == date(2026,10,2)
    assert resolve_date('October 12','Asia/Karachi',now) == date(2026,10,12)


def test_ambiguous_and_invalid_times():
    with pytest.raises(ValueError): time_window('around 4')
    with pytest.raises(ValueError): time_window('25:00')
    assert time_window('after 5 pm')[0] == time(17)
    with pytest.raises(ValueError): wall_time(date(2026,3,8),time(2,30),ZoneInfo('America/New_York'))
    with pytest.raises(ValueError): wall_time(date(2026,11,1),time(1,30),ZoneInfo('America/New_York'))
    with pytest.raises(ValueError): BusinessSettings(timezone='invalid')
