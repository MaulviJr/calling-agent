# Current semantic-path diagnostics (2026-10-01)

Use `SEMANTIC_TURN` for production interpretation. Earlier lifecycle descriptions
below include legacy planner terminology; see the final grounding section and
[docs/SEMANTIC_ROUTING.md](docs/SEMANTIC_ROUTING.md) for the current path.

# Voice Turn Debugging Guide

## Reply latency

`VOICE_WAIT_ACKNOWLEDGEMENT` means a turn was still processing after one second
and a short waiting phrase was sent to TTS. It does not mean any tool succeeded.
`VOICE_WAIT_FAILED` is an optional filler failure; the final answer still proceeds.
The final speech waits for any started acknowledgement stream to finish so audio
does not overlap. Each finalized turn gets at most one acknowledgement; startup
greetings do not. This improves feedback during waiting, not model/tool latency.

Compare these stages before changing audio playback: `LLM_COMPLETED` with call_id
(planner), `ACTION_COMPLETED` (controller/tools), `RESPONSE_DRAFT_COMPLETED`,
`RESPONSE_REVIEW_COMPLETED`, and `TTS_FIRST_AUDIO`. The aggregate response-generation
timer includes both draft and review; do not add it again to the separate timings.
`RESPONSE_REVIEW_SKIPPED reason=exact_baseline` means the draft exactly matched
application-authored wording. Changed wording still requires review.

Flux defaults are now `DEEPGRAM_EOT_THRESHOLD=0.7` and
`DEEPGRAM_EOT_TIMEOUT_MS=2000`. The latter forces a final turn after that duration
of silence when confidence has not already finished it. It is not a mandatory wait
for every turn. If Ava cuts off pauses in spoken names/phone numbers, restore
`DEEPGRAM_EOT_TIMEOUT_MS=5000` and restart the backend. Lower latency trades off
tolerance for within-sentence pauses. PCM playback behavior is unchanged here.

This guide describes the current implementation without changing its behavior. The primary path below is the browser voice path. The local microphone path uses the same `VoiceSession`, `Receptionist`, scheduling, calendar, and TTS abstractions, but replaces the browser WebSocket and browser audio with `sounddevice`.

## 1. One voice turn: exact runtime path

### Browser path

