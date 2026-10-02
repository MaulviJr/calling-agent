"""Isolated Vapi application: run with uvicorn --factory on a separate port."""
import json
import logging
import os
import secrets
import time

from fastapi import FastAPI, HTTPException, Request
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .business import StrictModel
from .database import database
from .vapi_tools import TOOLS, execute_tool

log = logging.getLogger('ava.vapi')
MAX_BODY_BYTES = 262144


class WebhookSettings(StrictModel):
    token: str = Field(min_length=32, max_length=512, repr=False)
    assistant_business_map: dict[str, str] = Field(min_length=1, max_length=100)

    @classmethod
    def from_env(cls):
        try:
            mapping = json.loads(os.getenv('VAPI_ASSISTANT_BUSINESS_MAP', '{}'))
            settings = cls(token=os.getenv('VAPI_WEBHOOK_TOKEN', ''),
                           assistant_business_map=mapping)
            if any(not key.strip() or not value.strip()
                   for key, value in settings.assistant_business_map.items()):
                raise ValueError
            return settings
        except (ValueError, TypeError):
            raise RuntimeError('Set a VAPI_WEBHOOK_TOKEN of at least 32 characters and a valid VAPI_ASSISTANT_BUSINESS_MAP.') from None


class Identifier(StrictModel):
    value: str = Field(min_length=1, max_length=120, pattern=r'^[a-zA-Z0-9_-]+$')


def bad_request():
    return HTTPException(400, 'Invalid Vapi webhook.')


def call_context(message, settings):
    try:
        call = message['call']
        call_id = Identifier(value=call['id']).value
        assistant_id = Identifier(value=call['assistantId']).value
        # Metadata may contain the expanded assistant as well. Reject conflicts.
        assistant = message.get('assistant')
        if assistant is not None and assistant.get('id') != assistant_id:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise bad_request() from None
    business_id = settings.assistant_business_map.get(assistant_id)
    if business_id is None:
        raise HTTPException(403, 'Assistant is not authorized.')
    return call_id, business_id


def parse_tool_calls(message):
    calls = message.get('toolCallList')
    if not isinstance(calls, list) or not 1 <= len(calls) <= 8:
        raise bad_request()
    parsed, seen = [], set()
    for item in calls:
        try:
            tool_id = Identifier(value=item['id']).value
            if tool_id in seen:
                raise ValueError
            seen.add(tool_id)
            # Vapi documents both flattened and OpenAI-style function envelopes.
            if 'function' in item:
                if 'name' in item or 'parameters' in item:
                    raise ValueError
                name = item['function']['name']
                arguments = item['function'].get('arguments', {})
            else:
                name = item['name']
                arguments = item.get('parameters', {})
            if not isinstance(name, str) or len(name) > 100:
                raise ValueError
            parsed.append((tool_id, name, arguments))
        except (KeyError, TypeError, ValueError):
            raise bad_request() from None
    return parsed


def tool_results(sessions, business_id, call_id, calls, actions=None):
    results = []
    for tool_id, name, arguments in calls:
        started = time.monotonic()
        from .vapi_actions import ACTION_SCHEMAS
        safe_name = name if name in TOOLS or (actions and name in ACTION_SCHEMAS) else 'unknown'
        log.info('VAPI_TOOL_REQUESTED call_id=%s tool=%s', call_id, safe_name)
        try:
            if name not in TOOLS and not (actions and name in ACTION_SCHEMAS):
                result = {'success': False, 'status': 'rejected', 'code': 'unknown_tool'}
            else:
                if isinstance(arguments, str):
                    if len(arguments) > 4096:
                        raise ValueError
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict):
                    raise ValueError
                if name in TOOLS:
                    result = execute_tool(sessions, business_id, name, arguments)
                else:
                    result = actions.handle(business_id, call_id, tool_id, name, arguments)
        except (ValueError, ValidationError):
            # Pydantic traces can include inputs; never return/log them.
            result = {'success': False, 'status': 'rejected', 'code': 'invalid_arguments_or_settings'}
        except Exception:
            result = {'success': False, 'status': 'unavailable', 'code': 'information_unavailable'}
        success = result['success']
        log.info('%s call_id=%s tool=%s latency_ms=%d success=%s',
                 'VAPI_TOOL_COMPLETED' if success else 'VAPI_TOOL_FAILED',
                 call_id, safe_name, (time.monotonic() - started) * 1000, success)
        # Vapi requires a flat string, containing our structured JSON contract.
        results.append({'toolCallId': tool_id,
                        'result' if success else 'error': json.dumps(result, separators=(',', ':'))})
    return {'results': results}


def create_app(sessions, settings, actions=None):
    """No custom controller, Calendar, STT, LLM SDK, or TTS initialization."""
    app = FastAPI(title='Ava Vapi read-only tools', docs_url=None, redoc_url=None,
                  openapi_url=None)

    async def authenticated_message(request):
        authorization = request.headers.get('authorization', '')
        if not secrets.compare_digest(authorization.encode(), ('Bearer ' + settings.token).encode()):
            raise HTTPException(401, 'Webhook authentication required.')
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                raise HTTPException(413, 'Request too large.')
        try:
            payload = json.loads(body)
            message = payload['message']
            if not isinstance(message, dict):
                raise ValueError
            return message
        except (ValueError, KeyError, TypeError):
            raise bad_request() from None

    @app.get('/health')
    def health():
        return {'status': 'ok', 'mode': 'vapi-actions' if actions is not None else 'vapi-read-only'}

    @app.post('/api/vapi/tools')
    async def tools(request: Request):
        message = await authenticated_message(request)
        call_id, business_id = call_context(message, settings)
        if message.get('type') != 'tool-calls':
            raise bad_request()
        calls = parse_tool_calls(message)
        return await run_in_threadpool(tool_results, sessions, business_id, call_id, calls, actions)

    @app.post('/api/vapi/events')
    async def events(request: Request):
        message = await authenticated_message(request)
        call_id, business_id = call_context(message, settings)
        kind = message.get('type')
        if kind == 'status-update' and message.get('status') == 'in-progress':
            log.info('VAPI_CALL_STARTED call_id=%s', call_id)
        elif kind == 'status-update' and message.get('status') == 'ended':
            log.info('VAPI_CALL_ENDED call_id=%s', call_id)
        persisted = False
        if actions is not None:
            persisted = await run_in_threadpool(actions.event, business_id, call_id, message)
        return {'accepted': True, 'persisted': persisted}

    return app


def build_app():
    from dotenv import load_dotenv
    load_dotenv()
    settings = WebhookSettings.from_env()
    _, sessions = database()
    logging.basicConfig(level=logging.INFO)
    actions = None
    if os.getenv('VAPI_ACTIONS_ENABLED', 'false').lower() == 'true':
        from .vapi_actions import Actions
        business_id = os.getenv('VAPI_CALENDAR_BUSINESS_ID', '')
        allowed = set(settings.assistant_business_map.values())
        if not business_id or business_id not in allowed:
            raise RuntimeError('Set VAPI_CALENDAR_BUSINESS_ID to the business owning the configured Google Calendar.')
        def scheduler_for_business(bid):
            from .calendar import GoogleCalendar, CalendarUnavailable
            from .scheduling import Scheduling
            if bid != business_id:
                raise CalendarUnavailable('Calendar not configured for this business.')
            return Scheduling(sessions, GoogleCalendar())
        actions = Actions(sessions, scheduler_for_business)
    return create_app(sessions, settings, actions)
