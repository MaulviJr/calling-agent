"""Exercise browser startup through PCM output without microphone input."""
import asyncio
from contextlib import contextmanager

from fastapi import WebSocketDisconnect

from legacy.app.voice import browser


def test_browser_sends_greeting_audio_once_without_input(system, monkeypatch):
    sessions, bid, _, _ = system
    spoken, ended = [], []

    class Agent:
        def __init__(self):
            self.sessions = sessions

        def start(self, *args):
            return 'test-call'

        def respond(self, *args):
            raise AssertionError('Greeting must not call the LLM/controller')

        def delivered(self, *args):
            raise AssertionError('Greeting must not update appointment consent')

        def end(self, *args):
            ended.append(args)

    class Speech:
        def __init__(self, *args):
            pass

        def stream(self, text):
            spoken.append(text)
            yield b'\x00\x00' * 320

    @contextmanager
    def flux(*args):
        yield object()

    monkeypatch.setattr(browser, 'ElevenSpeech', Speech)
    monkeypatch.setattr(browser, 'flux_connection', flux)

    async def run():
        class Socket:
            def __init__(self):
                self.messages = []
                self.audio = []
                self.received_audio = asyncio.Event()

            async def accept(self):
                pass

            async def send_json(self, message):
                self.messages.append(message)

            async def send_bytes(self, packet):
                self.audio.append(packet)
                self.received_audio.set()

            async def receive_bytes(self):
                # The caller remains silent until Ava has spoken, then hangs up.
                await self.received_audio.wait()
                raise WebSocketDisconnect()

            async def close(self):
                pass

        socket = Socket()
        await asyncio.wait_for(browser.browser_session(socket, Agent(), bid), timeout=5)
        assert [message['type'] for message in socket.messages] == ['ready']
        assert spoken == [socket.messages[0]['greeting']]
        assert socket.audio == [b'\x00\x00' * 320]
        assert len(ended) == 1

    asyncio.run(run())