1. `frontend/components/voice/VoiceDemo.tsx:toggleVoice()` creates a session with `createVoiceSession()` and calls `start()`.
2. `frontend/lib/voice-session.ts:createVoiceSession().start()` requests microphone permission, creates an `AudioContext`, loads `/audio-worklet.js`, opens `ws(s)://<host>/api/voice`, and sends each worklet message as binary PCM.
3. `frontend/public/audio-worklet.js:AvaCapture.process()` converts the browser input to mono, 16 kHz, signed 16-bit PCM and emits 1,280-sample / 80 ms buffers.
4. `backend/app/api.py:create_app()` registered the WebSocket route `voice()`. It checks `voice_enabled`, the origin, and the session cookie, then calls `backend/app/voice/browser.py:browser_session()`.
5. `browser_session()` accepts the socket, starts a database `Call` with `agent.start()`, loads business settings, constructs `ElevenSpeech`, constructs `VoiceSession`, and enters `flux_connection()`.
6. `backend/app/voice/providers.py:flux_connection()` constructs `DeepgramClient`, opens Deepgram Flux, starts the daemon `ava-stt` listener, and yields the connection.
7. `browser_session.receive()` receives each binary WebSocket packet and calls `connection.send_media(packet)` in a worker thread.
8. Deepgram invokes the callback installed by `flux_connection()`. The callback calls `browser_session.event()` with Deepgram’s event, transcript, and turn index.
9. `browser_session.event()` first calls `VoiceSession.event()`. On `StartOfTurn`, it schedules `clear_audio()`; on a non-empty `EndOfTurn`, it schedules a JSON `transcript` event for the browser.
10. `VoiceSession.event()` ignores interim events and empty/duplicate final events. For a new final event, it enqueues a `Turn` in `pending` and logs `USER_TURN_FINALIZED`.
11. `VoiceSession._run()` removes one `Turn`, logs `LLM_STARTED`, and calls the callback supplied by `browser_session`: `agent.respond(business_id, call_id, transcript, uid())`.
12. `Receptionist.respond()` loads the active call, settings, persisted history and `AppointmentState`; redacts the transcript; chooses a deterministic decision for emergency/card/explicit pending confirmation/escalation cases or calls `GeminiConversationPlanner.decide()`.
13. `GeminiConversationPlanner.decide()` calls Gemini `generate_content()` and validates JSON as `AgentDecision`. Its conversational proposals are advisory; Python still authorizes actions.
14. `Receptionist._act()` applies corrections and the decision. It calls `Scheduling.slots()` or confirmed `Scheduling.mutate()`, or inserts a confirmed `Message`. It returns `TrustedContext`, including any `ToolResult`. No model can execute these tools.
15. `conversation.render_response()` uses exact safety/consent/receipt text, or invokes `GeminiResponseGenerator.generate()` for a draft, local content checks, and a separate grounding review. Failures fall back safely without retrying tools. `respond()` persists the final reply, state, receipt, caller phone and outcome, then returns the reply string.
16. `VoiceSession._run()` logs `LLM_COMPLETED`. If the turn was not interrupted, it calls `browser_session.speak()`.
17. `browser_session.speak()` sends a JSON `reply` event, calls `ElevenSpeech.stream()`, receives PCM chunks from ElevenLabs, frames and paces them with `PcmPacer`, and puts binary PCM frames onto the async `output` queue.
18. `browser_session.send()` removes output items and sends JSON or binary frames through the WebSocket.
19. `frontend/lib/voice-session.ts:receive()` displays JSON `reply`/`transcript` events. For binary PCM it creates an `AudioBufferSourceNode`, queues it for playback, and sends it to the browser speakers.
20. `VoiceSession._run()` calls `Receptionist.delivered()` after speaking. This changes the latest assistant transcript delivery to `played` or `interrupted`. It updates `pending.ready` only when the delivered turn matches `pending.confirmation_turn_id`, so small talk cannot unlock an interrupted readback.

### Local microphone variant

`backend/app/voice/local.py:main()` performs the equivalent setup. `sounddevice.RawInputStream` invokes `capture()`, which places PCM in a bounded `queue.Queue`; the main loop sends those bytes to Deepgram. `VoiceSession` and the agent path are identical. `backend/app/voice/audio.py:play_pcm()` consumes the ElevenLabs stream and writes PCM to a local `sounddevice.RawOutputStream`.

## 2. Files and functions in order

| Order | File | Function or object | Responsibility |
| --- | --- | --- | --- |
| 1 | `frontend/components/voice/VoiceDemo.tsx` | `VoiceDemo.toggleVoice` | Starts/stops the browser session. |
| 2 | `frontend/lib/voice-session.ts` | `createVoiceSession`, `start` | Browser permission, WebSocket, worklet wiring. |
| 3 | `frontend/public/audio-worklet.js` | `AvaCapture.process` | Resampling/PCM framing. |
| 4 | `backend/app/api.py` | `create_app`, `voice` | Registers and authenticates `/api/voice`. |
| 5 | `backend/app/voice/browser.py` | `browser_session`, `receive`, `send`, `speak`, `event` | Browser transport, queues, TTS forwarding. |
| 6 | `backend/app/voice/providers.py` | `flux_connection` | Deepgram connection and STT callback. |
| 7 | `backend/app/voice/session.py` | `VoiceSession.event`, `_run` | Deduplication, interruption, serialized turn worker. |
| 8 | `backend/app/agent.py` | `Receptionist.respond` | Loads state, decides, acts, persists turn. |
| 9 | `backend/app/agent.py` | `GeminiConversationPlanner.decide` | Structured intent, field and conversational-goal proposals. |
| 10 | `backend/app/agent.py` | `Receptionist._act` | Application-owned conversation and tool decisions. |
| 11 | `backend/app/scheduling.py` | `Scheduling.slots`, `mutate`, `_execute` | Availability and durable calendar mutations. |
| 12 | `backend/app/calendar.py` | `GoogleCalendar.busy/get/create/update/delete` | Google Calendar REST calls. |
| 12a | `backend/app/conversation.py` | `TrustedContext`, `ToolResult`, `render_response`, `GeminiResponseGenerator` | Trusted results, language generation, validation/review and fallback. |
| 13 | `backend/app/voice/providers.py` | `ElevenSpeech.stream` | ElevenLabs TTS stream. |
| 14 | `backend/app/voice/browser.py` | `speak` | TTS pacing and output queueing. |
| 15 | `frontend/lib/voice-session.ts` | `receive` | Browser display and PCM playback. |
| 16 | `backend/app/agent.py` | `Receptionist.delivered` | Persists delivery/interruption status. |

