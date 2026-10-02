"""Opt-in JSON diagnostics. No headers, credentials or raw caller transcripts."""
import json
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

context = ContextVar('vapi_trace_context', default={})
logger = logging.getLogger('ava.vapi.trace')


def scrub(value, key=''):
    lowered = key.lower()
    if any(word in lowered for word in ('authorization', 'credential', 'secret', 'password', 'api_key', 'access_token', 'webhook_token')):
        return '[redacted]'
    if lowered in ('caller_name', 'caller_email', 'email', 'content', 'transcript', 'originaltranscript'):
        return '[redacted]'
    if 'phone' in lowered:
        return '[redacted]'
    if isinstance(value, dict):
        return {str(k): scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


def emit(stage, **fields):
    if not context.get() or os.getenv('VAPI_TRACE_ENABLED', 'false').lower() != 'true':
        return
    logger.info(json.dumps(scrub({'timestamp': datetime.now(timezone.utc).isoformat(),
        **context.get(), 'stage': stage, **fields}), default=str, separators=(',', ':')))


@contextmanager
def scope(**fields):
    token = context.set({**context.get(), **fields})
    try:
        yield
    finally:
        context.reset(token)


def configure():
    if os.getenv('VAPI_TRACE_ENABLED', 'false').lower() != 'true':
        return
    path = Path(os.getenv('VAPI_TRACE_FILE', 'logs/vapi-debug.jsonl')).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not any(isinstance(h, RotatingFileHandler) and h.baseFilename == str(path) for h in logger.handlers):
        handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
