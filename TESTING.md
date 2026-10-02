# Active tests

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Default pytest collects tests/ only. Fixtures use temporary databases and fake
calendars. The shared fixture no longer imports or monkeypatches the old agent.
Tests cover staff authentication, business isolation, scheduling, migrations,
Vapi tools/actions, diagnostics and active runtime isolation.

The runtime-isolation test blocks all legacy imports while constructing the staff
and Vapi applications, so removing legacy/ cannot silently break active startup.

For an offline booking trace with no provider calls or real bookings:

```powershell
.\venv\Scripts\python.exe -m scripts.dry_run_vapi_booking
```

For frontend QA:

```powershell
.\venv\Scripts\python.exe frontend/tests/fixture_backend.py
```

The fixture serves synthetic staff/dashboard data without the custom agent.
Start npm run dev from frontend/ separately. Custom voice/demo behavior is no
longer provided by this fixture; its opt-in transport echo remains for gateway QA.

Archived tests are opt-in:

```powershell
.\venv\Scripts\python.exe -m pytest legacy/tests -q
```

They retain legacy expectations and existing failures; see legacy/README.md.
Live Vapi/provider calls still require separate acceptance testing. Use
[diagnostics](docs/VAPI_DEBUG_LOGS.md) to compare tool results with spoken answers.
