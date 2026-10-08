"""Create a business and its first login.
Usage: python -m scripts.create_tenant "Clinic Name" Asia/Karachi owner@clinic.com"""
import secrets
import sys
from dotenv import load_dotenv
from pwdlib import PasswordHash
from sqlalchemy import select
from backend.app.business import BusinessSettings
from backend.app.database import Admin, Business, database


def main(name, timezone, email):
    load_dotenv()
    settings = BusinessSettings(name=name, timezone=timezone)   # rejects a bad timezone
    email = email.lower()
    password = secrets.token_urlsafe(12)
    _, sessions = database()
    with sessions.begin() as db:
        if db.scalar(select(Admin).where(Admin.email == email)):
            sys.exit('That email already has an account.')
        business = Business(settings=settings.model_dump(mode='json'))
        db.add(business); db.flush()
        db.add(Admin(business_id=business.id, email=email,
                     password_hash=PasswordHash.recommended().hash(password)))
        business_id = business.id
    print(f'Business ID: {business_id}\nLogin: {email}\nTemporary password: {password}')


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])