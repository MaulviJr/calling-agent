# Vapi action tools

This extends the initial read-only milestone with seven tools. The saved Vapi
assistant now has nine tools, including business and staff information.

| Tool | Backend behavior |
| --- | --- |
| check_availability | Read active service slots against business hours, booking rules, database appointments and Google Calendar |
| get_appointment | Require appointment reference and original booking phone; return only minimal appointment facts |
| create_appointment | Prepare a checked booking and return an action token and short confirmation prompt |
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

Prepare tools do not perform mutations. Python saves the proposed action in
minimal per-call state and returns an action token plus a short confirmation
prompt. Ava asks naturally whether to proceed; a later final caller transcript
with clear affirmation authorizes confirm_action. No full read-back, exact text
comparison, speech turn matching or speech completion event is required.

Only a final user transcript newer than the prepared action can confirm it.
Old, partial and assistant transcripts are ignored. A newer correction,
conditional response or other non-affirmative response revokes prior consent.
Changed action details require a fresh preparation and new affirmation. Tokens
are scoped to the call/business, expire after ten minutes or a settings change,
and completed tokens return the stored result without another write.

The assistant subscribes only to status updates and final transcripts, reducing
webhook traffic. Legacy speech and interruption events are ignored. Accepted
short English affirmations include yes, yes please, I confirm, go ahead and yep;
conditional or ambiguous responses do not approve an action. This checks the
caller response but relies on Vapi to connect that response to the intended
pending action; the backend does not verify what Ava said before it.

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
messages, affirmative versus conditional consent, ignored speech events, stale transcripts,
settings changes, call endings, token replay, calendar outages, uncertain-write
recovery and concurrent booking collisions. They do not write real appointments.

For a live check, request a booking or message, provide the required details,
and answer yes when Ava briefly asks whether to proceed. The result should be
completed without reading back all details. Also try a conditional response or
change a booking detail; Ava must prepare changed details and obtain fresh
agreement. Completed live bookings/messages create real records.
