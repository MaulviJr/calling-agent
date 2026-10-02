import pytest

from backend.app.conversation import GeminiResponseGenerator, ResponseDraft, TrustedContext
from backend.app.voice.providers import flux_turn_settings


def test_default_turn_settings_and_override(monkeypatch):
    monkeypatch.delenv('DEEPGRAM_EOT_THRESHOLD', raising=False)
    monkeypatch.delenv('DEEPGRAM_EOT_TIMEOUT_MS', raising=False)
    assert flux_turn_settings() == {'eot_threshold': '0.7', 'eot_timeout_ms': '2000'}
    monkeypatch.setenv('DEEPGRAM_EOT_THRESHOLD', '0.85')
    monkeypatch.setenv('DEEPGRAM_EOT_TIMEOUT_MS', '5000')
    assert flux_turn_settings() == {'eot_threshold': '0.85', 'eot_timeout_ms': '5000'}


@pytest.mark.parametrize('name,value', [
    ('DEEPGRAM_EOT_THRESHOLD', '0.1'), ('DEEPGRAM_EOT_THRESHOLD', 'nan'),
    ('DEEPGRAM_EOT_TIMEOUT_MS', '100'), ('DEEPGRAM_EOT_TIMEOUT_MS', 'oops'),
])
def test_invalid_turn_settings_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        flux_turn_settings()


def test_exact_approved_wording_skips_review():
    generator = GeminiResponseGenerator()
    calls = []
    def structured(prompt, payload, schema):
        calls.append(schema)
        assert schema is ResponseDraft, 'Exact approved text needs no remote review'
        return ResponseDraft(text='What date would you prefer?')
    generator._structured = structured
    context = TrustedContext(kind='question', goal='Ask for a date.',
                             baseline='What date would you prefer?')
    assert generator.generate('Book an appointment', [], {}, context) == context.baseline
    assert len(calls) == 1


def test_changed_wording_uses_only_one_call():
    generator = GeminiResponseGenerator()
    calls = []
    def structured(prompt, payload, schema):
        calls.append(schema)
        if schema is ResponseDraft:
            return ResponseDraft(text='Which date suits you?')
        raise TimeoutError('Review unavailable')
    generator._structured = structured
    context = TrustedContext(kind='question', goal='Ask for a date.',
                             baseline='What date would you prefer?')
    assert generator.generate('Book an appointment', [], {}, context) == 'Which date suits you?'
    assert len(calls) == 1
