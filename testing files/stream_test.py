import sounddevice as sd

SAMPLE_RATE = 16000
CHUNK_DURATION = 0.5  # 50 milliseconds

CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)

print("Samples per chunk:", CHUNK_SIZE)


def audio_callback(indata, frames, time, status):
    print(
        "Received chunk:",
        frames,
        "samples |",
        indata.nbytes,
        "bytes"
    )


with sd.InputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="int16",
    blocksize=CHUNK_SIZE,
    callback=audio_callback
):
    print("Listening...")
    input("Press ENTER to stop.\n")