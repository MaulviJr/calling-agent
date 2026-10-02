# Ava with Vapi

Vapi handles the live voice conversation. Python supplies trusted business facts,
checks availability and owns appointment/message writes. The staff API and Next.js
frontend use the shared database, calendar and scheduling layers.

The old custom receptionist is isolated under [legacy/](legacy/README.md).
It is optional; neither active backend factory imports it by default.

## Active entry points

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.vapi_api:build_app --factory --host 127.0.0.1 --port 8002
.\venv\Scripts\python.exe -m uvicorn backend.app.main:build_app --factory --host 127.0.0.1 --port 8001
```

Run the Vapi webhook server on 8002 and the staff/dashboard API on 8001 in separate
terminals. Keep the Vapi server reachable through a public HTTPS URL. The frontend
continues to use its existing staff API gateway.

## Code ownership

| Location | Purpose |
| --- | --- |
| backend/app/vapi_*.py | Vapi tools, webhook authentication, confirmation, configuration and diagnostics |
| backend/app/api.py and main.py | Staff login, settings, appointments, messages, call records and dashboard data |
| backend/app/database.py, business.py, scheduling.py, calendar.py, dates.py, lookup.py | Shared backend services; keep these when removing legacy |
| tests/ and root conftest.py | Active backend tests and isolated fixtures |
| scripts/ | Active Vapi configuration and dry-run utilities |
| legacy/ | Archived custom agent, voice, demo routes, scripts, tests, dependencies and historical docs |

See [setup](SETUP.md), [testing](TESTING.md), [action tools](docs/VAPI_ACTION_TOOLS.md)
and [diagnostic logs](docs/VAPI_DEBUG_LOGS.md).

Default tests exclude legacy. The normal staff API does not expose the old custom
text demo or browser voice endpoints. Existing frontend controls for those old
features require the optional legacy factory; frontend Vapi integration is separate.

Current calendar configuration belongs to one business. Multi-business calendar
connections, full Vapi transcript reconciliation and production hosting still need
separate implementation. Passing offline tests does not establish live provider quality.
