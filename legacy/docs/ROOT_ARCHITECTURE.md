# Ava architecture

The business backend is a modular monolith: one FastAPI app, one relational DB
and direct module calls. A separate Next.js App Router frontend serves the staff
workspace. No Redis, message broker, SIP stack or Vapi dependency.

| Module | Owns |
|---|---|
| `voice/session.py` | Unique final turns, bounded queue, worker and cancellation |
| `voice/providers.py` | Deepgram/ElevenLabs SDK calls and retained Gemini chat adapter |
| `voice/audio.py`, `local.py` | Local PCM transport connected to the receptionist |
| `voice/browser.py` | Provisional staff WebSocket audio transport |
| `agent.py`, `prompts.py` | Structured planning, persistent state, controlled tools, call lifecycle |
| `conversation.py` | TrustedContext/ToolResult, language generation, grounding checks and fallbacks |
| `business.py`, `dates.py` | Validated settings and business-timezone date handling |
| `scheduling.py`, `calendar.py` | Availability, serialized mutations, Google adapter |
| `database.py`, `migrations/` | Relational persistence and frozen schema history |
| `api.py` | Authentication, scoped routes, analytics; legacy static serving retained unchanged |
| `frontend/app/` | Next.js App Router pages, authenticated server layout and global styles |
| `frontend/components/` | Readable, typed staff UI grouped by feature |
| `frontend/lib/` | API client, server session check, types, formatting and browser voice session |
| `frontend/server.mjs` | Next HTTP server and transparent API/WebSocket gateway |
| `frontend/public/audio-worklet.js` | Original browser capture worklet, unchanged |

## Frontend boundary

The old Vite entry point has been replaced with Next.js, TypeScript and Tailwind.
Routes are `/login`, `/dashboard`, `/dashboard/calls`, `/dashboard/calls/[id]`,
`/dashboard/appointments`, `/dashboard/messages`, `/dashboard/settings` and
`/dashboard/demo`. Links support direct navigation, refresh and browser history.
`app/dashboard/layout.tsx` validates the HttpOnly session with FastAPI on the
server. Route wrappers and static presentation use server components. Interactive
lists, forms, navigation and voice use explicit client components and React state;
no extra state library is involved. FastAPI independently authorizes every API call.

`lib/types.ts` describes calls, transcript turns, appointments, messages, settings,
services and overview responses. The shared API client uses same-origin cookies
and redirects expired sessions to login. Settings components edit a typed draft;
availability, booking validation, business rules and persistence remain entirely
in Python. Appointment confirmation uses an accessible native dialog/form.

The existing visual CSS is formatted in `app/globals.css`; Tailwind theme and
utilities are enabled without Preflight resetting the existing design. Prettier
keeps JSX expanded and readable. See `docs/FRONTEND_REFACTOR.md` for checkpoints.

Run the public Node gateway on port 8000 and FastAPI internally on 8001. The
gateway forwards `/api/*`, `/health` and `/api/voice` upgrades without changing
Cookie, Origin, JSON or binary frames. This preserves the existing APP_ORIGIN
and authentication/audio contracts. Other requests go to Next, including its
development HMR upgrades. Use `npm start` after `npm run build`; plain static
hosting, `next start` and Next standalone output do not run this gateway.
The frontend has no new backend API or telephony adapter.

`VoiceDemo` owns conversation UI; `createVoiceSession` owns browser resources.
Capture remains mono with echo cancellation/noise suppression, an AudioWorklet,
16 kHz signed PCM, binary WebSocket frames and timed AudioBufferSource playback.
`clear` stops queued sources. Cleanup also handles leaving the route while
microphone permission is pending. No STT, TTS or agent protocol was changed.

## State and tool safety

TranscriptTurn is natural-language history. AppointmentState is operational
state: caller fields, service/date/time, offered/selected slots, pending action,
message/escalation fields and bounded request receipts. An Appointment row and
its matching Google event establish a booking, not something said in chat.

Production turns use `GeminiResponseGenerator.interpret()` with a strict
`SemanticDraft` schema. One call interprets intent, selects sources/entities,
proposes discourse changes and drafts the answer. Python validates IDs and factual
relations. No LLM classifier precedes this call and no grounding review follows it.
See [docs/SEMANTIC_ROUTING.md](docs/SEMANTIC_ROUTING.md) for both schemas.

Existing safety/privacy and explicit pending-confirmation guards run first.
Knowledge, conversation and clarification use one provider invocation. Action
proposals enter the existing `_act()` controller with at most one additional
bounded wording call. Ownership, slots, confirmation readiness, settings
fingerprints, idempotency and completed receipts remain application-owned.
The model has no executable tools. Automatic SDK function calling is disabled.

