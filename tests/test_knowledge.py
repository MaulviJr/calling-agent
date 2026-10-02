"""Real local routing/validation, synthetic generation, isolated business data."""
import logging

import pytest
from pydantic import ValidationError

from backend.app.agent import AppointmentState, Receptionist
from backend.app.business import BusinessSettings, StaffMember
from backend.app.database import Business, Call
from backend.app.knowledge import resolve_knowledge


STAFF = [
    {'id': 'hadi', 'name': 'Abdul Hadi', 'role': 'physiotherapist', 'qualifications': ['PhD']},
    {'id': 'hamza', 'name': 'Hamza', 'role': 'physiotherapist'},
    {'id': 'ali', 'name': 'Ali', 'role': 'physiotherapist'},
]
FAQS = [
    {'question': 'What is the name of phyiostherapists available', 'answer': 'The physiotherapists are Abdul Hadi, Hamza, Ali'},
    {'question': 'The Phd doctors?', 'answer': 'The phd doctors are Abdul Hadi'},
    {'question': 'Do you have parking?', 'answer': 'Parking is available behind the clinic.'},
]


class NoPlanner:
    def decide(self, *args):
        raise AssertionError('Knowledge must not invoke the planner')


class Generator:
    def __init__(self, answer=None, fail=False):
        self.contexts = []
        self.answer = answer
        self.fail = fail

    def generate(self, text, history, state, context):
        self.contexts.append(context)
        if self.fail:
            raise TimeoutError('synthetic')
        return self.answer or context.baseline


def setup_agent(system, generator=None, staff=None, transport='text'):
    sessions, bid, _, scheduler = system
    with sessions.begin() as db:
        business = db.get(Business, bid)
        business.settings = {**business.settings, 'staff': STAFF if staff is None else staff, 'knowledge': FAQS}
    generator = generator or Generator()
    agent = Receptionist(sessions, scheduler, NoPlanner(), generator)
    return agent, agent.start(bid, transport), generator


@pytest.mark.parametrize('question,concept,fragment', [
    ('Who are the physiotherapists?', 'role:physiotherapist', 'Abdul Hadi, Hamza, and Ali'),
    ('Which therapists work here?', 'role:physiotherapist', 'Abdul Hadi, Hamza, and Ali'),
    ('Who works here?', 'staff', 'Abdul Hadi, Hamza, and Ali'),
    ('Who are the doctors?', 'staff', 'If you mean our physiotherapists'),
    ('Can you tell me who are the doctors here?', 'staff', 'If you mean our physiotherapists'),
    ('Do you have medical doctors?', 'role:physician', 'do not have configured information about medical doctors'),
    ('Which staff member has a PhD?', 'qualification:PhD', 'Abdul Hadi has a PhD'),
    ('Tell me about physiotherapy.', 'services', 'Physiotherapy'),
    ('Do you have parking?', 'faq', 'Parking is available behind the clinic'),
])
def test_local_knowledge_routes_and_budget(system, caplog, question, concept, fragment):
    caplog.set_level(logging.INFO, logger='ava')
    agent, cid, generator = setup_agent(system)
    reply = agent.respond(system[1], cid, question, '1')
    assert fragment in reply
    assert len(generator.contexts) == 1
    assert f'concept={concept}' in caplog.text
    for field in ('route=knowledge', 'source_ids=', 'interpretation=', 'fallback_reason=', 'llm_calls=1',
                  'retrieval_ms=', 'response_generation_ms=', 'total_turn_ms='):
        assert field in caplog.text
    assert not system[2].events
    if concept == 'qualification:PhD':
        assert 'Hamza' not in reply and 'Ali' not in reply


def test_repair_records_failure_and_reloads_trusted_facts(system):
    agent, cid, generator = setup_agent(system, Generator(fail=True))
    first = agent.respond(system[1], cid, 'Who are the doctors?', '1')
    assert first.startswith('If you mean our physiotherapists')
    with system[0]() as db:
        state = db.get(Call, cid).state['knowledge_dialogue']
        assert state['used_fallback'] and state['failure'] == 'generation'
        assert state['fallback_reason'] == 'provider_or_schema_error'
        assert state['source_ids'] == ['staff:hadi', 'staff:hamza', 'staff:ali']
    with system[0].begin() as db:
        business = db.get(Business, system[1])
        business.settings = {**business.settings, 'staff': STAFF[:2]}
    generator.fail = False
    second = agent.respond(system[1], cid, "So you don't know about the doctors.", '2')
    assert second == 'If you mean our physiotherapists, they are Abdul Hadi and Hamza.'
    assert len(generator.contexts) == 2
    assert 'trouble explaining' not in first


