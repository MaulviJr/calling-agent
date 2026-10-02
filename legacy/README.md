# Optional archived Ava implementation

The original custom receptionist is preserved here. Active Vapi and staff API
applications do not import this package or enable its routes.

Contents:

- app/: custom controller, conversation generation, semantic routing, knowledge
  rules, prompts and voice transport; shared database/scheduling remain in backend/app.
- app/routes.py: old text demo and browser voice endpoints, explicitly mounted only
  by the optional legacy factory.
- tests/: old controller and voice tests, excluded from default pytest collection.
- scripts/: original comparison/replay and static preview tools.
- docs/: historical architecture, walkthroughs and setup documents.
- experiments/: early learning scripts and audio artifacts.
- requirements.txt: optional speech/Gemini/microphone dependencies.
- requirements.lock.txt: historical full environment snapshot, including legacy packages.

From the repository root, optional use:

```powershell
.\venv\Scripts\python.exe -m pip install -r legacy/requirements.txt
.\venv\Scripts\python.exe -m uvicorn legacy.app.main:build_app --factory --port 8001
.\venv\Scripts\python.exe -m legacy.app.voice.local
.\venv\Scripts\python.exe -m legacy.scripts.preview
.\venv\Scripts\python.exe -m pytest legacy/tests -q
```

Legacy tests preserve the old behavior and may retain existing failures. They
are not the Vapi acceptance suite. Historical documents may refer to old paths.

## Removing this archive later

Stop any optional legacy process, then remove this entire legacy/ directory.
Normal backend.app.main, backend.app.vapi_api, migrations, bootstrap, active
tests and frontend QA fixture do not require it. Shared calendar, scheduling,
database and business modules must stay. Installed optional packages can remain
unused or be omitted in a clean environment installed from requirements.txt.

The normal staff API no longer exposes /api/demo/* or /api/voice. Existing
frontend custom demo/voice controls are retained but are not functional against
that API; frontend migration to Vapi is separate work. To use those old controls,
run the explicit legacy factory instead.
