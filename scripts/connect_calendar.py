"""Connect a business to its Google Calendar and verify access.
Usage: python -m scripts.connect_calendar BUSINESS_ID CALENDAR_ID"""
import sys
from datetime import timedelta
from dotenv import load_dotenv
from backend.app.calendar import GoogleCalendar, CalendarUnavailable
from backend.app.database import Business, CalendarConnection, database, now, uid


def main(business_id, calendar_id):
    load_dotenv()
    _, sessions = database()
    with sessions() as db:
        if db.get(Business, business_id) is None:
            sys.exit('Unknown business ID.')
    try:
        calendar = GoogleCalendar(calendar_id)
        calendar.busy(now(), now() + timedelta(minutes=1))          # can we read?
        start = now() + timedelta(days=1)
        event_id = uid()                                              # can we write? create, then delete
        event = calendar.create(event_id, {'summary': 'Ava connection test',
            'start': {'dateTime': start.isoformat()},
            'end': {'dateTime': (start + timedelta(minutes=5)).isoformat()}})
        calendar.delete(event_id, event['etag'])
    except CalendarUnavailable as exc:
        sys.exit(f'Not saved: {exc} Is the calendar shared with the service account '
                 'with "Make changes to events" permission?')
    with sessions.begin() as db:
        row = db.get(CalendarConnection, business_id)
        if row:
            row.calendar_id, row.status, row.last_checked_at = calendar_id, 'connected', now()
        else:
            db.add(CalendarConnection(business_id=business_id, calendar_id=calendar_id,
                                      status='connected', last_checked_at=now()))
    print('Calendar connected and verified (read and write).')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])