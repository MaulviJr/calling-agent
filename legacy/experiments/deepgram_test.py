import os

from dotenv import load_dotenv
from deepgram import DeepgramClient
from deepgram.core.events import EventType


# Load variables from .env
load_dotenv()

# Get Deepgram API key
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

if not DEEPGRAM_API_KEY:
    raise ValueError("DEEPGRAM_API_KEY not found in .env")


# Initialize Deepgram
client = DeepgramClient(api_key=DEEPGRAM_API_KEY)


with client.listen.v2.connect(
    model="flux-general-en",
    encoding="linear16",
    sample_rate=16000
) as connection:

    def on_message(message):
        print("Deepgram message:")
        print(message.transcripts[0].text)

    connection.on(
        EventType.OPEN,
        lambda _: print("Connected to Deepgram")
    )

    connection.on(
        EventType.MESSAGE,
        on_message
    )

    connection.on(
        EventType.ERROR,
        lambda error: print("Error:", error)
    )

    connection.on(
        EventType.CLOSE,
        lambda _: print("Connection closed")
    )

    connection.start_listening()

    input("Press ENTER to stop...\n")