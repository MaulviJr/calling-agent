import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.business import BusinessSettings, Hours, Knowledge, Service, StaffMember
from backend.app.database import Base, Business, database
from backend.app.vapi_api import MAX_BODY_BYTES, WebhookSettings, create_app
from backend.app.vapi_config import assistant_config


TOKEN = 'test-only-webhook-token-with-32-characters'
AUTH = {'Authorization': 'Bearer ' + TOKEN}


@pytest.fixture
def vapi(tmp_path):
    engine, sessions = database('sqlite:///' + str(tmp_path / 'vapi.db'))
    Base.metadata.create_all(engine)
    settings = BusinessSettings(
        name='Example clinic', phone='+15551234567', location='Main Street',
        timezone='Asia/Karachi', cancellation_policy='Please give 24 hours notice.',
        voice_id='private-voice-setting', escalation_number='private-staff-phone',
        services=[Service(id='pt', name='Physiotherapy', price='Rs 3000'),
                  Service(id='inactive', name='Hidden service', active=False)],
        hours=[Hours(weekday=1, opens='09:00', closes='17:00')],
        knowledge=[Knowledge(question='Parking', answer='Use the north entrance.'),
                   Knowledge(question='Access', answer='The entrance has a wheelchair ramp.'),
                   Knowledge(question='Walk-ins', answer='Visits are by appointment only.'),
                   Knowledge(question='Staff prose', answer='Dr Example has a PhD.')],
        staff=[StaffMember(id='abdul', name='Abdul Hadi', role='physiotherapist', qualifications=['PhD']),
               StaffMember(id='ali', name='Ali', role='physician', qualifications=['MBBS']),
               StaffMember(id='hidden', name='Hidden person', role='physician', active=False)],
    )
    with sessions.begin() as db:
        first = Business(settings=settings.model_dump(mode='json'))
        other = Business(settings=BusinessSettings(name='Other clinic',
            staff=[StaffMember(id='other', name='Other person', role='nurse')]).model_dump(mode='json'))
        db.add_all([first, other]); db.flush()
        bid, other_bid = first.id, other.id
    client = TestClient(create_app(sessions, WebhookSettings(token=TOKEN,
        assistant_business_map={'assistant-a': bid, 'assistant-b': other_bid})))
    yield client, sessions, bid, other_bid
    client.close()
    engine.dispose()


def envelope(name='get_staff_information', arguments=None, *, assistant='assistant-a', nested=False):
    tool = {'id': 'tool-1'}
    if nested:
        tool['function'] = {'name': name, 'arguments': '{}' if arguments is None else arguments}
    else:
        tool.update(name=name, parameters={} if arguments is None else arguments)
    return {'message': {'type': 'tool-calls',
                        'call': {'id': 'call-1', 'assistantId': assistant},
                        'toolCallList': [tool]}}


def invoke(client, name='get_staff_information', args=None, **kwargs):
    response = client.post('/api/vapi/tools', json=envelope(name, args, **kwargs), headers=AUTH)
    assert response.status_code == 200
    item = response.json()['results'][0]
    assert item['toolCallId'] == 'tool-1'
    return json.loads(item.get('result', item.get('error')))


@pytest.mark.parametrize('headers', [{}, {'Origin': 'http://localhost:8000'},
                                      {'Authorization': 'Bearer wrong-token'},
                                      {'Authorization': TOKEN}])
def test_tools_require_service_authentication(vapi, headers):
    client, *_ = vapi
    assert client.post('/api/vapi/tools', json=envelope(), headers=headers).status_code == 401


