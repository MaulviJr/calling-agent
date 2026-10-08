"""Turn a Vapi end-of-call-report into plain values Ava can store. No database here."""
import re
from datetime import datetime, timezone

MAX_TURNS = 500
MAX_TEXT = 4000
CARD_NUMBER = re.compile(r'(?<!\d)(?:\d[ -]?){13,19}(?!\d)')   # same rule used for saved messages


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def number(value):
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
    return value if ok else None


def clean(text):
    return CARD_NUMBER.sub('[number omitted]', text.strip())[:MAX_TEXT]


def extract_report(message):
    call = message.get('call') if isinstance(message.get('call'), dict) else {}
    customer = call.get('customer') or message.get('customer') or {}
    phone = customer.get('number') if isinstance(customer, dict) else ''
    started = parse_time(message.get('startedAt') or call.get('startedAt'))
    ended = parse_time(message.get('endedAt') or call.get('endedAt'))

    duration = number(message.get('durationSeconds'))
    if duration is None and number(message.get('durationMs')) is not None:
        duration = message['durationMs'] / 1000
    if duration is None and number(message.get('durationMinutes')) is not None:
        duration = message['durationMinutes'] * 60
    if duration is None and started and ended:
        duration = (ended - started).total_seconds()

    analysis = message.get('analysis') if isinstance(message.get('analysis'), dict) else {}
    summary = analysis.get('summary') or message.get('summary') or ''
    artifact = message.get('artifact') if isinstance(message.get('artifact'), dict) else {}
    raw = artifact.get('messages') or message.get('messages') or []

    turns = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        role = {'user': 'user', 'assistant': 'assistant', 'bot': 'assistant'}.get(item.get('role'))
        text = item.get('message', item.get('content'))
        if role is None or not isinstance(text, str) or not text.strip():
            continue                       # skips system prompts and tool messages
        turns.append({'role': role, 'text': clean(text), 'seconds': number(item.get('secondsFromStart'))})
        if len(turns) >= MAX_TURNS:
            break

    reason = message.get('endedReason')
    return {
        'phone': phone[:50] if isinstance(phone, str) else '',
        'started_at': started, 'ended_at': ended,
        'duration_seconds': int(round(duration)) if duration is not None else None,
        'summary': clean(summary) if isinstance(summary, str) else '',
        'turns': turns,
        'ended_reason': reason[:100] if isinstance(reason, str) else '',
        'cost': number(message.get('cost')),
    }