## 3. Function contracts

### Transport and audio

| Function | Input / output | Side effects and external calls | Exceptions / callers / next call |
| --- | --- | --- | --- |
| `createVoiceSession(callbacks)` | Callbacks in; `{start, stop}` out. | Creates closure state, audio source set, diagnostics. No provider call yet. Called by `VoiceDemo.toggleVoice`; next is `start`. | `start` catches setup errors and reports through `onError`; `stop` is called by UI, socket close, or cleanup. |
| `start()` | No arguments; promise. | Requests microphone, creates `AudioContext`, loads worklet, creates WebSocket, sends worklet frames. Calls browser APIs. | Catch-all calls `stop()` and `errorMessage`; caller is `toggleVoice`. |
| `AvaCapture.process(inputs)` | Browser audio frames; boolean `true`. | Resamples to 16 kHz and posts transferable PCM buffers. Called by the browser audio engine; next is WebSocket `send`. | No explicit catch. Worklet/browser errors are outside application catch blocks. |
| `create_app().voice(ws)` | Authenticated WebSocket; no return payload. | Checks origin/session, delegates to `browser_session`. | Closes with 1008 for disabled/unauthorized/origin failure; calls `browser_session`. |
| `browser_session(ws, agent, business_id)` | WebSocket, shared agent, business ID; async completion. | Creates call, loads settings, creates TTS/session, opens Deepgram, creates asyncio tasks, sends `ready`, closes and ends call in `finally`. Calls `agent.start`, `flux_connection`, `VoiceSession`, `agent.end`. | `WebSocketDisconnect` is swallowed. Other exceptions log `VOICE_SESSION_FAILED`, attempt JSON error, then call `session.close` and `agent.end`; cleanup errors are swallowed/logged. |
| `receive()` | No arguments; async task. | Reads binary WebSocket packets, validates even PCM length and maximum size, calls Deepgram `send_media` via `to_thread`. | `TimeoutError`, invalid packet `ValueError`, socket errors propagate to `browser_session`; next is `stopped`. |
| `send()` | No arguments; async task. | Reads `output`; sends bytes or JSON over WebSocket. | Send errors propagate to the task and terminate the session. |
| `flux_connection(on_event, on_error)` | STT event/error callbacks; context manager yielding Deepgram connection. | Calls Deepgram API, registers OPEN/MESSAGE/ERROR/CLOSE handlers, starts `ava-stt`, sends close stream on exit. | Provider/setup errors propagate to caller; Deepgram ERROR/CLOSE only invokes `on_error`, which sets stopped. |
| `VoiceSession.event(event, transcript, turn_index)` | Deepgram event name, text, optional index; no output. | Under lock, increments generation/cancels current and queued turns on `StartOfTurn`; enqueues final `Turn`; may close on queue overflow. | Queue overflow sets `failed`, closes, logs `AGENT_QUEUE_OVERFLOW`; caller is Deepgram callback. Next is `_run`. |
| `VoiceSession._run()` | Worker loop; no return. | Serializes agent calls, interruption cancellation, TTS, delivery callback, queue task completion. | Any turn exception sets `failed` and logs `VOICE_TURN_FAILED`; worker remains alive unless closed. |
| `speak(text, cancel)` in `browser_session` | Reply text and cancellation event; no output. | Calls ElevenLabs stream, places JSON reply and paced PCM on output queue, logs TTS metrics. | Stream/queue errors propagate to `VoiceSession._run`; next is browser `send`. |
| `play_pcm(provider, text, cancel)` | TTS provider, text, cancellation event; no output. | Calls provider stream and writes PCM to `sounddevice`. | Provider/audio errors propagate to local `VoiceSession._run`; caller is `local.main` through the `speak` lambda. |
| `receive(event)` in `voice-session.ts` | JSON or ArrayBuffer WebSocket event; no output. | Updates UI callbacks, diagnostics, and scheduled browser audio nodes. | JSON parse/audio API errors are not locally caught; socket error invokes UI error. |

