"""Application integration/grounding tests; model semantics have a separate live replay.

Controlled outputs test the complete failed conversation and hostile proposals.
No output is inferred from exact-phrase rules in application code.
"""
import json
import logging

import pytest
from pydantic import ValidationError

from backend.app.agent import AppointmentState, Decision, Receptionist
from backend.app.business import BusinessSettings, StaffMember
from backend.app.conversation import GeminiResponseGenerator, ResponseDraft, ResponseRejected
from backend.app.database import Business, Call, Message, Appointment
from backend.app.knowledge import faq_id
from backend.app.semantic import (DiscourseState, DiscourseUpdate, SemanticDraft,
    PACKET_LIMIT, build_packet, render_answer, validate_selection, clean_discourse)
from scripts.replay_semantic_conversation import (
    TURNS, OfflineGenerator, ForbiddenActions, replay_settings,
)
from sqlalchemy import select


def configure(system, settings=None):
    with system[0].begin() as db:
        business = db.get(Business, system[1])
        business.settings = (settings or replay_settings()).model_dump(mode='json')


def model(drafts):
    """Replace only the SDK request; keep schema, validation, state and controller."""
    generator = GeminiResponseGenerator()
    iterator = iter(drafts)
    generator.requests = []
    def structured(prompt, payload, schema):
        generator.requests.append((schema, payload))
        value = next(iterator)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(payload, schema)
        return schema.model_validate(value)
    generator._structured = structured
    return generator


def grounded(mode, ids=(), entities=(), topic='', focus=None, role=None, qualification=None):
    kind = ('action' if mode == 'action' else 'conversation' if mode in
            ('greeting','wellbeing','acknowledgement','identity','hearing','previous_turn','capabilities')
            else 'clarification' if mode == 'clarification' else 'knowledge')
    def output(payload, schema):
        assert schema is SemanticDraft
        value = SemanticDraft(turn_kind=kind, answer_mode=mode, selected_source_ids=list(ids),
            resolved_entity_ids=list(entities), role_filter=role, qualification=qualification,
            discourse_update=DiscourseUpdate(topic=topic, focused_entity_id=focus, recent_source_ids=list(ids)),
            response_text='placeholder')
        return value.model_copy(update={'response_text': render_answer(value, payload['approved_packet'])})
    return output


def make_agent(system, generator, transport='text'):
    agent = Receptionist(system[0], system[3], ForbiddenActions(), generator)
    return agent, agent.start(system[1], transport)


def test_entire_failed_conversation_one_call_per_turn(system, caplog):
    configure(system)
    generator = OfflineGenerator()
    agent, cid = make_agent(system, generator)
    caplog.set_level(logging.INFO, logger='ava')
    expected_modes = ['wellbeing','services_overview','staff_list','staff_list','staff_role',
                      'staff_role_correction','staff_list','missing_information','missing_information','missing_information']
    for index, ((question, before), mode) in enumerate(zip(TURNS, expected_modes), 1):
        caplog.clear()
        calls = generator.calls
        after = agent.respond(system[1], cid, question, str(index))
        assert generator.calls - calls == 1
        line = next(r.message for r in caplog.records if r.message.startswith('SEMANTIC_TURN'))
        for field in ('turn_kind=', 'selected_source_ids=', 'resolved_entity_id=',
                      'answer_mode=' + mode, 'llm_calls=1', 'fallback_reason=none'):
            assert field in line
        if index == 2:
            assert 'Physiotherapy' in after and '1500' not in after and 'receptionist' not in after
        if index == 3:
            assert 'Abdul Hadi' in after and 'Ayan Khan' in after and 'minutes' not in after
        if index in (5, 6):
            assert after == 'Abdul Hadi is listed as a physician.'
            with system[0]() as db:
                assert db.get(Call, cid).state['discourse']['focused_entity_id'] == 'hadi'
        if index >= 8:
            assert ('wheelchair accessibility','parking','without an appointment')[index - 8] in after
            assert ("take a message" in after) == (index == 8)
        assert not system[2].events
    with system[0]() as db:
        assert db.get(Call, cid).state['pending'] is None
        assert db.get(Business, system[1]).settings == replay_settings().model_dump(mode='json')
        assert db.scalar(select(Message)) is None
        assert db.scalar(select(Appointment)) is None


