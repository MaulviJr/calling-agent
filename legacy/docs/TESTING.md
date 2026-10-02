# Single-call semantic checkpoint (2026-10-01)

Knowledge/conversation/clarification uses one structured call; actions use at most
two. No LLM grounding review. The regression suite covers all ten reported caller
turns, grounding failures, referent memory and transaction safety. See
[docs/SEMANTIC_ROUTING.md](docs/SEMANTIC_ROUTING.md) and the controlled offline
[before/after replay](docs/CONVERSATION_REPLAY.md). Live interpretation remains
unverified: network restrictions and approval review blocked the external payload.
Older dated checkpoints below describe previous implementations.

# Verification

Audio pacing correction: backend tests simulate send overhead and provider stalls;
frontend tests simulate near-deadline packet arrival, underruns and interruption.
Live acoustic smoothness still needs a microphone/headphone check. User logs show
successful extraction but 2–6 seconds in decision handling; the pacing correction
does not remove that provider latency.

Provider fix (2026-09-28): the Gemini schema error was reproduced as HTTP 400
`INVALID_ARGUMENT` for `additional_properties`. Switching to response_json_schema
passed a live synthetic extraction using the configured model. Three offline
SDK wire-format cases cover the schema field and rejection of invalid actions
and extra fields. A Deepgram Flux handshake succeeded without sending audio;
the earlier Windows DNS error was not reproducible during that check. This does
not establish full live microphone/STT/TTS acceptance.

```powershell
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall -q backend
.\venv\Scripts\python.exe -m pip check
cd frontend
npm run typecheck
npm run format:check
npm test
npm run build
cd ..
```

Next.js refactor checkpoint: 26 backend tests and six frontend audio regression
tests pass; TypeScript, formatting and the Next production build pass. The gateway
contract check passes for HTTP authentication, cookie forwarding, Origin rejection,
unchanged worklet bytes, WebSocket binary PCM and clear events. No automated test
uses provider credits or records a microphone.
Original interactive scripts are excluded from discovery. There are two upstream
Starlette/httpx/anyio deprecation warnings. No Python linter was preconfigured;
compileall is a syntax check, not a lint claim.

Covered: unique/empty/interim STT; interruptions during reasoning/output/queued
turns; normal and duplicate booking; missing name/phone; date/time/DST validation;
unavailable/alternative slots; changed date/time/settings; confirmation gates;
two concurrent SQLite attempts; ambiguous provider timeout recovery;
reschedule/cancel; FAQ/emergency/message/escalation; invented slot rejection;
AI summary failure; auth/origin/tenant isolation; migration up/down and reopen
persistence; Google partial free/busy errors and reschedule pagination.

Browser checks use `frontend/tests/fixture_backend.py`, a temporary database and
offline providers: login/protected routes, overview, call detail/transcript,
appointment reschedule/cancel dialogs and backend validation feedback, message status, settings
save, typed conversation and ending the call. These checks do not establish live
speech/provider/calendar operation. The retained worklet is byte-for-byte unchanged.

For the gateway contract check, stop any real application first. Start the fixture
in terminal 1 and the built Next server in terminal 2:

```powershell
.\venv\Scripts\python.exe frontend/tests/fixture_backend.py --transport-echo
```

```powershell
cd frontend
npm start
```

In terminal 3, from the project root:

```powershell
.\venv\Scripts\python.exe frontend/tests/check_gateway.py
```

The opt-in echo endpoint exists only in the test fixture. It checks transport,
not production voice authentication or speech. Do not use it for microphone tests.
Remove `--transport-echo` for normal offline UI QA. The fixture credentials are
documented in README and are never intended for a real deployment.

## Live microphone checklist

Follow SETUP.md first; use headphones and a dedicated test calendar.

| Say/do | Expected |
|---|---|
| Greet Ava, pause | One reply after the finalized turn; measure latency |
| “Friday at 5” | Clarify AM/PM; resolve in business timezone |
| “Friday afternoon” | Query real Google slots |
| “Actually Monday” | Clear old slot/confirmation; check Monday |
| Change the requested time | Repeat updated details before mutation |
| Interrupt while Ava speaks | Stop future audio; process new final turn |
| Interrupt during LLM wait | Suppress stale audio reply |
| Interrupt confirmation, then say yes | Repeat confirmation; no early booking |
| Request occupied time | Offer valid alternatives |
| Ask a configured FAQ then resume | Approved answer; preserve booking fields |
| Omit name/phone | Ask one missing field; no mutation |
| Confirm twice | One Google event and DB appointment |
| Two callers target one slot | At most one Ava booking; no silent conflict |
| Google unavailable/permissions removed | No success claim; follow-up offer |
| Lose response after creation | Uncertain ledger item; reconcile without duplicate |
| Reschedule into busy slot | Reject, retain old event |
| Cancel with valid reference/phone | Confirm; remote deletion and local cancellation |
| Ask for human | Collect/confirm follow-up message; no fake transfer |
| Clinical advice or urgent symptoms | No diagnosis; urgent professional help guidance |
| Restart application | Persistent records remain |
| Sign out / expire session | Protected API denies access |
| Narrow mobile viewport | Usable forms/navigation without page-level overflow |

## Remaining gates

Live PostgreSQL migrations and separate-process locking; live Gemini model/schema
access, Flux connection and ElevenLabs playback; browser/microphone latency,
disconnect/backpressure and playback completion; live Google operations/recovery;
provider decision and real inbound phone calls; production TLS/rate limits,
backups/restore and retention. Crash recovery of abandoned active calls is pending.
Do not mark acceptance A–L complete on the basis of offline tests.
# Knowledge fallback regression fix (2026-09-29)

Added regressions reproducing valid service descriptions and equivalent FAQ
sentence structure being rejected by ordered-word matching. Knowledge now uses
semantic review; the ordered-word check remains for tool results. Tests cover
clarification/out-of-scope context, useful service fallback on provider failure,
and privacy-safe rejection reason codes. Live synthetic checks exercise the real
Gemini planner, generator and reviewer without a database or calendar connection.
These checks sample provider behavior; they do not prove universal grounding.

# Conversation architecture checkpoint (2026-09-28)

The planner/controller/response-generator refactor passes 68 backend tests.
The browser voice regression suite passes all 7 tests; frontend typechecking and
Prettier checks also pass. Tests use temporary SQLite, a fake calendar and mocked
Gemini responses/HTTP transport. They do not create real appointments or establish
live microphone quality or live-model grounding reliability.

Coverage includes conversational/meta context, the requested FAQ grammar example,
added/removed staff facts, unknown prices, false availability, protected booking
receipts, provider failure, idempotency, field corrections, emergency/card handling,
and interrupted consent followed by successfully delivered small talk. The latter
must not unlock booking consent. Wire tests check both new generation schemas
against the installed Gemini SDK without enabling executable tools.

Normal generated turns add a draft and grounding-review request. Compare
`RESPONSE_GENERATION_COMPLETED` with TTS first-audio and browser underrun metrics
when measuring the live experience; passing unit tests is not an audio QA result.