### Agent and model

| Function | Input / output | Side effects and external calls | Exceptions / callers / next call |
| --- | --- | --- | --- |
| `Receptionist.start(business_id, transport, phone, external_id)` | Call metadata; call ID string. | Inserts `Call`; supports external ID idempotency; logs `CALL_STARTED`. | Database errors propagate. Called by browser/local/API demo; next is voice setup or turn handling. |
| `Receptionist.respond(business_id, call_id, transcript, request_key)` | Final transcript and idempotency key; reply string. | Acquires per-call lock; reads call/settings/history; redacts; writes `Call`, `TranscriptTurn` rows, state, receipt, outcome. Calls LLM, `_act`, scheduler, and message insert. | `ValueError` becomes a user-facing validation reply; all other exceptions become a generic message-taking reply and increment `state.failures`. Database write errors after the catch can still propagate. Called by `VoiceSession._run` or text API. |
| `GeminiConversationPlanner.decide(transcript, state, settings, history)` | Caller data and persisted context; validated `AgentDecision`. | Calls Gemini `generate_content` with JSON schema. | SDK/network/validation errors propagate to `Receptionist.respond` catch. |
| `Receptionist._act(...)` | Business/call state, settings, decision, text, key, history; `TrustedContext`. | Updates `AppointmentState`; may call date helpers, scheduler, insert `Message`, and build protected confirmation. | Validation/calendar/database errors propagate to `respond`; caller is `respond`. |
| `GeminiResponseGenerator.generate(...)` | Current turn, recent history, state snapshot, trusted context; checked text. | Two Gemini calls: draft and semantic review. No calendar/database tools. | Local content rejection, review rejection and provider errors propagate to `render_response`. |
| `render_response(...)` | Generator plus grounded inputs; final spoken text. | Logs response latency/fallback; bypasses generator for protected text. | Catches language errors; returns safe baseline or fixed knowledge-failure offer. Never retries a tool. |
| `Receptionist.delivered(bid, cid, interrupted)` | Delivery flag; no output. | Updates latest assistant `TranscriptTurn.delivery` and `Call.state.pending.ready`. | Database/model errors propagate to the voice callback and are logged as `VOICE_TURN_FAILED`. |
| `Receptionist.end(bid, cid, failure)` | Call ID and optional failure; no output. | Marks call completed/failed, records duration/reason, writes deterministic summary; optionally calls Gemini `summarize` and writes AI notes. | Missing call raises `ValueError`; AI summary failures are caught and logged `SUMMARY_FAILED`. Called in voice `finally` or API end route. |
| `GeminiConversationPlanner.summarize(turns)` | Persisted turns; summary string. | Calls Gemini and redacts result. | SDK errors propagate to `end`, where they become a warning only. |
| `redact(text)` | Text; text with obvious card-number patterns replaced. | Pure transformation. | No explicit exceptions. |

### Scheduling and calendar