def test_business_facts_and_public_field_whitelist(vapi):
    client, *_ = vapi
    result = invoke(client, 'get_business_information')
    assert result['success'] and result['status'] == 'completed'
    data = result['data']
    from datetime import date
    date.fromisoformat(data['business'].pop('current_date'))
    assert data['business'] == {
        'name': 'Example clinic', 'phone': '+15551234567', 'location': 'Main Street',
        'timezone': 'Asia/Karachi', 'hours': [{'weekday': 1, 'opens': '09:00:00', 'closes': '17:00:00'}],
        'cancellation_policy': 'Please give 24 hours notice.',
    }
    assert data['services'] == [{'id': 'pt', 'name': 'Physiotherapy', 'duration_minutes': 30, 'price': 'Rs 3000'}]
    assert [faq['answer'] for faq in data['faqs']['items']][:3] == [
        'Use the north entrance.', 'The entrance has a wheelchair ramp.', 'Visits are by appointment only.']
    encoded = json.dumps(result)
    for secret in ('private-voice-setting', 'private-staff-phone', 'Hidden service', TOKEN):
        assert secret not in encoded
    assert 'staff' not in data


def test_staff_roles_are_returned_verbatim_separate_from_qualifications(vapi):
    client, *_ = vapi
    data = invoke(client)['data']
    assert data['staff']['items'] == [
        {'id': 'abdul', 'name': 'Abdul Hadi', 'role': 'physiotherapist', 'qualifications': ['PhD']},
        {'id': 'ali', 'name': 'Ali', 'role': 'physician', 'qualifications': ['MBBS']},
    ]
    assert data['staff']['total'] == 2
    assert not data['staff']['has_more']
    assert data['roles_and_qualifications_are_separate']
    assert 'Dr Example' not in json.dumps(data)


@pytest.mark.parametrize('name', ['get_business_information', 'get_staff_information'])
def test_assistant_mapping_isolates_tenants(vapi, name):
    client, _, _, other_bid = vapi
    other = invoke(client, name, assistant='assistant-b')
    assert 'Example clinic' not in json.dumps(other)
    assert 'Abdul Hadi' not in json.dumps(other)
    injected = invoke(client, name, {'business_id': other_bid})
    assert not injected['success'] and injected['status'] == 'rejected'
    spoof = envelope(name)
    spoof['message']['business_id'] = other_bid
    response = client.post('/api/vapi/tools', json=spoof, headers=AUTH)
    assert 'Other clinic' not in response.text and 'Other person' not in response.text


def test_unknown_assistant_and_conflicting_metadata_rejected(vapi):
    client, *_ = vapi
    assert client.post('/api/vapi/tools', json=envelope(assistant='unknown'), headers=AUTH).status_code == 403
    data = envelope()
    data['message']['assistant'] = {'id': 'assistant-b'}
    assert client.post('/api/vapi/tools', json=data, headers=AUTH).status_code == 400
    del data['message']['call']['assistantId']
    assert client.post('/api/vapi/tools', json=data, headers=AUTH).status_code == 400


@pytest.mark.parametrize('args', [{'offset': -1}, {'limit': 21}, {'limit': 0},
                                  {'limit': True}, {'offset': '1'}, {'question': 'arbitrary language'},
                                  [], '{invalid', '{"limit": 100}'])
def test_invalid_staff_arguments_return_correlated_safe_failure(vapi, args):
    client, *_ = vapi
    result = invoke(client, args=args)
    assert not result['success'] and result['code'] == 'invalid_arguments_or_settings'


def test_both_documented_envelopes_and_batched_results(vapi):
    client, *_ = vapi
    assert invoke(client, nested=True)['success']
    data = envelope('get_business_information', nested=True)
    data['message']['toolCallList'].append({'id': 'tool-2', 'name': 'get_staff_information', 'parameters': {}})
    response = client.post('/api/vapi/tools', json=data, headers=AUTH)
    assert response.status_code == 200
    results = response.json()['results']
    assert [item['toolCallId'] for item in results] == ['tool-1', 'tool-2']
    assert all(isinstance(item['result'], str) and json.loads(item['result'])['success'] for item in results)


