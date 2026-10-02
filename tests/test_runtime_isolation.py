"""Active applications must run even when legacy imports are unavailable."""
import subprocess
import sys
from pathlib import Path


def test_active_factories_do_not_require_legacy():
    script = '''
import importlib.abc
import sys
class NoLegacy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'legacy' or fullname.startswith('legacy.'):
            raise ModuleNotFoundError('Legacy intentionally unavailable')
sys.meta_path.insert(0, NoLegacy())
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.api import create_app as staff
from backend.app.vapi_api import create_app as vapi, WebhookSettings
from backend.app.vapi_actions import Actions
sessions = sessionmaker(create_engine('sqlite://'))
app = staff(sessions)
paths = {getattr(route, 'path', '') for route in app.routes}
assert '/api/settings' in paths and '/api/appointments' in paths
assert '/api/voice' not in paths and not any(p.startswith('/api/demo') for p in paths)
assert not hasattr(app.state, 'agent')
vapi(sessions, WebhookSettings(token='test-only-webhook-token-with-32-characters',
     assistant_business_map={'a':'b'}), Actions(sessions, lambda bid: None))
assert not any(name == 'legacy' or name.startswith('legacy.') for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
