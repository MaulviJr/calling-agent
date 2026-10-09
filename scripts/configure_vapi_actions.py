"""Register the shared saved tools with Vapi. Run provision_assistant afterwards. Never log keys."""
import json
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

from backend.app.vapi_config import tool_definitions


def main():
    path = Path('.env')
    env = dict(dotenv_values(path))
    env['VAPI_ACTIONS_ENABLED'] = 'true'
    key = env.get('VAPI_PRIVATE_API_KEY') or env.get('VAPI_API_KEY')
    if not key:
        raise ValueError('Missing private API key.')
    with httpx.Client(base_url='https://api.vapi.ai', headers={'Authorization': 'Bearer ' + key}, timeout=60) as client:
        existing = client.get('/tool')
        existing.raise_for_status()
        existing = existing.json()
        ids = {}
        for tool in tool_definitions(env):
            name = tool['function']['name']
            match = next((item for item in existing if item.get('function', {}).get('name') == name), None)
            response = client.patch('/tool/' + match['id'], json=tool) if match else client.post('/tool', json=tool)
            if response.is_error:
                raise RuntimeError(f'Tool registration failed: {name}, HTTP {response.status_code}')
            ids[name] = response.json()['id']
    env['VAPI_BUSINESS_TOOL_ID'] = ids.pop('get_business_information')
    env['VAPI_STAFF_TOOL_ID'] = ids.pop('get_staff_information')
    env['VAPI_ACTION_TOOL_IDS'] = json.dumps(ids)
    for name in ('VAPI_ACTIONS_ENABLED', 'VAPI_BUSINESS_TOOL_ID', 'VAPI_STAFF_TOOL_ID', 'VAPI_ACTION_TOOL_IDS'):
        set_key(str(path), name, env[name])
    print('Tools registered (9). Now run: python -m scripts.provision_assistant --all')


if __name__ == '__main__':
    main()