def test_pagination_does_not_present_partial_facts_as_complete(vapi):
    client, *_ = vapi
    staff = invoke(client, args={'limit': 1})['data']['staff']
    assert staff['has_more'] and staff['next_offset'] == 1 and staff['total'] == 2
    next_staff = invoke(client, args={'limit': 1, 'offset': staff['next_offset']})['data']['staff']
    assert next_staff['items'][0]['name'] == 'Ali' and not next_staff['has_more']
    faqs = invoke(client, 'get_business_information', {'faq_limit': 1})['data']['faqs']
    assert faqs['has_more'] and faqs['next_offset'] == 1
    assert not invoke(client, 'get_business_information', {'faq_limit': 11})['success']


def test_missing_facts_remain_unknown_and_latest_settings_are_loaded(vapi):
    client, sessions, bid, _ = vapi
    with sessions.begin() as db:
        db.get(Business, bid).settings = BusinessSettings().model_dump(mode='json')
    data = invoke(client, 'get_business_information')['data']
    assert data['business']['phone'] is None and data['business']['location'] is None
    assert data['services'] == [] and data['faqs']['items'] == []
    assert invoke(client)['data']['staff']['items'] == []
    with sessions.begin() as db:
        db.get(Business, bid).settings = BusinessSettings(staff=[
            StaffMember(id='abdul', name='Abdul Hadi', role='receptionist')]).model_dump(mode='json')
    assert invoke(client)['data']['staff']['items'][0]['role'] == 'receptionist'


def test_database_failure_is_safe_and_logs_do_not_dump_inputs(vapi, monkeypatch, caplog):
    client, *_ = vapi
    def fail(*args):
        raise RuntimeError('sensitive-credentials')
    monkeypatch.setattr('backend.app.vapi_api.execute_tool', fail)
    with caplog.at_level('INFO', logger='ava.vapi'):
        result = invoke(client)
    assert result['code'] == 'information_unavailable'
    assert 'VAPI_TOOL_REQUESTED' in caplog.text and 'VAPI_TOOL_FAILED' in caplog.text
    assert 'sensitive-credentials' not in caplog.text and TOKEN not in caplog.text


@pytest.mark.parametrize('name', ['create_appointment', 'cancel_appointment', 'reschedule_appointment',
                                  'leave_message', 'confirm_action'])
def test_mutation_tools_are_not_available(vapi, name):
    client, *_ = vapi
    assert invoke(client, name)['code'] == 'unknown_tool'


def test_retries_and_events_never_write_database(vapi):
    client, sessions, *_ = vapi
    def counts():
        with sessions() as db:
            return {table.name: db.scalar(select(func.count()).select_from(table))
                    for table in Base.metadata.sorted_tables}
    before = counts()
    assert invoke(client) == invoke(client)
    event = {'message': {'type': 'status-update', 'status': 'in-progress',
                         'call': {'id': 'call-1', 'assistantId': 'assistant-a'}}}
    assert client.post('/api/vapi/events', json=event).status_code == 401
    assert client.post('/api/vapi/events', json=event, headers=AUTH).json() == {
        'accepted': True, 'persisted': False}
    event['message']['type'] = 'end-of-call-report'
    assert client.post('/api/vapi/events', json=event, headers=AUTH).status_code == 200
    event['message']['call']['assistantId'] = 'unknown'
    assert client.post('/api/vapi/events', json=event, headers=AUTH).status_code == 403
    assert counts() == before


@pytest.mark.parametrize('payload', [{}, {'message': None}, {'message': {'call': None}},
                                     {'message': {'call': {'id': '\nspoof', 'assistantId': 'assistant-a'}}}])
def test_malformed_envelopes_rejected(vapi, payload):
    client, *_ = vapi
    assert client.post('/api/vapi/tools', json=payload, headers=AUTH).status_code == 400


def test_body_limit_and_duplicate_tool_ids(vapi):
    client, *_ = vapi
    assert client.post('/api/vapi/tools', content=b'x' * (MAX_BODY_BYTES + 1), headers=AUTH).status_code == 413
    data = envelope()
    data['message']['toolCallList'] *= 2
    assert client.post('/api/vapi/tools', json=data, headers=AUTH).status_code == 400


