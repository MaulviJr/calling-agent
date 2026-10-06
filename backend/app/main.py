import logging
import os
from dotenv import load_dotenv
from .api import create_app
from .database import database
# from .calendar import GoogleCalendar, UnconfiguredCalendar


def build_app():
    load_dotenv()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    for name in ('httpx','httpcore','google','deepgram','elevenlabs'):
        logging.getLogger(name).setLevel(logging.WARNING)
    _,sessions=database()
    from .calendars import CalendarRouter
    return create_app(sessions,calendars=CalendarRouter(sessions))