| Function | Input / output | Side effects and external calls | Exceptions / callers / next call |
| --- | --- | --- | --- |
| `Scheduling.slots(business_id, service_id, day, earliest, latest)` | Desired day/window; list of ISO slot strings. | Reads settings/appointments and calls `calendar.busy` once; validates candidate slots. | Calendar errors propagate. Per-slot `ValueError` from validation is intentionally ignored. Called by `_act`; next is confirmation or no-slot reply. |
| `Scheduling.mutate(business_id, key, kind, payload, confirmed)` | Confirmed create/reschedule/cancel; appointment record dict. | Writes `Operation` before network work; calls `_execute`; writes operation status and appointment. | Validation `ValueError` becomes `rejected`; other errors become `uncertain` plus `CalendarUnavailable`. Called by `_act` or reconcile API. |
| `Scheduling._execute(db, settings, op)` | Locked DB session/settings/operation; `Appointment`. | Calls calendar `get`, then `create`, `update`, or `delete`; writes/updates `Appointment`. | Missing/invalid data raises `ValueError`; remote ambiguity raises `CalendarUnavailable`. Called only by `mutate`. |
| `GoogleCalendar._request(method, path, **kwargs)` | HTTP method/path/request data; decoded JSON or `{}`/`None`. | Authenticated Google Calendar REST request with 15-second timeout. | Network exceptions become `CalendarUnavailable('Calendar request failed.')`; 404/410 becomes `None`; 409 and non-2xx become specific `CalendarUnavailable`. |
| `GoogleCalendar.busy/get/create/update/delete` | Calendar/time/event data; availability, event, or no result. | Google free/busy and event REST calls. | Converts missing calendars/events and provider failures to `CalendarUnavailable`; callers are scheduling functions or calendar status API. |

## 4. Exceptions converted into fallback responses

### Voice path

- `Receptionist.respond()` catches `ValueError`. Structured validation errors keep the fixed `Please check the appointment details...` reply; other validation errors become trusted context for a generated explanation, with the original application error as fallback.
- `render_response()` catches generation, schema, content-check and grounding-review failures. It logs `RESPONSE_FALLBACK`, preserves operational state, and returns the controller baseline. For stored knowledge it uses a fixed trouble-explaining/follow-up offer; for checked calendar results it can use the authoritative slot text.
- `Receptionist.respond()` catches every other exception, logs `AGENT_FAILED`, and speaks `I'm sorry, I couldn't complete that request. I can take a message for the team.` After two such failures it switches the persisted state to message/escalated mode.
- `VoiceSession._run()` catches every exception around one turn, logs `VOICE_TURN_FAILED`, marks the session failed, and does not send an additional spoken fallback.
- `browser_session()` catches every non-disconnect exception, logs `VOICE_SESSION_FAILED`, attempts `{type: "error", text: "Voice connection failed..."}`, and still attempts cleanup/call finalization.
- Browser `start()` catches setup failures, closes local resources, and calls the UI error callback using `errorMessage()`.
- `browser_session()` swallows `WebSocketDisconnect` as a normal end. Cleanup errors from sending the error event, closing the session, ending the call, and closing the socket are suppressed or reduced to `CALL_END_PERSIST_FAILED`.
- `Receptionist.end()` catches AI summary failures and leaves the deterministic summary in place; logs `SUMMARY_FAILED`.

### HTTP/API path

- `api.py:bad_input()` converts `ValueError` to HTTP 400 with its message.
- `api.py:calendar_error()` converts `CalendarUnavailable` to HTTP 503.
- `api.py:server_error()` logs `API_FAILED` and converts all remaining exceptions to a generic HTTP 503.
- `api.py:calendar_status()` catches every exception and returns `connected: false` with a generic sharing/credentials message.
- Login/authentication uses explicit HTTP 401/403/429 responses rather than fallback text.

### Provider boundary conversions

- `GoogleCalendar._request()` converts network exceptions and HTTP failures into `CalendarUnavailable`.
- `Scheduling.mutate()` converts non-`ValueError` execution failures into durable `uncertain` operations, then raises a reconciliation message.
- `Scheduling.slots()` catches candidate-level `ValueError` only and skips that candidate; calendar errors are not swallowed.
- `dates.resolve_date()` catches parser `ValueError`s internally before returning a user-facing date error.

## 5. Mutable and shared state

