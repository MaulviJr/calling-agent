"""Pace PCM against a clock so send overhead doesn't accumulate as silence."""
import time


class PcmPacer:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.deadline = clock()

    def begin_frame(self, byte_count):
        # After a provider stall, resume from now instead of bursting stale time.
        # Small late timer wake-ups must not move the whole timeline forward.
        # Only a genuine stall resets it; catch up ordinary scheduling jitter.
        now = self.clock()
        if now - self.deadline > .12:
            self.deadline = now
        self.deadline += byte_count / 32000

    def remaining(self):
        return max(0, self.deadline - self.clock())
