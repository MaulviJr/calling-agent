# Repository audit and checkpoints

Inspected all eight Python sources, HTML test page and three Markdown files.
The existing FastAPI binary WebSocket passed an in-process 2,560-byte smoke test.
All prototype Python files parse; 20 audio devices were reported. No automated
test suite, dependency manifest, database, auth, calendar or product UI existed.
The folder is not a Git repository. Original scripts are preserved unchanged.

Reusable: Deepgram Flux, 16 kHz/80 ms PCM, separate STT/agent workers, Gemini
chat, ElevenLabs streaming PCM, sounddevice playback and Event cancellation.
Problems: unbounded queues, duplicate final events, stale-response cancellation
race, import-time side effects, text browser incompatible with binary server,
incorrect transcript access in standalone deepgram_test.py, no durable state.
Provider credentials are present; values were not printed. Live provider/audio
acceptance remains distinct from offline verification.

Target: one FastAPI application, small provider adapters, one deployment per
business, PostgreSQL with Alembic, serialized calendar mutations, validated
conversation state, same controller for local/browser/adapted telephony,
same-origin authenticated admin UI. Calendar service account is suitable for
this single-business deployment; staff explicitly share a dedicated calendar.

1. Voice core: isolate adapters, bound queues, fix cancellation and deduplication.
2. Structured conversation/tool state, validated settings and date handling.
3. SQLAlchemy persistence and migrations; scoped repositories and staff auth.
4. Google calendar, availability, durable idempotency and mutation locking.
5. Booking confirmations, knowledge, messages, escalation, summaries.
6. Protected API and analytics.
7. Responsive dashboard.
8. Browser/local core transport and authenticated telephony adapter contract.
9. Failure/concurrency tests and integration checks.
10. Setup, architecture, data flow and manual acceptance documentation.

Every stage uses offline tests; no test spends provider credits. Live Google,
microphone and phone acceptance requires configured external services.

## Dashboard checkpoint

Milestones 1-7 have implementations and offline checks; live external-provider
acceptance remains outstanding. Provisional browser audio exists. At the user's
request, pause before telephony provider selection/integration (Milestone 8).
See TELEPHONY_OPTIONS.md. No telephony SDK/webhook has been added.

Verification: 26 offline tests, TypeScript/Vite build, dependency consistency,
actual browser login/settings/text-call/transcript/summary checks. Live PostgreSQL,
AI audio and Google operations are not yet verified. Reliability and documentation
were developed incrementally alongside these milestones. There is no Git repository,
so checkpoints are recorded here rather than as commits.
