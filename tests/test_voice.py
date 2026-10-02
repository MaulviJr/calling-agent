import threading
import time
import unittest
from backend.app.voice.session import VoiceSession


class VoiceTests(unittest.TestCase):
    def test_start_speaks_greeting_without_caller_or_llm(self):
        spoken, calls, delivered = [], [], []
        s = VoiceSession(lambda text: calls.append(text),
                         lambda text, cancel: spoken.append(text),
                         lambda *args: delivered.append(args))
        s.start('This is Ava, how can I help you today?')
        s.pending.join()
        s.close()
        self.assertEqual(spoken, ['This is Ava, how can I help you today?'])
        self.assertEqual(calls, [])
        self.assertEqual(delivered, [])

    def test_greeting_can_be_interrupted_then_caller_is_processed(self):
        speaking, interrupted = threading.Event(), threading.Event()
        calls, replies = [], []
        def greet(text, cancel):
            speaking.set()
            if cancel.wait(2): interrupted.set()
        s = VoiceSession(lambda text: calls.append(text) or 'response',
                         lambda text, cancel: replies.append(text), speak_greeting=greet)
        s.start('Hello')
        self.assertTrue(speaking.wait(1))
        s.event('StartOfTurn')
        self.assertTrue(interrupted.wait(1))
        s.event('EndOfTurn', 'Book an appointment', 0)
        s.pending.join()
        s.close()
        self.assertEqual(calls, ['Book an appointment'])
        self.assertEqual(replies, ['response'])

    def test_close_before_stt_connection_starts_worker(self):
        s = VoiceSession(lambda _: None, lambda *args: None)
        s.close()
        self.assertFalse(s.worker.is_alive())

    def test_speech_start_before_worker_cancels_queued_audio(self):
        spoken = []
        s = VoiceSession(lambda _: 'answer', lambda *args: spoken.append(args))
        s.event('EndOfTurn','hello',0)
        s.event('StartOfTurn')
        s.start(); s.pending.join(); s.close()
        self.assertEqual(spoken, [])

    def test_only_unique_nonempty_final_turns_reason(self):
        calls = []
        s = VoiceSession(lambda text: calls.append(text) or 'answer', lambda *args: None)
        s.start()
        for event, text, index in [('Update','hello',0), ('EndOfTurn',' ',0),
            ('EndOfTurn','hello',0), ('EndOfTurn','hello',0), ('EndOfTurn','hello',1)]:
            s.event(event,text,index)
        s.pending.join(); s.close()
        self.assertEqual(calls, ['hello','hello'])

    def test_interrupt_during_llm_does_not_get_cleared(self):
        started, finish = threading.Event(), threading.Event()
        spoken = []
        def respond(text):
            started.set(); finish.wait(2); return 'answer'
        s = VoiceSession(respond, lambda *args: spoken.append(args))
        s.start(); s.event('EndOfTurn','hello',0)
        self.assertTrue(started.wait(1))
        s.event('StartOfTurn'); finish.set(); s.pending.join(); s.close()
        self.assertEqual(spoken, [])

    def test_interrupt_during_output(self):
        speaking, interrupted = threading.Event(), threading.Event()
        def speak(text, cancel):
            speaking.set()
            if cancel.wait(2): interrupted.set()
        s = VoiceSession(lambda _: 'answer', speak)
        s.start(); s.event('EndOfTurn','hello',0)
        self.assertTrue(speaking.wait(1)); s.event('StartOfTurn')
        self.assertTrue(interrupted.wait(1)); s.pending.join(); s.close()