@pytest.mark.parametrize('text', [
    'Tell me what sort of care this clinic provides.',
    'What happens at your practice?',
    'Could you explain the treatments you offer?',
])
def test_paraphrases_reach_same_semantic_packet_without_local_classification(system, text):
    configure(system)
    generator = model([grounded('services_overview', ['service:pt','service:neck'], topic='services')])
    agent, cid = make_agent(system, generator)
    reply = agent.respond(system[1], cid, text, '1')
    assert reply.startswith('We offer Physiotherapy')
    schema, payload = generator.requests[0]
    assert schema is SemanticDraft
    assert payload['user_turn'] == text
    assert len(generator.requests) == 1
    assert 'staff:hadi' in payload['approved_packet']['sources']
    assert 'trusted_context' not in payload


@pytest.mark.parametrize('field,value,reason', [
    ('selected_source_ids', ['staff:other_tenant'], 'invalid_source_ids'),
    ('resolved_entity_ids', ['other_tenant'], 'invalid_entity_ids'),
    ('resolved_entity_ids', ['ahmed'], 'entity_source_mismatch'),
    ('selected_source_ids', ['staff:hadi','staff:hadi'], 'invalid_source_ids'),
    ('discourse_update', {'topic':'staff','focused_entity_id':'ahmed'}, 'invalid_discourse_entity'),
    ('discourse_update', {'topic':'staff','recent_source_ids':['staff:ahmed']}, 'invalid_discourse_sources'),
    ('role_filter', 'physiotherapist', 'invalid_staff_relation'),
    ('turn_kind', 'conversation', 'invalid_turn_kind'),
])
def test_invalid_ids_relations_and_memory_never_reach_state(system, caplog, field, value, reason):
    configure(system)
    draft = {'turn_kind':'knowledge','answer_mode':'staff_role', 'selected_source_ids':['staff:hadi'],
        'resolved_entity_ids':['hadi'], 'response_text':'Abdul Hadi is listed as a physician.',
        'discourse_update': {'topic':'staff','focused_entity_id':'hadi','recent_source_ids':['staff:hadi']}}
    draft[field] = value
    if field == 'resolved_entity_ids' and value == ['ahmed']:
        draft['discourse_update']['focused_entity_id'] = None
    generator = model([draft])
    agent, cid = make_agent(system, generator)
    caplog.set_level(logging.INFO, logger='ava')
    reply = agent.respond(system[1], cid, 'Is Abdul Hadi a physician?', '1')
    assert 'could not verify' in reply
    assert 'fallback_reason=' + reason in caplog.text
    assert len(generator.requests) == 1
    with system[0]() as db:
        state = db.get(Call,cid).state
        assert state['discourse']['focused_entity_id'] is None
        assert state['discourse']['recent_source_ids'] == []
        assert state['pending'] is None


@pytest.mark.parametrize('text', [
    'Abdul Hadi is a physiotherapist.',
    'Abdul Hadi is listed as a physician. Your appointment is booked.',
    'Abdul Hadi is listed as a physician with a PhD.',
    'Abdul Hadi is not a physician.',
    'Abdul Hadi is listed as a physician. Visits cost 50.',
])
def test_factual_text_rejection_renders_selected_relation_without_second_call(system, caplog, text):
    configure(system)
    draft = {'turn_kind':'knowledge','answer_mode':'staff_role', 'selected_source_ids':['staff:hadi'],
        'resolved_entity_ids':['hadi'], 'response_text':text,
        'discourse_update': {'topic':'staff','focused_entity_id':'hadi','recent_source_ids':['staff:hadi']}}
    generator = model([draft])
    agent, cid = make_agent(system, generator)
    caplog.set_level(logging.INFO, logger='ava')
    assert agent.respond(system[1],cid,'Is Abdul Hadi a physician?','1') == 'Abdul Hadi is listed as a physician.'
    assert len(generator.requests) == 1
    assert 'fallback_reason=unsupported_response_relationship' in caplog.text