def test_referential_repair_and_expiry(system):
    agent, cid, generator = setup_agent(system)
    agent.respond(system[1], cid, 'Who are the doctors?', '1')
    assert 'If you mean' in agent.respond(system[1], cid, 'Who are they?', '2')
    assert 'Parking' in agent.respond(system[1], cid, 'Do you have parking?', '3')
    assert 'Parking' in agent.respond(system[1], cid, 'Say that again.', '4')
    agent.respond(system[1], cid, 'Hi', '5')
    agent.respond(system[1], cid, 'How are you?', '6')
    assert 'Parking' not in agent.respond(system[1], cid, 'Say that again.', '7')


def test_interrupted_knowledge_metadata_does_not_change_consent(system):
    agent, cid, _ = setup_agent(system, transport='browser')
    agent.respond(system[1], cid, 'Who are the doctors?', '1')
    agent.delivered(system[1], cid, True)
    with system[0]() as db:
        state = db.get(Call, cid).state
        assert state['knowledge_dialogue']['interrupted']
        assert state['pending'] is None
    assert 'If you mean' in agent.respond(system[1], cid, 'Say that again.', '2')


@pytest.mark.parametrize('draft', [
    'Our doctors are Abdul Hadi, Hamza, and Ali.',
    'Our physiotherapists are Abdul Hadi, Hamza, Ali, and Sam.',
    'Our physiotherapists are Abdul Hadi and Hamza.',
    'Our qualified physiotherapists are Abdul Hadi, Hamza, and Ali.',
    'Our physiotherapists are not Abdul Hadi, Hamza, and Ali.',
    'Our physiotherapists are Abdul Hadi, Hamza, and Ali. They all hold a PhD.',
    'Our physiotherapists are Abdul Hadi, Hamza, and Ali. Visits cost 500.',
    'Our physiotherapists are Abdul Hadi, Hamza, and Ali. They are available today.',
    'Our physiotherapists are Abdul Hadi, Hamza, and Ali. You are booked.',
])
def test_fabricated_claims_use_safe_fallback(system, draft):
    agent, cid, generator = setup_agent(system, Generator(draft))
    assert agent.respond(system[1], cid, 'Who are the physiotherapists?', '1') == 'Our physiotherapists are Abdul Hadi, Hamza, and Ali.'
    with system[0]() as db:
        assert db.get(Call, cid).state['knowledge_dialogue']['used_fallback']
    assert len(generator.contexts) == 1


@pytest.mark.parametrize('question,draft', [
    ('Who are the physiotherapists?', 'Hamza, Ali, and Abdul Hadi are our physiotherapists.'),
    ('Who are the physiotherapists?', 'Our physiotherapists include Abdul Hadi, Hamza and Ali.'),
    ('Who are the doctors?', 'If you mean our physiotherapists, they are Ali, Hamza and Abdul Hadi.'),
    ('Which staff member has a PhD?', 'Abdul Hadi holds a PhD.'),
])
def test_natural_supported_paraphrases_are_accepted(system, question, draft):
    agent, cid, _ = setup_agent(system, Generator(draft))
    assert agent.respond(system[1], cid, question, '1') == draft
    with system[0]() as db:
        assert not db.get(Call, cid).state['knowledge_dialogue']['used_fallback']


def test_related_interpretation_cannot_drop_qualifier(system):
    agent, cid, _ = setup_agent(system, Generator('Our physiotherapists are Abdul Hadi, Hamza, and Ali.'))
    assert agent.respond(system[1], cid, 'Who are the doctors?', '1').startswith('If you mean')


def test_typed_roles_and_qualifications_are_not_inferred_from_legacy(system):
    agent, cid, _ = setup_agent(system, staff=[{**STAFF[0], 'qualifications': []}])
    assert 'do not have configured information' in agent.respond(system[1], cid, 'Who has a PhD?', '1')


def test_legacy_typo_competing_faq_and_no_automatic_migration():
    settings = BusinessSettings(knowledge=FAQS)
    assert settings.staff == []
    assert resolve_knowledge('Who are the physiotherapists?', settings).faq_index == 0
    assert resolve_knowledge('Who has a PhD?', settings).faq_index == 1
    assert resolve_knowledge('Who are the doctors?', settings).interpretation == 'ambiguous'
    assert resolve_knowledge('Do you have medical doctors?', settings).missing
    original = resolve_knowledge('Do you have parking?', settings).source_ids
    settings.knowledge.reverse()
    assert resolve_knowledge('Do you have parking?', settings).source_ids == original


def test_physician_only_when_configured_and_inactive_excluded(system):
    agent, cid, _ = setup_agent(system, staff=STAFF + [
        {'id': 'physician', 'name': 'Jane', 'role': 'physician'},
        {'id': 'inactive', 'name': 'Inactive Person', 'role': 'physician', 'active': False},
    ])
    assert agent.respond(system[1], cid, 'Who are the doctors?', '1') == 'Our physician is Jane.'


