import sounddevice as sd
import numpy as np

SAMPLE_RATE = 16000
DURATION = 3

print("Speak now...")

audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="int16"
)

sd.wait()

print("Recording finished!")

print("Shape:")
print(audio.shape)

print("\nFirst 30 samples:")
print(audio[:30].flatten())

print("\nMinimum sample:")
print(np.min(audio))

print("\nMaximum sample:")
print(np.max(audio))