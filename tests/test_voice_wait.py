import threading

from backend.app.voice.session import VoiceSession
from backend.app.lookup import appointment_lookup


def test_slow_lookup_speaks_once_before_answer_without_extra_delivery():
    acknowledged = threading.Event()
    spoken, delivered, inputs = [], [], []

    def speak(text, cancel):
        spoken.append(text)
        acknowledged.set()

    def respond(text):
        inputs.append(text)
        with appointment_lookup():
            assert acknowledged.wait(2)
        return 'The clinic opens at nine.'

    session = VoiceSession(respond, speak, lambda *args: delivered.append(args), wait_seconds=.01)
    session.start()
    session.event('EndOfTurn', 'What are your hours?', 0)
    session.pending.join()
    session.close()
    assert spoken == ['Let me check that.', 'The clinic opens at nine.']
    assert inputs == ['What are your hours?']
    assert delivered == [('The clinic opens at nine.', False)]


def test_fast_response_has_no_filler():
    spoken = []
    session = VoiceSession(lambda _: 'Hello!', lambda text, cancel: spoken.append(text))
    session.start()
    session.event('EndOfTurn', 'Hi', 0)
    session.pending.join()
    session.close()
    assert spoken == ['Hello!']


def test_interruption_cancels_filler_and_suppresses_final_audio():
    speaking, cancelled = threading.Event(), threading.Event()
    spoken, delivered = [], []

    def speak(text, cancel):
        spoken.append(text)
        speaking.set()
        if cancel.wait(2):
            cancelled.set()

    def respond(text):
        with appointment_lookup():
            assert cancelled.wait(2)
        return 'The result'

    session = VoiceSession(respond, speak, lambda *args: delivered.append(args), wait_seconds=.01)
    session.start()
    session.event('EndOfTurn', 'Check something', 0)
    assert speaking.wait(2)
    session.event('StartOfTurn')
    session.pending.join()
    session.close()
    assert spoken == ['Let me check that.']
    assert delivered == [('The result', True)]


def test_final_speech_waits_until_acknowledgement_finishes():
    speaking, finish = threading.Event(), threading.Event()
    spoken = []

    def speak(text, cancel):
        spoken.append(text)
        if text == 'Let me check that.':
            speaking.set()
            assert finish.wait(2)

    def respond(text):
        with appointment_lookup():
            assert speaking.wait(2)
        return 'Ready'

    session = VoiceSession(respond, speak, wait_seconds=.01)
    session.start()
    session.event('EndOfTurn', 'Question', 0)
    assert speaking.wait(2)
    assert spoken == ['Let me check that.']
    finish.set()
    session.pending.join()
    session.close()
    assert spoken == ['Let me check that.', 'Ready']


def test_optional_acknowledgement_failure_does_not_lose_answer():
    attempted = threading.Event()
    spoken = []

    def speak(text, cancel):
        if text == 'Let me check that.':
            attempted.set()
            raise RuntimeError('TTS failed')
        spoken.append(text)

    def respond(text):
        with appointment_lookup():
            assert attempted.wait(2)
        return 'Ready'

    session = VoiceSession(respond, speak, wait_seconds=.01)
    session.start()
    session.event('EndOfTurn', 'Question', 0)
    session.pending.join()
    session.close()
    assert spoken == ['Ready']
    assert not session.failed


def test_slow_llm_has_no_wait_acknowledgement():
    import time
    spoken = []
    def respond(text):
        time.sleep(.05)
        return 'Hello!'
    session = VoiceSession(respond, lambda text, cancel: spoken.append(text), wait_seconds=.005)
    session.start()
    session.event('EndOfTurn', 'Hi', 0)
    session.pending.join()
    session.close()
    assert spoken == ['Hello!']


def test_fast_lookup_followed_by_slow_generation_has_no_acknowledgement():
    import time
    spoken = []
    def respond(text):
        with appointment_lookup():
            pass
        time.sleep(.05)
        return 'Ready'
    session = VoiceSession(respond, lambda text, cancel: spoken.append(text), wait_seconds=.005)
    session.start()
    session.event('EndOfTurn', 'Check my appointment', 0)
    session.pending.join()
    session.close()
    assert spoken == ['Ready']