`AgentDecision`, `Decision`, `GeminiExtractor` and `LLMProvider.decide()` remain
compatible for generate-only integrations. Only those integrations retain the old
local semantic router. The default generator uses the new semantic path. Schemas
use `response_json_schema` and strict local Pydantic validation.

### Grounding boundaries and limits

Factual answer modes render from selected current typed records or approved FAQ
answers. Python checks membership, staff predicates, list completeness, referent
provenance and memory IDs. Unsupported wording falls back to validated relations;
invalid selections/provider failures use a generic verification/clarification
fallback. No fallback retries a model or tool. Memory stores references, not
business facts, and cannot overwrite settings.

Safety, consent readbacks and completed receipts remain exact Python text.
Calendar/tool wording retains existing local checks. The smallest semantic path
bounds factual wording rather than claiming arbitrary prose entailment can be
proven locally. A valid source can still be semantically irrelevant.

The packet is bounded and reports coverage. Partial catalogs cannot authorize
complete lists. Offline tests verify application behavior, not live-model
interpretation accuracy. The saved before/after replay is explicitly controlled
and offline; live replay requires approval for its external payload.

### Response classification

| Responses audited in `respond`, `_act`, `_confirmation_text`, `end` | Treatment |
|---|---|
| Emergency, medical boundary, card warning | A: exact deterministic safety text |
| Inactive call, empty turn, turn limit, invalid structured output, provider/system failure | A: deterministic error |
| Booking/message/cancel/reschedule consent, interrupted readback, greeting with pending consent | A: exact readback linked to its transcript turn |
| Greeting, capabilities, unknown request, hearing/AI identity/history/interruption/wellbeing | B: generated conversation from capability facts/history |
| Name, phone, email, date, service, message and reference questions | B: generated wording; Python selects the next required field |
| FAQ, services/prices, hours, name, phone, location, policy | C: approved context plus constrained generated wording |
| Missing information/services, changed settings, invalid slot/date/input | C: trusted condition plus generated explanation; deterministic fallback |
| Slot offers/no slots and ownership verification failure | C: explicit ToolResult plus constrained wording |
| Staff follow-up and absence of live transfer | C: trusted capability context; no invented transfer |
| Saved message, completed create/cancel/reschedule | C: completed ToolResult; receipt sentence deliberately remains protected/exact |
| Call outcome and summary | Deterministic outcome/baseline, separately labelled AI notes |

Booking requires a saved pending payload and stable operation key. Only a small
explicit set of affirmative utterances can execute it. Changed details or clinic
settings invalidate confirmation. Interrupted voice confirmations must be repeated.
Pending voice consent stores `confirmation_turn_id`; only delivery of that exact
readback updates readiness. Delivering later small talk cannot unlock consent.
Corrections are applied before conversational branches, so a mislabelled social
turn with extracted changed fields still invalidates previous consent.
Caller cancellation/reschedule requires a high-entropy reference and matching
phone; staff mutations require login and confirmation. No phone-only lookup.

## Threads, queues, asyncio and cancellation

For a caller turn still processing after one second, VoiceSession uses a single
timer to speak a short acknowledgement through the existing TTS callback. It
alternates “Let me check that.” and “Just a moment, please.” No additional model
request is made. The timer is cancelled/joined before final speech, preventing
overlapping TTS streams. Both use the same cancellation flag. Fast responses,
cancelled turns and startup greetings do not get filler. An acknowledgement has
no delivery callback and cannot mark pending consent ready. In browser mode it
is visible as transient reply text, but is not persisted as an agent turn.
It masks some waiting; it does not accelerate tools/models and may briefly delay
a final answer that becomes ready while the acknowledgement is being spoken.

Browser startup sends the configured greeting in `ready`, then queues that same
text as outbound speech on VoiceSession's worker. It bypasses Gemini and caller
turn persistence, uses the existing TTS/PCM path, and can be interrupted by
StartOfTurn. No extra reply event is sent for the greeting, preventing duplicate
UI text. Greeting completion never updates pending appointment consent.

Flux now defaults to turn confidence 0.7 and a 2000 ms silence timeout, configured
through DEEPGRAM_EOT_THRESHOLD and DEEPGRAM_EOT_TIMEOUT_MS. Previously the values
were 0.85 and 5000 ms. This reduces the maximum silence wait for uncertain turns,
not every turn by a fixed amount. Longer pauses while speaking a phone number may
need the old timeout. Only finalized turns execute controller actions; speculative
turns are still ignored. Planner, controller, draft, review and TTS timings are
logged separately to locate remaining delay. Live latency is not established by
unit tests.

Local input uses 16 kHz mono PCM in 80 ms blocks. The sounddevice callback only
copies into a bounded queue. The main thread sends PCM. Deepgram has a listener
thread, while one agent worker handles reasoning/tools/TTS. Expensive work never
runs in the STT callback. Only unique nonempty EndOfTurn triggers reasoning.

