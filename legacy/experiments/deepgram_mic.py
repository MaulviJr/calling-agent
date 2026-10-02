import os
import queue
import threading
import numpy as np
import sounddevice as sd

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from deepgram import DeepgramClient
from deepgram.core.events import EventType
from elevenlabs.client import ElevenLabs


load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

if not DEEPGRAM_API_KEY:
    raise ValueError("DEEPGRAM_API_KEY not found")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found")

if not ELEVENLABS_API_KEY:
    raise ValueError("ELEVENLABS_API_KEY not found")


deepgram_client = DeepgramClient(
    api_key=DEEPGRAM_API_KEY
)

gemini_client = genai.Client(
    api_key=GEMINI_API_KEY
)

elevenlabs_client = ElevenLabs(
    api_key=ELEVENLABS_API_KEY
)


chat = gemini_client.chats.create(
    model="gemini-3.5-flash-lite",
    config=genai_types.GenerateContentConfig(
        system_instruction="""
You are Ava, a helpful and friendly AI assistant.

Keep responses concise, informative, and conversational.
"""
    )
)


def ask_llm(user_text):
    response = chat.send_message(
        message=user_text
    )
    return response.text


SAMPLE_RATE = 16000
CHUNK_DURATION = 0.08
CHUNK_SIZE = int(
    SAMPLE_RATE * CHUNK_DURATION
)

audio_queue = queue.Queue()
agent_queue = queue.Queue()

stop_speaking_event = threading.Event()


def audio_callback(indata, frames, time, status):

    if status:
        print("Audio status:", status)

    audio_queue.put(
        indata.copy()
    )


def speak(text):

    stop_speaking_event.clear()

    audio_stream = elevenlabs_client.text_to_speech.stream(
        text=text,
        voice_id="JBFqnCBsd6RMkjVDRZzb",
        model_id="eleven_flash_v2_5",
        output_format="pcm_16000",
    )

    with sd.OutputStream(
        samplerate=16000,
        channels=1,
        dtype="int16"
    ) as output_stream:

        for chunk in audio_stream:

            if stop_speaking_event.is_set():
                print("Ava interrupted")
                break

            if not chunk:
                continue

            audio_array = np.frombuffer(
                chunk,
                dtype=np.int16
            )

            output_stream.write(
                audio_array
            )


def agent_worker():

    while True:

        transcript = agent_queue.get()

        try:

            response = ask_llm(
                transcript
            )

            print(
                "Ava:",
                response
            )

            speak(
                response
            )

        except Exception as e:

            print(
                "Agent error:",
                e
            )


agent_thread = threading.Thread(
    target=agent_worker,
    daemon=True
)

agent_thread.start()


with deepgram_client.listen.v2.connect(
    model="flux-general-en",
    encoding="linear16",
    sample_rate=SAMPLE_RATE,
    eot_threshold="0.85",
    eot_timeout_ms="5000"
) as connection:

    connection_ready = threading.Event()

    def on_message(message):

        event = getattr(
            message,
            "event",
            None
        )

        transcript = getattr(
            message,
            "transcript",
            ""
        )

        if event == "StartOfTurn":

            print(
                "\nUser started speaking"
            )

            stop_speaking_event.set()

        elif event == "Update":

            if transcript:

                print(
                    "Interim:",
                    transcript
                )

        elif event == "EndOfTurn":

            if transcript:

                print(
                    "\nUser:",
                    transcript
                )

                agent_queue.put(
                    transcript
                )


    connection.on(
        EventType.OPEN,
        lambda _: (
            print(
                "Connected to Deepgram"
            ),
            connection_ready.set()
        )
    )

    connection.on(
        EventType.MESSAGE,
        on_message
    )

    connection.on(
        EventType.ERROR,
        lambda error: print(
            "Deepgram error:",
            error
        )
    )

    connection.on(
        EventType.CLOSE,
        lambda _: print(
            "Deepgram connection closed"
        )
    )


    listener_thread = threading.Thread(
        target=connection.start_listening,
        daemon=True
    )

    listener_thread.start()


    if not connection_ready.wait(
        timeout=10
    ):
        raise TimeoutError(
            "Timed out waiting for Deepgram connection"
        )


    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=CHUNK_SIZE,
        callback=audio_callback
    ):

        print("Microphone started")
        print("Speak now...")
        print("Press Ctrl+C to stop\n")

        try:

            while True:

                audio_chunk = (
                    audio_queue.get()
                )

                connection.send_media(
                    audio_chunk.tobytes()
                )

        except KeyboardInterrupt:

            print("\nStopping...")


    connection.send_close_stream()