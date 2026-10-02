"""Explicit first-run admin creation; never automatically seed caller records."""
import os
from dotenv import load_dotenv
from sqlalchemy import select
from pwdlib import PasswordHash
from .business import BusinessSettings
from .database import database, Business, Admin


def main():
    load_dotenv()
    email, password = os.environ['ADMIN_EMAIL'].lower(), os.environ['ADMIN_PASSWORD']
    if len(password) < 14 or '@' not in email:
        raise ValueError('Set ADMIN_EMAIL and a password of at least 14 characters.')
    _, sessions = database()
    with sessions.begin() as db:
        if db.scalar(select(Admin)):
            raise RuntimeError('Admin already exists; bootstrap does not overwrite users.')
        business = db.scalar(select(Business))
        if business is None:
            business = Business(settings=BusinessSettings().model_dump(mode='json'))
            db.add(business); db.flush()
        db.add(Admin(business_id=business.id, email=email, password_hash=PasswordHash.recommended().hash(password)))
    print('Admin created. Remove ADMIN_PASSWORD from the environment after bootstrap.')


if __name__ == '__main__':
    main()
