"""Usage: python -m scripts.set_overrides BUSINESS_ID key=value [key=value ...]
       python -m scripts.set_overrides BUSINESS_ID --clear
Then run: python -m scripts.provision_assistant BUSINESS_ID"""
import sys
from dotenv import load_dotenv
from sqlalchemy import select
from backend.app.database import VapiAssistant, database
from backend.app.vapi_config import ALLOWED_OVERRIDES


def main(business_id, pairs):
    load_dotenv()
    _, sessions = database()
    with sessions.begin() as db:
        row = db.scalar(select(VapiAssistant).where(VapiAssistant.business_id == business_id))
        if row is None:
            sys.exit('No assistant for that business yet. Run provision_assistant first.')
        if pairs == ['--clear']:
            row.overrides = {}
        else:
            changes = dict(p.split('=', 1) for p in pairs)
            bad = set(changes) - ALLOWED_OVERRIDES
            if bad:
                sys.exit(f'Not allowed: {sorted(bad)}. Allowed: {sorted(ALLOWED_OVERRIDES)}')
            row.overrides = {**row.overrides, **changes}
        print('Overrides now:', row.overrides)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])