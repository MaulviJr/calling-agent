import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.business import BusinessSettings
from backend.app.database import Appointment, Business, Call, Message, Operation
from backend.app.vapi_actions import Actions
from backend.app.vapi_api import WebhookSettings, create_app
from backend.app.vapi_config import assistant_config

TOKEN = 'test-only-webhook-token-with-32-characters'
AUTH = {'Authorization': 'Bearer ' + TOKEN}


@pytest.fixture
def action_system(system):
    sessions, bid, calendar, scheduler = system
    def scheduler_for_business(business_id):
        from backend.app.calendar import CalendarUnavailable
        if business_id != bid:
            raise CalendarUnavailable('No calendar for this tenant.')
        return scheduler
    with sessions.begin() as db:
        other = Business(settings=BusinessSettings().model_dump(mode='json'))
        db.add(other); db.flush(); other_bid = other.id
    actions = Actions(sessions, scheduler_for_business)
    client = TestClient(create_app(sessions, WebhookSettings(token=TOKEN,
        assistant_business_map={'a': bid, 'b': other_bid}), actions))
    yield client, actions, sessions, bid, calendar, scheduler
    client.close()


def invoke(client, name, arguments=None, *, call='call-a', key=None, assistant='a'):
    response = client.post('/api/vapi/tools', headers=AUTH, json={'message': {
        'type': 'tool-calls', 'call': {'id': call, 'assistantId': assistant},
        'toolCallList': [{'id': key or str(time.time_ns()), 'name': name, 'parameters': arguments or {}}]}})
    assert response.status_code == 200
    item = response.json()['results'][0]
    return json.loads(item.get('result', item.get('error')))


def event(client, kind, stamp, *, call='call-a', assistant='a', **fields):
    response = client.post('/api/vapi/events', headers=AUTH, json={'message': {
        'type': kind, 'timestamp': stamp, 'call': {'id': call, 'assistantId': assistant}, **fields}})
    assert response.status_code == 200
    return response.json()


def pending_state(system, call='call-a'):
    _, actions, _, bid, *_ = system
    return actions.load(bid, call)[1]['pending']


def consent(system, preparation, call='call-a', turn=1):
    pending = pending_state(system, call)
    state = system[1].load(system[3], call)[1]
    stamp = max(pending['created_ms'], state.get('last_user_ms', 0)) + 100
    event(system[0], 'transcript', stamp, call=call,
          role='user', transcriptType='final', transcript='Yes, please.')


def checked_booking(system, *, call='call-a', start=None, name='Caller', key=None):
    client = system[0]
    slots = invoke(client, 'check_availability', {'service_id': 'pt', 'date': '2026-10-02'}, call=call)
    assert slots['success'] and not slots['data']['booked']
    payload = {'caller_name': name, 'caller_phone': '+15551234567', 'service_id': 'pt',
               'start_at': start or slots['data']['slots'][0]}
    result = invoke(client, 'create_appointment', payload, call=call, key=key)
    assert result['status'] == 'confirmation_required'
    return result, payload


def book(system, call='call-a'):
    preparation, _ = checked_booking(system, call=call)
    consent(system, preparation, call)
    result = invoke(system[0], 'confirm_action', {'action_token': preparation['data']['action_token']}, call=call)
    assert result['status'] == 'completed'
    return result['data']


def test_booking_changes_selection_and_books_exactly_once(action_system):
    client, _, sessions, _, calendar, _ = action_system
    original, payload = checked_booking(action_system, key='prepare-1')
    assert not calendar.events
    slots = invoke(client, 'check_availability', {'service_id': 'pt', 'date': '2026-10-02'})['data']['slots']
    updated = invoke(client, 'create_appointment', {**payload, 'start_at': slots[1]}, key='prepare-2')
    assert updated['data']['action_token'] != original['data']['action_token']
    assert invoke(client, 'confirm_action', {'action_token': original['data']['action_token']})['code'] == 'action_expired'
    consent(action_system, updated)
    result = invoke(client, 'confirm_action', {'action_token': updated['data']['action_token']}, key='confirm-1')
    assert result['data']['start_at'] == slots[1]
    assert invoke(client, 'confirm_action', {'action_token': updated['data']['action_token']}, key='confirm-1') == result
    assert invoke(client, 'confirm_action', {'action_token': updated['data']['action_token']}, key='confirm-2') == result
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Appointment)) == 1
        row = db.scalar(select(Appointment))
        assert db.get(Call, row.call_id).transport == 'vapi'
    assert len(calendar.events) == 1


