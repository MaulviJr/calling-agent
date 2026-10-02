"""Resolve common phrases, but reject ambiguous wall times instead of guessing."""
import re
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def wall_time(day, clock, zone):
    naive = datetime.combine(day, clock)
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError('That local time changes with daylight saving. Please choose another time.')
    if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
        raise ValueError('That local time does not exist.')
    return first


def resolve_date(phrase, zone, now):
    local = now.astimezone(ZoneInfo(zone)).date()
    phrase = phrase.strip().lower()
    if phrase == 'today': return local
    if phrase == 'tomorrow': return local + timedelta(days=1)
    days = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
    name = phrase.removeprefix('next ')
    if name in days:
        delta = (days.index(name)-local.weekday()) % 7
        return local + timedelta(days=delta or 7)
    try:
        return datetime.strptime(phrase, '%Y-%m-%d').date()
    except ValueError:
        try:
            result = datetime.strptime(f'{phrase} {local.year}', '%B %d %Y').date()
            return result if result >= local else result.replace(year=local.year+1)
        except ValueError:
            raise ValueError('Please give a date such as October 12 or 2026-10-12.')


def time_window(phrase):
    phrase = phrase.lower().strip()
    if not phrase or phrase == 'any': return time(0), time(23,59)
    if phrase == 'morning': return time(8), time(12)
    if phrase == 'afternoon': return time(12), time(17)
    if phrase == 'evening': return time(17), time(23)
    match = re.fullmatch(r'(after |around )?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', phrase)
    if not match:
        raise ValueError('Please give a time with AM or PM, or say morning or afternoon.')
    modifier, hour, minute, meridiem = match.groups()
    hour, minute = int(hour), int(minute or 0)
    if meridiem:
        if not 1 <= hour <= 12: raise ValueError('Invalid time.')
        hour = hour % 12 + (12 if meridiem == 'pm' else 0)
    elif hour <= 12 and ':' not in phrase:
        raise ValueError('Do you mean AM or PM?')
    clock = time(hour, minute)
    if modifier == 'after ': return clock, time(23,59)
    return clock, clock