def test_mapping_configuration_fails_closed_without_leaking_secrets(monkeypatch):
    monkeypatch.setenv('VAPI_WEBHOOK_TOKEN', TOKEN)
    monkeypatch.setenv('VAPI_ASSISTANT_BUSINESS_MAP', '{invalid')
    with pytest.raises(RuntimeError) as error:
        WebhookSettings.from_env()
    assert TOKEN not in str(error.value)
    monkeypatch.setenv('VAPI_ASSISTANT_BUSINESS_MAP', '{"assistant-a":"business-a"}')
    assert WebhookSettings.from_env().assistant_business_map == {'assistant-a': 'business-a'}
    monkeypatch.setenv('VAPI_WEBHOOK_TOKEN', '')
    with pytest.raises(RuntimeError):
        WebhookSettings.from_env()


def test_isolated_runtime_never_imports_legacy_modules():
    root = Path(__file__).resolve().parents[1]
    script = """
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.vapi_api import create_app, WebhookSettings
create_app(sessionmaker(create_engine('sqlite://')), WebhookSettings(
    token='test-only-webhook-token-with-32-characters', assistant_business_map={'a':'b'}))
for prefix in ('backend.app.agent', 'backend.app.conversation', 'backend.app.semantic',
               'backend.app.voice', 'backend.app.scheduling', 'backend.app.calendar',
               'deepgram', 'elevenlabs', 'google.genai'):
    assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules), prefix
"""
    completed = subprocess.run([sys.executable, '-c', script], cwd=root, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_assistant_configuration_has_only_two_authenticated_tools():
    config = assistant_config({'VAPI_PUBLIC_BASE_URL': 'https://example.test',
        'VAPI_SERVER_CREDENTIAL_ID': 'credential-id', 'VAPI_ELEVENLABS_VOICE_ID': 'voice-id',
        'VAPI_WEBHOOK_TOKEN': TOKEN, 'VAPI_MODEL': 'chosen-model'})
    assert config['model']['model'] == 'chosen-model'
    assert [tool['function']['name'] for tool in config['model']['tools']] == [
        'get_business_information', 'get_staff_information']
    assert all(tool['server']['credentialId'] == 'credential-id' for tool in config['model']['tools'])
    assert all(tool['function']['parameters']['additionalProperties'] is False for tool in config['model']['tools'])
    for tool in config['model']['tools']:
        schema = tool['function']['parameters']
        assert 'title' not in schema
        assert all('title' not in field for field in schema['properties'].values())
    assert config['serverMessages'] == ['status-update']
    assert TOKEN not in json.dumps(config)
    assert 'functions' not in config['model']


@pytest.mark.parametrize('url', ['http://example.test', 'https://user:secret@example.test',
                                'https://example.test?token=secret', ''])
def test_configuration_requires_clean_https_url(url):
    with pytest.raises(ValueError):
        assistant_config({'VAPI_PUBLIC_BASE_URL': url,
                          'VAPI_SERVER_CREDENTIAL_ID': 'credential-id', 'VAPI_ELEVENLABS_VOICE_ID': 'voice-id'})


def test_saved_tool_ids_replace_inline_definitions():
    env = {'VAPI_PUBLIC_BASE_URL': 'https://example.test',
           'VAPI_SERVER_CREDENTIAL_ID': 'credential-id', 'VAPI_ELEVENLABS_VOICE_ID': 'voice-id',
           'VAPI_BUSINESS_TOOL_ID': 'business-tool', 'VAPI_STAFF_TOOL_ID': 'staff-tool'}
    model = assistant_config(env)['model']
    assert model['tools'] == []
    assert model['toolIds'] == ['business-tool', 'staff-tool']
    del env['VAPI_STAFF_TOOL_ID']
    with pytest.raises(ValueError):
        assistant_config(env)
