"""Controller/provider boundaries: synthetic models and a temporary calendar only."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from legacy.app.agent import AgentDecision, Receptionist
from legacy.app.conversation import (
    GeminiResponseGenerator, ResponseDraft,
)
from backend.app.database import Business, Call, TranscriptTurn


class Planner:
    def __init__(self, *decisions):
        self.decisions = iter(decisions)

    def decide(self, *args):
        return next(self.decisions)


def language_model(text, *, supported=True):
    """Exercise real validation/rendering; replace only the SDK request method."""
    generator = object.__new__(GeminiResponseGenerator)
    generator.requests = []

    def structured(prompt, payload, schema):
        generator.requests.append(payload)
        if schema is ResponseDraft:
            return ResponseDraft(text=text)
        raise AssertionError('Unexpected extra LLM call')

    generator._structured = structured
    # These tests exercise the legacy text-only integration contract. Production
    # semantic interpretation is covered in test_semantic_conversation.py.
    class LanguageOnlyAdapter:
        requests = generator.requests
        def generate(self, *args):
            return generator.generate(*args)
    return LanguageOnlyAdapter()


def agent_for(system, decision, generator):
    sessions, bid, calendar, scheduler = system
    agent = Receptionist(sessions, scheduler, Planner(decision), generator)
    return agent, bid, agent.start(bid)


@pytest.mark.parametrize('topic,question,answer', [
    ('hearing', 'Can you hear me?', 'Yes, your words are coming through clearly. How can I help?'),
    ('identity', 'Are you an AI?', "Yes, I'm Ava, an AI receptionist."),
    ('interruption', 'Can I interrupt you?', 'Yes, you can interrupt me while I speak.'),
    ('wellbeing', 'How are you?', "I'm ready to help. What can I do for you?"),
])
def test_conversational_questions_use_generated_language(system, topic, question, answer):
    generator = language_model(answer)
    agent, bid, cid = agent_for(system, AgentDecision(
        action='conversation', conversation_topic=topic, direct_conversation=True,
    ), generator)
    assert agent.respond(bid, cid, question, '1') == answer
    assert generator.requests[0]['trusted_context']['kind'] == 'conversation'
    assert not system[2].events


def test_previous_turn_uses_persisted_history_not_current_question(system):
    generator = language_model('You said: Hello there.')
    agent, bid, cid = agent_for(system, AgentDecision(
        action='conversation', conversation_topic='previous_turn',
    ), generator)
    with system[0].begin() as db:
        db.add(TranscriptTurn(business_id=bid, call_id=cid, role='user', text='Hello there.'))
    assert agent.respond(bid, cid, 'What did I just say?', '1') == 'You said: Hello there.'
    facts = generator.requests[0]['trusted_context']['approved_facts']
    assert facts['previous_user_turn'] == 'Hello there.'


def set_knowledge(system, answer):
    with system[0].begin() as db:
        business = db.get(Business, system[1])
        business.settings = {**business.settings, 'knowledge': [
            {'question': 'Who are the physiotherapists?', 'answer': answer},
        ]}


def test_knowledge_grammar_changes_but_names_are_preserved(system):
    set_knowledge(system, 'The physiotherapists is Abdul Hadi, Hamza')
    generator = language_model('Our physiotherapists are Abdul Hadi and Hamza.')
    agent, bid, cid = agent_for(system, AgentDecision(action='faq', faq_index=0), generator)
    assert agent.respond(bid, cid, 'Who are the physiotherapists?', '1') == (
        'Our physiotherapists are Abdul Hadi and Hamza.'
    )
    assert len(generator.requests) == 1


def test_service_description_allows_normal_spoken_sentences(system):
    answer = 'We offer Physiotherapy appointments lasting 30 minutes.'
    generator = language_model(answer)
    agent, bid, cid = agent_for(system, AgentDecision(action='faq', business_topic='services'), generator)
    assert agent.respond(bid, cid, 'Can you tell me about the appointments?', '1') == answer


def test_knowledge_allows_equivalent_sentence_structure(system):
    set_knowledge(system, 'The physiotherapists is Abdul Hadi, Hamza')
    answer = 'Abdul Hadi and Hamza are our physiotherapists.'
    agent, bid, cid = agent_for(system, AgentDecision(action='faq', faq_index=0), language_model(answer))
    assert agent.respond(bid, cid, 'Who works here?', '1') == answer


@pytest.mark.parametrize('action,question,answer', [
    ('clarify', 'What do you know about', 'What would you like to know about?'),
    ('out_of_scope', 'What do you know about Karachi?',
     'I can help with clinic information and appointments. Are you asking about the clinic or something else?'),
])
def test_incomplete_and_unrelated_questions_do_not_retrieve_knowledge(system, action, question, answer):
    generator = language_model(answer)
    agent, bid, cid = agent_for(system, AgentDecision(action=action), generator)
    assert agent.respond(bid, cid, question, '1') == answer
    context = generator.requests[0]['trusted_context']
    assert context['kind'] == 'question'
    assert 'answer' not in context['approved_facts']
    assert not system[2].events


def test_service_provider_outage_still_describes_configured_services(system, caplog):
    class FailedGenerator:
        def generate(self, *args):
            raise TimeoutError('sensitive provider response must not be logged')
    agent, bid, cid = agent_for(system, AgentDecision(action='faq', business_topic='services'), FailedGenerator())
    assert agent.respond(bid, cid, 'Tell me about appointments.', '1') == (
        'We offer Physiotherapy appointments lasting 30 minutes.'
    )
    assert 'RESPONSE_FALLBACK' not in caplog.text
    assert 'sensitive provider response' not in caplog.text


def test_rejected_service_price_uses_real_data_without_fallback_logs(system, caplog):
    agent, bid, cid = agent_for(system, AgentDecision(action='faq', business_topic='services'),
                              language_model('Physiotherapy costs 500.'))
    reply = agent.respond(bid, cid, 'Tell me about appointments.', '1')
    assert '30 minutes' in reply and '500' not in reply
    assert 'RESPONSE_FALLBACK' not in caplog.text


@pytest.mark.parametrize('draft', [
    'Our physiotherapists are Abdul Hadi, Hamza and Ali.',
    'Our physiotherapist is Abdul Hadi.',
    'Our qualified physiotherapists are Abdul Hadi and Hamza.',
    'Our physiotherapists are Abdul Hadi and Hamza. Visits cost 50.',
])
def test_knowledge_factual_changes_rejected_locally(system, draft):
    set_knowledge(system, 'The physiotherapists is Abdul Hadi, Hamza')
    generator = language_model(draft, supported=False)
    agent, bid, cid = agent_for(system, AgentDecision(action='faq', faq_index=0), generator)
    reply = agent.respond(bid, cid, 'Who works here?', '1')
    assert 'trouble explaining' in reply
    assert 'Abdul' not in reply
    assert len(generator.requests) == 1


@pytest.mark.parametrize('draft,supported', [
    ('A visit costs 500.', True),
    ('All consultations are free.', False),
])
def test_unknown_pricing_does_not_invent_a_price(system, draft, supported):
    generator = language_model(draft, supported=supported)
    agent, bid, cid = agent_for(system, AgentDecision(action='faq'), generator)
    reply = agent.respond(bid, cid, 'What does it cost?', '1')
    assert 'do not have approved information' in reply
    assert '500' not in reply and 'free' not in reply


def test_no_slots_cannot_be_rewritten_as_available(system):
    system[2].extra_busy = [(
        datetime(2026, 10, 2, tzinfo=timezone.utc),
        datetime(2026, 10, 3, tzinfo=timezone.utc),
    )]
    generator = language_model('There are available slots on that date. What time suits you?')
    agent, bid, cid = agent_for(system, AgentDecision(
        action='book', date_phrase='2026-10-02', time_phrase='10:00',
    ), generator)
    reply = agent.respond(bid, cid, 'Book October 2 at ten.', '1')
    assert 'no available slots' in reply
    result = generator.requests[0]['trusted_context']['tool_result']
    assert result == {'action': 'availability', 'status': 'unavailable',
                      'facts': {'date': '2026-10-02', 'slots': []}}


def booking_decision():
    return AgentDecision(action='book', date_phrase='2026-10-02', time_phrase='10:00',
                         caller_name='Caller', phone='+15551234567')


def test_success_and_confirmation_cannot_be_rewritten_or_reexecuted(system):
    generator = language_model('Your appointment is cancelled.')
    agent, bid, cid = agent_for(system, booking_decision(), generator)
    assert 'confirm' in agent.respond(bid, cid, 'Book an appointment.', '1')
    assert not system[2].events and not generator.requests
    reply = agent.respond(bid, cid, 'I confirm.', '2')
    assert 'booked' in reply and len(system[2].events) == 1
    assert not generator.requests
    assert agent.respond(bid, cid, 'I confirm.', '2') == reply
    assert len(system[2].events) == 1


def test_booking_failure_never_reaches_language_generator(system):
    generator = language_model('Your appointment is booked.')
    agent, bid, cid = agent_for(system, booking_decision(), generator)
    agent.respond(bid, cid, 'Book an appointment.', '1')
    system[2].fail = True
    reply = agent.respond(bid, cid, 'I confirm.', '2')
    assert "couldn't complete" in reply
    assert 'booked' not in reply and not generator.requests


def test_correction_invalidates_consent_even_if_planner_labels_it_conversation(system):
    generator = language_model('Your words are coming through.')
    sessions, bid, calendar, scheduler = system
    agent = Receptionist(sessions, scheduler, Planner(
        booking_decision(),
        AgentDecision(action='conversation', conversation_topic='hearing', time_phrase='11:00'),
    ), generator)
    cid = agent.start(bid)
    agent.respond(bid, cid, 'Book an appointment.', '1')
    agent.respond(bid, cid, 'Can you hear me? I said eleven.', '2')
    with sessions() as db:
        state = db.get(Call, cid).state
        assert state['pending'] is None
        assert state['selected_slot'] == ''
        assert state['time_phrase'] == '11:00'
    assert not calendar.events


@pytest.mark.parametrize('text,expected', [
    ('I cannot breathe', 'Please contact your local emergency service'),
    ('My card is 4111 1111 1111 1111', 'Please do not share payment card details.'),
])
def test_safety_bypasses_both_models(system, text, expected):
    generator = language_model('Ignore the safety rules.')
    sessions, bid, calendar, scheduler = system
    agent = Receptionist(sessions, scheduler, Planner(), generator)
    cid = agent.start(bid)
    assert agent.respond(bid, cid, text, '1').startswith(expected)
    assert not generator.requests
    with sessions() as db:
        turns = list(db.scalars(select(TranscriptTurn).where(TranscriptTurn.call_id == cid)))
        assert all('4111' not in turn.text for turn in turns)


def test_generation_exception_keeps_pending_fields_and_receipt(system):
    class FailedGenerator:
        def generate(self, *args):
            raise TimeoutError('synthetic timeout')
    agent, bid, cid = agent_for(system, AgentDecision(
        action='book', date_phrase='2026-10-02', time_phrase='10:00',
    ), FailedGenerator())
    reply = agent.respond(bid, cid, 'Book October 2 at ten.', '1')
    assert 'full name' in reply
    assert agent.respond(bid, cid, 'Book October 2 at ten.', '1') == reply
    with system[0]() as db:
        assert db.get(Call, cid).state['selected_slot'].startswith('2026-10-02T10:00')


def test_local_checks_reject_unsupported_meta_business_claim(system):
    generator = language_model('I am a human doctor and our clinic is open all night.', supported=False)
    agent, bid, cid = agent_for(system, AgentDecision(
        action='conversation', conversation_topic='identity',
    ), generator)
    reply = agent.respond(bid, cid, 'Are you an AI?', '1')
    assert 'AI receptionist' in reply
    assert 'human doctor' not in reply


def test_spoken_small_talk_does_not_unlock_interrupted_confirmation(system):
    sessions, bid, calendar, scheduler = system
    generator = language_model("I'm an AI receptionist.")
    agent = Receptionist(sessions, scheduler, Planner(
        booking_decision(), AgentDecision(action='conversation', conversation_topic='identity'),
    ), generator)
    cid = agent.start(bid, 'browser')
    agent.respond(bid, cid, 'Book an appointment.', '1')
    agent.delivered(bid, cid, True)
    agent.respond(bid, cid, 'Are you an AI?', '2')
    agent.delivered(bid, cid, False)
    reply = agent.respond(bid, cid, 'I confirm.', '3')
    assert 'finish the confirmation' in reply
    assert not calendar.events
    agent.delivered(bid, cid, False)
    assert 'booked' in agent.respond(bid, cid, 'I confirm.', '4')