def test_provider_or_schema_failure_does_not_poison_memory_or_retry(system, caplog):
    configure(system)
    generator = model([grounded('staff_role',['staff:hadi'],['hadi'],topic='staff',focus='hadi'),
                       TimeoutError('sensitive provider detail'), {'unexpected': 'value'}])
    agent,cid = make_agent(system,generator)
    agent.respond(system[1],cid,'Is Abdul Hadi a doctor?','1')
    caplog.set_level(logging.INFO,logger='ava')
    for index in (2,3):
        assert 'could not verify' in agent.respond(system[1],cid,'Could you explain further?',str(index))
    assert len(generator.requests) == 3
    assert 'sensitive provider detail' not in caplog.text
    with system[0]() as db:
        discourse = db.get(Call,cid).state['discourse']
        assert discourse['focused_entity_id'] == 'hadi' and discourse['age'] == 2


def test_knowledge_during_pending_action_preserves_confirmation_and_interruptions(system):
    configure(system)
    settings = replay_settings()
    settings.hours = BusinessSettings(hours=[{'weekday':i,'opens':'09:00','closes':'18:00'} for i in range(7)]).hours
    settings.minimum_notice_minutes = 0
    configure(system,settings)
    action = SemanticDraft(turn_kind='action',answer_mode='action',response_text='Proposed appointment.',
        action_proposal=Decision(action='book',service_id='pt',date_phrase='2026-10-02',time_phrase='10:00',
                                caller_name='Caller',phone='+15551234567'))
    generator=model([action,grounded('missing_information',topic='parking')])
    agent,cid=make_agent(system,generator,'browser')
    assert 'confirm' in agent.respond(system[1],cid,'I would like an appointment.','1')
    agent.delivered(system[1],cid,True)
    with system[0]() as db:
        pending_before=db.get(Call,cid).state['pending']
    assert 'parking' in agent.respond(system[1],cid,'Where could I leave my car?','2')
    agent.delivered(system[1],cid,False)
    with system[0]() as db:
        assert db.get(Call,cid).state['pending']==pending_before
    assert 'finish the confirmation' in agent.respond(system[1],cid,'yes','3')
    assert not system[2].events
    agent.delivered(system[1],cid,False)
    assert 'booked' in agent.respond(system[1],cid,'yes','4')
    assert len(system[2].events)==1
    assert len(generator.requests)==2


def test_semantic_action_has_at_most_two_calls_and_no_implicit_commit(system,caplog):
    # Default test clinic has a single service and open hours.
    proposal=SemanticDraft(turn_kind='action',answer_mode='action',response_text='Proposed action.',
        action_proposal=Decision(action='book',date_phrase='2026-10-02',time_phrase='10:00'))
    def phrase(payload,schema):
        assert schema is ResponseDraft
        return {'text':payload['trusted_context']['baseline']}
    generator=model([proposal,phrase])
    agent,cid=make_agent(system,generator)
    caplog.set_level(logging.INFO,logger='ava')
    assert 'full name' in agent.respond(system[1],cid,'Could you arrange a visit for me?','1')
    assert len(generator.requests)==2
    assert 'turn_kind=action' in caplog.text and 'llm_calls=2' in caplog.text
    assert not system[2].events


