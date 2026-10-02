"""One worker owns reasoning; the STT callback only enqueues and interrupts."""
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from backend.app.lookup import lookup_observer

log = logging.getLogger('ava')


@dataclass
class Turn:
    text: str
    generation: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)
    received: float = field(default_factory=time.monotonic)
    is_greeting: bool = False


class VoiceSession:
    def __init__(self, respond, speak, on_reply=lambda text, interrupted: None, speak_greeting=None,
                 wait_seconds=1.0):
        self.respond, self.speak, self.on_reply = respond, speak, on_reply
        self.speak_greeting = speak_greeting or speak
        self.wait_seconds = wait_seconds
        self.wait_count = 0
        self.pending = queue.Queue(maxsize=16)
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.current = None
        self.last_final_index = -1
        # generation Helps detect replies made outdated by interruption
        self.generation = 0
        self.failed = False
        self.worker = threading.Thread(
            target=self._run, 
            name='ava-agent', 
            daemon=True
            )

    def start(self, greeting=''):
        if greeting.strip():
            # Outbound audio uses the normal worker/cancellation path, but
            # must never be interpreted as a fabricated caller turn.
            self.pending.put_nowait(Turn(greeting.strip(), is_greeting=True))
        self.worker.start()

    def event(self, event, transcript='', turn_index=None):
        with self.lock:
            if self.closed.is_set():
                return
            if event == 'StartOfTurn':
                self.generation += 1
                if self.current:
                    self.current.cancel.set()
                # A fresh event belongs to the next response. Never clear an old
                # cancellation flag: an LLM request may still be in flight.
                with self.pending.mutex:
                    for turn in self.pending.queue:
                        turn.cancel.set()
                return
            if event != 'EndOfTurn' or not transcript.strip():
                return
            if turn_index is None or turn_index <= self.last_final_index:
                return
            self.last_final_index = turn_index
            try:
                self.pending.put_nowait(Turn(transcript.strip(), self.generation))
            except queue.Full:
                self.failed = True
                self.closed.set()

    def _run(self):
        # Keep checking for work while this voice session is open.
        while not self.closed.is_set():
            try:
                turn = self.pending.get(timeout=.1)
            except queue.Empty:
                continue
            with self.lock:
                self.current = turn
                # StartOfTurn can arrive between queue.get() and acquiring this
                # lock. The generation check covers that otherwise missed race.
                if turn.generation != self.generation or self.closed.is_set():
                    turn.cancel.set()
            try:
                if turn.is_greeting:
                    if not turn.cancel.is_set():
                        self.speak_greeting(turn.text, turn.cancel)
                    # No agent turn/confirmation exists to mark delivered.
                    continue
                # Preserve the user's finalized turn even if its audio reply is
                # cancelled. Operational state is owned by the controller.
                reply = self._respond_with_acknowledgement(turn)
                log.info('VOICE_TURN_COMPLETED latency_ms=%d', (time.monotonic()-turn.received)*1000)
                if reply and not turn.cancel.is_set():
                    self.speak(reply, turn.cancel)
                self.on_reply(reply, turn.cancel.is_set())
            except Exception as exc:
                self.failed = True
            finally:
                with self.lock:
                    self.current = None
                self.pending.task_done()

    def _respond_with_acknowledgement(self, turn):
        """Speak once during an actual slow appointment/calendar lookup, without running a second agent turn.

        Join the timer before final speech so two TTS streams never overlap.
        Both streams share the turn's interruption flag. Only the final answer
        receives a delivery callback; filler cannot authorize a pending booking.
        """
        finished = threading.Event()
        active = threading.Event()
        timers = []
        acknowledged = False

        def acknowledge():
            nonlocal acknowledged
            # “Do nothing if the lookup has ended, we already acknowledged, processing has finished, the user interrupted, or the call has closed
            if not active.is_set() or acknowledged or finished.is_set() or turn.cancel.is_set() or self.closed.is_set():
                return
            acknowledged = True
            phrases = ('Let me check that.', 'Just a moment, please.')
            text = phrases[self.wait_count % len(phrases)]
            self.wait_count += 1
            try:
                self.speak(text, turn.cancel)
            except Exception as exc:
                # Optional filler failure must not discard a real tool result.
                pass

        def observe(running):
            if running:
                active.set()
                timer = threading.Timer(self.wait_seconds, acknowledge)
                timer.daemon = True
                timers.append(timer)
                timer.start()
            else:
                active.clear()
                if timers:
                    timers[-1].cancel()
                    timers[-1].join()

        token = lookup_observer.set(observe)
        try:
            return self.respond(turn.text)
        finally:
            lookup_observer.reset(token)
            finished.set()
            active.clear()
            for timer in timers:
                timer.cancel()
                timer.join()

    def close(self):
        with self.lock:
            self.closed.set()
            if self.current:
                self.current.cancel.set()
        if self.worker.ident is not None:
            self.worker.join(timeout=35)
