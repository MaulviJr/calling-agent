# Frontend refactor plan and verification

Scope: frontend architecture/readability only. Backend Python, migrations,
database files and audio-worklet bytes must remain unchanged.

Audit: frontend/src/main.tsx held the entire React app, virtual page navigation,
API calls, generic Record<string, any>, browser dialogs and live audio. Vite
served a static bundle through FastAPI. That was an implementation shortcut,
not a requirement or a suitable final structure. The baseline build now fails
because Vite is absent from the local installation.

Next 16.3.6 and Tailwind 4.3.3 are already installed at the repository root, but
there are no Next routes. Preserve the root package files; frontend/ becomes
the independently installable application.

1. Runtime checkpoint: App Router, Tailwind, explicit types, shared layout and
   login. A frontend gateway keeps localhost:8000 and forwards /api HTTP and
   WebSocket upgrades unchanged to FastAPI on 8001. No auth/Origin changes.
2. Screen checkpoint: overview, calls and real call-detail route, appointments
   with dialogs, messages, settings sections. Keep backend decisions in FastAPI.
3. Voice checkpoint: extract the existing browser session into a typed helper
   and client component. Preserve worklet bytes, media constraints, PCM format,
   websocket messages, clear, pacing and shutdown behavior.
4. Verification/cleanup: route/auth refresh, existing data flows, dialogs,
   mocked audio tests and live local proxy contract checks, production build, formatting and source
   hashes. Update setup/architecture/data flow docs; retire Vite source after
   replacement verification. No telephony work.

Why a gateway: the existing FastAPI Origin policy expects the public origin,
and the browser voice URL is same-origin /api/voice. Moving the UI to a separate
public port would require changing those contracts. The small Node gateway
passes bytes, cookies and Origin through; it owns no business APIs. The Next
custom server must run with npm start, not standalone output or static hosting.

Use frontend/tests/fixture_backend.py for isolated browser QA. It seeds only a
temporary test DB and cannot call paid providers. Never test mutations on the
user's ava-local.db. Hash baseline recorded before editing proves scope.

## Completed checkpoints (2026-09-28)

- Runtime: development server ran with authenticated login and protected-route
  redirects verified in the browser. No backend authentication changes.
- Screens: each requested route now has a server page wrapper and a feature
  component. Calls have a deep-linkable detail page. Settings are split by
  business details, scheduling, hours, services and knowledge. Message status and
  settings persistence were checked through the UI.
- Dialogs: invalid reschedule input displays the backend error; valid reschedule
  and cancellation update the table using an offline calendar and disposable DB.
  Native dialogs replace prompt/confirm and retain focus management.
- Voice: the original worklet is byte-identical. The extracted session retains
  microphone constraints, binary PCM upload/playback, timing and clear events.
  Six regression tests cover those behaviors plus backpressure, denied permission
  and cleanup while permission is pending. Typed demo start/turn/end works.
- Production: Next build, type generation/check and Prettier check pass. The
  production server ran; login, logout, route navigation and refresh were exercised.
  Gateway checks verify authentication, HttpOnly cookies, Origin rejection,
  original worklet bytes, binary WebSocket frames and clear events.
- Existing backend suite: 26 tests pass (two existing dependency deprecations).
- Scope: all 22 protected source/migration/database/worklet hashes match
  `docs/checkpoints/frontend-protected-hashes.json`. No backend, migration,
  real database, .env or root dependency file was edited.
- Visual review: the existing design is retained. Appointments and settings
  fit the narrow viewport without page-level horizontal overflow; tables and
  navigation retain their internal scrolling.
  `docs/screenshots/next-dashboard.png` records the production UI with fixture data.

`docs/checkpoints/frontend-before-next.zip` preserves the old main.tsx,
style.css and index.html for reference. Their active Vite source files have
been removed. Old ignored dist output and the backend's legacy static routes
are not part of the Next runtime and remain untouched to respect backend scope.

Live microphone/provider acceptance was not rerun during this refactor. The
automated audio doubles and transport echo verify code/protocol behavior, not
hardware acoustics or live provider latency. Follow SETUP.md for real microphone
testing. Feature development and telephony remain paused at this checkpoint.