@pytest.mark.parametrize('proposal,reason', [
    (Decision(action='book',service_id='foreign'), 'invalid_action_service_id'),
    (Decision(action='book',selected_slot='invented'), 'invalid_action_slot_id'),
])
def test_action_ids_validated_before_controller_mutates_state(system,proposal,reason,caplog):
    generator=model([SemanticDraft(turn_kind='action',answer_mode='action',response_text='Proposed action.',action_proposal=proposal)])
    agent,cid=make_agent(system,generator)
    caplog.set_level(logging.INFO,logger='ava')
    assert 'could not verify' in agent.respond(system[1],cid,'Arrange an appointment.','1')
    assert reason in caplog.text and len(generator.requests)==1
    with system[0]() as db:
        state=db.get(Call,cid).state
        assert state['service_id']=='' and state['pending'] is None


def test_packet_is_bounded_excludes_inactive_and_keeps_current_focused_entity():
    settings=replay_settings()
    settings.knowledge=BusinessSettings(knowledge=[{'question':f'Question {i}', 'answer':'x'*2000} for i in range(100)]).knowledge
    settings.staff[1].active=False
    packet=build_packet(settings,'An unrelated query',[],DiscourseState(topic='staff',focused_entity_id='hadi',recent_source_ids=['staff:hadi']))
    assert len(json.dumps(packet,ensure_ascii=False))<=PACKET_LIMIT
    assert 'staff:hadi' in packet['sources'] and 'staff:ahmed' not in packet['sources']
    assert packet['coverage']['faq']['included']<100
    assert packet['discourse']['focused_entity_id']=='hadi'


def test_memory_expiry_and_authoritative_reload():
    settings=replay_settings()
    sources=build_packet(settings,'Hello',[],DiscourseState())['sources']
    memory=DiscourseState(topic='staff',focused_entity_id='hadi',recent_source_ids=['staff:hadi'])
    assert clean_discourse(memory.model_copy(update={'age':7}),sources)==DiscourseState()
    del sources['staff:hadi']
    assert clean_discourse(memory,sources).focused_entity_id is None
    assert clean_discourse(memory,sources).recent_source_ids==[]


def test_ambiguous_similar_names_cannot_establish_individual_relation():
    settings=replay_settings()
    settings.staff.append(StaffMember(id='similar',name='Abdul Hadhi',role='physiotherapist'))
    packet=build_packet(settings,'Is Abdul Hadih a doctor?',[],DiscourseState())
    draft=SemanticDraft(turn_kind='knowledge',answer_mode='staff_role',response_text='Abdul Hadi is listed as a physician.',
        selected_source_ids=['staff:hadi'],resolved_entity_ids=['hadi'],discourse_update=DiscourseUpdate(topic='staff'))
    with pytest.raises(ResponseRejected,match='unresolved_staff_referent'):
        validate_selection(draft,packet)


def test_schema_cannot_update_business_facts():
    assert AppointmentState.model_validate({}).discourse==DiscourseState()
    with pytest.raises(ValidationError):
        DiscourseUpdate.model_validate({'topic':'staff','role':'physiotherapist'})


def test_interrupted_knowledge_updates_only_discourse_delivery(system):
    configure(system)
    generator=model([grounded('staff_role',['staff:hadi'],['hadi'],topic='staff',focus='hadi')])
    agent,cid=make_agent(system,generator,'browser')
    agent.respond(system[1],cid,'Is Abdul Hadi a physician?','1')
    agent.delivered(system[1],cid,True)
    with system[0]() as db:
        state=db.get(Call,cid).state
        assert state['discourse']['interrupted'] and state['pending'] is None


def test_semantic_duplicate_receipt_does_not_call_model(system):
    generator=model([grounded('wellbeing')])
    agent,cid=make_agent(system,generator)
    first=agent.respond(system[1],cid,'Hello, how is your day?','1')
    assert agent.respond(system[1],cid,'Hello, how is your day?','1')==first
    assert len(generator.requests)==1


