import json
import logging

from backend.app.vapi_trace import emit, scope, scrub


def test_diagnostics_require_opt_in_and_call_scope(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger='ava.vapi.trace')
    monkeypatch.setenv('VAPI_TRACE_ENABLED', 'false')
    with scope(call_id='test-call'):
        emit('disabled')
    monkeypatch.setenv('VAPI_TRACE_ENABLED', 'true')
    emit('no_scope')
    with scope(call_id='test-call', tool_call_id='tool-1'):
        emit('tool.request', arguments={'caller_name':'Private Caller','caller_phone':'+15551234567',
             'caller_email':'private@example.com','service_id':'pt','start_at':'2026-10-03T09:00:00Z',
             'nested': {'api_key':'private-key','authorization':'Bearer secret'}})
    entries = [json.loads(r.message) for r in caplog.records if r.name == 'ava.vapi.trace']
    assert len(entries) == 1 and entries[0]['call_id'] == 'test-call'
    assert entries[0]['arguments']['service_id'] == 'pt'
    for private in ('Private Caller', '+15551234567', 'private@example.com', 'private-key', 'Bearer secret'):
        assert private not in json.dumps(entries)


def test_redaction_preserves_debugging_fields():
    value = scrub({'action_token':'draft-id','result':{'status':'rejected','code':'invalid_details'},
                   'slots':['2026-10-03T09:00:00Z'],'transcript':'private speech',
                   'credentialId':'private-credential','caller_phone':'123456789'})
    assert value['action_token'] == 'draft-id' and value['result']['code'] == 'invalid_details'
    assert value['slots'] == ['2026-10-03T09:00:00Z']
    assert value['transcript'] == value['credentialId'] == value['caller_phone'] == '[redacted]'
