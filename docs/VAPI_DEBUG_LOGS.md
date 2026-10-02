# Booking and availability diagnostics

Tracing is enabled in the private .env. Restart the Vapi backend to load it.
Structured JSON lines are written to logs/vapi-debug.jsonl and the terminal.
Files rotate at 5 MB with three backups. Set VAPI_TRACE_ENABLED=false to disable.
No authentication headers, credential files, raw caller transcripts, caller names,
phones, emails or message bodies are logged by this tracer. Public business/staff
facts remain visible. Treat the file as internal diagnostics.

Watch the file while making a call:

```powershell
Get-Content .\logs\vapi-debug.jsonl -Tail 30 -Wait
```

Find one call without the rest of the traffic:

```powershell
Get-Content .\logs\vapi-debug.jsonl | ForEach-Object { $_ | ConvertFrom-Json } |
    Where-Object call_id -eq 'YOUR_VAPI_CALL_ID' | ConvertTo-Json -Depth 20
```

| Stage | What to inspect |
| --- | --- |
| tool.request | Vapi tool arguments, requested date/time/service, tool_call_id |
| action.state | Current draft token, active call status, saved affirmation |
| availability.rules | Actual current time, timezone, hours, service duration, booking notice/window/buffer |
| google.request / google.response | API resource, method, time window, HTTP status and latency; no credential values |
| availability.busy_intervals | Calendar/database intervals preventing availability |
| availability.candidate_rejected | Why a generated slot failed booking rules |
| availability.result | Exact slots supplied to Vapi; availability is not a reservation |
| slot.conflict / slot.free | Final calendar/database collision checks |
| event.received / event.processed | Event timestamp/type and whether the event affected call state |
| confirmation.evidence | Whether final caller affirmation was accepted |
| confirmation.request / confirmation.rejected / confirmation.authorized | Submitted token, exact rejection reason or authorized action |
| action.exception | Exception class and invalid field/type names without Pydantic input values |
| calendar.operation_intent | Durable operation created before attempting the calendar write |
| calendar.operation_completed / rejected / uncertain | Final calendar operation outcome |
| action.completed | Backend completion and resulting appointment/message ID |
| tool.response | Structured result returned to Vapi, including error code and latency |

Use the Vapi call transcript alongside these records. If Ava says a slot is free
but there is no corresponding availability tool call, or that time is absent from
availability.result/tool.response, her claim is unsupported by the backend.
If Vapi sent the wrong date, inspect current_date/timezone in the business tool
response and compare them to tool.request. If prepare returns confirmation_required,
the booking has not been created. Success requires confirm_action returning completed.

Trace ordering inside a tool is correlated by call_id and tool_call_id. Events
have call_id but do not correspond to a particular tool request. Internal call IDs
and calendar operation IDs are separate identifiers; do not confuse them.

Tracing records actual execution, but does not guarantee the model speaks only
returned facts. It cannot recover past unlogged event payloads or identify a spoken
hallucination without the Vapi transcript. It does not add transcripts to the dashboard.