def test_logistics_facts_selected_semantically_without_action_dispatch(system):
    settings=replay_settings()
    settings.knowledge=BusinessSettings(knowledge=[
        {'question':'Can visitors enter using a mobility aid?', 'answer':'The entrance has a wheelchair ramp.'},
        {'question':'Where can vehicles be left?', 'answer':'Use the visitor spaces behind the clinic.'},
        {'question':'Must a visit be arranged in advance?', 'answer':'An appointment is required before visiting.'},
    ]).knowledge
    configure(system,settings)
    ids=[faq_id(entry) for entry in settings.knowledge]
    outputs=[grounded('source_answer',[sid],topic=topic) for sid,topic in
             zip(ids,('accessibility','parking','walk_in'))]
    generator=model(outputs)
    agent,cid=make_agent(system,generator)
    questions=['Could my wheelchair get through the entrance?',
               'And somewhere for the car?', 'Can I turn up without arranging anything?']
    for index,(question,entry) in enumerate(zip(questions,settings.knowledge),1):
        assert agent.respond(system[1],cid,question,str(index))==entry.answer
        assert ids[index-1] in generator.requests[-1][1]['approved_packet']['sources']
    assert len(generator.requests)==3 and not system[2].events


def test_acknowledgement_preserves_focus_but_new_topic_clears_it(system):
    configure(system)
    generator=model([
        grounded('staff_role',['staff:hadi'],['hadi'],topic='staff',focus='hadi'),
        grounded('acknowledgement'),
        grounded('staff_role',['staff:hadi'],['hadi'],topic='staff',focus='hadi'),
        grounded('missing_information',topic='parking'),
    ])
    agent,cid=make_agent(system,generator)
    for index,question in enumerate(['Is Abdul Hadi a doctor?', 'Thanks.',
                                    'And what is his role?', 'Where is the parking?'],1):
        agent.respond(system[1],cid,question,str(index))
    assert generator.requests[2][1]['approved_packet']['discourse']['focused_entity_id']=='hadi'
    assert generator.requests[2][1]['approved_packet']['discourse']['age']==1
    with system[0]() as db:
        discourse=db.get(Call,cid).state['discourse']
        assert discourse['topic']=='parking' and discourse['focused_entity_id'] is None


def test_changed_business_role_is_reloaded_in_followup(system):
    configure(system)
    generator=model([
        grounded('staff_role',['staff:hadi'],['hadi'],topic='staff',focus='hadi'),
        grounded('staff_role',['staff:hadi'],['hadi'],topic='staff',focus='hadi'),
    ])
    agent,cid=make_agent(system,generator)
    agent.respond(system[1],cid,'Is Abdul Hadi a doctor?','1')
    updated=replay_settings()
    updated.staff[0].role='physiotherapist'
    configure(system,updated)
    assert agent.respond(system[1],cid,'What is his role again?','2')=='Abdul Hadi is listed as a physiotherapist.'


def test_incomplete_role_list_rejected_locally(system,caplog):
    configure(system)
    generator=model([grounded('staff_list',['staff:hadi'],['hadi'],topic='staff',role='physician')])
    agent,cid=make_agent(system,generator)
    caplog.set_level(logging.INFO,logger='ava')
    assert 'could not verify' in agent.respond(system[1],cid,'Which physicians work here?','1')
    assert 'fallback_reason=incomplete_staff_relation' in caplog.text


def test_fabricated_qualification_cannot_select_typed_staff(system,caplog):
    configure(system)
    generator=model([grounded('staff_qualification',['staff:hadi'],['hadi'],topic='staff',qualification='PhD')])
    agent,cid=make_agent(system,generator)
    caplog.set_level(logging.INFO,logger='ava')
    assert 'could not verify' in agent.respond(system[1],cid,'Does Abdul Hadi hold a PhD?','1')
    assert 'fallback_reason=incomplete_staff_relation' in caplog.text


