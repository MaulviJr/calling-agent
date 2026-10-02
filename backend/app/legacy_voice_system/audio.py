import logging
import sounddevice as sd

log = logging.getLogger('ava')


def play_pcm(provider, text, cancel):
    chunks = provider.stream(text)
    pending = b''
    try:
        with sd.RawOutputStream(samplerate=16000, channels=1, dtype='int16') as output:
            for chunk in chunks:
                if cancel.is_set():
                    output.abort()
                    break
                pending += chunk
                # Small writes bound local interruption latency and handle odd
                # network chunk boundaries without corrupting 16-bit samples.
                while len(pending) >= 640 and not cancel.is_set():
                    output.write(pending[:640])
                    pending = pending[640:]
            if pending and not cancel.is_set():
                output.write(pending[:len(pending)//2*2])
    finally:
        chunks.close()