def test_schema_compatibility_and_unique_ids():
    assert AppointmentState.model_validate({}).knowledge_dialogue.concept == ''
    with pytest.raises(ValidationError):
        BusinessSettings(staff=[STAFF[0], STAFF[0]])
    assert StaffMember(**{**STAFF[0], 'qualifications': [' PhD ', '', 'PhD']}).qualifications == ['PhD']


def test_business_topics_precede_competing_faq(system):
    agent, cid, _ = setup_agent(system)
    with system[0].begin() as db:
        business = db.get(Business, system[1])
        business.settings = {**business.settings, 'location': 'North Road', 'knowledge': [
            {'question': 'What is your address?', 'answer': 'Wrong old address.'}]}
    assert agent.respond(system[1], cid, 'What is your address?', '1') == 'North Road'


def test_unknown_price_keeps_existing_fallback(system):
    agent, cid, _ = setup_agent(system)
    assert 'do not have approved' in agent.respond(system[1], cid, 'What does it cost?', '1')


def test_missing_or_ambiguous_retrieval_never_claims_absence(system):
    agent, cid, _ = setup_agent(system, staff=[{**STAFF[0], 'active': False}])
    reply = agent.respond(system[1], cid, 'Who are the physiotherapists?', '1')
    assert 'do not have configured information' in reply
    assert 'no physiotherapists' not in reply


def test_role_filter_is_preserved_in_qualification_question(system):
    agent, cid, _ = setup_agent(system, staff=STAFF + [
        {'id': 'nurse', 'name': 'Jane', 'role': 'nurse', 'qualifications': ['PhD']},
    ])
    assert agent.respond(system[1], cid, 'Which physiotherapists have a PhD?', '1') == 'Abdul Hadi has a PhD.'


def test_vague_repair_uses_recent_topic(system):
    agent, cid, _ = setup_agent(system)
    agent.respond(system[1], cid, 'Who are the doctors?', '1')
    assert 'If you mean' in agent.respond(system[1], cid, "So you don't know?", '2')


def test_missing_topic_state_distinguishes_retrieval_failure(system):
    agent, cid, _ = setup_agent(system)
    agent.respond(system[1], cid, 'Do you have medical doctors?', '1')
    with system[0]() as db:
        state = db.get(Call, cid).state['knowledge_dialogue']
        assert state['failure'] == 'retrieval' and not state['used_fallback']


def test_tenant_staff_isolation(system):
    agent, cid, _ = setup_agent(system)
    with system[0].begin() as db:
        other = Business(settings=BusinessSettings(staff=[
            StaffMember(id='other', name='Other Person', role='physician')]).model_dump(mode='json'))
        db.add(other)
        db.flush()
        other_id = other.id
    other_call = agent.start(other_id)
    assert 'Other Person' not in agent.respond(system[1], cid, 'Who works here?', '1')
    reply = agent.respond(other_id, other_call, 'Who works here?', '1')
    assert 'Other Person' in reply and 'Abdul Hadi' not in reply


def test_settings_api_round_trip_and_legacy_loading(system):
    from fastapi.testclient import TestClient
    from backend.app.api import create_app, passwords
    from backend.app.database import Admin
    with system[0].begin() as db:
        business = db.get(Business, system[1])
        old = dict(business.settings)
        old.pop('staff', None)
        business.settings = old
        db.add(Admin(business_id=system[1], email='knowledge@example.test', password_hash=passwords.hash('test-only-password')))
    client = TestClient(create_app(system[0], system[2]))
    headers = {'origin': 'http://localhost:8000'}
    assert client.post('/api/login', headers=headers, json={'email': 'knowledge@example.test', 'password': 'test-only-password'}).status_code == 200
    settings = client.get('/api/settings').json()
    assert BusinessSettings.model_validate(settings).staff == []
    settings.update(staff=STAFF, knowledge=FAQS)
    saved = client.put('/api/settings', headers=headers, json=settings)
    assert saved.status_code == 200
    restored = client.get('/api/settings').json()
    assert restored['staff'][0]['qualifications'] == ['PhD']
    assert restored['knowledge'] == FAQS


def test_planner_resolved_knowledge_does_not_add_generation_call(system, caplog):
    from backend.app.agent import Decision
    class Planner:
        calls = 0
        def decide(self, *args):
            self.calls += 1
            return Decision(action='faq', business_topic='services')
    agent, cid, generator = setup_agent(system)
    agent.llm = Planner()
    caplog.set_level(logging.INFO, logger='ava')
    assert 'Physiotherapy' in agent.respond(system[1], cid, 'Tell me about appointments available.', '1')
    assert agent.llm.calls == 1 and not generator.contexts
    assert 'route=knowledge llm_calls=1' in caplog.text
