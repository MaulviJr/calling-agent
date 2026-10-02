"""Read-only live Gemini smoke check, using synthetic settings and no database.

Run from the repository root: python -m legacy.scripts.check_conversation
Uses the configured Gemini key and incurs normal provider usage. Never calls
calendar/STT/TTS or loads real business settings, call records or credentials files.
"""
import sys
import argparse

from dotenv import load_dotenv

from legacy.app.agent import AppointmentState, GeminiConversationPlanner, Receptionist
from backend.app.business import BusinessSettings, Service
from legacy.app.conversation import GeminiResponseGenerator, ResponseRejected, check_surface


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['all', 'services', 'clarify', 'scope', 'staff'], default='all')
    selected = parser.parse_args().case
    load_dotenv()
    planner = GeminiConversationPlanner()
    generator = GeminiResponseGenerator(client=planner.client, model=planner.model)
    controller = Receptionist(None, None, planner, generator)
    settings = BusinessSettings(
        name='Example clinic',
        services=[Service(id='pt', name='Physiotherapy', duration=30)],
        knowledge=[{'question': 'Who are the physiotherapists?',
                    'answer': 'The physiotherapists is Alex, Sam'}],
    )
    history = []
    failed = False
    cases = [
        ('services', 'Can you tell me about the appointments?', 'faq'),
        ('clarify', 'What do you know about', 'clarify'),
        ('scope', 'What do you know about Karachi?', 'out_of_scope'),
        ('staff', 'Who are the physiotherapists?', 'faq'),
    ]
    try:
        for case, question, expected in cases:
            if selected not in ('all', case):
                continue
            try:
                state = AppointmentState()
                decision = planner.decide(question, state, settings, history)
                # Only these read-only branches are allowed in this diagnostic.
                if decision.action != expected:
                    print(f'FAIL expected={expected} actual={decision.action}', flush=True)
                    failed = True
                    continue
                context = controller._act('synthetic', 'synthetic', state, settings,
                                          decision, question, 'synthetic', history)
                reply = generator.generate(question, history, state.model_dump(), context)
                check_surface(reply, context)
                print(f'PASS action={decision.action}: {reply}', flush=True)
                history.extend([{'role': 'user', 'text': question},
                                {'role': 'assistant', 'text': reply}])
            except Exception as exc:
                # No raw HTTP response, API key, provider URL or exception body.
                reason = exc.reason if isinstance(exc, ResponseRejected) else 'provider_or_schema_error'
                print(f'FAIL kind={type(exc).__name__} reason={reason}', flush=True)
                failed = True
    finally:
        planner.client.close()
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