def test_legacy_prose_cannot_override_typed_staff(system,caplog):
    settings=replay_settings()
    settings.knowledge=BusinessSettings(knowledge=[{'question':'Which physicians have doctorates?',
                                                  'answer':'All staff hold a PhD.'}]).knowledge
    configure(system,settings)
    sid=faq_id(settings.knowledge[0])
    generator=model([grounded('source_answer',[sid],topic='other')])
    agent,cid=make_agent(system,generator)
    caplog.set_level(logging.INFO,logger='ava')
    assert 'could not verify' in agent.respond(system[1],cid,'Which staff have doctorates?','1')
    assert 'fallback_reason=untyped_staff_relation' in caplog.text


def test_conversation_text_cannot_smuggle_business_claims(system,caplog):
    generator=model([SemanticDraft(turn_kind='conversation',answer_mode='wellbeing',
                                   response_text='Our clinic accepts walk-ins and all services are free.')])
    agent,cid=make_agent(system,generator)
    caplog.set_level(logging.INFO,logger='ava')
    reply=agent.respond(system[1],cid,'How is it going?','1')
    assert reply=="I'm ready to help, thanks for asking!"
    assert 'unsupported_response_relationship' in caplog.text


def test_social_acknowledgement_can_use_natural_bounded_variant(system,caplog):
    generator=model([SemanticDraft(turn_kind='conversation',answer_mode='acknowledgement',response_text='Okay.')])
    agent,cid=make_agent(system,generator)
    caplog.set_level(logging.INFO,logger='ava')
    assert agent.respond(system[1],cid,'All right then.','1')=='Okay.'
    assert 'fallback_reason=none' in caplog.text and len(generator.requests)==1


def test_correction_through_semantic_proposal_invalidates_pending_consent(system):
    initial=SemanticDraft(turn_kind='action',answer_mode='action',response_text='Proposed action.',
        action_proposal=Decision(action='book',date_phrase='2026-10-02',time_phrase='10:00',
                                caller_name='Caller',phone='+15551234567'))
    correction=SemanticDraft(turn_kind='action',answer_mode='action',response_text='Proposed correction.',
        action_proposal=Decision(action='book',time_phrase='11:00'))
    generator=model([initial,correction])
    agent,cid=make_agent(system,generator)
    agent.respond(system[1],cid,'Please arrange a visit.','1')
    with system[0]() as db:
        before=db.get(Call,cid).state['pending']
    agent.respond(system[1],cid,'Make the time eleven.','2')
    with system[0]() as db:
        state=db.get(Call,cid).state
        assert state['time_phrase']=='11:00'
        assert state['pending']['payload']['start_at']!=before['payload']['start_at']
    assert not system[2].events


def test_unmentioned_person_cannot_become_focus_from_a_list(system,caplog):
    configure(system)
    ids=['staff:hadi','staff:ahmed']
    generator=model([grounded('staff_list',ids,['hadi','ahmed'],topic='staff',focus='hadi',role='physician')])
    agent,cid=make_agent(system,generator)
    caplog.set_level(logging.INFO,logger='ava')
    assert 'could not verify' in agent.respond(system[1],cid,'Tell me about your physicians.','1')
    assert 'unresolved_discourse_referent' in caplog.text


def test_partial_catalog_cannot_be_presented_as_complete_list():
    packet=build_packet(replay_settings(),'Which physicians work here?',[],DiscourseState())
    packet['coverage']['staff']['total']+=1
    draft=SemanticDraft(turn_kind='knowledge',answer_mode='staff_list',role_filter='physician',
        selected_source_ids=['staff:hadi','staff:ahmed'],resolved_entity_ids=['hadi','ahmed'],
        response_text='Our physicians are Abdul Hadi and ahmed.',discourse_update=DiscourseUpdate(topic='staff'))
    with pytest.raises(ResponseRejected,match='incomplete_packet_for_list'):
        validate_selection(draft,packet)