def test_no_model_boolean_or_early_confirmation_can_commit(action_system):
    client = action_system[0]
    preparation, _ = checked_booking(action_system)
    token = preparation['data']['action_token']
    assert invoke(client, 'confirm_action', {'action_token': token})['code'] == 'confirmation_not_verified'
    assert not invoke(client, 'confirm_action', {'action_token': token, 'confirmed': True})['success']
    assert not action_system[4].events


@pytest.mark.parametrize('utterance', ['No, actually 11 please', 'Yes but change the name', 'Maybe', 'Yes if it is free'])
def test_changed_conditional_or_ambiguous_agreement_invalidates_action(action_system, utterance):
    client = action_system[0]
    preparation, _ = checked_booking(action_system)
    pending = pending_state(action_system)
    stamp = pending['created_ms'] + 100
    event(client, 'transcript', stamp + 200, role='user', transcriptType='final', transcript=utterance)
    assert invoke(client, 'confirm_action', {'action_token': preparation['data']['action_token']})['code'] == 'confirmation_not_verified'
    assert not action_system[4].events


def test_yes_alone_confirms_without_speech_events(action_system):
    preparation, _ = checked_booking(action_system)
    consent(action_system, preparation)
    result = invoke(action_system[0], 'confirm_action', {'action_token': preparation['data']['action_token']})
    assert result['status'] == 'completed'
    assert len(action_system[4].events) == 1


def test_interruption_does_not_block_affirmation(action_system):
    preparation, _ = checked_booking(action_system)
    event(action_system[0], 'user-interrupted', pending_state(action_system)['created_ms'] + 10)
    consent(action_system, preparation)
    assert invoke(action_system[0], 'confirm_action', {'action_token': preparation['data']['action_token']})['status'] == 'completed'


def test_latest_correction_revokes_previous_affirmation(action_system):
    preparation, _ = checked_booking(action_system)
    consent(action_system, preparation)
    stamp = pending_state(action_system)['affirmed_ms'] + 100
    event(action_system[0], 'transcript', stamp, role='user', transcriptType='final', transcript='Yes but make it 10 instead')
    assert invoke(action_system[0], 'confirm_action', {'action_token': preparation['data']['action_token']})['code'] == 'confirmation_not_verified'
    assert not action_system[4].events


def test_old_partial_and_assistant_transcripts_cannot_confirm(action_system):
    preparation, _ = checked_booking(action_system)
    stamp = pending_state(action_system)['created_ms']
    event(action_system[0], 'transcript', stamp - 1, role='user', transcriptType='final', transcript='Yes')
    event(action_system[0], 'transcript', stamp + 100, role='user', transcriptType='partial', transcript='Yes')
    event(action_system[0], 'transcript', stamp + 200, role='assistant', transcriptType='final', transcript='Yes')
    assert invoke(action_system[0], 'confirm_action', {'action_token': preparation['data']['action_token']})['code'] == 'confirmation_not_verified'
    assert not action_system[4].events


def test_final_only_subscription_and_outdated_transcript(action_system):
    preparation, _ = checked_booking(action_system)
    stamp = pending_state(action_system)['created_ms'] + 100
    event(action_system[0], 'transcript[transcriptType="final"]', stamp + 100, role='user', transcript='Yes')
    event(action_system[0], 'transcript', stamp, role='user', transcriptType='final', transcript='No')
    assert invoke(action_system[0], 'confirm_action', {'action_token': preparation['data']['action_token']})['status'] == 'completed'


def test_settings_changes_expire_confirmation(action_system):
    client, _, sessions, bid, calendar, _ = action_system
    preparation, _ = checked_booking(action_system)
    consent(action_system, preparation)
    with sessions.begin() as db:
        row = db.get(Business, bid)
        row.settings = {**row.settings, 'buffer_minutes': 10}
    assert invoke(client, 'confirm_action', {'action_token': preparation['data']['action_token']})['code'] == 'action_expired'
    assert not calendar.events


