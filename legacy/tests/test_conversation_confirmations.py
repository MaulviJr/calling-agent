import pytest
from sqlalchemy import select
from legacy.app.agent import Decision, Receptionist
from backend.app.database import Appointment


class BookingIntent:
    def decide(self, *args):
        return Decision(action='book', date_phrase='2026-10-05', time_phrase='10:00',
                        caller_name='Abdul Hadi', phone='03011310006')


@pytest.mark.parametrize('confirmation', ['Yes. Go ahead, please.', 'I confirm.',
                                         'Yes, please proceed.', 'Yes, book it please.'])
def test_natural_confirmation_books_once(system, confirmation):
    sessions, bid, calendar, scheduler = system
    agent = Receptionist(sessions, scheduler, BookingIntent())
    cid = agent.start(bid, 'browser')
    agent.respond(bid, cid, 'Book physiotherapy Monday at ten.', 'request')
    assert not calendar.events
    agent.delivered(bid, cid, False)
    reply = agent.respond(bid, cid, confirmation, 'confirmation')
    assert 'booked' in reply
    assert len(calendar.events) == 1
    assert agent.respond(bid, cid, confirmation, 'confirmation') == reply
    with sessions() as db:
        assert len(list(db.scalars(select(Appointment)))) == 1


@pytest.mark.parametrize('text', ['yes but make it eleven', 'I do not confirm',
    'yes if it is free', 'do not go ahead please', 'yes no wait',
    'I confirm tomorrow instead', 'can I confirm later?', 'yes cancel it instead'])
def test_conditional_or_changed_confirmation_is_not_automatic(text):
    assert not Receptionist._yes(text)


def test_interrupted_confirmation_is_repeated_then_can_be_confirmed(system):
    sessions, bid, calendar, scheduler = system
    agent = Receptionist(sessions, scheduler, BookingIntent())
    cid = agent.start(bid, 'browser')
    agent.respond(bid, cid, 'Book Monday at ten.', '1')
    agent.delivered(bid, cid, True)
    assert 'finish the confirmation' in agent.respond(bid, cid, 'I confirm.', '2')
    assert not calendar.events
    agent.delivered(bid, cid, False)
    assert 'booked' in agent.respond(bid, cid, 'Yes. Go ahead, please.', '3')


def test_greeting_and_capabilities_use_planned_context(system):
    sessions, bid, calendar, scheduler = system
    class Planner:
        def __init__(self):
            self.decisions=iter([Decision(action='greeting'),Decision(action='capabilities')])
        def decide(self, *args):
            return next(self.decisions)
    agent = Receptionist(sessions, scheduler, Planner())
    cid = agent.start(bid)
    assert "Hi, I'm Ava" in agent.respond(bid, cid, 'Hello.', '1')
    assert 'our services' in agent.respond(bid, cid, 'What information can you give me?', '2')
    assert not calendar.events
