"""Create a business and its first login, or reset a password.
Usage:
  python -m scripts.create_tenant "Clinic Name" Asia/Karachi owner@clinic.com
  python -m scripts.create_tenant --reset-password owner@clinic.com"""
import secrets
import sys
from dotenv import load_dotenv
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from backend.app.business import BusinessSettings
from backend.app.database import Admin, Business, LoginSession, database


def create(name, timezone, email):
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
    print(f'Business ID: {business_id}\nLogin: {email}\nTemporary password: {password}\n'
          f'Next:\n  python -m scripts.connect_calendar "{business_id}" "CALENDAR_ID"\n'
          f'  python -m scripts.provision_assistant "{business_id}"')


def reset(email):
    email = email.lower()
    password = secrets.token_urlsafe(12)
    _, sessions = database()
    with sessions.begin() as db:
        admin = db.scalar(select(Admin).where(Admin.email == email))
        if admin is None:
            sys.exit('No account with that email.')
        admin.password_hash = PasswordHash.recommended().hash(password)
        db.execute(delete(LoginSession).where(LoginSession.admin_id == admin.id))  # end old logins
    print(f'Login: {email}\nNew temporary password: {password}')


if __name__ == '__main__':
    load_dotenv()
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == '--reset-password':
        reset(args[1])
    elif len(args) == 3:
        create(*args)
    else:
        sys.exit(__doc__)