def test_reference_phone_and_tenant_verification(action_system):
    client = action_system[0]
    row = book(action_system)
    for reference, phone in [('f' * 32, '+15551234567'), (row['id'], '+15559876543')]:
        result = invoke(client, 'get_appointment', {'appointment_id': reference, 'caller_phone': phone})
        assert result['status'] == 'unverified' and 'data' not in result
    result = invoke(client, 'get_appointment', {'appointment_id': row['id'], 'caller_phone': '+1 (555) 123-4567'})
    assert result['data']['appointment_id'] == row['id']
    assert 'caller_name' not in result['data'] and 'caller_email' not in result['data']
    assert invoke(client, 'get_appointment', {'appointment_id': row['id'], 'caller_phone': '+15551234567'}, assistant='b')['status'] == 'unverified'
    assert not invoke(client, 'check_availability', {'service_id': 'pt', 'date': '2026-10-02'}, assistant='b')['success']


def test_cancel_requires_confirmation_and_policy_is_read_only(action_system):
    client, _, sessions, _, calendar, _ = action_system
    row = book(action_system)
    invoke(client, 'get_business_information')
    assert len(calendar.events) == 1
    preparation = invoke(client, 'cancel_appointment', {'appointment_id': row['id'], 'caller_phone': '+15551234567'})
    assert len(calendar.events) == 1
    consent(action_system, preparation)
    result = invoke(client, 'confirm_action', {'action_token': preparation['data']['action_token']})
    assert result['data']['status'] == 'cancelled'
    assert not calendar.events
    with sessions() as db:
        assert db.get(Appointment, row['id']).status == 'cancelled'


def test_reschedule_keeps_calendar_and_database_consistent(action_system):
    client, _, sessions, _, calendar, _ = action_system
    row = book(action_system)
    args = {'service_id': 'pt', 'date': '2026-10-02', 'appointment_id': row['id'], 'caller_phone': '+15551234567'}
    slots = invoke(client, 'check_availability', args)['data']['slots']
    assert row['start_at'] in slots
    chosen = slots[2]
    preparation = invoke(client, 'reschedule_appointment', {'appointment_id': row['id'],
        'caller_phone': '+15551234567', 'start_at': chosen})
    consent(action_system, preparation)
    result = invoke(client, 'confirm_action', {'action_token': preparation['data']['action_token']})
    assert result['data']['start_at'] == chosen
    with sessions() as db:
        stored = db.get(Appointment, row['id'])
        assert calendar.events[stored.calendar_event_id]['start']['dateTime'] == chosen
    assert len(calendar.events) == 1


def test_message_saved_once_only_after_confirmation(action_system):
    client, _, sessions, *_ = action_system
    preparation = invoke(client, 'leave_message', {'caller_name': 'Caller', 'caller_phone': '+15551234567', 'content': 'Please call back.'}, key='message-1')
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 0
    consent(action_system, preparation)
    token = preparation['data']['action_token']
    result = invoke(client, 'confirm_action', {'action_token': token})
    assert result['data']['status'] == 'saved'
    assert invoke(client, 'confirm_action', {'action_token': token}) == result
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 1


def test_timeout_after_remote_write_never_duplicates_booking(action_system):
    client, _, sessions, _, calendar, _ = action_system
    preparation, _ = checked_booking(action_system)
    consent(action_system, preparation)
    token = preparation['data']['action_token']
    calendar.after_create = True
    result = invoke(client, 'confirm_action', {'action_token': token}, key='confirm-1')
    assert not result['success'] and len(calendar.events) == 1
    calendar.after_create = False
    result = invoke(client, 'confirm_action', {'action_token': token}, key='confirm-2')
    assert result['status'] == 'completed' and len(calendar.events) == 1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Appointment)) == 1


