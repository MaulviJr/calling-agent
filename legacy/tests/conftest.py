import pytest

@pytest.fixture(autouse=True)
def legacy_language_double(monkeypatch):
    class BaselineGenerator:
        def generate(self, transcript, history, state, context):
            return context.baseline
    monkeypatch.setattr('legacy.app.agent.GeminiResponseGenerator', BaselineGenerator)
