from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.app.api import create_app,passwords
from backend.app.database import Admin,Business,Call
from backend.app.business import BusinessSettings


def test_auth_origin_tenant_isolation_and_settings(system):
    sessions,bid,cal,scheduler=system
    with sessions.begin() as db:
        db.add(Admin(business_id=bid,email='staff@example.test',password_hash=passwords.hash('a-long-test-password')))
        other=Business(settings=BusinessSettings().model_dump(mode='json')); db.add(other); db.flush()
        call=Call(business_id=other.id); db.add(call); db.flush(); hidden=call.id
    client=TestClient(create_app(sessions,cal))
    assert client.get('/api/calls').status_code==401
    data={'email':'staff@example.test','password':'a-long-test-password'}
    assert client.post('/api/login',json=data).status_code==403
    headers={'origin':'http://localhost:8000'}
    assert client.post('/api/login',json=data,headers=headers).status_code==200
    assert client.get('/api/calls').json()==[]
    assert client.get('/api/calls/'+hidden).status_code==404
    assert client.get('/api/overview').json()['total_calls']==0
    settings=client.get('/api/settings').json()
    settings['timezone']='nonsense'
    assert client.put('/api/settings',json=settings,headers=headers).status_code==422
    assert client.post('/api/logout',headers=headers).status_code==200
    assert client.get('/api/me').status_code==401
