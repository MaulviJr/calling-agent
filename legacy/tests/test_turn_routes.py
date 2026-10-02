import logging

import pytest

from legacy.app.agent import Decision, Receptionist
from legacy.app.conversation import GeminiResponseGenerator, ResponseDraft
from backend.app.database import Business
from legacy.app.semantic import SemanticDraft, DiscourseUpdate, render_answer


class CountingPlanner:
    def __init__(self):
        self.calls = 0

    def decide(self, *args):
        self.calls += 1
        return Decision(action='book', date_phrase='2026-10-02', time_phrase='10:00')


@pytest.mark.parametrize('text,route,expected,planning', [
    ('How are you?', 'conversation', 1, 0),
    ('Tell me about services.', 'knowledge', 1, 0),
    ('Where can I park?', 'knowledge', 1, 0),
    ('Book October 2 at ten.', 'booking', 2, 0),
    ('I cannot breathe', 'fixed', 0, 0),
    ('Can you recommend treatment?', 'fixed', 0, 0),
    ('My card is 4111 1111 1111 1111', 'fixed', 0, 0),
])
def test_route_counts_actual_model_invocations(system, caplog, text, route, expected, planning):
    sessions, bid, calendar, scheduler = system
    with sessions.begin() as db:
        business = db.get(Business, bid)
        business.settings = {**business.settings, 'knowledge': [
            {'question': 'Where can I park?', 'answer': 'Use the north entrance.'}]}
    planner = CountingPlanner()
    generator = GeminiResponseGenerator()
    calls = []
    def structured(prompt, payload, schema):
        calls.append(schema)
        if schema is SemanticDraft:
            packet = payload['approved_packet']
            if route == 'booking':
                return SemanticDraft(turn_kind='action', answer_mode='action', response_text='Action proposal.',
                    action_proposal=Decision(action='book', date_phrase='2026-10-02', time_phrase='10:00'))
            elif route == 'conversation':
                draft = SemanticDraft(turn_kind='conversation', answer_mode='wellbeing', response_text='placeholder')
            elif text == 'Tell me about services.':
                ids = [sid for sid, s in packet['sources'].items() if s['kind'] == 'service']
                draft = SemanticDraft(turn_kind='knowledge', answer_mode='services_overview', selected_source_ids=ids,
                    discourse_update=DiscourseUpdate(topic='services', recent_source_ids=ids), response_text='placeholder')
            else:
                ids = [sid for sid, s in packet['sources'].items() if s['kind'] == 'faq']
                draft = SemanticDraft(turn_kind='knowledge', answer_mode='source_answer', selected_source_ids=ids,
                    discourse_update=DiscourseUpdate(topic='parking', recent_source_ids=ids), response_text='placeholder')
            return draft.model_copy(update={'response_text': render_answer(draft, packet)})
        assert schema is ResponseDraft
        return ResponseDraft(text=payload['trusted_context']['baseline'])
    generator._structured = structured
    agent = Receptionist(sessions, scheduler, planner, generator)
    cid = agent.start(bid)
    caplog.set_level(logging.INFO, logger='ava')
    reply = agent.respond(bid, cid, text, '1')
    assert reply
    assert planner.calls == planning
    assert planner.calls + len(calls) == expected
    assert f'route={route} llm_calls={expected}' in caplog.text
    assert not calendar.events
    caplog.clear()
    assert agent.respond(bid, cid, text, '1') == reply
    assert planner.calls + len(calls) == expected
    assert 'route=fixed llm_calls=0 cached=true' in caplog.text


def test_failed_generation_does_not_retry_or_review(system, caplog):
    sessions, bid, _, scheduler = system
    planner = CountingPlanner()
    generator = GeminiResponseGenerator()
    calls = []
    def fail(*args):
        calls.append(1)
        raise TimeoutError()
    generator._structured = fail
    agent = Receptionist(sessions, scheduler, planner, generator)
    cid = agent.start(bid)
    caplog.set_level(logging.INFO, logger='ava')
    assert agent.respond(bid, cid, 'Hi', '1')
    assert len(calls) == 1 and planner.calls == 0
    assert 'route=clarification llm_calls=1' in caplog.text
    assert 'fallback_reason=provider_or_schema_error' in caplog.text
