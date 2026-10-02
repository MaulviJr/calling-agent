import asyncio
import queue

import sounddevice as sd
import websockets


SAMPLE_RATE = 16000
CHUNK_DURATION = 0.02

CHUNK_SIZE = int(
    SAMPLE_RATE * CHUNK_DURATION
)

audio_queue = queue.Queue()


def audio_callback(indata, frames, time, status):

    if status:
        print(status)

    audio_queue.put(indata.copy())


async def send_audio():

    uri = "ws://127.0.0.1:8000/ws"

    async with websockets.connect(uri) as websocket:

        print("Connected to server")
        print("Speak now...")

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=audio_callback
        ):

            while True:

                audio_chunk = await asyncio.to_thread(
                    audio_queue.get
                )

                await websocket.send(
                    audio_chunk.tobytes()
                )


asyncio.run(send_audio())