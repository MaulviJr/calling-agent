"""Run from the repository root: python -m backend.app.voice.local."""
import logging
import queue
import threading
from dotenv import load_dotenv
import sounddevice as sd
from .session import VoiceSession
from .providers import ElevenSpeech, flux_connection
from .audio import play_pcm
from ..agent import Receptionist, GeminiConversationPlanner
from ..database import database, Business, uid
from ..scheduling import Scheduling
from ..calendar import GoogleCalendar, UnconfiguredCalendar
from sqlalchemy import select
import os


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    _, sessions = database()
    with sessions() as db:
        business = db.scalar(select(Business))
        if not business: raise RuntimeError('Run bootstrap and configure the clinic first.')
        bid = business.id
        voice = business.settings.get('voice_id')
    calendar = GoogleCalendar() if os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE') else UnconfiguredCalendar()
    agent = Receptionist(sessions, Scheduling(sessions, calendar), GeminiConversationPlanner())
    call_id = agent.start(bid, 'local')
    tts = ElevenSpeech(voice)
    session = VoiceSession(lambda text: agent.respond(bid,call_id,text,uid()),
        lambda text, cancel: play_pcm(tts,text,cancel),
        lambda text, interrupted: agent.delivered(bid,call_id,interrupted))
    audio = queue.Queue(maxsize=125)
    failed = threading.Event()

    def capture(data, frames, timing, status):
        try:
            audio.put_nowait(bytes(data))
        except queue.Full:
            failed.set()

    session.start()
    try:
        with flux_connection(session.event, failed.set) as connection:
            with sd.RawInputStream(samplerate=16000, channels=1, dtype='int16',
                                   blocksize=1280, callback=capture):
                print('Ava listening. Use headphones; Ctrl+C to stop.')
                while not failed.is_set() and not session.closed.is_set():
                    try:
                        connection.send_media(audio.get(timeout=.2))
                    except queue.Empty:
                        continue
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
        agent.end(bid,call_id,'voice_failure' if failed.is_set() or session.failed else '')


if __name__ == '__main__':
    main()
