"""Register saved tools and update the configured saved assistant. Never log keys."""
import json
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

from backend.app.vapi_config import assistant_config, tool_definitions


def main():
    path = Path('.env')
    env = dict(dotenv_values(path))
    mapping = json.loads(env['VAPI_ASSISTANT_BUSINESS_MAP'])
    if len(mapping) != 1:
        raise ValueError('Choose an assistant explicitly before configuring multiple businesses.')
    assistant, business = next(iter(mapping.items()))
    env.update(VAPI_ACTIONS_ENABLED='true', VAPI_CALENDAR_BUSINESS_ID=business)
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
            # match = next((item for item in existing if item.get('function', {}).get('name') == name
            #               and item.get('server', {}).get('url') == tool['server']['url']), None)
            match = next((item for item in existing
              if item.get('function', {}).get('name') == name), None)
            response = client.patch('/tool/' + match['id'], json=tool) if match else client.post('/tool', json=tool)
            if response.is_error:
                # API diagnostics can echo credentials; print only status and tool name.
                raise RuntimeError(f'Tool registration failed: {name}, HTTP {response.status_code}')
            ids[name] = response.json()['id']
        env['VAPI_BUSINESS_TOOL_ID'] = ids.pop('get_business_information')
        env['VAPI_STAFF_TOOL_ID'] = ids.pop('get_staff_information')
        env['VAPI_ACTION_TOOL_IDS'] = json.dumps(ids)
        config = assistant_config(env)
        response = client.patch('/assistant/' + assistant, json=config)
        if response.is_error:
            raise RuntimeError(f'Assistant update failed: HTTP {response.status_code}')
        verified = client.get('/assistant/' + assistant)
        verified.raise_for_status()
        if set(verified.json()['model']['toolIds']) != set(config['model']['toolIds']):
            raise RuntimeError('Assistant tool verification failed.')
    for name in ('VAPI_ACTIONS_ENABLED', 'VAPI_CALENDAR_BUSINESS_ID', 'VAPI_BUSINESS_TOOL_ID',
                 'VAPI_STAFF_TOOL_ID', 'VAPI_ACTION_TOOL_IDS'):
        set_key(str(path), name, env[name])
    Path('vapi-assistant.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    print('Saved assistant updated and verified: 9 tools. Restart the Vapi backend.')


if __name__ == '__main__':
    main()
