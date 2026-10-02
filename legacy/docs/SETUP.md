# Setup and microphone testing

## Dependencies

The existing environment is Python 3.14 on Windows. Keep the existing `venv`.
For a fresh environment, run `python -m venv venv` first.

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.lock.txt
cd frontend
npm ci
npm run build
cd ..
```

`requirements.txt` lists direct dependencies; `requirements.lock.txt` snapshots
the installed environment. The frontend lockfile pins its dependency graph.
Use Node 20.19+ or 22.12+. Other Python versions need fresh-install verification.

## Test with your microphone

The offline preview at localhost is **not** the actual voice application.
Stop both preview terminals with Ctrl+C before starting the real backend and
frontend on ports 8001 and 8000.

1. Edit your existing `.env` privately. Keep your existing provider keys.
   Do not overwrite `.env` with the example file. Add these local-test settings:

```dotenv
DATABASE_URL=sqlite:///ava-local.db
APP_ORIGIN=http://localhost:8000
COOKIE_SECURE=false
ADMIN_EMAIL=YOUR_EMAIL
ADMIN_PASSWORD=YOUR_UNIQUE_PASSWORD_AT_LEAST_14_CHARACTERS
```

2. Confirm `.env` contains `DEEPGRAM_API_KEY`, `GEMINI_API_KEY` and
   `ELEVENLABS_API_KEY`. Live use consumes your provider quotas/credits.
3. Initialize the database and create your staff login once:

```powershell
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m backend.app.bootstrap
```

4. Start the backend from the project root (terminal 1):

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.main:build_app --factory --host 127.0.0.1 --port 8001
```

   Start the Next.js frontend in terminal 2:

```powershell
cd "F:\Abdul Hadi\voice-agent-learning\frontend"
npm run dev
```

   For the production build, use `npm run build` followed by `npm start` instead.
   Both commands use the frontend gateway on port 8000, forwarding REST and
   WebSocket traffic to the backend on 8001. Keep both terminals open. You do
   not need to change the existing `APP_ORIGIN=http://localhost:8000`.
   Optional frontend environment variables: `PORT` (8000), `HOST` (127.0.0.1),
   `BACKEND_URL` (http://127.0.0.1:8001). If changing the public origin, its exact
   value must match the backend's APP_ORIGIN. Do not put provider keys in frontend
   variables or `NEXT_PUBLIC_*` values.

5. Open **http://localhost:8000/login**, sign in with the account you created, and open
   Settings. Enter your business information and approved FAQs. Services and
   opening hours start empty so the application cannot invent a schedule.
6. Open **Talk to Ava → Start voice** (`/dashboard/demo`) and allow microphone access. Use headphones.
   Speak, pause for turn detection, then interrupt Ava while it is speaking.
   Click **Stop voice** to end. Review the call and transcript under Calls.

For the local sounddevice microphone/speaker alternative, use another terminal
from the project root with the same configured database:

```powershell
.\venv\Scripts\python.exe -m backend.app.voice.local
```

Ctrl+C ends local mode. It uses the same receptionist, tools and persistent
records as the browser. You do not need a telephone number or Vapi account.
Google Calendar is required for actual availability/bookings, but not greetings,
configured FAQs or message-taking. Without Google credentials, availability
fails clearly rather than inventing slots.

The existing prototype default `gemini-3.5-flash-lite` is retained. Live access
has not yet been verified for this build; the separate older experiment used
`gemini-2.5-flash`. Do not assume either account/model works without testing.
`GEMINI_MODEL` can override the default after you verify access. ElevenLabs uses
`eleven_flash_v2_5`, PCM 16 kHz, and the existing configurable voice ID.

## PostgreSQL for the deployment

SQLite above is only for local experimentation. For concurrent deployment,
provision PostgreSQL and set a dedicated database/user:

```dotenv
DATABASE_URL=postgresql+psycopg://ava:YOUR_PASSWORD@localhost:5432/ava
```

Then migrate and bootstrap that database separately. SQLite data is not
automatically copied to PostgreSQL. Use provider-required TLS parameters for
managed PostgreSQL. Live PostgreSQL testing is outstanding in this workspace.

Bootstrap refuses to overwrite an existing admin. It stores an Argon2 hash.
Remove `ADMIN_PASSWORD` from `.env` after bootstrap. No public registration or
password-reset email flow is implemented. Migrations own schema changes; back up
before upgrading. Initial migration downgrade deletes the tables.

## Google Calendar authorization

The implemented single-business model uses a **service account with a dedicated
calendar shared to its email**. Google Auth obtains OAuth access tokens; Ava
does not handcraft or log credentials.

1. In Google Cloud Console, select/create a business-owned project.
2. APIs & Services → Library → enable Google Calendar API.
3. IAM & Admin → Service Accounts → Create service account. A broad project
   Owner/Editor role is not required. Do not enable domain-wide delegation.
4. If organizational policy permits local keys: service account → Keys → Add
   key → Create new key → JSON. Keep the downloaded key outside the repository
   in a restricted directory. Do not paste its contents into chat or logs.
5. In Google Calendar, create a dedicated appointments calendar under a human
   business account. Settings and sharing → Share with specific people/groups:
   add the service-account email with **Make changes to events** permission.
   Workspace policy may require an administrator to permit sharing.
6. Under Integrate calendar, copy the Calendar ID, not the public embed URL.
7. Set these variables and restart Ava:

```dotenv
GOOGLE_SERVICE_ACCOUNT_FILE=C:/secure/ava-service-account.json
GOOGLE_CALENDAR_ID=YOUR_CALENDAR_ID
```

8. Check Settings' calendar connection status. Test known busy/free slots and
   confirmed creation/rescheduling/cancellation in a separate test calendar.

This flow does **not** require an end-user OAuth consent screen, redirect URI,
`GOOGLE_CLIENT_ID`, or `GOOGLE_CLIENT_SECRET`. Those belong to a future
user-connected calendar flow, not this service-account deployment. If your
organization forbids downloaded keys, an ADC/workload-identity adaptation is
needed; the file-based adapter does not pretend that authorization is complete.

Scopes: `calendar.events` and `calendar.freebusy`. Events contain a generic title
and internal operation identifiers; caller details remain in the DB. No attendee
invites are sent. Settings APIs never return Google credentials.

Official sources: [service-account authorization](https://developers.google.com/identity/protocols/oauth2/service-account),
[free/busy](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query),
[event insertion](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert),
[event updates](https://developers.google.com/workspace/calendar/api/v3/reference/events/update).

## Before public deployment

Use PostgreSQL, HTTPS, `COOKIE_SECURE=true`, and an exact HTTPS `APP_ORIGIN`.
Start with one worker. A reverse proxy must enforce global login/connection rate
limits, body-size limits including chunked requests, TLS and suitable timeouts.
Test DB backups/restore and decide transcript retention and provider data terms
with the business. Audio recordings are not stored. Card-number redaction is
best effort, not a complete sensitive-data detector.

Uncertain calendar operations appear on Overview. Reconcile retrieves the
existing event before retrying the already-confirmed action. Do not delete the
ledger to bypass its safety block. Google does not provide an atomic
free/busy-and-book transaction; external staff edits can race Ava. Coordinate
manual changes on the dedicated calendar.

A server crash may leave calls active; automatic stale-call recovery is pending.
Browser playback completion is currently measured server-side, not hardware-acked.
Complete [TESTING.md](TESTING.md) live acceptance before real callers.
