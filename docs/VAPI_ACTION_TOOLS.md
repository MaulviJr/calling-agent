# Vapi action tools

This extends the initial read-only milestone with seven tools. The saved Vapi
assistant now has nine tools, including business and staff information.

| Tool | Backend behavior |
| --- | --- |
| check_availability | Read active service slots against business hours, booking rules, database appointments and Google Calendar |
| get_appointment | Require appointment reference and original booking phone; return only minimal appointment facts |
| create_appointment | Prepare a checked booking and return an action token and exact confirmation text |
| cancel_appointment | Verify the appointment and prepare cancellation |
| reschedule_appointment | Verify the appointment and prepare moving it to a checked slot |
| leave_message | Prepare a staff message with callback details |
| confirm_action | Verify call evidence and commit the prepared action; retries use the same token |

## Runtime

Vapi sends authenticated tool requests to `/api/vapi/tools`. FastAPI resolves the
saved assistant to its configured business. `vapi_actions.py` validates arguments
and uses the existing scheduling/database/calendar layers. Business IDs are never
caller-supplied arguments. The custom agent, conversation, semantic and legacy
voice modules are outside this path.

Prepare tools do not perform mutations. Python records the exact action and
read-back in minimal per-call database state. Authenticated Vapi events must show
the matching assistant speech, that turn stopping, and a later final caller
transcript with unconditional agreement before `confirm_action` can commit.
An interruption during the read-back or a follow-up question revokes confirmation
evidence while retaining the draft. A changed prepared payload replaces its token.
Missing evidence
fails closed. Tokens expire after ten minutes or a settings change, are scoped
to the business and call, and completed tokens return the recorded result.

Speech comparison allows equivalent voice formatting of whole-hour times,
zero-padded days and spaced phone digits. It does not accept changed times or
other changed action details. Speech and final transcript webhooks may arrive
out of order: authorization uses their event timestamps, not arrival order.
A premature affirmative remains unverified rather than falsely expiring the
token. An interruption during the matching read-back requires a fresh full
read-back and subsequent agreement. Interruptions outside that interval do not
revoke consent. Event timestamps define the interval, including delayed events.
Non-affirmative caller responses require a read-back after that response before
a later affirmative can authorize the draft. `VAPI_CONFIRMATION_STATE` and
`VAPI_CONFIRMATION_BLOCKED` logs report reasons without caller details.

Caller consent currently accepts a conservative set of short English affirmative
responses. Ambiguous or conditional responses require another read-back. Event
delivery and read-back behavior must be checked in a live call; offline tests do
not establish that production Vapi delivers every event in the expected order.

Calendar writes reuse the existing idempotent operation/reconciliation mechanism.
Uncertain results never become spoken success through the backend response. Call
state and outcomes are saved, but full transcript reconciliation, recordings and
frontend call-tracking integration are still separate work.

## Configuration

The private `.env` enables `VAPI_ACTIONS_ENABLED=true` and sets
`VAPI_CALENDAR_BUSINESS_ID` to the business owning the configured Google Calendar.
`VAPI_ACTION_TOOL_IDS` stores saved Vapi tool IDs, alongside the two existing read
tool IDs. Credentials remain private and are not embedded in generated JSON.

The current calendar configuration belongs to one business. Other mapped
businesses may use read tools, but calendar actions are rejected until their own
calendar credentials/routing are implemented. Do not map several businesses to
one calendar accidentally. PostgreSQL is required for shared scheduling locks
across multiple backend processes; SQLite is suitable for local testing only.

Restart the Vapi backend after configuration changes:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.app.vapi_api:build_app --factory --host 127.0.0.1 --port 8002
```

Keep the existing ngrok tunnel pointed at port 8002. `/health` should report
`vapi-actions`. The saved assistant is already updated; no JSON upload is needed.

`python -m scripts.configure_vapi_actions` registers/reuses saved tools and updates
the assistant using the configured private API key. It makes network requests and
currently requires exactly one assistant/business mapping. Generating JSON alone
with `python -m backend.app.vapi_config` remains offline.

## Verification

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_vapi_tools.py tests/test_vapi_actions.py tests/test_scheduling.py -q
```

These tests use isolated databases and a fake calendar. They cover tenant and
appointment verification, checked slots, booking/cancellation/rescheduling and
messages, affirmative versus conditional consent, interruptions, wrong speech,
settings changes, call endings, token replay, calendar outages, uncertain-write
recovery and concurrent booking collisions. They do not write real appointments.

For a live check, first prepare a staff message and confirm it only after Ava
finishes reading its details. Then test an interruption or correction before
agreement and check that no old action is committed. If the backend returns
`confirmation_not_verified`, inspect speech/turn/transcript events before testing
real appointment changes. Completed live bookings/messages create real records.
