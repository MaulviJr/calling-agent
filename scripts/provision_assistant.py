"""Create or update the Vapi assistant for a business.
Usage:
  python -m scripts.provision_assistant BUSINESS_ID
  python -m scripts.provision_assistant BUSINESS_ID --adopt ASSISTANT_ID   (link one you already made)
  python -m scripts.provision_assistant --all        (re-push every assistant after a change)"""
import sys

import httpx
from dotenv import dotenv_values, load_dotenv
from sqlalchemy import select

from backend.app.business import BusinessSettings
from backend.app.database import Business, VapiAssistant, database
from backend.app.vapi_config import assistant_config


def push(client, env, sessions, business_id, existing=None):
    with sessions() as db:
        business = db.get(Business, business_id)
        if business is None:
            sys.exit(f'Unknown business ID {business_id}.')
        settings = BusinessSettings.model_validate(business.settings)
        if existing is None:
            row = db.scalar(select(VapiAssistant).where(VapiAssistant.business_id == business_id))
            existing = row.assistant_id if row else None
        else:
            taken = db.get(VapiAssistant, existing)
            if taken and taken.business_id != business_id:
                sys.exit('That assistant already belongs to a different business.')
    config = assistant_config(env, settings)
    verb = 'updated' if existing else 'created'
    response = (client.patch('/assistant/' + existing, json=config) if existing
                else client.post('/assistant', json=config))
    if response.is_error:
        # Vapi's error body can echo configuration; print only the status.
        sys.exit(f'Vapi {verb} failed for {business_id}: HTTP {response.status_code}')
    assistant_id = existing or response.json()['id']
    with sessions.begin() as db:
        if db.get(VapiAssistant, assistant_id) is None:
            db.add(VapiAssistant(assistant_id=assistant_id, business_id=business_id))
    print(f'{settings.name}: assistant {verb} -> {assistant_id}')
    return assistant_id


def main(args):
    load_dotenv()
    env = dict(dotenv_values('.env'))
    key = env.get('VAPI_PRIVATE_API_KEY') or env.get('VAPI_API_KEY')
    if not key:
        sys.exit('Missing private API key.')
    _, sessions = database()
    with httpx.Client(base_url='https://api.vapi.ai', headers={'Authorization': 'Bearer ' + key}, timeout=60) as client:
        if args == ['--all']:
            with sessions() as db:
                rows = [(r.assistant_id, r.business_id) for r in db.scalars(select(VapiAssistant))]
            for assistant_id, business_id in rows:
                push(client, env, sessions, business_id, assistant_id)
        elif len(args) == 1 and not args[0].startswith('--'):
            assistant_id = push(client, env, sessions, args[0])
            print('Next: assign a phone number to this assistant in the Vapi dashboard.')
        elif len(args) == 3 and args[1] == '--adopt':
            push(client, env, sessions, args[0], existing=args[2])
        else:
            sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])