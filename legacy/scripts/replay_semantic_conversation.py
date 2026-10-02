"""Replay the reported caller turns against one live semantic call per turn.

Synthetic business and temporary SQLite only. No real calls, calendar, STT or TTS.
Run: python -m legacy.scripts.replay_semantic_conversation --output legacy/docs/CONVERSATION_REPLAY.md
"""
import argparse
import json
import logging
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from legacy.app.agent import Receptionist
from backend.app.business import BusinessSettings
from legacy.app.conversation import GeminiResponseGenerator
from backend.app.database import Base, Business, Call, database
from legacy.app.semantic import SemanticDraft, DiscourseUpdate, render_answer


TURNS = [
    ('Hey. How are you?', 'Hello! I am doing well, thanks for asking. I am an AI receptionist here to help with clinic questions, appointments, or a message for the team. What would you like help with?'),
    ('What exactly do you guys do there?', 'I am an AI receptionist here to help with clinic questions, appointments, or a message for the team. What would you like help with?'),
    ('And who would actually treat me?', 'We offer Physiotherapy appointments lasting 30 minutes. The listed price is 1500 USD. We offer Phyiotherapy of neck appointments lasting 90 minutes. The listed price is 1455.'),
    ('Do you have any doctors there?', 'Our physicians are Abdul Hadi and ahmed.'),
    ('What about Abdul Hadhi? Is he a doctor?', 'Our physicians are Abdul Hadi and ahmed.'),
    ("Okay. So he's a physiotherapist.", 'Our physiotherapists are Ayan Khan, Ali Raza, and Hamza Khan.'),
    ('And who are the actual physician again?', 'Our physicians are Abdul Hadi and ahmed.'),
    ('Cool. Is the place wheelchair friendly?', 'I am not able to answer that. Is there anything else I can help you with regarding our services or appointments?'),
    ('What about parking?', 'I do not have approved information about that. Would you like me to take a message?'),
    ('And if I just show up, is that okay?', 'I can help with clinic questions, appointments, or take a message for the team. What would you like help with?'),
]


def replay_settings():
    # Only facts evidenced by the supplied conversation. No logistics policies
    # are invented, and the configured spelling/currency are preserved.
    return BusinessSettings(name='Example clinic', staff=[
        {'id': 'hadi', 'name': 'Abdul Hadi', 'role': 'physician'},
        {'id': 'ahmed', 'name': 'ahmed', 'role': 'physician'},
        {'id': 'ayan', 'name': 'Ayan Khan', 'role': 'physiotherapist'},
        {'id': 'ali', 'name': 'Ali Raza', 'role': 'physiotherapist'},
        {'id': 'hamza', 'name': 'Hamza Khan', 'role': 'physiotherapist'},
    ], services=[
        {'id': 'pt', 'name': 'Physiotherapy', 'duration': 30, 'price': '1500 USD'},
        {'id': 'neck', 'name': 'Phyiotherapy of neck', 'duration': 90, 'price': '1455'},
    ])


class ForbiddenActions:
    def __getattr__(self, name):
        raise AssertionError('This read-only replay must not use an action planner or scheduler')


class RecordingGenerator(GeminiResponseGenerator):
    def __init__(self):
        super().__init__()
        self.calls = 0
        self.last = None

    def interpret(self, *args):
        self.calls += 1
        self.last = super().interpret(*args)
        return self.last