- Browser closure state: `stopped`, `next`, `sources`, diagnostics, packet timing, and reply-audio flags.
- Browser async queues/events: `output` (`asyncio.Queue`), `stopped` (`asyncio.Event`), and the WebSocket.
- `VoiceSession`: bounded `pending` queue, `closed`, `lock`, `current`, `last_final_index`, `generation`, and `failed`.
- Each `Turn`: transcript, generation, cancellation event, and receive timestamp.
- `Receptionist` dependencies: shared SQLAlchemy session factory, scheduler, and LLM object.
- Per-call conversational state: `Call.state` JSON containing `AppointmentState`, receipts, pending action, offered slots, and failure count.
- Process-wide `_locks` in `agent.py`: 64 `RLock`s selected by call ID hash. PostgreSQL additionally uses a database advisory lock.
- Process-wide scheduling `_sqlite_lock`: serializes SQLite mutations in this process only; PostgreSQL uses row locks.
- API process state: login throttling `attempts`, dummy password hash, and environment-derived provider configuration.
- Database state: `Business.settings`, `Call`, `TranscriptTurn`, `Appointment`, `Operation`, `Message`, and `LoginSession` rows.
- Provider-side state: Deepgram connection/listener, Gemini chat/model clients, ElevenLabs client/stream, and browser audio graph.

## 6. Threads, tasks, queues, and WebSockets

- Browser: one FastAPI WebSocket `/api/voice`; asyncio tasks `receive`, `send`, and `stopped.wait`.
- Browser-to-agent bridge: `asyncio.to_thread` for `agent.start`, Deepgram context enter/exit, `connection.send_media`, `session.close`, and `agent.end`.
- Deepgram: daemon thread named `ava-stt` running `conn.start_listening`.
- Per voice session: daemon thread named `ava-agent` running `VoiceSession._run`.
- Local microphone: `sounddevice` callback thread calls `capture`; bounded `queue.Queue(maxsize=125)` buffers PCM; the main thread sends media.
- Browser output: bounded `asyncio.Queue(maxsize=100)` buffers JSON and PCM; `enqueue` bridges the agent/TTS thread to the event loop with `run_coroutine_threadsafe`.
- Per-session agent input: bounded `queue.Queue(maxsize=16)` buffers finalized turns.
- No application job queue or persistent background worker exists. The provider listener and voice worker are daemon threads and end with the session/process.

## 7. Database writes and calendar mutations

### Every voice call/turn

- `Receptionist.start()` inserts one active `Call`.
- `Receptionist.respond()` updates `Call.caller_phone`, `Call.state`, and sometimes `Call.outcome`; inserts one user and one assistant `TranscriptTurn`; stores an idempotency receipt in `Call.state`.
- `Receptionist.delivered()` updates the latest assistant `TranscriptTurn.delivery` and pending confirmation readiness.
- `Receptionist.end()` sets call end time, duration, status, failure reason, deterministic summary, and optionally AI summary notes.

### Message flow

After confirmation, `_act()` inserts one `Message` if the `(business_id, key)` does not already exist. The key is generated in pending state and makes confirmation idempotent.

### Appointment/calendar flow

1. `_act()` asks `Scheduling.slots()` for availability; this calls Google `freeBusy` and reads local booked appointments.
2. After explicit confirmation, `Scheduling.mutate()` inserts an `Operation(status='pending')` before the network request.
3. `_execute()` calls `calendar.get()` to inspect ownership/recovery state.
4. Create calls `calendar.create()` and then inserts `Appointment`.
5. Reschedule calls `calendar.update()` and updates `Appointment.start_at/end_at`.
6. Cancel calls `calendar.delete()` and sets `Appointment.status='cancelled'`.
7. Success marks `Operation.status='completed'`; validation failures mark it `rejected`; uncertain provider/database failures mark it `uncertain` and block later mutations until `/api/operations/{id}/reconcile` succeeds.

## 8. Symptom-driven debugging

