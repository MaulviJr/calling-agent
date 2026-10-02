from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from backend.app.database import database, Business


def test_upgrade_restart_and_downgrade(tmp_path,monkeypatch):
    url='sqlite:///'+str(tmp_path/'migration.db')
    monkeypatch.setenv('DATABASE_URL',url)
    command.upgrade(Config('alembic.ini'),'head')
    engine,sessions=database(url)
    assert 'appointments' in inspect(engine).get_table_names()
    with sessions.begin() as db:
        business=Business(settings={'test':True});db.add(business);db.flush();bid=business.id
    engine.dispose()
    engine,sessions=database(url)
    with sessions() as db: assert db.get(Business,bid).settings=={'test':True}
    engine.dispose()
    command.downgrade(Config('alembic.ini'),'base')
    engine,_=database(url)
    assert 'businesses' not in inspect(engine).get_table_names()
    engine.dispose()
