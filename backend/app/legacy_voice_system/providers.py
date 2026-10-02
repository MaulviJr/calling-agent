"""Provider SDK calls stay here; models retain the prototype defaults."""
import os
from contextlib import contextmanager
from deepgram import DeepgramClient
from deepgram.core.events import EventType
from elevenlabs.client import ElevenLabs
from google import genai
from google.genai import types


class GeminiChat:
    def __init__(self, instruction):
        self.client = genai.Client(api_key=os.environ['GEMINI_API_KEY'],
                                   http_options=types.HttpOptions(timeout=30000))
        self.instruction = instruction
        self.chat = self.client.chats.create(
            model=os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite'),
            config=types.GenerateContentConfig(system_instruction=instruction))

    def respond(self, text):
        print('LLM_INPUT [chat.respond]', {'system_instruction': self.instruction,
              'message': text}, flush=True)
        result = self.chat.send_message(message=text)
        print('LLM_OUTPUT [chat.respond]', result.text, flush=True)
        return result.text or ''


class ElevenSpeech:
    def __init__(self, voice=None):
        self.client = ElevenLabs(api_key=os.environ['ELEVENLABS_API_KEY'], timeout=30)
        self.voice = voice or os.getenv('ELEVENLABS_VOICE_ID', 'JBFqnCBsd6RMkjVDRZzb')

    def stream(self, text):
        return self.client.text_to_speech.stream(text=text, voice_id=self.voice,
            model_id='eleven_flash_v2_5', output_format='pcm_16000')


@contextmanager
def flux_connection(on_event, on_error):
    import threading
    client = DeepgramClient(api_key=os.environ['DEEPGRAM_API_KEY'])
    thresholds = flux_turn_settings()
    with client.listen.v2.connect(
        model='flux-general-en',
        encoding='linear16',
        sample_rate=16000,
        **thresholds
        ) as conn:
        conn.on(EventType.MESSAGE,
                 lambda m: on_event(getattr(m, 'event', ''),
                  getattr(m, 'transcript', ''), 
                  getattr(m, 'turn_index', None)))
        conn.on(EventType.ERROR, lambda _: on_error())
        conn.on(EventType.CLOSE, lambda _: on_error())
        listener = threading.Thread(
            target=conn.start_listening,
            daemon=True,
            name='ava-stt'
            )
        listener.start()
        try:
            yield conn
        finally:
            conn.send_close_stream()


def flux_turn_settings():
    """Balance turn latency against pauses while spelling names/phone numbers."""
    threshold = float(os.getenv('DEEPGRAM_EOT_THRESHOLD', '0.7'))
    timeout = int(os.getenv('DEEPGRAM_EOT_TIMEOUT_MS', '2000'))
    if not 0.5 <= threshold <= 1.0:
        raise ValueError('DEEPGRAM_EOT_THRESHOLD must be between 0.5 and 1.0.')
    if not 500 <= timeout <= 60000:
        raise ValueError('DEEPGRAM_EOT_TIMEOUT_MS must be between 500 and 60000.')
    return {'eot_threshold': str(threshold), 'eot_timeout_ms': str(timeout)}