A threading.Event is a thread-safe flag. Every reply gets its own Event;
StartOfTurn sets it and it is never cleared/reused. A generation counter covers
the gap between queue removal and setting the active reply. Cancelled finalized
turns still reach state handling, but stale output is suppressed. Local playback
writes 20 ms blocks. Cancellation cannot undo heard audio or a committed action.
Provider reads have timeouts but cannot always abort instantly while awaiting bytes.

Browser mode uses asyncio tasks for input/output and a thread for blocking SDK
work. An asyncio queue delivers worker output to the event loop. The worklet
averages device-rate samples into 16 kHz PCM; this is a simple development
resampler. `clear` stops queued browser sources. Input/output are separate streams;
PCM sending now uses a frame deadline that includes enqueue overhead, avoiding
cumulative drift from sleeping a full frame after every send. Browser playback
reserves 80 ms at startup/underrun and keeps queued frames contiguous. This small
jitter reserve does not reduce the separate Gemini decision latency.
headphones help acoustic echo. Live browser audio QA is outstanding. Server-side
delivery does not yet constitute hardware playback acknowledgment.

## Database and tenancy

SQLAlchemy maps objects to relational tables. A `sessions.begin()` block commits
writes together or rolls them back on error. Alembic tracks frozen migrations;
future schema changes require new revisions rather than editing deployed 0001.

Tables: Business, Admin, LoginSession, Call, TranscriptTurn, Appointment, Operation,
Message. Bounded services/hours/FAQs are validated JSON on Business. Escalation is
a structured Message flag; caller fields stay with appointments/messages instead
of adding a premature CRM. One deployment owns one business, one credential pair,
one capacity-one calendar. Staff queries derive business_id from the login,
never an untrusted tenant parameter. Credential files remain server-side.

PostgreSQL is the deployment database. SQLite is only for local tests. PostgreSQL
Business row locks serialize Ava booking writers across processes. A per-call
advisory lock holds a dedicated DB connection while the controller uses short
transactions. An advisory lock is an application-chosen lock; cooperating code
must use the same convention. SQLite uses Python process locks, so its passing
tests do not establish PostgreSQL multiprocess correctness.

## Idempotency and the Google boundary

Idempotency means retrying a logical request produces one result. Operation has
a unique business/key pair. Different arguments cannot reuse that key. Its ID
is also the stable Google create-event ID, so a lost response does not require a
new event ID. Before a network mutation, the pending operation is committed.

Then, under a Business row lock: retrieve/check Google, validate the slot again,
create/update/delete, save the appointment and mark the operation completed in
the same local transaction. A provider failure leaves an uncertain operation
that blocks competing mutations. Staff reconcile by retrieving the deterministic
event and its operation marker. ETags condition updates/deletes on the version
read. There is no blind duplicate-producing retry loop.

Google is availability truth. Partial free/busy errors fail closed. Reschedule
uses paginated expanded events to exclude exactly the original event. Python
validates service duration, hours, buffers, notice and advance window. Manual
external edits do not take Ava's DB lock; Google has no atomic availability-and-
insert transaction, so conflicts against external writers remain a documented limit.

Dates resolve in the business IANA timezone. Next Friday means the next occurrence
strictly after today; month/day without year rolls forward. Bare times need AM/PM.
Nonexistent/ambiguous DST wall times are rejected. Searches use a 15-minute grid
and return at most 12 slots; validation requires five-minute boundaries.

## Authentication, summaries and failures

pwdlib/Argon2 hashes passwords. Random cookie tokens are stored as SHA-256 hashes
with eight-hour expiry. Cookies are HttpOnly/SameSite Strict; production requires
Secure. Mutation requests and WebSockets check APP_ORIGIN. Login throttling is
process-local; deployment requires proxy-level limits as documented in SETUP.

Call end first commits duration/status/outcome and a deterministic summary.
Gemini may append labelled AI notes; failure preserves the baseline. Analytics
uses structured records, not summary text. Event logs contain fixed names/IDs
and exception classes, not transcript text or raw provider error bodies. Voice
measures generation and first-audio latency. Full structured JSON aggregation
and speech-end-to-audio instrumentation remain for reliability work.

Provider failures offer follow-up rather than claiming success. DB failure may
prevent transcript saving; the durable operation ledger allows transaction
recovery. Emergency recognition combines explicit examples and model intent;
it is not exhaustive clinical triage or diagnosis. Audio is not recorded.

## Planned only

Telephone adapters, provider webhook validation, telephone codecs, live transfer,
hardware playback acknowledgment, multi-clinician capacity and automatic stale-call
recovery are not implemented. Telephony implementation is paused at the user's
request. See `docs/TELEPHONY_OPTIONS.md` before selecting a provider.