def expected_drafts(packet):
    """Controlled model outputs, not a phrase classifier or live-model evidence."""
    def draft(mode, ids=(), entities=(), topic='', focus=None, role=None):
        kind = 'conversation' if mode == 'wellbeing' else 'knowledge'
        value = SemanticDraft(turn_kind=kind, answer_mode=mode,
            selected_source_ids=list(ids), resolved_entity_ids=list(entities),
            role_filter=role, response_text='placeholder',
            discourse_update=DiscourseUpdate(topic=topic, focused_entity_id=focus,
                                             recent_source_ids=list(ids)))
        return value.model_copy(update={'response_text': render_answer(value, packet)})
    staff = [s for s, v in packet['sources'].items() if v['kind'] == 'staff']
    physicians = [s for s in staff if packet['sources'][s]['role'] == 'physician']
    services = [s for s, v in packet['sources'].items() if v['kind'] == 'service']
    return [
        draft('wellbeing'),
        draft('services_overview', services, topic='services'),
        draft('staff_list', staff, [s.split(':', 1)[1] for s in staff], topic='staff'),
        draft('staff_list', physicians, ['hadi', 'ahmed'], topic='staff', role='physician'),
        draft('staff_role', ['staff:hadi'], ['hadi'], topic='staff', focus='hadi'),
        draft('staff_role_correction', ['staff:hadi'], ['hadi'], topic='staff', focus='hadi'),
        draft('staff_list', physicians, ['hadi', 'ahmed'], topic='staff', focus='hadi', role='physician'),
        draft('missing_information', topic='accessibility'),
        draft('missing_information', topic='parking'),
        draft('missing_information', topic='walk_in'),
    ]


class OfflineGenerator(RecordingGenerator):
    """Exercise the real generation adapter with only the provider replaced."""
    def _structured(self, prompt, payload, schema):
        assert schema is SemanticDraft
        return expected_drafts(payload['approved_packet'])[self.calls - 1]


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        if record.getMessage().startswith('SEMANTIC_TURN'):
            self.messages.append(record.getMessage())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='legacy/docs/CONVERSATION_REPLAY.md')
    parser.add_argument('--live', action='store_true', help='Send synthetic replay data to configured Gemini provider')
    args = parser.parse_args()
    if args.live:
        load_dotenv('.env')
    generator = RecordingGenerator() if args.live else OfflineGenerator()
    capture = Capture()
    logger = logging.getLogger('ava')
    logger.setLevel(logging.INFO)
    logger.addHandler(capture)
    rows = []
    with tempfile.TemporaryDirectory(prefix='ava-semantic-replay-') as directory:
        engine, sessions = database('sqlite:///' + str(Path(directory) / 'replay.db'))
        Base.metadata.create_all(engine)
        try:
            with sessions.begin() as db:
                business = Business(settings=replay_settings().model_dump(mode='json'))
                db.add(business)
                db.flush()
                bid = business.id
            forbidden = ForbiddenActions()
            agent = Receptionist(sessions, forbidden, forbidden, generator)
            cid = agent.start(bid)
            for index, (question, before) in enumerate(TURNS, 1):
                calls = generator.calls
                after = agent.respond(bid, cid, question, str(index))
                with sessions() as db:
                    state = db.get(Call, cid).state
                row = {'turn': index, 'user': question, 'before': before, 'after': after,
                       'calls': generator.calls - calls,
                       'discourse': state['discourse'], 'diagnostic': capture.messages[-1]}
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
        finally:
            engine.dispose()
            logger.removeHandler(capture)
            if generator.client:
                generator.client.close()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ['# ' + ('Live' if args.live else 'Controlled offline') + ' semantic conversation replay', '',
        'Synthetic clinic facts reconstructed from the supplied conversation. '
        'Accessibility, parking and walk-in policies were not supplied. ' +
        ('Each after response came from the live provider/controller path.' if args.live else
         'The provider was replaced with controlled structured outputs. This verifies the application path, '
         'not live model interpretation quality.') + ' Diagnostics include any local rendering fallback.', '',
        'The startup greeting is outside turn interpretation. The repeated greeting '
        'was not injected into the repaired conversation; browser greeting delivery has separate regression coverage.', '',
        '| Caller | Before | After |', '|---|---|---|']
    for row in rows:
        cells = [row['user'], row['before'], row['after']]
        lines.append('| ' + ' | '.join(c.replace('|', '\\|').replace('\n', ' ') for c in cells) + ' |')
    lines.extend(['', '## Per-turn diagnostics', '', '```text'])
    lines.extend(row['diagnostic'] for row in rows)
    lines.extend(['```', ''])
    path.write_text('\n'.join(lines), encoding='utf-8')
    path.with_suffix('.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
    return int(any(row['calls'] != 1 or 'provider_or_schema_error' in row['diagnostic'] for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
