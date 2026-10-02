"""Offline UI preview. Temporary database; no provider calls or real bookings.

Run: python -m scripts.preview
This is deliberately separate from the production application factory.
"""
import os
import tempfile
from pathlib import Path
import uvicorn
from alembic.config import Config
from alembic import command
from backend.app.database import database, Business, Admin
from backend.app.business import BusinessSettings
from backend.app.api import create_app, passwords
from backend.app.agent import Decision


class OfflineLLM:
    def decide(self,*args): return Decision(action='unknown')


def main():
    with tempfile.TemporaryDirectory(prefix='ava-preview-') as directory:
        os.environ['DATABASE_URL']='sqlite:///'+str(Path(directory)/'preview.db')
        os.environ['APP_ORIGIN']='http://localhost:8000'
        os.environ['COOKIE_SECURE']='false'
        command.upgrade(Config('alembic.ini'),'head')
        engine,sessions=database()
        with sessions.begin() as db:
            business=Business(settings=BusinessSettings().model_dump(mode='json'))
            db.add(business); db.flush()
            db.add(Admin(business_id=business.id,email='preview@example.test',
                         password_hash=passwords.hash('preview-only-ava-123')))
        print('OFFLINE PREVIEW ONLY: http://localhost:8000')
        print('Login: preview@example.test / preview-only-ava-123')
        try: uvicorn.run(create_app(sessions,llm=OfflineLLM(),voice_enabled=False),host='127.0.0.1',port=8000)
        finally: engine.dispose()


if __name__=='__main__': main()
