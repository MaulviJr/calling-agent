import logging
import os
from dotenv import load_dotenv
from .api import create_app
from .database import database
from .calendar import GoogleCalendar, UnconfiguredCalendar


def build_app():
    load_dotenv()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    # SDK HTTP logs can contain URLs and provider response metadata.
    for name in ('httpx','httpcore','google','deepgram','elevenlabs'):
        logging.getLogger(name).setLevel(logging.WARNING)
    _,sessions=database()
    calendar=GoogleCalendar() if os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE') else UnconfiguredCalendar()
    return create_app(sessions,calendar)
