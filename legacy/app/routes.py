"""Explicitly mounted legacy text-demo and custom browser voice routes."""
import threading
from fastapi import Depends, HTTPException, WebSocket
from pydantic import Field
from backend.app.business import StrictModel
from .agent import Receptionist, GeminiConversationPlanner

class TextTurn(StrictModel):
    text: str = Field(min_length=1,max_length=3000)
    key: str = Field(min_length=1,max_length=100)

def mount(app, sessions, scheduler, current, authenticate, origin, llm, voice_enabled):
    class LazyLLM:
        def __init__(self):
            self.instance = None
            self.lock = threading.Lock()
        def provider(self):
            with self.lock:
                if self.instance is None:
                    self.instance = GeminiConversationPlanner()
            return self.instance
        def decide(self,*args): return self.provider().decide(*args)
        def summarize(self,*args): return self.provider().summarize(*args)
    agent = Receptionist(sessions, scheduler, llm or LazyLLM())
    app.state.agent = agent
    @app.post('/api/demo/calls')
    def start_call(admin=Depends(current)): return {'id':agent.start(admin.business_id)}

    @app.post('/api/demo/calls/{call_id}/turn')
    def turn(call_id:str,data:TextTurn,admin=Depends(current)):
        return {'reply':agent.respond(admin.business_id,call_id,data.text,data.key)}

    @app.post('/api/demo/calls/{call_id}/end')
    def end_call(call_id:str,admin=Depends(current)):
        agent.end(admin.business_id,call_id); return {'ok':True}

    @app.websocket('/api/voice')
    async def voice(ws:WebSocket):
        if not voice_enabled:
            await ws.close(code=1008); return
        if ws.headers.get('origin')!=origin:
            await ws.close(code=1008); return
        try: admin=authenticate(ws.cookies.get('ava_session'))
        except HTTPException:
            await ws.close(code=1008); return
        from .voice.browser import browser_session
        await browser_session(ws,agent,admin.business_id)

