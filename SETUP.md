# Active backend setup

From the repository root:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m alembic upgrade head
```

Configure the private .env using .env.example. Keep credentials out of version
control. Preserve the existing DATABASE_URL and Google Calendar configuration;
no database or credentials are moved by the legacy isolation.

Run the staff API and Vapi webhook API in separate terminals:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:build_app --factory --host 127.0.0.1 --port 8001
.\venv\Scripts\python.exe -m uvicorn backend.app.vapi_api:build_app --factory --host 127.0.0.1 --port 8002
```

Expose the Vapi server through the configured public HTTPS address. The saved
assistant's tool and event URLs must point there. See docs/VAPI_ACTION_TOOLS.md.
The Next.js dashboard continues using its existing staff API configuration.

To generate assistant JSON offline:

```powershell
.\venv\Scripts\python.exe -m backend.app.vapi_config
```

To update the saved assistant and tools through Vapi's API (network calls):

```powershell
.\venv\Scripts\python.exe -m scripts.configure_vapi_actions
```

Original setup/bootstrap details are preserved in legacy/docs/SETUP.md. Custom
microphone/STT/TTS/Gemini installation is optional: see legacy/README.md.