| Symptom | Likely module | Logs or state to inspect | Start here |
| --- | --- | --- | --- |
| Microphone permission/device failure | Browser `voice-session.ts` | Browser console; UI error from `errorMessage`; `AVA_AUDIO_STATS` | `createVoiceSession().start()` |
| No `STT_CONNECTED` | `providers.py` / Deepgram config | Backend startup logs and provider exception; browser WebSocket close | `flux_connection()` |
| Audio connects but no finalized turn | Worklet, WebSocket, or Deepgram callback | Browser `AVA_AUDIO_STATS`; `USER_TURN_FINALIZED`; `AGENT_QUEUE_OVERFLOW` | `AvaCapture.process()` then `VoiceSession.event()` |
| Final transcript appears but no reply | Agent worker or Gemini | `LLM_STARTED`, `LLM_COMPLETED`, `VOICE_TURN_FAILED`, `AGENT_FAILED` | `VoiceSession._run()` |
| Generic “couldn't complete” reply | LLM, state validation, scheduling, or DB | `AGENT_FAILED kind=...`; inspect call state and transcript rows | `Receptionist.respond()` catch blocks |
| “Trouble explaining that information” | Response generation or grounding rejection | `RESPONSE_FALLBACK kind=... context=knowledge`; test approved facts against content-preservation rules | `conversation.check_surface()` and `GeminiResponseGenerator.generate()` |
| Long pause before reply text | Interpretation, tools and action wording | `LLM_STARTED/COMPLETED`, `RESPONSE_GENERATION_COMPLETED latency_ms` | Compare model latency with `TTS_FIRST_AUDIO`; knowledge uses one request; action wording can add one |
| Stutters inside a spoken sentence | TTS provider gaps, server pacing, browser scheduling | `TTS_STREAM_STATS max_provider_wait_ms`, browser `AVA_AUDIO_STATS playbackUnderruns/maxPacketGapMs` | `PcmPacer`, `browser_session.speak`, browser binary receive path |
| Reply text appears but no sound | ElevenLabs, browser output queue, or audio graph | `TTS_FIRST_AUDIO`, `TTS_STREAM_STATS`, `AVA_AUDIO_STATS`; browser console | `browser_session.speak()` or `receive()` binary branch |
| Reply is cut off on interruption | Generation/cancel flow | `TTS_STREAM_STATS interrupted=true`; transcript delivery field | `VoiceSession.event('StartOfTurn')` |
| Calendar says disconnected | Calendar ID/share/scopes | `/api/calendar/status`; direct `test_calendar.py`; backend `CALENDAR_CHECK` | `GoogleCalendar.busy()` |
| No available slots | Settings, timezone, hours, or calendar | `CALENDAR_CHECK`; business settings; Google free/busy response | `Scheduling.slots()` |
| Booking spoken as failed but calendar may contain it | Google timeout/network ambiguity | `BOOKING_FAILED operation_id=...`; `Operation.status='uncertain'`; Google event ID is operation ID | `Scheduling.mutate()` then reconcile |
| Booking is rejected before Google | Input/settings/slot conflict | HTTP 400 or spoken `ValueError`; operation status `rejected` | `Scheduling._execute()` |
| Call remains active after disconnect | Finalization/DB issue | `CALL_END_PERSIST_FAILED`, call status, `VOICE_SESSION_FAILED` | `browser_session()` `finally` |
| Summary missing but call is completed | Gemini summary only | `SUMMARY_FAILED`; `Call.summary_status='deterministic'` | `Receptionist.end()` |

Useful log sequence for one browser turn:

```text
CALL_STARTED
STT_CONNECTED
USER_TURN_FINALIZED
LLM_STARTED
LLM_COMPLETED
RESPONSE_GENERATION_COMPLETED
TTS_FIRST_AUDIO
TTS_STREAM_STATS
```

The current `main.py` sets the `ava` logger to INFO and suppresses `google`, `deepgram`, `elevenlabs`, `httpx`, and `httpcore` to WARNING. Provider SDK debug details therefore require temporary local logging changes or a provider-specific diagnostic script; do not enable them in production without checking for sensitive data.

## 9. More abstract or complex than necessary

These are observations only; this guide does not refactor them.