def test_calendar_outage_and_unchecked_slots_fail_closed(action_system):
    client, _, _, _, calendar, _ = action_system
    payload = {'caller_name': 'Caller', 'caller_phone': '+15551234567', 'service_id': 'pt', 'start_at': '2026-10-02T09:00:00+00:00'}
    assert invoke(client, 'create_appointment', payload)['code'] == 'select_checked_slot'
    calendar.fail = True
    assert not invoke(client, 'check_availability', {'service_id': 'pt', 'date': '2026-10-02'})['success']
    assert not calendar.events


def test_token_cannot_cross_calls_and_invalid_correction_expires_it(action_system):
    client = action_system[0]
    preparation, payload = checked_booking(action_system)
    assert invoke(client, 'confirm_action', {'action_token': preparation['data']['action_token']}, call='call-b')['code'] == 'action_expired'
    assert not invoke(client, 'create_appointment', {**payload, 'start_at': 'not-a-date'})['success']
    assert invoke(client, 'confirm_action', {'action_token': preparation['data']['action_token']})['code'] == 'action_expired'


def test_concurrent_confirmations_cannot_double_book(action_system):
    first, _ = checked_booking(action_system, call='call-a')
    second, _ = checked_booking(action_system, call='call-b')
    consent(action_system, first, 'call-a'); consent(action_system, second, 'call-b')
    def confirm(item):
        call, preparation = item
        return invoke(action_system[0], 'confirm_action', {'action_token': preparation['data']['action_token']}, call=call)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(confirm, [('call-a', first), ('call-b', second)]))
    assert sum(result['success'] for result in results) == 1
    assert len(action_system[4].events) == 1


def test_end_event_blocks_pending_actions(action_system):
    client = action_system[0]
    preparation, _ = checked_booking(action_system)
    stamp = pending_state(action_system)['created_ms'] + 100
    event(client, 'status-update', stamp, status='ended')
    assert invoke(client, 'confirm_action', {'action_token': preparation['data']['action_token']})['code'] == 'call_ended'


def test_action_configuration_exposes_nine_tools_and_confirmation_events():
    config = assistant_config({'VAPI_PUBLIC_BASE_URL': 'https://example.test',
        'VAPI_SERVER_CREDENTIAL_ID': 'credential', 'VAPI_ELEVENLABS_VOICE_ID': 'voice', 'VAPI_ACTIONS_ENABLED': 'true'})
    assert len(config['model']['tools']) == 9
   assert config['serverMessages'] == ['status-update', 'transcript']
    assert 'confirm_action' in config['model']['messages'][0]['content']
    for tool in config['model']['tools']:
        assert '"title"' not in json.dumps(tool['function']['parameters'])
    availability = next(tool for tool in config['model']['tools'] if tool['function']['name'] == 'check_availability')
    assert availability['function']['parameters']['properties']['earliest']['type'] == ['string', 'null']


def test_booking_trace_shows_data_flow_and_validation_without_private_inputs(action_system, monkeypatch, caplog):
    import logging
    monkeypatch.setenv('VAPI_TRACE_ENABLED', 'true')
    caplog.set_level(logging.INFO, logger='ava.vapi.trace')
    preparation, payload = checked_booking(action_system)
    invalid = invoke(action_system[0], 'create_appointment', {**payload, 'caller_phone': '03009'})
    assert not invalid['success']
    # Changed invalid details invalidate the earlier draft. Prepare fresh details.
    preparation = invoke(action_system[0], 'create_appointment', payload)
    consent(action_system, preparation)
    assert invoke(action_system[0], 'confirm_action', {'action_token': preparation['data']['action_token']})['status'] == 'completed'
    entries = [json.loads(r.message) for r in caplog.records if r.name == 'ava.vapi.trace']
    stages = {e['stage'] for e in entries}
    assert {'tool.request', 'tool.response', 'availability.rules', 'availability.busy_intervals',
            'availability.result', 'action.exception', 'confirmation.authorized',
            'calendar.operation_intent', 'calendar.operation_completed', 'action.completed'} <= stages
    assert all(e['call_id'] == 'call-a' for e in entries)
    errors = next(e for e in entries if e['stage'] == 'action.exception')
    assert errors['validation_errors'][0]['field'] == ['caller_phone']
    assert '+15551234567' not in json.dumps(entries) and '03009' not in json.dumps(entries)
