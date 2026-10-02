"""Authenticated 16 kHz PCM WebSocket, shared Receptionist controller."""
import asyncio
import logging
import time
from fastapi import WebSocketDisconnect
from .session import VoiceSession
from .providers import ElevenSpeech, flux_connection
from .pacing import PcmPacer
from backend.app.database import uid, Business

log=logging.getLogger('ava')


async def browser_session(ws,agent,business_id):
    await ws.accept()
    loop=asyncio.get_running_loop()
    output=asyncio.Queue(maxsize=100)
    stopped=asyncio.Event()
    call_id=None; session=None; failure=''

    def enqueue(item):
        if stopped.is_set(): return
        future=asyncio.run_coroutine_threadsafe(output.put(item),loop)
        try: future.result(timeout=2)
        except Exception:
            future.cancel(); loop.call_soon_threadsafe(stopped.set)

    def clear_audio():
        while not output.empty():
            try: output.get_nowait()
            except asyncio.QueueEmpty: break
        output.put_nowait({'type':'clear'})

    try:
        call_id=await asyncio.to_thread(agent.start,business_id,'browser')
        with agent.sessions() as db:
            settings=db.get(Business,business_id).settings
        tts=ElevenSpeech(settings.get('voice_id'))

        def speak(text,cancel,announce=True):
            if announce: enqueue({'type':'reply','text':text})
            stream=tts.stream(text); started=time.monotonic(); first=True
            read_started=started; max_provider_wait=0; pcm_bytes=0
            try:
                pending=b''
                pacer=PcmPacer()
                for chunk in stream:
                    max_provider_wait=max(max_provider_wait,time.monotonic()-read_started)
                    pcm_bytes+=len(chunk)
                    if cancel.is_set() or stopped.is_set(): break
                    pending+=chunk
                    while len(pending)>=640 and not cancel.is_set() and not stopped.is_set():
                        if first:
                            log.info('TTS_FIRST_AUDIO latency_ms=%d',(time.monotonic()-started)*1000); first=False
                        pacer.begin_frame(640)
                        enqueue(pending[:640]); pending=pending[640:]
                        # Pace PCM delivery to avoid seconds of uncancellable
                        # audio accumulating in the browser/network buffers.
                        # cancel.wait(pacer.remaining())
                    read_started=time.monotonic()
                if pending and not cancel.is_set(): enqueue(pending[:len(pending)//2*2])
            finally:
                stream.close()
                log.info('TTS_LATENCY elapsed_ms=%d max_provider_wait_ms=%d',
                    (time.monotonic()-started)*1000,max_provider_wait*1000)

        session=VoiceSession(lambda text: agent.respond(business_id,call_id,text,uid()),speak,
            lambda text,interrupted: agent.delivered(business_id,call_id,interrupted),
            speak_greeting=lambda text,cancel: speak(text,cancel,announce=False))
        def event(kind,text,index):
            session.event(kind,text,index)
            if kind=='StartOfTurn': loop.call_soon_threadsafe(clear_audio)
            elif kind=='EndOfTurn' and text.strip(): loop.call_soon_threadsafe(lambda: output.put_nowait({'type':'transcript','text':text}))

        context=flux_connection(event,lambda: loop.call_soon_threadsafe(stopped.set))
        connection=await asyncio.to_thread(context.__enter__)
        await ws.send_json({'type':'ready','call_id':call_id,'greeting':settings['greeting']})
        # Ready already displays the greeting. Speak it once after STT connects
        # so caller speech can interrupt it, without duplicating the UI message.
        session.start(greeting=settings['greeting'])

        async def receive():
            while not stopped.is_set():
                packet=await asyncio.wait_for(ws.receive_bytes(),timeout=60)
                if not packet or len(packet)>16000 or len(packet)%2: raise ValueError('Invalid PCM packet.')
                await asyncio.to_thread(connection.send_media,packet)

        async def send():
            while not stopped.is_set():
                item=await output.get()
                if isinstance(item,bytes): await ws.send_bytes(item)
                else: await ws.send_json(item)

        tasks=[asyncio.create_task(receive()),asyncio.create_task(send()),asyncio.create_task(stopped.wait())]
        try:
            done,_=await asyncio.wait(tasks,timeout=1800,return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception(): raise task.exception()
        finally:
            stopped.set()
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            await asyncio.to_thread(context.__exit__,None,None,None)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        failure=type(exc).__name__
        try: await ws.send_json({'type':'error','text':'Voice connection failed. Please retry or use the text demo.'})
        except Exception: pass
    finally:
        stopped.set()
        if session: await asyncio.to_thread(session.close)
        if call_id:
            try: await asyncio.to_thread(agent.end,business_id,call_id,failure)
            except Exception: pass
        try: await ws.close()
        except Exception: pass
