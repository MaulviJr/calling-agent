"""Run against npm start/dev + fixture_backend.py --transport-echo only."""
import json
from pathlib import Path
import httpx
from websockets.sync.client import connect

origin = 'http://localhost:8000'
with httpx.Client(base_url=origin) as client:
    denied = client.get('/api/me')
    assert denied.status_code == 401
    response = client.post('/api/login', headers={'Origin': origin},
                           json={'email': 'qa@example.test', 'password': 'frontend-qa-only-123'})
    assert response.status_code == 200, response.text
    assert 'HttpOnly' in response.headers['set-cookie']
    assert client.get('/api/me').status_code == 200
    assert client.post('/api/logout', headers={'Origin': 'https://wrong.test'}).status_code == 403
    expected = (Path(__file__).parents[1] / 'public' / 'audio-worklet.js').read_bytes()
    assert client.get('/audio-worklet.js').content == expected
    # This is a synthetic test credential, not a browser cookie/profile.
    cookie = 'ava_session=transport-test-only'
    with connect('ws://localhost:8000/api/voice', origin=origin,
                 additional_headers={'Cookie': cookie}, open_timeout=10) as socket:
        assert json.loads(socket.recv()) == {'origin': origin, 'cookie': cookie}
        pcm = bytes(range(256)) * 10
        socket.send(pcm)
        assert socket.recv() == pcm
        assert json.loads(socket.recv()) == {'type': 'clear'}
    assert client.post('/api/logout', headers={'Origin': origin}).status_code == 200
    assert client.get('/api/me').status_code == 401
print('Gateway passed: auth, cookie, Origin rejection, unchanged worklet, binary PCM and clear.')
