"""Small CalendarProvider boundary. Google is the only production implementation."""
import os
from typing import Protocol
from urllib.parse import quote
from datetime import datetime, timezone, time
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession


class CalendarUnavailable(RuntimeError):
    pass


class CalendarProvider(Protocol):
    def busy(self, start, end, exclude=None): ...
    def get(self, event_id): ...
    def create(self, event_id, body): ...
    def update(self, event_id, body, etag): ...
    def delete(self, event_id, etag): ...


class GoogleCalendar:
    def __init__(self):
        self.calendar_id = os.environ.get('GOOGLE_CALENDAR_ID', '')
        path = os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE', '')
        if not self.calendar_id or not path:
            raise CalendarUnavailable('Calendar is not configured.')
        credentials = service_account.Credentials.from_service_account_file(path,
            scopes=['https://www.googleapis.com/auth/calendar.events',
                    'https://www.googleapis.com/auth/calendar.freebusy'])
        self.http = AuthorizedSession(credentials)
        self.base = 'https://www.googleapis.com/calendar/v3'
        self.events = '/calendars/' + quote(self.calendar_id, safe='') + '/events'

    def _request(self, method, path, **kwargs):
        try:
            response = self.http.request(method, self.base+path, timeout=15, **kwargs)
        except Exception:
            raise CalendarUnavailable('Calendar request failed.') from None
        if response.status_code in (404,410): return None
        if response.status_code == 409: raise CalendarUnavailable('Calendar event conflict; reconcile first.')
        if not response.ok: raise CalendarUnavailable('Calendar request rejected.')
        return response.json() if response.content else {}

    def get(self, event_id):
        event = self._request('GET', self.events+'/'+quote(event_id,safe=''))
        return None if event and event.get('status') == 'cancelled' else event

    def busy(self, start, end, exclude=None):
        if exclude is None:
            data = self._request('POST','/freeBusy',json={
                'timeMin':start.isoformat(),'timeMax':end.isoformat(),
                'items':[{'id':self.calendar_id}]})
            item = (data or {}).get('calendars',{}).get(self.calendar_id,{})
            if 'busy' not in item or item.get('errors'):
                raise CalendarUnavailable('Calendar free/busy unavailable.')
            return [(datetime.fromisoformat(x['start']),datetime.fromisoformat(x['end'])) for x in item['busy']]
        # freeBusy has no event IDs. Rescheduling uses expanded events to exclude
        # exactly the original event, never an entire busy interval.
        result, page = [], None
        while True:
            params = {'timeMin':start.isoformat(),'timeMax':end.isoformat(),
                      'singleEvents':'true','maxResults':2500}
            if page: params['pageToken'] = page
            data = self._request('GET',self.events,params=params)
            if data is None: raise CalendarUnavailable('Calendar unavailable.')
            for event in data.get('items',[]):
                if event.get('id') == exclude or event.get('status') == 'cancelled' or event.get('transparency') == 'transparent':
                    continue
                # All-day events are conservatively busy across their date range.
                if 'dateTime' not in event['start']:
                    from zoneinfo import ZoneInfo
                    zone = ZoneInfo(data.get('timeZone','UTC'))
                    a = datetime.combine(datetime.fromisoformat(event['start']['date']).date(),time(),zone)
                    b = datetime.combine(datetime.fromisoformat(event['end']['date']).date(),time(),zone)
                else:
                    a,b = (datetime.fromisoformat(event[k]['dateTime']) for k in ('start','end'))
                result.append((a,b))
            page = data.get('nextPageToken')
            if not page: return result

    def create(self, event_id, body):
        result = self._request('POST',self.events,json={**body,'id':event_id})
        if result is None: raise CalendarUnavailable('Calendar not found.')
        return result

    def update(self, event_id, body, etag):
        result = self._request('PATCH',self.events+'/'+quote(event_id,safe=''),
            json=body,headers={'If-Match':etag})
        if result is None: raise CalendarUnavailable('Appointment no longer exists.')
        return result

    def delete(self, event_id, etag):
        self._request('DELETE',self.events+'/'+quote(event_id,safe=''), headers={'If-Match':etag})


class UnconfiguredCalendar:
    def __getattr__(self, name):
        def unavailable(*args, **kwargs):
            raise CalendarUnavailable('Calendar is not configured.')
        return unavailable
