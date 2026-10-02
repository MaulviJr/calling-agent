"""Exercise the installed SDK's wire serialization without contacting Gemini."""
import json

import httpx
import pytest
from google import genai
from google.genai import types
from pydantic import ValidationError

from backend.app.agent import AppointmentState, GeminiExtractor
from backend.app.business import BusinessSettings
from backend.app.conversation import GeminiResponseGenerator, TrustedContext
from backend.app.semantic import SemanticDraft, DiscourseState, build_packet


@pytest.mark.parametrize('reply, valid', [
    ({'action': 'faq', 'business_topic': 'name'}, True),
    ({'action': 'invented_action'}, False),
    ({'action': 'faq', 'unexpected_field': 'not allowed'}, False),
])
def test_json_schema_wire_format_and_local_validation(monkeypatch, reply, valid):
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-key')
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            'candidates': [{'content': {'role': 'model', 'parts': [
                {'text': json.dumps(reply)}]}, 'finishReason': 'STOP'}]})

    extractor = GeminiExtractor()
    extractor.client.close()
    extractor.client = genai.Client(api_key='synthetic-test-key',
        http_options=types.HttpOptions(client_args={
            'transport': httpx.MockTransport(respond)}))
    try:
        args = ('What is your name?', AppointmentState(),
                BusinessSettings(name='Test clinic', timezone='UTC'), [])
        if valid:
            decision = extractor.decide(*args)
            assert decision.action == 'faq'
            assert decision.business_topic == 'name'
        else:
            with pytest.raises(ValidationError):
                extractor.decide(*args)
        config = requests[0]['generationConfig']
        assert 'responseSchema' not in config
        assert config['responseMimeType'] == 'application/json'
        assert config['responseJsonSchema']['additionalProperties'] is False
        assert 'additional_properties' not in json.dumps(config)
    finally:
        extractor.client.close()


def test_generation_uses_one_call_without_executable_tools():
    requests = []
    responses = iter([
        {'text': 'Our physiotherapists are Abdul Hadi and Hamza.'},
        {'supported': True, 'preserves_all_facts': True, 'follows_goal': True},
    ])

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            'candidates': [{'content': {'role': 'model', 'parts': [
                {'text': json.dumps(next(responses))}]}, 'finishReason': 'STOP'}],
        })

    client = genai.Client(api_key='synthetic-test-key', http_options=types.HttpOptions(
        client_args={'transport': httpx.MockTransport(respond)},
    ))
    try:
        generator = GeminiResponseGenerator(client=client, model='test-model')
        context = TrustedContext(kind='knowledge', goal='Explain the approved staff list.',
            baseline='The physiotherapists is Abdul Hadi, Hamza',
            approved_facts={'answer': 'The physiotherapists is Abdul Hadi, Hamza'})
        assert generator.generate('Who works here?', [], {}, context) == (
            'Our physiotherapists are Abdul Hadi and Hamza.'
        )
        assert len(requests) == 1
        for request in requests:
            assert not request.get('tools')
            config = request['generationConfig']
            assert config['responseMimeType'] == 'application/json'
            assert config['responseJsonSchema']['additionalProperties'] is False
            assert 'responseSchema' not in config
    finally:
        client.close()


def test_semantic_schema_wire_format_one_call_and_no_tools():
    requests=[]
    reply=SemanticDraft(turn_kind='conversation',answer_mode='wellbeing',
                         response_text="I'm ready to help, thanks for asking!")
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'candidates':[{'content':{'role':'model','parts':[
            {'text':reply.model_dump_json()}]},'finishReason':'STOP'}]})
    client=genai.Client(api_key='synthetic-test-key',http_options=types.HttpOptions(
        client_args={'transport':httpx.MockTransport(respond)}))
    try:
        generator=GeminiResponseGenerator(client=client,model='test-model')
        packet=build_packet(BusinessSettings(),'Hello',[],DiscourseState())
        assert generator.interpret('Hello',[],{},packet)==reply
        assert len(requests)==1 and not requests[0].get('tools')
        config=requests[0]['generationConfig']
        schema=config['responseJsonSchema']
        assert schema['additionalProperties'] is False
        assert 'turn_kind' in schema['properties'] and 'action_proposal' in schema['properties']
        assert 'responseSchema' not in config
        assert 'additional_properties' not in json.dumps(config)
    finally:
        client.close()