- `browser_session()` combines authentication-adjacent transport setup, provider lifecycle, asyncio task supervision, TTS pacing, and call finalization. It is the hardest single function to debug.
- `VoiceSession` coordinates a lock, two cancellation generations, a bounded queue, a daemon worker, and delivery persistence. The concurrency is justified by interruption handling but is more complex than a synchronous text turn.
- `Scheduling.mutate()` uses a durable operation ledger, idempotency, remote recovery, ownership markers, and two locked transactions. This protects against double booking and timeouts, but creates a second state machine beside the appointment state.
- `Receptionist.respond()` combines conversation state loading, deterministic intent shortcuts, LLM extraction, action dispatch, persistence, and fallback policy. It is the main coupling point in the application.
- `Receptionist._act()` is a large state machine with booking, rescheduling, cancellation, messaging, FAQ, escalation, emergency, and confirmation branches. A new branch must be checked against state mutation, confirmation invalidation, and persistence.
- Provider adapters expose raw SDK streams directly to transport functions. This keeps files small but makes browser/local TTS behavior diverge.
- `run_coroutine_threadsafe(...).result(timeout=2)` in `enqueue()` synchronously waits from a provider/agent thread on the event loop. It is deliberate backpressure, but can turn a slow browser into a voice-session failure.
- `createVoiceSession()` mixes WebSocket protocol, PCM decoding, playback scheduling, and diagnostics. It is convenient for the frontend but makes transport/audio bugs overlap.

## 10. Suggested simplifications, without refactoring

1. Keep a one-page sequence diagram beside this document showing only the browser path and link each arrow to one function.
2. Add a diagnostic mode that preserves exception class and provider status/reason in server logs while keeping user responses generic.
3. Implemented in this refactor: separate planning, trusted application results, and response generation. Persistent state/actions remain together in the existing controller to limit scope.
4. Implemented: `TrustedContext` carries response meaning, outcome and delivery policy; `ToolResult` carries application-owned tool status/facts. Pending action remains persisted in `AppointmentState`.
5. Give calendar operations a small state transition table (`pending -> completed/rejected/uncertain`) and make reconciliation logs include the operation kind and remote event ID.
6. Centralize browser/local TTS framing and cancellation rules so both transports can be debugged with the same metrics.
7. Add focused integration tests for the real provider boundaries separately from the current fake-calendar and `VoiceSession` tests.
8. Add correlation fields consistently to every voice log (`call_id`, turn index, and operation ID where applicable). Current logs have partial coverage.

## Focused checks

```powershell
.\venv\Scripts\python.exe -m pytest -q tests/test_conversation_generation.py tests/test_gemini_schema.py tests/test_reliability.py tests/test_scheduling.py
.\venv\Scripts\python.exe test_calendar.py
```

`test_calendar.py` performs a read-only `calendars.get` using the configured service account and calendar ID. It prints the provider exception, so keep its output private if it includes request metadata.

## Grounding checks and their limits

Production `SEMANTIC_TURN` records `turn_kind`, `selected_source_ids`,
`resolved_entity_id`, `answer_mode`, `llm_calls` and `fallback_reason` without
caller prose or provider exception bodies. Knowledge/conversation/clarification
uses one request; actions use at most two. There is no grounding-review call.

`semantic.validate_selection` checks typed relations, membership, completeness
and referent/discourse provenance. Unsupported response text falls back to the
validated rendering. Invalid selections or provider failures use a generic
verification/clarification fallback. Existing `check_surface` still protects
action/tool wording and legacy text-only integrations. No fallback retries a tool
or commits an action. See [docs/SEMANTIC_ROUTING.md](docs/SEMANTIC_ROUTING.md).

Run `python -m scripts.replay_semantic_conversation` for the controlled offline
before/after replay. `--live` sends the synthetic payload to the configured Gemini
provider and requires payload authorization. The older `scripts.check_conversation`
exercises the legacy planner/wording path. Neither replay uses a real calendar.

Source selection can still be semantically wrong. Offline tests establish local
validation/controller behavior, not live-model interpretation quality. Live
provider latency and microphone QA remain separate checks.
