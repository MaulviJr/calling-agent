"""Which calendar belongs to which business. The only place that decides."""
import threading
from .calendar import GoogleCalendar, CalendarUnavailable
from .database import CalendarConnection
from .scheduling import Scheduling


class CalendarRouter:
    def __init__(self, sessions, factory=GoogleCalendar):
        self.sessions, self.factory = sessions, factory
        self._cache, self._lock = {}, threading.Lock()

    def calendar_for(self, business_id):
        # Looked up on every call, so reconnecting a calendar takes effect immediately.
        with self.sessions() as db:
            row = db.get(CalendarConnection, business_id)
            calendar_id = row.calendar_id if row else None
        if not calendar_id:
            raise CalendarUnavailable('No calendar is connected for this business.')
        with self._lock:  # reuse one object per calendar instead of rebuilding per call
            if calendar_id not in self._cache:
                self._cache[calendar_id] = self.factory(calendar_id)
            return self._cache[calendar_id]

    def scheduler_for(self, business_id):
        return Scheduling(self.sessions, self.calendar_for(business_id))


class FixedCalendar:
    """One calendar for every business. Tests and local development only."""
    def __init__(self, sessions, calendar):
        self.sessions, self.calendar = sessions, calendar

    def calendar_for(self, business_id):
        return self.calendar

    def scheduler_for(self, business_id):
        return Scheduling(self.sessions, self.calendar)