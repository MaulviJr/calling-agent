# Ava

A modular voice receptionist: FastAPI, PostgreSQL, Google Calendar and an
authenticated Next.js App Router/TypeScript/Tailwind dashboard. The original learning scripts are
preserved in `testing files/`. No Vapi or telephone provider is integrated.

**Current checkpoint:** backend/dashboard implemented and tested offline.
Live PostgreSQL, AI audio, Google Calendar and telephone acceptance remain
outstanding. The complete production MVP is not yet verified.

Start with [SETUP.md](SETUP.md), especially **Test with your microphone**.
Study [ARCHITECTURE.md](ARCHITECTURE.md) and [DATA_FLOW.md](DATA_FLOW.md).
Verification and manual acceptance are in [TESTING.md](TESTING.md).

```powershell
.\venv\Scripts\python.exe -m pytest -q
cd frontend
npm ci
npm run build
cd ..
```

For an isolated offline frontend preview, run this from the project root in one terminal:

```powershell
.\venv\Scripts\python.exe frontend/tests/fixture_backend.py
```

Then run `npm run dev` from `frontend/` in a second terminal. Open
http://localhost:8000/login using `qa@example.test` / `frontend-qa-only-123`.
This fixture uses temporary SQLite, an in-memory calendar and a stub text responder;
it never reads `.env`, writes your real DB or calls speech providers. Voice is
disabled. Never use the fixture credential as a deployment credential.
The original `scripts.preview` is a legacy static preview, not the Next application.

For the actual application, configure `.env`, migrate, bootstrap, and run:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:build_app --factory --host 127.0.0.1 --port 8001
```

In another terminal, run `npm run dev` from `frontend/`, then visit
http://localhost:8000. For production, use `npm run build` and `npm start`.
The frontend gateway preserves the backend's existing cookie, Origin and
WebSocket contracts. See [frontend refactor](docs/FRONTEND_REFACTOR.md).

Implemented: explicit appointment state, confirmation gates, real Google adapter,
idempotent mutation recovery, calls/transcripts, messages/escalation, summaries,
staff login, metrics, settings and local/provisional browser audio transports.
One deployment serves one business and one capacity-one calendar. Multiple
clinicians/calendars, public browser voice, live transfer and automatic recovery
of calls left active after a crash are not implemented.

See [telephony options](docs/TELEPHONY_OPTIONS.md). Provider implementation is
paused at the user's explicit request, pending a provider decision.
